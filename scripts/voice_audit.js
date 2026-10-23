/** 语音链路：注入假 SpeechRecognition，验证错误码是否被 onend 覆盖。 */

const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8702';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 900 } });

  await page.addInitScript(() => {
    // 假识别器：start 后先发 onerror('not-allowed')，再按规范发 onend()
    class FakeSR {
      constructor() {
        this.lang = '';
        this.interimResults = false;
        this.continuous = false;
        this.maxAlternatives = 1;
        this.onstart = null; this.onresult = null; this.onerror = null; this.onend = null;
      }
      start() {
        setTimeout(() => {
          if (this.onstart) this.onstart();
          setTimeout(() => {
            if (this.onerror) this.onerror({ error: 'not-allowed' });
            setTimeout(() => { if (this.onend) this.onend(); }, 60);
          }, 120);
        }, 30);
      }
      stop() { if (this.onend) this.onend(); }
      abort() { if (this.onend) this.onend(); }
    }
    window.SpeechRecognition = FakeSR;
    window.webkitSpeechRecognition = FakeSR;
  });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok').catch(() => {});
  await page.click('.mode-tab[data-mode="voice"]');
  await page.waitForTimeout(300);

  const supported = await page.locator('#voice-fallback').isHidden();
  console.log('语音控件可用:', supported);

  await page.dispatchEvent('#btn-voice', 'pointerdown', { pointerId: 1, pointerType: 'mouse' });
  await page.waitForTimeout(500);
  const hintAfterError = (await page.locator('#voice-hint').innerText()).trim();
  console.log('错误发生时提示:', JSON.stringify(hintAfterError));

  await page.dispatchEvent('#btn-voice', 'pointerup', { pointerId: 1, pointerType: 'mouse' });
  await page.waitForTimeout(500);
  const hintFinal = (await page.locator('#voice-hint').innerText()).trim();
  console.log('onend 之后提示:', JSON.stringify(hintFinal));

  const specific = hintFinal.includes('权限') || hintFinal.includes('麦克风') || hintFinal.includes('浏览器不允许');
  console.log(specific ? '[PASS] 具体错误码保留' : '[FAIL] 具体错误被 onend 覆盖为通用文案');

  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
