const { chromium } = require('playwright');

(async () => {
  const results = [];
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 860 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()); });

  await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok');

  // 1) XSS：脚本当文本渲染，不执行
  await page.fill('#input', '<img src=x onerror="window.__xss=1"> 你好');
  await page.click('#btn-send');
  await page.waitForTimeout(2600);
  const xss = await page.evaluate(() => window.__xss || 0);
  const userBubble = await page.locator('.msg.user .bubble').last().innerText();
  results.push(['XSS 不执行', xss === 0]);
  results.push(['HTML 按原文渲染', userBubble.includes('<img')]);

  // 2) 空输入禁用发送
  const disabled = await page.locator('#btn-send').isDisabled();
  results.push(['空输入禁用发送', disabled]);

  // 3) 双击只入一条
  const before = await page.locator('.msg.user').count();
  await page.fill('#input', '测试双击发送');
  await page.click('#btn-send');
  await page.click('#btn-send', { force: true }).catch(() => {});
  await page.waitForTimeout(2600);
  const after = await page.locator('.msg.user').count();
  results.push(['重复点击只发一条', after - before === 1]);

  // 4) 1500 字长文本
  await page.fill('#input', '啊'.repeat(1500));
  await page.click('#btn-send');
  await page.waitForTimeout(3000);
  const longLen = (await page.locator('.msg.user .bubble').last().innerText()).length;
  results.push(['1500 字可发送', longLen >= 1500]);

  // 5) 红线卡片可点击（tel: 链接）
  await page.fill('#input', '我真的不想活了');
  await page.click('#btn-send');
  await page.waitForTimeout(3200);
  const hotlineCards = await page.locator('.res-card.hotline').count();
  const firstHref = await page.locator('.res-card.hotline a').first().getAttribute('href');
  results.push(['红线出现 2 张热线卡', hotlineCards === 2, String(hotlineCards)]);
  results.push(['热线卡为 tel: 链接', (firstHref || '').startsWith('tel:')]);

  // 6) 超过 10MB 图片被拒
  await page.click('.mode-tab[data-mode="image"]');
  const big = Buffer.alloc(11 * 1024 * 1024, 1);
  await page.setInputFiles('#file-input', { name: 'big.png', mimeType: 'image/png', buffer: big });
  await page.waitForTimeout(900);
  const tip = await page.locator('.panel-tip').innerText();
  results.push(['超大图片被拒', tip.includes('10MB')]);

  // 7) 新对话清空
  await page.click('#btn-new');
  await page.waitForTimeout(500);
  results.push(['新对话清空', (await page.locator('.msg').count()) === 0]);

  // 8) 刷新后历史恢复（等回复真正完成，兼容 mock 与真实模型）
  await page.click('.mode-tab[data-mode="text"]');
  await page.fill('#input', '刷新恢复测试');
  await page.click('#btn-send');
  await page.waitForFunction(() => {
    const el = document.querySelector('.msg.bot .bubble');
    return el && el.textContent.length > 40 && !el.classList.contains('streaming');
  }, null, { timeout: 60000 });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  results.push(['刷新后历史恢复', (await page.locator('.msg').count()) >= 2]);

  results.push(['无 JS 报错', errs.length === 0, errs.join(' | ')]);
  console.log(JSON.stringify(results, null, 0));
  await browser.close();
})();
