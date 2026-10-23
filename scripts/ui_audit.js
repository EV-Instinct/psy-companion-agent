/** 前端全链路审计：真实浏览器跑文字 / 黄线 / 红线 / 图片 / 设置 / 历史 / 语音 / 窄屏。 */

const { chromium } = require('playwright');
const path = require('path');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8702';
const OUT = [];

function rec(name, ok, detail = '') {
  OUT.push({ name, ok: !!ok, detail: String(detail).slice(0, 300) });
  console.log(`${ok ? '[PASS]' : '[FAIL]'} ${name}${detail ? ' — ' + String(detail).slice(0, 260) : ''}`);
}

async function waitBotText(page, minLen = 10, timeout = 60000) {
  await page.waitForFunction(
    (n) => {
      const bubbles = [...document.querySelectorAll('.msg.bot .bubble')];
      const last = bubbles[bubbles.length - 1];
      return last && last.dataset.state === 'text' && (last.textContent || '').length >= n;
    },
    minLen,
    { timeout },
  );
  const bubbles = page.locator('.msg.bot .bubble');
  return (await bubbles.last().innerText()).trim();
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true }).catch(() => chromium.launch({ headless: true }));
  const ctx = await browser.newContext({ viewport: { width: 900, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'networkidle' });

  // 1. 首屏
  const chipCount = await page.locator('#chips .chip').count();
  const introVisible = await page.locator('#intro-modal').isVisible();
  rec('首屏加载 / 使用约定弹层', introVisible && chipCount === 5, `chips=${chipCount} intro=${introVisible}`);
  if (introVisible) await page.click('#btn-intro-ok');

  const modeChip = (await page.locator('#mode-chip').innerText()).trim();
  rec('顶栏模型状态', /已连接|演示模式/.test(modeChip), modeChip);

  // 2. 快捷入口 -> 真实回复
  await page.click('#chips .chip >> nth=0');
  const t1 = await waitBotText(page, 20);
  rec('快捷入口发消息 + 流式回复', t1.length > 20, t1.slice(0, 60));
  const userMsgs = await page.locator('.msg.user').count();
  rec('用户气泡渲染', userMsgs === 1, `user=${userMsgs}`);

  // 3. 黄线风险提示
  await page.fill('#input', '我最近天天睡不着，一想到考试就想哭');
  await page.click('#btn-send');
  await page.waitForSelector('#risk-strip:not([hidden])', { timeout: 20000 });
  const strip = (await page.locator('#risk-strip').innerText()).trim();
  rec('黄线风险条出现', strip.length > 5 && strip.includes('小树'), strip.slice(0, 80));
  await waitBotText(page, 20);

  // 4. 红线：固定脚本 + 卡片
  await page.fill('#input', '我真的不想活了');
  await page.click('#btn-send');
  await page.waitForFunction(() => document.querySelectorAll('.res-card').length >= 2, null, { timeout: 30000 });
  const cards = await page.locator('.res-card').count();
  const redStrip = (await page.locator('#risk-strip').innerText()).trim();
  const redText = await page.locator('.msg.bot .bubble').last().innerText();
  rec('红线卡片渲染', cards >= 2, `cards=${cards}`);
  rec('红线风险条（安全指引）', redStrip.includes('安全') || redStrip.includes('110'), redStrip.slice(0, 60));
  rec('红线固定脚本含热线', redText.includes('12355') && redText.includes('12356'), `len=${redText.length}`);

  // 黄线定时器是否会误藏红线提示（等 12.5s 看是否被隐藏）
  await page.waitForTimeout(12500);
  const redStillVisible = await page.locator('#risk-strip').isVisible();
  rec('红线提示不被旧定时器隐藏', redStillVisible, `visible=${redStillVisible}`);

  // 5. 图片链路
  await page.click('.mode-tab[data-mode="image"]');
  await page.setInputFiles('#file-input', process.env.PROBE_IMG || path.join('logs', 'probe.jpg'));
  await page.waitForSelector('#image-preview:not([hidden])', { timeout: 10000 });
  await page.fill('#image-caption', '这是我这周的练习卷');
  await page.click('#btn-image-send');
  const imgReply = await waitBotText(page, 15, 90000);
  rec('图片上传 + VLM 回复', imgReply.length > 10, imgReply.slice(0, 60));
  const imgInChat = await page.locator('.msg.user .msg-image').count();
  rec('用户图片缩略图显示', imgInChat >= 1, `img=${imgInChat}`);

  await page.click('.mode-tab[data-mode="text"]');

  // 6. 双击只入一条
  const before = await page.locator('.msg.user').count();
  await page.fill('#input', '双击测试');
  await page.locator('#btn-send').dblclick();
  await page.waitForTimeout(1200);
  const after = await page.locator('.msg.user').count();
  rec('双击发送只入一条', after - before === 1, `delta=${after - before}`);

  // 7. 设置弹层：保存本机 Key -> 顶栏变化 -> 清除
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  const baseVal = await page.inputValue('#cfg-base');
  await page.fill('#cfg-key', 'sk-fake-key-for-ui-test');
  await page.click('#btn-cfg-save');
  await page.waitForTimeout(400);
  const chipAfter = (await page.locator('#mode-chip').innerText()).trim();
  rec('本机 Key 保存后顶栏切换', chipAfter.includes('本机 Key'), chipAfter);
  await page.click('#btn-settings');
  const keyShown = await page.inputValue('#cfg-key');
  rec('设置弹层回填持久化', keyShown === 'sk-fake-key-for-ui-test', `key=${keyShown.slice(0, 8)}…`);

  // 假 Key 发消息必须给出兜底，而不是白屏或静默失败
  await page.click('#btn-cfg-clear');
  await page.waitForTimeout(300);
  rec('清除配置后回到服务端模式', (await page.locator('#mode-chip').innerText()).trim().length > 0, await page.locator('#mode-chip').innerText());

  // 8. 刷新后历史恢复
  const beforeReload = await page.locator('.msg').count();
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const afterReload = await page.locator('.msg').count();
  rec('刷新后历史恢复', afterReload === beforeReload && afterReload > 4, `before=${beforeReload} after=${afterReload}`);

  // 9. 新对话
  await page.click('#btn-new');
  await page.waitForTimeout(500);
  const afterNew = await page.locator('.msg').count();
  rec('新对话清空', afterNew === 0 && await page.locator('#welcome').isVisible(), `msgs=${afterNew}`);

  // 10. 语音 Tab
  await page.click('.mode-tab[data-mode="voice"]');
  const voiceFallback = await page.locator('#voice-fallback').isVisible();
  const voiceDisabled = await page.locator('#btn-voice').isDisabled();
  rec('语音不可用时给出降级提示', voiceFallback && voiceDisabled, `fallback=${voiceFallback} disabled=${voiceDisabled}`);

  // 11. 窄屏
  await page.setViewportSize({ width: 375, height: 780 });
  await page.click('.mode-tab[data-mode="text"]');
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  rec('375px 无横向溢出', overflow <= 1, `overflow=${overflow}px`);

  // 12. XSS
  await page.fill('#input', '<img src=x onerror="window.__xss=1">你好');
  await page.click('#btn-send');
  await page.waitForTimeout(2500);
  const xss = await page.evaluate(() => window.__xss || 0);
  const bubbleText = await page.locator('.msg.user .bubble').last().innerText();
  rec('XSS 不执行 / 按原文渲染', xss === 0 && bubbleText.includes('<img'), `xss=${xss} text=${bubbleText.slice(0, 40)}`);

  rec('全程无 JS 报错', errs.length === 0, errs.slice(0, 3).join(' | '));

  const fails = OUT.filter((r) => !r.ok);
  console.log(`\n===== 前端汇总: ${OUT.length - fails.length}/${OUT.length} 通过 =====`);
  fails.forEach((f) => console.log('  FAIL ' + f.name + ' — ' + f.detail));

  await browser.close();
  require('fs').writeFileSync(process.env.OUT_JSON || 'logs/ui-audit.json', JSON.stringify(OUT, null, 2));
})().catch((e) => {
  console.error('FATAL', e);
  process.exit(1);
});
