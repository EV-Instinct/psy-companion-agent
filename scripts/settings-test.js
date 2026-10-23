const { chromium } = require('playwright');

const GLM_KEY = '80ebaefc8fe84f47ad8534c6c9ceb7a9.VPFzL2V8U3MgEZuj';

(async () => {
  const results = [];
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 880 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()); });

  await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok');

  // 1) 小按钮存在且尺寸小
  const box = await page.locator('#btn-settings').boundingBox();
  results.push(['配置按钮存在且够小', box && box.width <= 40 && box.height <= 40, `${box && box.width}x${box && box.height}`]);

  // 2) 打开配置弹层
  await page.click('#btn-settings');
  await page.waitForTimeout(300);
  results.push(['配置弹层可打开', await page.locator('#settings-modal').isVisible()]);
  await page.screenshot({ path: 'shots/26-settings-modal.png' });

  // 3) 错误 Key -> 测试连接报错
  await page.fill('#cfg-key', 'invalid-key-000');
  await page.click('#btn-cfg-test');
  await page.waitForFunction(() => !document.getElementById('cfg-status').hidden, { timeout: 30000 });
  await page.waitForTimeout(300);
  const badStatus = await page.locator('#cfg-status').innerText();
  results.push(['错误 Key 测试连接报错', badStatus.includes('失败'), badStatus.slice(0, 40)]);

  // 4) 正确 Key + 智谱预设 -> 测试连接成功
  await page.selectOption('#cfg-platform', 'zhipu');
  await page.fill('#cfg-key', GLM_KEY);
  await page.click('#btn-cfg-test');
  await page.waitForFunction(() => {
    const el = document.getElementById('cfg-status');
    return el && !el.hidden && (el.textContent.includes('成功') || el.textContent.includes('失败'));
  }, null, { timeout: 60000 });
  const goodStatus = await page.locator('#cfg-status').innerText();
  results.push(['正确 Key 测试连接成功', goodStatus.includes('成功'), goodStatus.slice(0, 50)]);

  // 5) 保存 -> 顶栏显示本机 Key
  await page.click('#btn-cfg-save');
  await page.waitForTimeout(400);
  const chip = await page.locator('#mode-chip').innerText();
  results.push(['保存后顶栏显示本机 Key', chip.includes('本机 Key'), chip]);
  results.push(['配置按钮高亮', await page.locator('#btn-settings').evaluate((el) => el.classList.contains('is-on'))]);

  // 6) 用本机 Key 发消息 -> 真实回复
  await page.fill('#input', '用本机 Key 测试一下');
  await page.click('#btn-send');
  await page.waitForFunction(() => {
    const el = document.querySelector('.msg.bot .bubble');
    return el && el.textContent.length > 30 && !el.classList.contains('streaming');
  }, null, { timeout: 60000 });
  const reply = await page.locator('.msg.bot .bubble').last().innerText();
  results.push(['本机 Key 对话成功', reply.length > 30, reply.slice(0, 40)]);

  // 7) 刷新后配置仍在
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const chip2 = await page.locator('#mode-chip').innerText();
  results.push(['刷新后配置保留', chip2.includes('本机 Key'), chip2]);

  // 8) 清除配置 -> 回到服务端默认
  await page.click('#btn-settings');
  await page.click('#btn-cfg-clear');
  await page.waitForTimeout(400);
  const chip3 = await page.locator('#mode-chip').innerText();
  results.push(['清除后恢复服务端默认', !chip3.includes('本机 Key'), chip3]);

  results.push(['无 JS 报错', errs.length === 0, errs.join(' | ')]);
  console.log(JSON.stringify(results));
  await browser.close();
})();
