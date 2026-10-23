const { chromium } = require('playwright');

(async () => {
  const results = [];
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 860 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGE: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

  await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok');

  // 1) 文字发送 + 等待完成
  await page.fill('#input', '考试前总是睡不着，脑子停不下来');
  await page.click('#btn-send');
  // 等回复真正完成（兼容 mock 与真实模型），否则刷新时历史还没落库
  await page.waitForFunction(() => {
    const el = document.querySelector('.msg.bot .bubble');
    return el && el.textContent.length > 40 && !el.classList.contains('streaming');
  }, null, { timeout: 60000 });
  const botCount = await page.locator('.msg.bot').count();
  results.push(['文字发送', botCount >= 1]);

  // 2) 刷新后历史恢复
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const restored = await page.locator('.msg').count();
  results.push(['历史恢复', restored >= 2]);

  // 3) 图片上传 -> 预览 -> 发送
  await page.click('.mode-tab[data-mode="image"]');
  await page.setInputFiles('#file-input', 'shots/test-paper.png');
  await page.waitForTimeout(600);
  const previewVisible = await page.locator('#image-preview').isVisible();
  results.push(['图片预览', previewVisible]);
  await page.screenshot({ path: 'shots/07-image-preview.png' });

  await page.fill('#image-caption', '这张卷子我做错了好多');
  await page.click('#btn-image-send');
  await page.waitForTimeout(3500);
  const imageBubbles = await page.locator('.msg-image').count();
  results.push(['图片消息', imageBubbles >= 1]);
  await page.screenshot({ path: 'shots/08-image-sent.png' });

  // 4) 语音面板提示
  await page.click('.mode-tab[data-mode="voice"]');
  await page.waitForTimeout(200);
  const voiceVisible = await page.locator('#panel-voice').isVisible();
  results.push(['语音面板', voiceVisible]);

  // 5) 快捷入口
  await page.click('.mode-tab[data-mode="text"]');
  const chips = await page.locator('.chip').count();
  results.push(['情绪快捷入口', chips >= 5]);

  console.log(JSON.stringify({ results, errors }, null, 2));
  await browser.close();
})();
