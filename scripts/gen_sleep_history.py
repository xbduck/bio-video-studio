#!/usr/bin/env python3
"""睡觉听历史 · 长音频历史科普生成器（音频优先，0 积分主路线）。

定位：视频号的「睡前听历史」专栏。主交付是一条 20–30 分钟平缓旁白，
用户可「看视频」也可「锁屏听音」；视频只是发布壳，音频才是核心。

输入一个 episode json：
  {
    "series": "睡觉听历史",
    "episode": "EP.01",
    "title": "唐朝：从贞观之治到安史之乱",
    "subject": "一场盛世的升起与落幕",
    "voice": "zh-CN-YunjianNeural",
    "rate": "-10%",
    "bgm": "/abs/calm.mp3", "bgm_volume": 0.10,
    "image": "/abs/tang.jpg 或 空",
    "paragraphs": [ "公元六百一十八年……", {"heading":"贞观","text":"……"}, … ]
  }

输出（projects/<标题>/output/）：
  - <标题>.mp3   纯旁白音频（睡前听音主交付，锁屏可听）
  - <标题>.mp4   暗色舒缓氛围视频壳（视频号发布，锁屏继续播音频）
  - cover.jpg    封面

流程：
  1) 旁白按段落/句子分块，逐块 edge-tts 合成（避开长文本截断与单请求超时）
  2) 分块音频统一转 wav 后拼接，再编码为单条 mp3（计算总时长）
  3) 用 templates/sleep_history 渲染一段 12s 无缝循环氛围视频
  4) ffmpeg -stream_loop -1 把循环铺满音频时长 → 混音 →（可选）加 BGM → 封面

用法：
  python scripts/gen_sleep_history.py                         # 内置示例（唐朝简史）
  python scripts/gen_sleep_history.py my.json                # 自定义
  python scripts/gen_sleep_history.py my.json --limit-paras 3 # 只跑前 3 段试看
  python scripts/gen_sleep_history.py my.json --bgm ~/calm.mp3 --voice zh-CN-YunjianNeural --rate -10%
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import store, compose, tts, config  # noqa: E402

NODE = "/Users/lingmf/.workbuddy/binaries/node/versions/22.12.0/bin/node"
RENDER_JS = os.path.join(ROOT, "scripts", "sleep_render.js")
TEMPLATE = os.path.join(ROOT, "templates", "sleep_history", "index.html")
SAMPLE = os.path.join(ROOT, "templates", "sleep_history", "sample_tang.json")

# 单次 edge-tts 合成的文本上限（中文），超过则按句子再切，避免截断
_MAX_CHUNK = 220


def _load(path, title_h, voice_h, rate_h, bgm_h):
    if path and os.path.exists(path):
        data = json.load(open(path, encoding="utf-8"))
    elif path:
        raise FileNotFoundError(f"脚本文件不存在: {path}")
    else:
        data = json.load(open(SAMPLE, encoding="utf-8"))

    paras = data.get("paragraphs", [])
    items: list[dict] = []
    for p in paras:
        if isinstance(p, str):
            items.append({"heading": "", "text": p.strip()})
        elif isinstance(p, dict):
            items.append({"heading": (p.get("heading") or "").strip(),
                          "text": (p.get("text") or p.get("title") or "").strip()})
        else:
            continue
    items = [i for i in items if i["text"]]

    title = (title_h or data.get("title") or "睡觉听历史").strip()
    voice = (voice_h or data.get("voice") or config.DEFAULT_VOICE).strip()
    rate = (rate_h or data.get("rate") or "-10%").strip()
    bgm = (bgm_h or data.get("bgm") or "").strip() or None
    bgm_vol = float(data.get("bgm_volume") or 0.10)
    series = (data.get("series") or "睡觉听历史").strip()
    subject = (data.get("subject") or data.get("subtitle") or "").strip()
    image = (data.get("image") or "").strip() or None
    episode = (data.get("episode") or "").strip()
    return items, title, voice, rate, bgm, bgm_vol, series, subject, image, episode


def _split_chunks(text: str, max_chars: int = _MAX_CHUNK) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    buf = ""
    for seg in re.split(r"(?<=[。！？；!?;])", text):
        seg = seg.strip()
        if not seg:
            continue
        if len(buf) + len(seg) <= max_chars:
            buf = (buf + seg) if buf else seg
        else:
            if buf:
                pieces.append(buf)
                buf = ""
            if len(seg) <= max_chars:
                buf = seg
            else:
                while len(seg) > max_chars:
                    cut = max_chars
                    for sp in ("，", "、", ",", " "):
                        idx = seg.rfind(sp, 0, max_chars)
                        if idx > max_chars * 0.5:
                            cut = idx + 1
                            break
                    pieces.append(seg[:cut])
                    seg = seg[cut:]
                buf = seg
    if buf:
        pieces.append(buf)
    return pieces or [text]


def _synth_one(ch: str, mp3: str, voice: str, rate: str, max_retry: int = 3) -> bool:
    """合成单块旁白，带重试与 0 字节校验。

    edge-tts 偶发冷启动会返回空响应（0 字节文件），这里重试规避。
    """
    import time
    for attempt in range(1, max_retry + 1):
        try:
            tts.synthesize(ch, mp3, voice, rate, "+0%")
        except Exception as e:  # noqa: BLE001
            print(f"    [重试 {attempt}/{max_retry}] 合成异常: {e}")
            if attempt < max_retry:
                time.sleep(2)
                continue
            return False
        if os.path.exists(mp3) and os.path.getsize(mp3) > 1024:
            return True
        print(f"    [重试 {attempt}/{max_retry}] 输出为空，重合成")
        if attempt < max_retry:
            time.sleep(2)
            continue
        return False
    return False


def _synth(items, audio_dir, voice, rate, limit_paras):
    if limit_paras and limit_paras > 0:
        items = items[:limit_paras]
    chunks = []
    for it in items:
        chunks.extend(_split_chunks(it["text"]))

    wavs: list[str] = []
    total_dur = 0.0
    for i, ch in enumerate(chunks, 1):
        mp3 = os.path.join(audio_dir, f"c_{i:03d}.mp3")
        wav = os.path.join(audio_dir, f"c_{i:03d}.wav")
        ok = bool(os.path.exists(mp3) and os.path.getsize(mp3) > 1024)
        if not ok:
            ok = _synth_one(ch, mp3, voice, rate)
        if ok and os.path.exists(mp3) and os.path.getsize(mp3) > 1024:
            d = compose.probe_duration(mp3) or (len(ch) / 4.5)
            total_dur += d
            subprocess.run([compose.ffmpeg(), "-y", "-i", mp3, wav],
                           capture_output=True, check=False)
            if os.path.exists(wav) and os.path.getsize(wav) > 0:
                wavs.append(wav)
                print(f"  [配音 {i}/{len(chunks)}] {ch[:18]}… ({d:.1f}s)")
                continue
        # 失败兜底：插入静音补位，保持时间轴对齐，不中断整条生成
        print(f"  [配音失败 {i}] {ch[:18]}… 用静音补位")
        d = len(ch) / 4.5
        total_dur += d
        sil = os.path.join(audio_dir, f"c_{i:03d}_sil.wav")
        subprocess.run([compose.ffmpeg(), "-y", "-f", "lavfi", "-i",
                        f"anullsrc=r=24000:d={d:.3f}:cl=mono", sil],
                       capture_output=True, check=False)
        wavs.append(sil)
    return wavs, total_dur


def _concat_wavs(wavs, out_wav):
    listf = os.path.join(os.path.dirname(out_wav), "_wavs.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for w in wavs:
            f.write(f"file '{os.path.abspath(w).replace(chr(92), '/')}'\n")
    subprocess.run([compose.ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                    "-i", listf, "-c", "copy", out_wav],
                   capture_output=True, check=False)


def _build_html(series, title, subject, image):
    html = open(TEMPLATE, encoding="utf-8").read()
    html = (html
            .replace("{{SERIES}}", series)
            .replace("{{TITLE}}", title)
            .replace("{{SUBJECT}}", subject)
            .replace("{{BG}}", image or ""))
    return html


def main():
    ap = argparse.ArgumentParser(description="睡觉听历史 长音频历史科普生成器")
    ap.add_argument("script", nargs="?", default=None, help="episode json（默认用内置示例）")
    ap.add_argument("--title", help="标题 / 项目名")
    ap.add_argument("--voice", help="edge-tts 音色")
    ap.add_argument("--rate", help="语速，如 -10%")
    ap.add_argument("--bgm", help="背景音乐绝对路径")
    ap.add_argument("--limit-paras", type=int, default=0, help="只跑前 N 段（试看）")
    ap.add_argument("--person", help="项目目录名（默认同标题）")
    ap.add_argument("--no-bgm", action="store_true", help="不要背景音乐")
    args = ap.parse_args()

    items, title, voice, rate, bgm, bgm_vol, series, subject, image, episode = _load(
        args.script, args.title, args.voice, args.rate, args.bgm)
    if not items:
        print(json.dumps({"error": "没有任何文案段落"}, ensure_ascii=False))
        sys.exit(1)

    # 封面显示标题：与项目名/文件名解耦，可用 \n 手动换行
    disp_title = title
    try:
        _src = args.script or SAMPLE
        disp_title = (json.load(open(_src, encoding="utf-8")).get("display_title") or "").strip() or title
    except Exception:
        pass

    person = (args.person or title).strip()
    proj = store.create_project(person, title)
    pid = proj["id"]
    pdir = store.project_dir(pid)
    audio_dir = os.path.join(pdir, "audio")
    video_dir = os.path.join(pdir, "videos")
    hf_dir = os.path.join(pdir, "hf")
    output_dir = os.path.join(pdir, "output")
    assets_dir = os.path.join(pdir, "assets")
    for d in (audio_dir, video_dir, hf_dir, output_dir, assets_dir):
        os.makedirs(d, exist_ok=True)

    safe = re.sub(r'[\\/:*?"<>|\r\n\t ]+', '_', title)[:50] or "sleep_history"
    out_mp3 = os.path.join(output_dir, f"{safe}.mp3")
    out_mp4 = os.path.join(output_dir, f"{safe}.mp4")
    out_cover = os.path.join(output_dir, "cover.jpg")

    print(f"项目 {pid}（{person}）共 {len(items)} 段，开始分块配音……")

    # 1) 分块配音 → wav 列表 + 总时长
    wavs, total_dur = _synth(items, audio_dir, voice, rate, args.limit_paras)
    if total_dur <= 0:
        print("配音总时长为 0，终止")
        sys.exit(1)

    # 2) 拼接 wav → 单条 mp3（纯旁白，睡前听音主交付）
    full_wav = os.path.join(audio_dir, "_full.wav")
    _concat_wavs(wavs, full_wav)
    if not (os.path.exists(full_wav) and os.path.getsize(full_wav) > 0):
        print("拼接 wav 失败，未产出 _full.wav")
        sys.exit(1)
    subprocess.run([compose.ffmpeg(), "-y", "-i", full_wav,
                    "-c:a", "libmp3lame", "-b:a", "96k", out_mp3],
                   capture_output=True, check=False)
    if not (os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1024):
        print(f"旁白 MP3 编码失败：{out_mp3}")
        sys.exit(1)
    print(f"  旁白 MP3 完成：{out_mp3}（约 {total_dur/60:.1f} 分钟）")

    # 3) 渲染氛围循环视频
    html = _build_html(series, disp_title, subject, image)
    hdir = os.path.join(hf_dir, "loop")
    os.makedirs(hdir, exist_ok=True)
    html_path = os.path.join(hdir, "index.html")
    open(html_path, "w", encoding="utf-8").write(html)
    loop_mp4 = os.path.join(hdir, "loop.mp4")
    print("渲染氛围循环视频（0 积分）……")
    r = subprocess.run([NODE, RENDER_JS, html_path, loop_mp4, compose.ffmpeg()],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(loop_mp4):
        print("氛围渲染失败：\n" + (r.stderr or r.stdout)[-2000:])
        sys.exit(1)
    print(r.stdout[-600:])

    # 4) 循环铺满音频时长 → 混音 → 出片
    tmp_body = os.path.join(video_dir, "_body.mp4")
    subprocess.run([
        compose.ffmpeg(), "-y",
        "-stream_loop", "-1", "-i", loop_mp4,
        "-i", out_mp3,
        "-t", f"{total_dur:.3f}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ar", "24000", "-ac", "1",
        tmp_body,
    ], capture_output=True, check=False)

    if not (os.path.exists(tmp_body) and os.path.getsize(tmp_body) > 1024):
        print("氛围视频合成失败，未产出 _body.mp4（检查 loop.mp4 与旁白 mp3）")
        sys.exit(1)

    if not args.no_bgm and bgm and os.path.exists(bgm):
        ok, err = compose.add_bgm(tmp_body, bgm, bgm_vol, out_mp4)
        if not ok:
            print("BGM 混入失败，退回无 BGM:", err)
            import shutil
            shutil.copy(tmp_body, out_mp4)
    else:
        import shutil
        shutil.copy(tmp_body, out_mp4)

    # 5) 封面
    compose.extract_cover(out_mp4, out_cover, at=1.0)

    proj["output_path"] = out_mp4
    proj["output_url"] = "/" + store.rel(out_mp4)
    proj["cover_url"] = "/" + store.rel(out_cover) if os.path.exists(out_cover) else ""
    proj["audio_path"] = out_mp3
    proj["duration"] = round(total_dur, 1)
    store.save_project(proj)

    print(json.dumps({
        "ok": True, "project_id": pid, "title": title, "episode": episode,
        "audio": out_mp3, "video": out_mp4, "cover": out_cover,
        "duration_min": round(total_dur / 60, 1),
        "size_mb": round(os.path.getsize(out_mp4) / 1024 / 1024, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
