#!/usr/bin/env node
/**
 * HyperFrames 批量渲染器（纯本地，0 积分）。
 *
 * 输入 manifest.json：[{ html, out, dur }, ...]
 * 单浏览器循环：每镜只截「入场动画」帧（0.8s @ 30fps = 24 帧），
 * 之后用 ffmpeg 的 tpad 把最后一帧（已定格的终态）冻结补齐到 dur，
 * 既保证入场顺滑，又避免对静止画面逐帧截图浪费时间。
 *
 * 输出：无声 1080x1920 30fps 的 mp4，交给 compose 混音/拼片头。
 *
 * 注意：HTML 必须暴露 window.__update(t)（t 为秒），且 window.__DUR__ 与
 * manifest 里的 dur 一致。headless Chrome 会节流 setInterval，所以动画靠
 * 外部每帧主动喂时间，绝不在页面里用 rAF/Date.now 计时。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const puppeteer = require('/Users/lingmf/.workbuddy/binaries/node/workspace/node_modules/puppeteer-core');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ENTRANCE = 0.8;   // 入场动画时长（秒）
const FPS = 30;
const FRAMES = Math.round(ENTRANCE * FPS); // 24

function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { cwd, stdio: 'pipe' });
  if (r.status !== 0) {
    const err = (r.stderr || Buffer.from('')).toString();
    throw new Error(`命令失败 ${cmd} ${args.join(' ')}: ${err.slice(-800)}`);
  }
  return r;
}

async function renderScene(browser, item, ffmpeg) {
  const dir = path.dirname(item.out);
  fs.mkdirSync(dir, { recursive: true });
  // 临时帧目录
  const frameDir = path.join(dir, '.frames_' + path.basename(item.out, '.mp4'));
  fs.mkdirSync(frameDir, { recursive: true });

  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(item.html), { waitUntil: 'load' });
  // 等字体/布局/本地图片稳定（大图需要更久）
  await new Promise(r => setTimeout(r, 280));

  for (let i = 0; i < FRAMES; i++) {
    const t = i / FPS;
    await page.evaluate((tt) => window.__update(tt), t);
    await new Promise(r => setTimeout(r, 8));
    const buf = await page.screenshot({ type: 'jpeg', quality: 90 });
    fs.writeFileSync(path.join(frameDir, `f_${String(i).padStart(3, '0')}.jpg`), buf);
  }
  await page.close();

  // ffmpeg：24 帧(0.8s) + tpad 冻结最后一帧补齐到 dur
  const pad = Math.max(0, item.dur - ENTRANCE);
  const list = path.join(frameDir, 'list.txt');
  const lines = [];
  for (let i = 0; i < FRAMES; i++) lines.push(`file '${path.join(frameDir, `f_${String(i).padStart(3, '0')}.jpg`)}'`);
  fs.writeFileSync(list, lines.join('\n'));
  const vf = pad > 0.01
    ? `tpad=stop_mode=clone:stop_duration=${pad.toFixed(3)}`
    : `null`;
  const args = [
    '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-framerate', String(FPS),
    '-vf', `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,${vf}`,
    '-t', item.dur.toFixed(3),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
    '-an', item.out,
  ];
  run(ffmpeg, args);

  // 保留帧目录，避免单场景 25 个文件批量删除触发安全确认；后续可手工清理。
  // try { fs.rmSync(frameDir, { recursive: true, force: true }); } catch (e) {}
}

async function main() {
  const manifestPath = process.argv[2];
  if (!manifestPath) { console.error('usage: hf_render.js <manifest.json>'); process.exit(1); }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  const ffmpeg = manifest.ffmpeg || 'ffmpeg';
  const items = manifest.items || [];

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--mute-audio'],
    defaultViewport: { width: 1080, height: 1920, deviceScaleFactor: 1 },
  });

  let ok = 0, fail = 0;
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    try {
      await renderScene(browser, it, ffmpeg);
      ok++;
      console.log(`[${i + 1}/${items.length}] ok  ${it.out}  (${it.dur.toFixed(2)}s)`);
    } catch (e) {
      fail++;
      console.error(`[${i + 1}/${items.length}] FAIL ${it.out}: ${e.message}`);
    }
  }
  await browser.close();
  console.log(`DONE ok=${ok} fail=${fail}`);
  process.exit(fail > 0 ? 2 : 0);
}

main().catch(e => { console.error(e); process.exit(1); });
