// 把每个分段的 HTML 截成一张 1080x1920 的静态画面（用于 ffmpeg Ken Burns）
// 用法： node scripts/still_render.js items.json
// items.json: [{"html": "/abs/sec_01.html", "out": "/abs/sec_01.jpg"}, ...]
const fs = require('fs');
const path = require('path');
const puppeteer = require('/Users/lingmf/.workbuddy/binaries/node/workspace/node_modules/puppeteer-core');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

(async () => {
  const items = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  if (!items.length) { console.log('no items'); return; }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
           '--allow-file-access-from-files', '--disable-web-security'],
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
  });

  for (const it of items) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
    await page.goto('file://' + path.resolve(it.html), { waitUntil: 'load', timeout: 30000 });
    // 等背景图解码完成
    await page.evaluate(() => {
      const bg = getComputedStyle(document.getElementById('img')).backgroundImage;
      const m = bg && bg.match(/url\(["']?(.+?)["']?\)/);
      if (!m) return Promise.resolve();
      return new Promise(res => {
        const im = new Image();
        im.onload = im.onerror = () => res();
        im.src = m[1];
      });
    }).catch(() => {});
    await new Promise(r => setTimeout(r, 450));
    await page.screenshot({ path: it.out, type: 'jpeg', quality: 92 });
    await page.close();
    console.log('still', path.basename(it.out));
  }

  await browser.close();
})().catch(e => { console.error('still render failed:', e.message); process.exit(1); });
