#!/usr/bin/env node
/**
 * 睡觉听历史 · 氛围循环渲染器（纯本地，0 积分）。
 *
 * 与 hf_render.js 的区别：这里不冻结帧，而是把整段 LOOP 秒的「周期动画」
 * 逐帧截图，得到一段可无缝循环的氛围视频；再由 gen_sleep_history.py 用
 * ffmpeg -stream_loop -1 把它铺满整条音频时长。
 *
 * HTML 必须暴露 window.__update(t)（t 为秒，动画以 LOOP 秒为周期），
 * 绝不在页面里用 setInterval / Date.now 计时（headless Chrome 会节流）。
 *
 * 用法：node sleep_render.js <template.html> <out.mp4> <ffmpeg>
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const puppeteer = require('/Users/lingmf/.workbuddy/binaries/node/workspace/node_modules/puppeteer-core');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FPS = 30;
const LOOP = 12; // 必须与模板里的 LOOP 一致
const FRAMES = Math.round(LOOP * FPS);

function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { cwd, stdio: 'pipe' });
  if (r.status !== 0) {
    const err = (r.stderr || Buffer.from('')).toString();
    throw new Error(`命令失败 ${cmd} ${args.join(' ')}: ${err.slice(-800)}`);
  }
  return r;
}

async function main() {
  const html = process.argv[2];
  const out = process.argv[3];
  const ffmpeg = process.argv[4];
  if (!html || !out || !ffmpeg) {
    console.error('usage: sleep_render.js <template.html> <out.mp4> <ffmpeg>');
    process.exit(1);
  }

  const dir = path.dirname(out);
  fs.mkdirSync(dir, { recursive: true });
  const frameDir = path.join(dir, '.frames_' + path.basename(out, '.mp4'));
  fs.mkdirSync(frameDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--mute-audio'],
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(html), { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 320)); // 等字体/背景图稳定

  for (let i = 0; i < FRAMES; i++) {
    const t = i / FPS;
    await page.evaluate(tt => window.__update(tt), t);
    await new Promise(r => setTimeout(r, 8));
    const buf = await page.screenshot({ type: 'jpeg', quality: 88 });
    fs.writeFileSync(path.join(frameDir, `f_${String(i).padStart(4, '0')}.jpg`), buf);
  }
  await browser.close();

  const list = path.join(frameDir, 'list.txt');
  const lines = [];
  for (let i = 0; i < FRAMES; i++) {
    lines.push(`file '${path.join(frameDir, `f_${String(i).padStart(4, '0')}.jpg`)}'`);
  }
  fs.writeFileSync(list, lines.join('\n'));

  run(ffmpeg, [
    '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-framerate', String(FPS),
    '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
    '-r', '30',
    '-t', LOOP.toFixed(3),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
    '-an', out,
  ]);

  console.log('rendered loop: ' + out + ' (' + LOOP + 's seamless loop)');
}

main().catch(e => { console.error(e); process.exit(1); });
