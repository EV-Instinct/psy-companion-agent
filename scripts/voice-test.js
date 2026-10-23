const { chromium } = require('playwright');

const FAKE_STREAM = `({
  getTracks: () => [{ stop() {} }],
})`;

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];

  // A. 不支持录音的浏览器 -> 优雅降级（不再依赖浏览器识别引擎）
  {
    const ctx = await browser.newContext({ viewport: { width: 420, height: 860 } });
    await ctx.addInitScript(() => {
      Object.defineProperty(navigator, 'mediaDevices', { get: () => undefined, configurable: true });
    });
    const page = await ctx.newPage();
    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    await page.click('#btn-intro-ok');
    await page.click('.mode-tab[data-mode="voice"]');
    await page.waitForTimeout(300);
    const fallbackVisible = await page.locator('#voice-fallback').isVisible();
    const btnDisabled = await page.locator('#btn-voice').isDisabled();
    results.push(['不支持录音时降级提示', fallbackVisible && btnDisabled]);
    await page.screenshot({ path: 'shots/09-voice-fallback.png' });
    await ctx.close();
  }

  // B. 假麦克风 + 假录音器 + 拦截识别接口，跑完整语音流程
  {
    const ctx = await browser.newContext({ viewport: { width: 420, height: 860 }, deviceScaleFactor: 2 });
    await ctx.addInitScript(() => {
      const stream = { getTracks: () => [{ stop() {} }] };
      Object.defineProperty(navigator, 'mediaDevices', {
        get: () => ({ getUserMedia: async () => stream }),
        configurable: true,
      });
      class FakeRecorder {
        constructor(_stream, options) {
          this.mimeType = (options && options.mimeType) || 'audio/webm';
          this.ondataavailable = null;
          this.onstop = null;
          this.state = 'inactive';
        }
        static isTypeSupported(type) { return String(type).indexOf('audio/webm') === 0; }
        start() { this.state = 'recording'; }
        stop() {
          this.state = 'inactive';
          const blob = new Blob([new Uint8Array([26, 69, 223, 163, 1, 2, 3, 4])], { type: this.mimeType });
          if (this.ondataavailable) this.ondataavailable({ data: blob });
          if (this.onstop) this.onstop();
        }
      }
      window.MediaRecorder = FakeRecorder;
    });

    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.route('**/api/asr', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ text: '我最近一想到升学就紧张，晚上也睡不好' }),
    }));

    await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
    await page.click('#btn-intro-ok');
    await page.click('.mode-tab[data-mode="voice"]');
    await page.locator('#btn-voice').dispatchEvent('pointerdown', { pointerId: 1 });
    await page.waitForTimeout(400);
    const hintRecording = await page.locator('#voice-hint').innerText();
    results.push(['按住进入录音态', /录音|正在听/.test(hintRecording), hintRecording]);
    await page.locator('#btn-voice').dispatchEvent('pointerup', { pointerId: 1 });
    await page.waitForTimeout(800);

    const transcript = await page.locator('#voice-transcript').innerText();
    const actionsVisible = await page.locator('#voice-actions').isVisible();
    results.push(['服务端识别结果显示', transcript.includes('升学')]);
    results.push(['转写可编辑+发送按钮', actionsVisible]);
    await page.screenshot({ path: 'shots/10-voice-transcript.png' });

    await page.click('#btn-voice-send');
    await page.waitForTimeout(3000);
    const voiceTag = await page.locator('.msg-tag').last().innerText();
    const lastUserText = await page.locator('.msg.user .bubble').last().innerText();
    results.push(['语音消息发出', voiceTag.includes('语音') && lastUserText.includes('升学')]);
    await page.screenshot({ path: 'shots/11-voice-sent.png' });
    results.push(['无 JS 报错', errors.length === 0, errors.join('|').slice(0, 60)]);
    await ctx.close();
  }

  console.log(JSON.stringify(results, null, 1));
  await browser.close();
})();
