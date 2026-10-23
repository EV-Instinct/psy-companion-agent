/** 手动测试用：开一个真实 Edge 窗口指向本地服务，授权麦克风，把窗口留在桌面等你测。 */

const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8702';
const KEEP_MS = Number(process.env.KEEP_MS || 20 * 60 * 1000);

(async () => {
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: false,
    args: ['--start-maximized', '--disable-features=Translate'],
  });
  const ctx = await browser.newContext({
    permissions: ['microphone'],
    viewport: null,
    locale: 'zh-CN',
  });
  const page = await ctx.newPage();

  // 把控制台错误打到终端，方便现场看
  page.on('pageerror', (e) => console.log('[页面错误]', e.message));
  page.on('console', (m) => { if (m.type() === 'error') console.log('[控制台]', m.text()); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok').catch(() => {});

  const srSupported = await page.evaluate(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    return { hasApi: !!SR, ua: navigator.userAgent.includes('Edg') ? 'Edge' : 'Other' };
  });
  console.log('浏览器:', srSupported.ua, '| SpeechRecognition 接口:', srSupported.hasApi ? '有' : '无');
  console.log('麦克风权限:', await page.evaluate(() => navigator.permissions.query({ name: 'microphone' }).then((p) => p.state).catch(() => 'unknown')));
  console.log(`窗口已打开：${BASE}/  保持 ${Math.round(KEEP_MS / 60000)} 分钟，测完直接关窗口即可。`);

  // 保持窗口存活，直到用户手动关闭
  const start = Date.now();
  while (Date.now() - start < KEEP_MS) {
    await page.waitForTimeout(3000);
    if (page.isClosed()) break;
  }
  await browser.close().catch(() => {});
})().catch((e) => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
