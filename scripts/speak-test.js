const { chromium } = require('playwright');

(async () => {
  const results = [];
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const ctx = await browser.newContext({ viewport: { width: 420, height: 880 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()); });

    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    if (await page.locator('#btn-intro-ok').isVisible().catch(() => false)) {
      await page.click('#btn-intro-ok');
    }

    await page.fill('#input', '明天要考试了我好紧张');
    await page.click('#btn-send');
    await page.waitForFunction(() => {
      const el = document.querySelector('.msg.bot .bubble');
      return el && el.textContent.length > 40 && !el.classList.contains('streaming');
    }, null, { timeout: 90000 });
    results.push(['回复完成后显示朗读按钮', await page.locator('.speak-btn').last().isVisible()]);
    await page.screenshot({ path: 'shots/27-speak-button.png' });

    const lastSpeak = () => page.locator('.speak-btn').last();
    const waitRestored = (timeout) => page.waitForFunction(() => {
      const btn = document.querySelectorAll('.speak-btn');
      const last = btn[btn.length - 1];
      return last && !last.disabled && last.textContent.includes('朗读');
    }, null, { timeout }).then(() => true).catch(() => false);

    // 1) 默认浏览器引擎：即时朗读，按钮快速恢复
    const t1 = Date.now();
    await lastSpeak().click();
    results.push(['朗读走服务端并恢复', await waitRestored(150000), `${((Date.now() - t1) / 1000).toFixed(1)}s`]);

    // 2) 显式选 AI 音色：能播放，或失败后自动降级本机朗读，按钮最终恢复
    await page.click('#btn-settings');
    await page.fill('#cfg-key', 'sk-xxpnolzertyibpjxelvlfvyywfcxiesadnijxgnutxbdlslj');
    await page.click('#btn-cfg-save');
    await page.waitForSelector('#settings-modal', { state: 'hidden' });
    await page.waitForTimeout(400);
    const t2 = Date.now();
    await lastSpeak().click();
    const aiOk = await waitRestored(150000);
    const tip = await lastSpeak().getAttribute('title');
    results.push(['AI 音色朗读可用或自动降级', aiOk, `${((Date.now() - t2) / 1000).toFixed(1)}s ${tip ? '| ' + tip.slice(0, 30) : ''}`]);

    // 3) 自动朗读开关可保存
    await page.click('#btn-settings');
    await page.check('#cfg-autoread');
    await page.click('#btn-cfg-save');
    await page.waitForTimeout(300);
    const autoSaved = await page.evaluate(() => JSON.parse(localStorage.getItem('shudong.llm') || '{}').auto_read === true);
    results.push(['自动朗读可保存', autoSaved]);

    results.push(['无 JS 报错', errs.length === 0, errs.join('|').slice(0, 80)]);
    console.log(JSON.stringify(results));
  } finally {
    if (browser) await browser.close();
  }
})();
