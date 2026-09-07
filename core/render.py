"""成片渲染：配音 -> 字幕 -> 片段 -> 拼接 -> 片头/BGM -> 封面。

没有生成视频的分镜会退化为「图片 + 缓慢推近（Ken Burns）」，
这样即使只跑完图片阶段也能出片。
"""
from __future__ import annotations

import os
import threading

from . import compose, config, jobs, store, tts


def image_to_clip(image_path: str, out_path: str, seconds: float = 5.0) -> tuple[bool, str]:
    """图片 -> 带缓慢推近效果的视频片段。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    frames = max(30, int(seconds * compose.FPS))
    vf = (
        "scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
        f"zoompan=z='min(zoom+0.0012,1.25)':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={compose.WIDTH}x{compose.HEIGHT}:fps={compose.FPS},"
        f"trim=duration={seconds:.2f},setpts=PTS-STARTPTS"
    )
    return compose._run([
        "-loop", "1", "-i", image_path,
        "-filter_complex", vf,
        "-t", f"{seconds:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        out_path,
    ])


def _estimate_duration(text: str) -> float:
    """没有配音时按中文语速估算时长（约 4.6 字/秒）。"""
    n = len((text or "").strip())
    return max(3.0, n / 4.6)


def render_project(project_id: str, with_title: bool = True, with_bgm: bool = True) -> dict:
    """同步渲染，返回产物路径字典。供后台线程调用。"""
    job_id = f"render:{project_id}"
    pdir = store.project_dir(project_id)
    project = store.load_project(project_id)
    if not project:
        raise FileNotFoundError("项目不存在")

    images_dir = os.path.join(pdir, "images")
    videos_dir = os.path.join(pdir, "videos")
    audio_dir = os.path.join(pdir, "audio")
    subs_dir = os.path.join(pdir, "subs")
    clips_dir = os.path.join(pdir, "clips")
    output_dir = os.path.join(pdir, "output")
    for d in (audio_dir, subs_dir, clips_dir, output_dir):
        os.makedirs(d, exist_ok=True)

    scenes = [s for s in project.get("scenes", [])]
    usable = []
    for s in scenes:
        img = s.get("image_path") or ""
        vid = s.get("video_path") or ""
        if img and not os.path.isabs(img):
            img = os.path.join(pdir, img)
        if vid and not os.path.isabs(vid):
            vid = os.path.join(pdir, vid)
        if os.path.exists(vid) or os.path.exists(img):
            s = dict(s)
            s["_img"] = img if os.path.exists(img) else ""
            s["_vid"] = vid if os.path.exists(vid) else ""
            usable.append(s)

    if not usable:
        raise RuntimeError("没有任何可用素材，请先生成图片或视频")

    total = len(usable) + 3
    jobs.update(job_id, 0, f"共 {len(usable)} 个分镜")

    # ---- 1. 配音 -------------------------------------------------------
    voice = project.get("voice") or config.DEFAULT_VOICE
    rate = project.get("rate") or config.DEFAULT_RATE
    for i, s in enumerate(usable):
        jobs.update(job_id, int(i / total * 70), f"配音 {i+1}/{len(usable)}")
        apath = os.path.join(audio_dir, f"{s['index']:02d}.mp3")
        narration = (s.get("narration") or "").strip()
        if not os.path.exists(apath) and narration:
            try:
                tts.synthesize(narration, apath, voice, rate, "+0%")
            except Exception:
                apath = None
        s["_audio"] = apath if apath and os.path.exists(apath) else None

    # ---- 2. 逐分镜合成片段 ---------------------------------------------
    clips: list[str] = []
    for i, s in enumerate(usable):
        jobs.update(job_id, 70 + int((i + 1) / total * 25), f"合成片段 {i+1}/{len(usable)}")

        # 视频源：优先 AI 视频，否则图片推近
        src_video = s["_vid"]
        if not src_video:
            kb = os.path.join(clips_dir, f"{s['index']:02d}_kb.mp4")
            if not os.path.exists(kb):
                ok, err = image_to_clip(s["_img"], kb, seconds=6.0)
                if not ok:
                    continue
            src_video = kb

        # 时长：以旁白为准，留 0.6s 尾白
        if s["_audio"]:
            dur = compose.probe_duration(s["_audio"]) + 0.6
        else:
            dur = _estimate_duration(s.get("narration", "")) + 0.6
        dur = min(dur, 20.0)

        ass_path = os.path.join(subs_dir, f"{s['index']:02d}.ass")
        compose.build_ass([(0.0, dur, s.get("narration", ""))], ass_path)

        clip = os.path.join(clips_dir, f"{s['index']:02d}.mp4")
        ok, err = compose.build_scene_clip(src_video, s["_audio"], dur, ass_path, clip)
        if not ok:
            jobs.fail(job_id, f"分镜 {s['index']} 合成失败: {err}")
            raise RuntimeError(f"分镜 {s['index']} 合成失败: {err}")
        clips.append(clip)

    if not clips:
        raise RuntimeError("片段合成全部失败")

    # ---- 3. 片头 -------------------------------------------------------
    final = os.path.join(clips_dir, "_body.mp4")
    if with_title and usable:
        jobs.update(job_id, 96, "生成片头")
        title_clip = os.path.join(clips_dir, "00_title.mp4")
        bg = usable[0]["_img"]
        ok, err = compose.build_title_clip(
            project.get("title") or project["person"],
            project["person"],
            2.6, title_clip, bg_image=bg,
        )
        if ok:
            clips = [title_clip] + clips

    ok, err = compose.concat_clips(clips, final)
    if not ok:
        raise RuntimeError(f"拼接失败: {err}")

    # ---- 4. BGM --------------------------------------------------------
    bgm = project.get("bgm_path") or ""
    if bgm and not os.path.isabs(bgm):
        bgm = os.path.join(pdir, bgm)
    out_name = f"{project['person']}_生平短片.mp4"
    out_path = os.path.join(output_dir, out_name)

    if with_bgm and bgm and os.path.exists(bgm):
        jobs.update(job_id, 98, "混入背景音乐")
        ok, err = compose.add_bgm(final, bgm, float(project.get("bgm_volume") or 0.18), out_path)
        if not ok:
            out_path = final
    else:
        if os.path.abspath(final) != os.path.abspath(out_path):
            with open(final, "rb") as fi, open(out_path, "wb") as fo:
                fo.write(fi.read())

    jobs.update(job_id, 99, "生成封面")
    cover = os.path.join(output_dir, "cover.jpg")
    compose.extract_cover(out_path, cover, at=0.8)

    return {
        "output": out_path,
        "url": "/" + store.rel(out_path),
        "cover": "/" + store.rel(cover) if os.path.exists(cover) else "",
        "duration": compose.probe_duration(out_path),
        "size_mb": round(os.path.getsize(out_path) / 1024 / 1024, 2),
        "scenes": len(usable),
    }


def start_render(project_id: str, with_title: bool = True, with_bgm: bool = True) -> str:
    job_id = f"render:{project_id}"
    jobs.start(job_id, "render", 100)

    def _run():
        try:
            result = render_project(project_id, with_title, with_bgm)
            project = store.load_project(project_id)
            project["output_path"] = result["output"]
            project["output_url"] = result["url"]
            project["cover_url"] = result["cover"]
            store.save_project(project)
            jobs.finish(job_id, result)
        except Exception as e:
            jobs.fail(job_id, str(e))

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def start_tts(project_id: str) -> str:
    job_id = f"tts:{project_id}"
    pdir = store.project_dir(project_id)
    project = store.load_project(project_id)
    scenes = project.get("scenes", [])
    jobs.start(job_id, "tts", len(scenes))

    def _run():
        audio_dir = os.path.join(pdir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        voice = project.get("voice") or config.DEFAULT_VOICE
        rate = project.get("rate") or config.DEFAULT_RATE
        ok_n = 0
        err = ""
        for i, s in enumerate(scenes):
            jobs.update(job_id, int((i + 1) / max(1, len(scenes)) * 100),
                        f"配音 {i+1}/{len(scenes)}")
            apath = os.path.join(audio_dir, f"{s['index']:02d}.mp3")
            narration = (s.get("narration") or "").strip()
            if not narration:
                continue
            try:
                tts.synthesize(narration, apath, voice, rate, "+0%")
                s["audio_path"] = os.path.join("audio", f"{s['index']:02d}.mp3").replace("\\", "/")
                ok_n += 1
            except Exception as e:
                err = str(e)
                break
        store.save_project(project)
        if err:
            jobs.fail(job_id, f"配音中断（网络或音色不可用）: {err}")
        else:
            jobs.finish(job_id, {"count": ok_n})

    threading.Thread(target=_run, daemon=True).start()
    return job_id
