const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 860 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));
  page.on('console', (msg) => { if (msg.type() === 'error') console.log('CONSOLE ERROR:', msg.text()); });

  await page.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
  await page.click('#btn-intro-ok');
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'shots/01-mobile-welcome.png' });

  await page.fill('#input', '这次数学考试没考好，我妈肯定要说我，我好怕她失望');
  await page.click('#btn-send');
  await page.waitForTimeout(4500);
  await page.screenshot({ path: 'shots/02-mobile-chat.png' });

  await page.click('.mode-tab[data-mode="voice"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'shots/03-mobile-voice.png' });

  await page.click('.mode-tab[data-mode="image"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'shots/04-mobile-image.png' });

  await page.click('.mode-tab[data-mode="text"]');
  await page.fill('#input', '我真的不想活了');
  await page.click('#btn-send');
  await page.waitForTimeout(3500);
  await page.screenshot({ path: 'shots/05-mobile-crisis.png' });

  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
  const p2 = await ctx2.newPage();
  await p2.goto('http://127.0.0.1:8701/', { waitUntil: 'networkidle' });
  await p2.click('#btn-intro-ok');
  await p2.fill('#input', '一想到要上初中就害怕，怕自己跟不上');
  await p2.click('#btn-send');
  await p2.waitForTimeout(4500);
  await p2.screenshot({ path: 'shots/06-desktop-chat.png' });

  await browser.close();
  console.log('shots done');
})();
