const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const out = [];

  // 1) 375 窄屏
  {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    await page.click('#btn-intro-ok');
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'shots/12-narrow-welcome.png' });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    out.push(['375 无横向溢出', !overflow]);
    await page.fill('#input', '快毕业了，一想到要和同学分开就很难受');
    await page.click('#btn-send');
    await page.waitForTimeout(3500);
    await page.screenshot({ path: 'shots/13-narrow-chat.png' });
    await ctx.close();
  }

  // 2) 黄线提示条
  {
    const ctx = await browser.newContext({ viewport: { width: 420, height: 860 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    await page.click('#btn-intro-ok');
    await page.fill('#input', '我最近天天睡不着，一想到考试就想哭');
    await page.click('#btn-send');
    // 真实模型下分级可能要几秒，等提示条出现而不是固定等待
    await page.waitForFunction(() => {
      const el = document.getElementById('risk-strip');
      return el && !el.hidden;
    }, null, { timeout: 30000 }).catch(() => {});
    const strip = await page.locator('#risk-strip').isVisible();
    const text = await page.locator('#risk-strip').innerText();
    out.push(['黄线提示条', strip && text.includes('12356')]);
    await page.screenshot({ path: 'shots/14-yellow-strip.png' });

    // 3) 新对话清空
    await page.click('#btn-new');
    await page.waitForTimeout(500);
    const msgs = await page.locator('.msg').count();
    const welcomeVisible = await page.locator('#welcome').isVisible();
    out.push(['新对话清空', msgs === 0 && welcomeVisible]);
    await page.screenshot({ path: 'shots/15-new-session.png' });
    await ctx.close();
  }

  // 4) 桌面 1440 + 使用约定弹层
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    await page.screenshot({ path: 'shots/16-desktop-modal.png' });
    await page.click('#btn-intro-ok');
    await page.click('#btn-intro');
    const modalVisible = await page.locator('#intro-modal').isVisible();
    out.push(['约定弹层可重开', modalVisible]);
    await page.click('#btn-intro-ok');
    await page.waitForTimeout(200);
    await page.screenshot({ path: 'shots/17-desktop-welcome.png' });
    await ctx.close();
  }

  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
