#!/usr/bin/env python3
"""「人生副本」单集视频生成器（HyperFrames 0 积分路线）。

每期只做一种人生体验，类似：
  今日副本 · 县城月薪4000却活的像富二代
风格：暗色背景 + 游戏化标题 + 卡通 meme 人物 + 分镜金句 + 配音。

用法：
  python scripts/gen_life_copy.py                          # 用内置示例脚本
  python scripts/gen_life_copy.py my_copy.json             # 自定义脚本
  python scripts/gen_life_copy.py --bgm ~/music.mp3 --voice zh-CN-YunxiNeural

script.json 结构：
{
  "title": "县城月薪4000，却活的像富二代",
  "series": "今日副本",
  "episode": "EP.01",
  "author": "二狗君",
  "voice": "zh-CN-YunxiNeural",
  "bgm": "/abs/bgm.mp3",
  "bgm_volume": 0.18,
  "scenes": [
    {"type":"cover", "heading":"", "text":"主标题\n可换行", "sub":"副标题", "image":"", "color":["#2a0a0a","#0f0505"]},
    {"type":"scene", "heading":"开局", "text":"文案", "sub":"小字", "image":"/abs/photo.jpg"},
    {"type":"quote", "heading":"金句", "text":"大字金句", "sub":""},
    {"type":"end", "heading":"副本结算", "text":"结尾", "sub":"关注我"}
  ]
}
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

from core import store, compose, tts, config  # noqa: E402
from scripts.fetch_images import fetch_image  # noqa: E402

NODE = "/Users/lingmf/.workbuddy/binaries/node/versions/22.12.0/bin/node"
RENDER_JS = os.path.join(ROOT, "scripts", "hf_render.js")
TEMPLATE = os.path.join(ROOT, "templates", "life_copy", "index.html")
SAMPLE = os.path.join(ROOT, "templates", "life_copy", "sample.json")

_PY = "/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python"


def _safe_name(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]+", "_", s).strip("_")[:40] or "life_copy"


def _load_script(path: str | None) -> dict:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif path:
        raise FileNotFoundError(f"脚本文件不存在: {path}")
    else:
        with open(SAMPLE, "r", encoding="utf-8") as f:
            data = json.load(f)
    return data


def _js_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _scene_to_json(scene: dict, meta: dict) -> str:
    """把 scene 转成注入 HTML 的 JS 对象字符串。"""
    obj = {
        "type": scene.get("type", "scene"),
        "series": scene.get("series") or meta.get("series", "今日副本"),
        "episode": scene.get("episode") or meta.get("episode", ""),
        "title": scene.get("title") or meta.get("title", ""),
        "sub": scene.get("sub", ""),
        "heading": scene.get("heading", ""),
        "text": scene.get("text", ""),
        "author": scene.get("author") or meta.get("author", ""),
        "color": scene.get("color", ["#2a0a0a", "#0f0505"]),
        "image": scene.get("image", ""),
        "emoji": scene.get("emoji", ""),
    }
    # cover 默认用 meta 标题
    if obj["type"] == "cover" and not obj.get("title"):
        obj["title"] = meta.get("title", "")
    # quote/end 的标题兜底
    if not obj["heading"]:
        if obj["type"] == "quote":
            obj["heading"] = "金句"
        elif obj["type"] == "end":
            obj["heading"] = "副本结算"
    return json.dumps(obj, ensure_ascii=False)


def _build_html(scene: dict, meta: dict, scene_dir: str, scene_idx: int) -> str:
    """生成单镜 HTML 文件，返回绝对路径。"""
    os.makedirs(scene_dir, exist_ok=True)
    out_html = os.path.join(scene_dir, "index.html")

    # 图片：若提供本地文件，复制到 scene_dir 并用相对路径
    img_src = scene.get("image", "")
    if img_src and os.path.exists(img_src):
        ext = os.path.splitext(img_src)[1].lower() or ".jpg"
        dst = os.path.join(scene_dir, f"image{ext}")
        shutil.copy2(img_src, dst)
        img_src = f"image{ext}"
        scene = dict(scene, image=img_src)

    scene_json = _scene_to_json(scene, meta)
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        tpl = f.read()

    # 替换 window.__SCENE__ = {...}
    # 用 lambda 避免 re.sub 对反斜杠做转义解释
    tpl = re.sub(
        r"window\.__SCENE__\s*=\s*\{[\s\S]*?\};",
        lambda m: f"window.__SCENE__ = {scene_json};",
        tpl,
        count=1,
    )
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(tpl)
    return out_html


def _render_scenes(manifest: list[dict], ffmpeg: str) -> bool:
    """调用 puppeteer 批量渲染。"""
    payload = {"ffmpeg": ffmpeg, "items": manifest}
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(payload, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    try:
        cmd = [NODE, RENDER_JS, tmp.name]
        print(f"[render] {' '.join(cmd)}")
        r = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(r.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("[HF render error]", e.stderr or e.stdout, file=sys.stderr)
        return False
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="生成单集「人生副本」视频")
    parser.add_argument("script", nargs="?", default=None, help="脚本 JSON 路径（默认用示例）")
    parser.add_argument("--voice", default=None, help="覆盖 voice")
    parser.add_argument("--bgm", default=None, help="覆盖 BGM 路径")
    parser.add_argument("--bgm-volume", type=float, default=None, help="覆盖 BGM 音量")
    parser.add_argument("--limit-scenes", type=int, default=None, help="只渲染前 N 个 scene 试跑")
    parser.add_argument("--max-scene-dur", type=float, default=45.0, help="单 scene 最大时长(秒)，默认 45")
    parser.add_argument("--no-fetch", action="store_true", help="不联网拉配图，改用 emoji/SVG 兜底")
    parser.add_argument("--project-dir", default=None, help="指定输出项目目录，默认用 title")
    args = parser.parse_args()

    data = _load_script(args.script)
    title = data.get("title", "人生副本")
    series = data.get("series", "今日副本")
    episode = data.get("episode", "")
    author = data.get("author", "二狗君")
    voice = (args.voice or data.get("voice") or config.DEFAULT_VOICE).strip()
    bgm = (args.bgm or data.get("bgm") or "").strip()
    bgm_vol = float(args.bgm_volume if args.bgm_volume is not None else data.get("bgm_volume", 0.18))
    scenes = data.get("scenes", [])
    if not scenes:
        raise ValueError("脚本里没有 scenes")

    project_dir = args.project_dir or os.path.join(ROOT, "projects", _safe_name(title))
    hf_dir = os.path.join(project_dir, "hf")
    video_dir = os.path.join(project_dir, "video")
    audio_dir = os.path.join(project_dir, "audio")
    output_dir = os.path.join(project_dir, "output")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 写入项目元信息
    meta = {
        "title": title,
        "series": series,
        "episode": episode,
        "author": author,
        "voice": voice,
        "bgm": bgm,
        "bgm_volume": bgm_vol,
    }
    with open(os.path.join(project_dir, "project.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "scenes": scenes}, f, ensure_ascii=False, indent=2)

    scenes = scenes[:args.limit_scenes] if args.limit_scenes else scenes

    # 1) 逐 scene 配音 + 写 HTML
    manifest: list[dict] = []
    scene_audios: list[str] = []
    scene_durations: list[float] = []

    for i, sc in enumerate(scenes, start=1):
        text_for_tts = sc.get("text", "").replace("\n", "，")
        if sc.get("sub"):
            text_for_tts += "，" + sc.get("sub").replace("\n", "，")
        if not text_for_tts.strip():
            text_for_tts = title

        audio_path = os.path.join(audio_dir, f"{i:03d}.mp3")
        print(f"[tts] scene {i}: {text_for_tts[:40]}...")
        dur = 3.5
        ok_audio = False
        for attempt in range(1, 4):
            try:
                cand = tts.synthesize(text_for_tts, audio_path, voice=voice)
            except Exception as e:
                print(f"[tts] scene {i} 第 {attempt} 次配音异常: {e}", file=sys.stderr)
                cand = 0.0
            # 校验：文件存在、够大、且能被 ffmpeg 解析出有效时长
            pdur = 0.0
            try:
                if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1024:
                    pdur = compose.probe_duration(audio_path) or 0.0
            except Exception:
                pdur = 0.0
            if cand and cand > 0 and pdur > 0.5:
                dur = cand
                ok_audio = True
                break
            else:
                print(f"[tts] scene {i} 第 {attempt} 次音频无效(cand={cand:.2f}, pdur={pdur:.2f})，重试", file=sys.stderr)
                import time
                time.sleep(0.6 * attempt)
        if not ok_audio:
            print(f"[tts] scene {i} 配音最终失败，使用默认 3.5s", file=sys.stderr)
        scene_audios.append(audio_path)
        scene_durations.append(dur)

        # 自动配图：image_query 优先于 emoji/SVG 兜底
        if not sc.get("image") and sc.get("image_query") and not args.no_fetch:
            q = sc["image_query"]
            slug = f"{i:03d}_{_safe_name(q)}"
            cached = fetch_image(q, os.path.join(project_dir, "assets"), slug)
            if cached:
                sc = dict(sc, image=cached)

        scene_dir = os.path.join(hf_dir, f"{i:03d}")
        html_path = _build_html(sc, meta, scene_dir, i)
        out_video = os.path.join(video_dir, f"{i:03d}.mp4")
        # 每镜至少 3s、不超过上限，给配音留余量
        clip_dur = min(max(dur + 0.6, 3.0), args.max_scene_dur)
        manifest.append({
            "html": html_path,
            "out": out_video,
            "dur": clip_dur,
        })

    # 2) HyperFrames 渲染
    ffmpeg = compose.ffmpeg() if hasattr(compose, "ffmpeg") else compose.get_ffmpeg()
    if not os.path.exists(ffmpeg):
        raise RuntimeError(f"找不到 ffmpeg: {ffmpeg}")
    print(f"[hf] 开始渲染 {len(manifest)} 个 scene ...")
    ok = _render_scenes(manifest, ffmpeg)
    if not ok:
        raise RuntimeError("HyperFrames 渲染失败")

    # 3) 每镜混音（HTML 无声视频 + TTS 配音）
    clip_paths: list[str] = []
    for i, item in enumerate(manifest, start=1):
        silent = item["out"]
        audio = scene_audios[i - 1]
        target = item["dur"]
        mixed = os.path.join(video_dir, f"{i:03d}_mixed.mp4")
        ok, err = compose.build_scene_clip(silent, audio, target, "", mixed)
        if not ok:
            print(f"[mix] scene {i} 混音失败: {err}，跳过音频", file=sys.stderr)
            mixed = silent
        clip_paths.append(mixed)

    # 4) 拼接 + BGM + 封面
    final_no_bgm = os.path.join(output_dir, "_no_bgm.mp4")
    ok, err = compose.concat_clips(clip_paths, final_no_bgm)
    if not ok:
        raise RuntimeError(f"拼接失败: {err}")

    final_path = os.path.join(output_dir, f"{_safe_name(title)}.mp4")
    if bgm and os.path.exists(bgm):
        ok, err = compose.add_bgm(final_no_bgm, bgm, final_path, volume=bgm_vol)
        if not ok:
            print(f"[bgm] 加 BGM 失败: {err}，使用无 BGM 版本", file=sys.stderr)
            shutil.copy2(final_no_bgm, final_path)
    else:
        shutil.copy2(final_no_bgm, final_path)

    cover_path = os.path.join(output_dir, "cover.jpg")
    try:
        compose.extract_cover(final_path, cover_path, at=0.3)
    except Exception as e:
        print(f"[cover] 封面抽取失败: {e}", file=sys.stderr)

    # 保留中间文件，避免批量删除触发安全确认；用户可手动清理 video/ 目录。
    # for item in manifest:
    #     try: os.remove(item["out"])
    #     except OSError: pass
    # try: os.remove(final_no_bgm)
    # except OSError: pass

    print(f"\n✅ 成片: {final_path}")
    if os.path.exists(cover_path):
        print(f"🖼  封面: {cover_path}")
    print(f"📁 项目: {project_dir}")


if __name__ == "__main__":
    main()
