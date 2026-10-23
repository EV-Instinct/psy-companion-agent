/** 验证：朗读只走服务端 /api/tts（不再有浏览器/系统音色分支），且页面无语法/运行错误。 */

const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8702';
const OUT = [];
const rec = (n, ok, d = '') => { OUT.push({ n, ok: !!ok, d }); console.log(`${ok ? '[PASS]' : '[FAIL]'} ${n}${d ? ' — ' + d : ''}`); };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 900, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  let ttsReq = null;
  let ttsStatus = null;

  page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()); });
  page.on('request', (r) => { if (r.url().includes('/api/tts')) ttsReq = r.url(); });
  page.on('response', (r) => { if (r.url().includes('/api/tts')) ttsStatus = r.status(); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'networkidle' });
  rec('页面加载无 JS 报错', errs.length === 0, errs.slice(0, 2).join(' | '));

  await page.click('#btn-intro-ok').catch(() => {});

  // 设置弹层：确认删掉“朗读音源”后仍能正常打开与保存
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  const engineGone = (await page.locator('#cfg-tts-engine').count()) === 0;
  rec('设置弹层已无“朗读音源”选项', engineGone);
  await page.fill('#cfg-key', 'sk-fake-ui-check');
  await page.click('#btn-cfg-save');
  await page.waitForTimeout(500);
  rec('设置保存无报错', (await page.locator('#settings-modal').isHidden()) && errs.length === 0, errs.slice(0, 2).join(' | '));
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  await page.click('#btn-cfg-clear');
  await page.waitForTimeout(300);

  // 发消息，等朗读按钮
  await page.fill('#input', '这次考试我有点紧张');
  await page.click('#btn-send');
  await page.waitForSelector('.msg.bot .speak-btn:not([hidden])', { timeout: 90000 });
  rec('回复后出现朗读按钮', true);

  // 点朗读：必须直接打 /api/tts
  const btn = page.locator('.msg.bot .speak-btn').last();
  await btn.click();
  await page.waitForTimeout(1500);
  rec('朗读只走服务端 /api/tts', !!ttsReq, `请求=${ttsReq ? 'yes' : 'no'} 状态=${ttsStatus}`);
  rec('点击后按钮进入生成中', /生成中|朗读中/.test(await btn.innerText()), await btn.innerText());

  await page.waitForTimeout(3000);
  rec('前端未调用浏览器语音合成', await page.evaluate(() => !('speechSynthesis' in window) || !window.speechSynthesis.speaking), '');

  const fails = OUT.filter((r) => !r.ok);
  console.log(`\n===== 汇总: ${OUT.length - fails.length}/${OUT.length} 通过 =====`);
  fails.forEach((f) => console.log('  FAIL ' + f.n + ' — ' + f.d));
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
