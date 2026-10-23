#!/usr/bin/env python3
"""给「睡觉听历史」成片配套免费图片（0 积分）。

思路：不重新配音、不重新渲染氛围循环，只在已有产物上做一版「配图版」：
    篇章分段 -> 每段按关键词拉一张免费图（Wikimedia CC / Picsum）
    -> 用模板渲染每段的静态画面（标题/系列名压在上面）
    -> ffmpeg 缓慢推近/拉远（Ken Burns）-> 拼接 -> 与已有 MP3 合流

用法：
    <PY> scripts/add_images.py --series series/ming-emperors --ep EP.01
    <PY> scripts/add_images.py --series series/ming-emperors --ep EP.01 --sections 10 --zoom 0.06
    <PY> scripts/add_images.py --series series/ming-emperors --ep EP.01 --limit-sections 2   # 试跑前 2 段

脚本里的配图来源（按优先级）：
    "images": [{"query": "Forbidden City", "paras": [0, 6]}, ...]   # 精确分段
    "image_queries": ["Ming dynasty painting", ...]                  # 平均分配到各段
    "image": "/abs/pic.jpg"                                          # 单图铺满（等同原生成器）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import compose, config  # noqa: E402
from fetch_images import fetch_image  # noqa: E402

TEMPLATE = os.path.join(ROOT, "templates", "sleep_history", "index.html")
STILL_JS = os.path.join(ROOT, "scripts", "still_render.js")
FPS = 24


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def count_chars(data: dict) -> int:
    n = 0
    for p in data.get("paragraphs", []):
        if isinstance(p, str):
            n += len(p)
        elif isinstance(p, dict):
            n += len(p.get("text") or p.get("title") or "")
    return n


def para_text(p) -> str:
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        return p.get("text") or p.get("title") or ""
    return ""


def resolve_project(series_dir: str, ep_id: str) -> tuple[dict, str, dict]:
    manifest = read_json(os.path.join(series_dir, "manifest.json"))
    if not manifest:
        sys.exit(f"找不到 manifest：{series_dir}")
    state = read_json(os.path.join(series_dir, ".state.json"), {}) or {}
    st = state.get(ep_id)
    if not st or st.get("status") != "done":
        sys.exit(f"{ep_id} 还没有完成生成（state={st and st.get('status')}）")
    video = st.get("video") or ""
    audio = st.get("audio") or ""
    if not (video and os.path.isfile(video)):
        sys.exit(f"{ep_id} 成片不存在：{video}")
    if not (audio and os.path.isfile(audio)):
        sys.exit(f"{ep_id} 音频不存在：{audio}")

    ep_file = next((e["file"] for e in manifest.get("episodes", []) if e.get("id") == ep_id), None)
    if not ep_file:
        sys.exit(f"manifest 里没有 {ep_id}")
    ep_data = read_json(os.path.join(series_dir, ep_file))
    if not ep_data:
        sys.exit(f"读不到脚本：{ep_file}")
    return ep_data, video, {"audio": audio, "manifest": manifest}


def build_sections(ep_data: dict, n_sections: int) -> list[dict]:
    paras = [para_text(p) for p in ep_data.get("paragraphs", []) if para_text(p).strip()]
    if not paras:
        sys.exit("脚本没有段落")

    exact = ep_data.get("images")
    if isinstance(exact, list) and exact:
        out = []
        for it in exact:
            if not isinstance(it, dict):
                continue
            a, b = (it.get("paras") or [0, len(paras)])[:2]
            a = max(0, min(int(a), len(paras) - 1))
            b = max(a + 1, min(int(b), len(paras)))
            text = "".join(paras[a:b])
            out.append({"query": it.get("query") or "", "image": it.get("image") or "",
                        "chars": len(text), "from": a, "to": b})
        if out:
            return out

    queries = ep_data.get("image_queries") or []
    single = (ep_data.get("image") or "").strip()
    if not queries and single:
        queries = [""]

    k = max(1, min(n_sections, len(paras)))
    if not queries:
        # 没有任何配图线索：用副标题兜底
        queries = [(ep_data.get("subject") or ep_data.get("series") or "history")] * k
    if len(queries) < k:
        queries = [queries[i % len(queries)] for i in range(k)]
    queries = queries[:k]

    # 按段落数平均切，余数往前放
    base, rem = divmod(len(paras), k)
    out, idx = [], 0
    for i in range(k):
        take = base + (1 if i < rem else 0)
        a, b = idx, idx + take
        idx = b
        out.append({"query": queries[i], "image": single if i == 0 else "",
                    "chars": len("".join(paras[a:b])), "from": a, "to": b})
    return out


def build_html(series: str, title: str, subject: str, image: str, out_html: str) -> None:
    html = open(TEMPLATE, encoding="utf-8").read()
    html = (html.replace("{{SERIES}}", series or "")
                .replace("{{TITLE}}", title or "")
                .replace("{{SUBJECT}}", subject or "")
                .replace("{{BG}}", (image or "").replace("'", "")))
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)


def render_stills(items: list[dict]) -> None:
    """items: [{html, out}]，用 puppeteer 逐个截 1080x1920。"""
    if not items:
        return
    tmp = tempfile.mktemp(suffix=".json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    node = shutil.which("node") or "/Users/lingmf/.workbuddy/binaries/node/versions/22.12.0/bin/node"
    r = subprocess.run([node, STILL_JS, tmp], capture_output=True, text=True)
    try:
        os.remove(tmp)
    except OSError:
        pass
    if r.returncode != 0:
        sys.exit(f"静态画面渲染失败：{(r.stderr or r.stdout)[-800:]}")
    print((r.stdout or "").strip())


def kenburns_filter(n_frames: int, variant: int, zoom: float) -> str:
    z = max(0.02, min(zoom, 0.30))
    pre = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if variant == 0:      # 缓慢推近，中心
        expr = f"z='min(1+{z}*on/{n_frames},1+{z})'"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif variant == 1:    # 缓慢拉远，中心
        expr = f"z='max(1+{z}-{z}*on/{n_frames},1.0)'"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif variant == 2:    # 横向漂移 + 轻微推近
        expr = f"z='min(1+{z}*0.6+{z}*0.4*on/{n_frames},1+{z})'"
        x, y = f"(iw-iw/zoom)*on/{n_frames}", "ih/2-(ih/zoom/2)"
    else:                 # 反向横向漂移
        expr = f"z='min(1+{z}*0.6+{z}*0.4*on/{n_frames},1+{z})'"
        x, y = f"(iw-iw/zoom)*(1-on/{n_frames})", "ih/2-(ih/zoom/2)"
    return (f"{pre},zoompan={expr}:x='{x}':y='{y}':"
            f"d={n_frames}:s=1080x1920:fps={FPS}")


def render_clip(still: str, dur: float, out: str, variant: int, zoom: float) -> None:
    n = max(2, int(round(dur * FPS)))
    vf = kenburns_filter(n, variant, zoom)
    args = [
        compose.ffmpeg(), "-y", "-loop", "1", "-i", still,
        "-vf", vf, "-frames:v", str(n), "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an", out,
    ]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"片段渲染失败 {os.path.basename(out)}：{(r.stderr or '')[-600:]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="给睡觉听历史成片配套免费图片（0 积分）")
    ap.add_argument("--series", required=True, help="系列目录，如 series/ming-emperors")
    ap.add_argument("--ep", required=True, help="集号，如 EP.01")
    ap.add_argument("--sections", type=int, default=12, help="配图段数（默认 12）")
    ap.add_argument("--zoom", type=float, default=0.06, help="Ken Burns 缩放幅度（默认 0.06）")
    ap.add_argument("--limit-sections", type=int, default=0, help="只做前 N 段，试跑用")
    ap.add_argument("--out", help="输出路径（默认 <title>_配图.mp4）")
    args = ap.parse_args()

    series_dir = args.series if os.path.isabs(args.series) else os.path.join(ROOT, args.series)
    ep_data, video, meta = resolve_project(series_dir, args.ep)
    audio = meta["audio"]
    work = os.path.dirname(video)
    assets = os.path.join(work, "assets", "img")
    stills_dir = os.path.join(work, "assets", "still")
    clips_dir = os.path.join(work, "assets", "clips")
    for d in (assets, stills_dir, clips_dir):
        os.makedirs(d, exist_ok=True)

    total_dur = compose.probe_duration(audio)
    if not total_dur:
        sys.exit("探测不到音频时长")
    sections = build_sections(ep_data, args.sections)
    total_chars = sum(s["chars"] for s in sections) or 1
    if args.limit_sections:
        sections = sections[: args.limit_sections]
        total_dur = total_dur * sum(s["chars"] for s in sections) / total_chars
        total_chars = sum(s["chars"] for s in sections) or 1

    print(f"{args.ep}：{len(sections)} 段，音频 {total_dur/60:.1f} 分钟，开始拉免费图……")

    title = ep_data.get("display_title") or ep_data.get("title") or args.ep
    subject = ep_data.get("subject") or ""
    series = ep_data.get("series") or "睡觉听历史"

    still_items = []
    durations = []
    for i, s in enumerate(sections, 1):
        dur = total_dur * s["chars"] / total_chars
        durations.append(dur)
        img = s.get("image") or ""
        if not img:
            img = fetch_image(s.get("query") or "", assets, f"sec_{i:02d}") or ""
        if not img:
            print(f"  [段 {i}] 没取到图，跳过（保留氛围背景）")
        html = os.path.join(stills_dir, f"sec_{i:02d}.html")
        build_html(series, title, subject, img, html)
        still_items.append({"html": html, "out": os.path.join(stills_dir, f"sec_{i:02d}.jpg")})
        print(f"  [段 {i}/{len(sections)}] {dur/60:.1f} 分钟 · {s.get('query') or os.path.basename(img) or '默认背景'}")

    render_stills(still_items)

    print("渲染 Ken Burns 片段……")
    clip_files = []
    for i, (still, dur) in enumerate(zip([it["out"] for it in still_items], durations), 1):
        out = os.path.join(clips_dir, f"sec_{i:02d}.mp4")
        render_clip(still, dur, out, variant=(i - 1) % 4, zoom=args.zoom)
        clip_files.append(out)
        print(f"  [片段 {i}/{len(clip_files)}] {dur/60:.1f} 分钟")

    listf = os.path.join(clips_dir, "list.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for c in clip_files:
            f.write(f"file '{os.path.abspath(c)}'\n")

    body = os.path.join(clips_dir, "_body.mp4")
    r = subprocess.run([compose.ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                        "-i", listf, "-c", "copy", body], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"拼接失败：{(r.stderr or '')[-600:]}")

    base = os.path.splitext(os.path.basename(video))[0]
    out_mp4 = args.out or os.path.join(work, f"{base}_配图.mp4")
    r = subprocess.run([
        compose.ffmpeg(), "-y", "-i", body, "-i", audio,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "96k", "-ar", "24000", "-ac", "1",
        "-shortest", out_mp4,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"合流失败：{(r.stderr or '')[-600:]}")

    cover = os.path.join(work, "cover_配图.jpg")
    subprocess.run([compose.ffmpeg(), "-y", "-i", out_mp4, "-ss", "1",
                    "-frames:v", "1", cover], capture_output=True, text=True)

    size = os.path.getsize(out_mp4) / 1024 / 1024
    print(json.dumps({"ok": True, "video": out_mp4, "cover": cover,
                      "sections": len(clip_files), "size_mb": round(size, 1),
                      "duration_min": round(compose.probe_duration(out_mp4) / 60, 1)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
