/** TTS 链路前端审计：朗读按钮 / 音源选项是否生效 / 自动朗读开关可达性 / 切换平台是否清配置。 */

const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8702';
const OUT = [];
function rec(name, ok, detail = '') {
  OUT.push({ name, ok: !!ok, detail: String(detail).slice(0, 300) });
  console.log(`${ok ? '[PASS]' : '[FAIL]'} ${name}${detail ? ' — ' + String(detail).slice(0, 240) : ''}`);
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 900, height: 900 } });
  const page = await ctx.newPage();
  const ttsCalls = [];
  page.on('request', (r) => { if (r.url().includes('/api/tts')) ttsCalls.push({ url: r.url(), method: r.method() }); });
  page.on('response', async (r) => {
    if (r.url().includes('/api/tts')) {
      const i = ttsCalls.findIndex((c) => c.url === r.url() && !c.status);
      if (i >= 0) ttsCalls[i].status = r.status();
    }
  });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok').catch(() => {});

  // 1. 发一条消息，等朗读按钮出现
  await page.fill('#input', '这次考试我有点紧张');
  await page.click('#btn-send');
  await page.waitForSelector('.msg.bot .speak-btn:not([hidden])', { timeout: 90000 });
  rec('回复后出现朗读按钮', true, await page.locator('.msg.bot .speak-btn').last().innerText());

  // 2. 不填 Key 直接开自动朗读 —— 能否保存
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  await page.check('#cfg-autoread').catch(() => {});
  await page.click('#btn-cfg-save');
  await page.waitForTimeout(400);
  const statusText = (await page.locator('#cfg-status').innerText().catch(() => '')).trim();
  const modalStillOpen = await page.locator('#settings-modal').isVisible();
  rec('服务端模式可直接开启自动朗读', !modalStillOpen, `弹层开着=${modalStillOpen} 提示=${statusText}`);

  // 3. 填 Key 保存后检查落盘内容（保存成功后弹层会关闭，需重新打开）
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  await page.fill('#cfg-key', 'sk-fake-key-ui-test');
  await page.click('#btn-cfg-save');
  await page.waitForTimeout(400);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('shudong.llm') || '{}'));
  rec('TTS 配置落盘', Boolean(saved.tts_model) && saved.auto_read === true,
    `auto_read=${saved.auto_read} tts_model=${saved.tts_model} tts_voice=${saved.tts_voice}`);

  // 4. 切换平台是否清空 TTS 字段 / 取消自动朗读
  await page.click('#btn-settings');
  await page.waitForSelector('#settings-modal:not([hidden])');
  const beforeTts = await page.inputValue('#cfg-tts-model');
  const beforeAuto = await page.isChecked('#cfg-autoread');
  await page.selectOption('#cfg-platform', 'zhipu');
  const afterTts = await page.inputValue('#cfg-tts-model');
  const afterAuto = await page.isChecked('#cfg-autoread');
  rec('切换平台保留 TTS 配置', afterAuto === beforeAuto && afterTts === beforeTts,
    `auto ${beforeAuto}->${afterAuto} tts_model '${beforeTts}'->'${afterTts}'`);
  await page.click('#btn-cfg-clear'); // 回到服务端模式
  await page.waitForTimeout(300);

  // 5. 点朗读按钮：是否发请求、是否成功
  const btn = page.locator('.msg.bot .speak-btn').last();
  await btn.click();
  await page.waitForTimeout(1200);
  const during = (await btn.innerText()).trim();
  rec('点击朗读后进入加载态', /朗读中|生成中/.test(during), during);

  // 等按钮恢复可用（生成中 -> 朗读 / 朗读失败），不再依赖固定文案
  await page.waitForFunction(() => {
    const list = document.querySelectorAll('.msg.bot .speak-btn');
    const b = list[list.length - 1];
    return b && !b.disabled;
  }, null, { timeout: 120000 }).catch(() => {});
  const finalText = (await btn.innerText()).trim();
  const ttsStatus = ttsCalls.length ? ttsCalls[ttsCalls.length - 1].status : 'none';
  rec('朗读请求成功返回音频', ttsStatus === 200 && !/失败/.test(finalText), `status=${ttsStatus} btn=${finalText}`);

  // 6. 用户选的是“浏览器即时朗读”，是否仍然打了服务端
  rec('朗读只走服务端 /api/tts（无浏览器音色分支）', ttsCalls.length >= 1,
    `实际 /api/tts 调用 ${ttsCalls.length} 次（status=${ttsStatus}）`);

  const fails = OUT.filter((r) => !r.ok);
  console.log(`\n===== TTS 汇总: ${OUT.length - fails.length}/${OUT.length} 通过 =====`);
  fails.forEach((f) => console.log('  FAIL ' + f.name + ' — ' + f.detail));
  require('fs').writeFileSync('logs/tts-audit.json', JSON.stringify(OUT, null, 2));
  await browser.close();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
