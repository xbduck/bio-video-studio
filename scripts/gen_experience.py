#!/usr/bin/env python3
"""100 种人生体验 / 体验清单类视频生成器（HyperFrames 0 积分路线）。

与「生平短片」的区别：
  - 静止图文卡片，不需要 ImageGen / VideoGen（全链路 0 积分，只有 CPU 渲染时间）
  - 每条体验配 edge-tts 画外音（免费）朗读，节奏由配音时长驱动
  - 视觉纯 CSS 渐变 + 排版，由 templates/experience/index.html 渲染

用法：
  python scripts/gen_experience.py                      # 用内置 sample_100.json 全量
  python scripts/gen_experience.py my_list.json        # 自定义清单
  python scripts/gen_experience.py --limit 5           # 试跑前 5 条
  python scripts/gen_experience.py --bgm ~/music.mp3 --voice zh-CN-XiaoxiaoNeural

script.json 结构：
  {"title":"100种人生体验","voice":"...","bgm":"/abs/bgm.mp3","bgm_volume":0.18,
   "experiences":[{"category":"自然","text":"在山顶看一次日出"}, "只是文案也行", ...]}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import store, compose, tts, config  # noqa: E402

NODE = "/Users/lingmf/.workbuddy/binaries/node/versions/22.12.0/bin/node"
RENDER_JS = os.path.join(ROOT, "scripts", "hf_render.js")
TEMPLATE = os.path.join(ROOT, "templates", "experience", "index.html")
SAMPLE = os.path.join(ROOT, "templates", "experience", "sample_100.json")

_PY = "/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python"


def _js_escape(s: str) -> str:
    """转义进 JS 双引号字符串的字符。"""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _load_experiences(path: str | None, title_hint: str | None, voice_hint: str | None,
                      bgm_hint: str | None) -> tuple[list[dict], str, str, str | None, float]:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = {"experiences": data}
    elif path:
        raise FileNotFoundError(f"清单文件不存在: {path}")
    else:
        with open(SAMPLE, "r", encoding="utf-8") as f:
            data = json.load(f)

    raw = data.get("experiences", [])
    items: list[dict] = []
    for e in raw:
        if isinstance(e, str):
            items.append({"category": "", "text": e.strip()})
        elif isinstance(e, dict):
            items.append({"category": (e.get("category") or "").strip(),
                          "text": (e.get("text") or e.get("title") or "").strip()})
        else:
            continue
    items = [i for i in items if i["text"]]

    title = (title_hint or data.get("title") or "100种人生体验").strip()
    voice = (voice_hint or data.get("voice") or config.DEFAULT_VOICE).strip()
    bgm = (bgm_hint or data.get("bgm") or "").strip()
    bgm_vol = float(data.get("bgm_volume") or 0.18)
    return items, title, voice, (bgm or None), bgm_vol


def _build_html(idx: int, total: int, category: str, text: str, dur: float) -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()
    html = (html
            .replace("{{IDX}}", str(idx))
            .replace("{{TOTAL}}", str(total))
            .replace("{{CATEGORY}}", _js_escape(category))
            .replace("{{TEXT}}", _js_escape(text))
            .replace("{{DUR}}", f"{dur:.3f}"))
    return html


def main():
    ap = argparse.ArgumentParser(description="100 种人生体验视频生成器（HyperFrames 0 积分）")
    ap.add_argument("script", nargs="?", default=None, help="清单 json（默认用内置 sample_100.json）")
    ap.add_argument("--title", help="视频标题 / 项目名")
    ap.add_argument("--voice", help="edge-tts 音色，如 zh-CN-XiaoxiaoNeural")
    ap.add_argument("--bgm", help="背景音乐绝对路径")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（试跑）")
    ap.add_argument("--person", help="项目目录名（默认同标题）")
    ap.add_argument("--no-title", action="store_true", help="不要片头卡")
    ap.add_argument("--no-bgm", action="store_true", help="不要背景音乐")
    args = ap.parse_args()

    items, title, voice, bgm, bgm_vol = _load_experiences(
        args.script, args.title, args.voice, args.bgm)
    if args.limit > 0:
        items = items[: args.limit]
    if not items:
        print(json.dumps({"error": "没有任何体验文案"}, ensure_ascii=False))
        sys.exit(1)

    total = len(items)
    person = (args.person or title).strip()
    proj = store.create_project(person, title)
    pid = proj["id"]
    pdir = store.project_dir(pid)
    audio_dir = os.path.join(pdir, "audio")
    video_dir = os.path.join(pdir, "videos")
    hf_dir = os.path.join(pdir, "hf")
    clips_dir = os.path.join(pdir, "clips")
    output_dir = os.path.join(pdir, "output")
    for d in (audio_dir, video_dir, hf_dir, clips_dir, output_dir):
        os.makedirs(d, exist_ok=True)

    # 写 scenes（兼容结构，但文本走 card，不烧字幕）
    scenes = []
    for i, it in enumerate(items, 1):
        scenes.append({
            "index": i, "category": it["category"], "text": it["text"],
            "narration": "", "image_path": "", "video_path": "", "audio_path": "",
            "image_status": "done", "video_status": "pending",
        })
    proj["scenes"] = scenes
    proj["title"] = title
    proj["voice"] = voice
    store.save_project(proj)

    print(f"项目 {pid}（{person}）共 {total} 条，开始配音 + 渲染……")

    # ---- 1. 逐条：配音 + 写 HF 模板 ----
    manifest_items = []
    for i, it in enumerate(items, 1):
        apath = os.path.join(audio_dir, f"{i:02d}.mp3")
        dur = 3.5
        if not os.path.exists(apath):
            try:
                d = tts.synthesize(it["text"], apath, voice, "+0%", "+0%")
                if d and d > 0:
                    dur = d
            except Exception as e:
                print(f"  [配音失败 {i}] {it['text'][:12]}… 用静音兜底: {e}")
                apath = None
        clip_dur = round(dur + 0.6, 3)

        html = _build_html(i, total, it["category"], it["text"], clip_dur)
        hdir = os.path.join(hf_dir, f"{i:02d}")
        os.makedirs(hdir, exist_ok=True)
        with open(os.path.join(hdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        scenes[i - 1]["audio_path"] = os.path.relpath(apath, pdir).replace("\\", "/") if apath else ""
        vpath = os.path.join(video_dir, f"{i:02d}.mp4")
        scenes[i - 1]["video_path"] = os.path.relpath(vpath, pdir).replace("\\", "/")
        manifest_items.append({
            "html": os.path.join(hdir, "index.html"),
            "out": vpath,
            "dur": clip_dur,
        })
        print(f"  [准备 {i}/{total}] {it['text'][:16]}  ({clip_dur:.2f}s)")

    store.save_project(proj)

    # ---- 2. 批量 puppeteer 渲染（单浏览器） ----
    manifest = {"ffmpeg": compose.ffmpeg(), "items": manifest_items}
    mpath = os.path.join(pdir, ".hf_manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    print("渲染视频（HyperFrames，0 积分）……")
    r = subprocess.run([NODE, RENDER_JS, mpath], capture_output=True, text=True)
    if r.returncode not in (0, 2):
        print("渲染器报错：\n" + (r.stderr or r.stdout)[-2000:])
        sys.exit(1)
    print(r.stdout[-1500:])

    # ---- 3. 混音：每镜 HF 静帧 + 配音 -> clips/NN.mp4 ----
    print("逐镜混音 + 拼接……")
    clip_paths = []
    for i, it in enumerate(items, 1):
        vpath = os.path.join(video_dir, f"{i:02d}.mp4")
        apath = os.path.join(audio_dir, f"{i:02d}.mp3")
        if not os.path.exists(apath):
            apath = ""
        ass = os.path.join(pdir, "subs", f"{i:02d}.ass")  # 不创建 -> 不烧字幕
        clip = os.path.join(clips_dir, f"{i:02d}.mp4")
        ok, err = compose.build_scene_clip(vpath, apath or None, manifest_items[i - 1]["dur"], ass, clip)
        if not ok:
            print(f"  [混音失败 {i}] {err}")
            sys.exit(1)
        clip_paths.append(clip)

    # ---- 4. 片头 ----
    final_clips = []
    if not args.no_title:
        title_clip = os.path.join(clips_dir, "00_title.mp4")
        ok, err = compose.build_title_clip(title, "100 种人生体验", 2.6, title_clip, bg_image=None)
        if ok:
            final_clips.append(title_clip)

    final_clips += clip_paths
    body = os.path.join(clips_dir, "_body.mp4")
    ok, err = compose.concat_clips(final_clips, body)
    if not ok:
        print("拼接失败:", err)
        sys.exit(1)

    # ---- 5. BGM + 出片 + 封面 ----
    safe = re.sub(r'[\\/:*?"<>|\r\n\t ]+', '_', title)[:50] or "体验清单"
    out_name = f"{safe}.mp4"
    out_path = os.path.join(output_dir, out_name)
    if not args.no_bgm and bgm and os.path.exists(bgm):
        ok, err = compose.add_bgm(body, bgm, bgm_vol, out_path)
        if not ok:
            print("BGM 混入失败，退回无 BGM:", err)
            import shutil
            shutil.copy(body, out_path)
    else:
        import shutil
        shutil.copy(body, out_path)

    cover = os.path.join(output_dir, "cover.jpg")
    compose.extract_cover(out_path, cover, at=0.8)

    proj["output_path"] = out_path
    proj["output_url"] = "/" + store.rel(out_path)
    proj["cover_url"] = "/" + store.rel(cover) if os.path.exists(cover) else ""
    store.save_project(proj)

    print(json.dumps({
        "ok": True, "project_id": pid, "title": title, "total": total,
        "output": out_path, "url": "/" + store.rel(out_path),
        "cover": "/" + store.rel(cover) if os.path.exists(cover) else "",
        "duration": round(compose.probe_duration(out_path), 2),
        "size_mb": round(os.path.getsize(out_path) / 1024 / 1024, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
