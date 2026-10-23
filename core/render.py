"""成片渲染：配音 -> 字幕 -> 片段 -> 拼接 -> 片头/BGM -> 封面。

没有生成视频的分镜会退化为「图片 + 缓慢推近（Ken Burns）」，
这样即使只跑完图片阶段也能出片。
"""
from __future__ import annotations

import os
import re
import threading

from . import atmos, compose, config, jobs, store, tts, video_plan


def output_basename(project: dict) -> str:
    """成片文件名主干（不含画幅后缀与 .mp4）。

    - 企业文化专栏「叮叮城故事」：用剧集 slug / 标题，如「叮叮城故事EP.01_坚守底线」，
      不再套用「<人物>_生平短片」。
    - 其余（生平短片）：沿用「<人物>_生平短片」。
    """
    is_culture = (
        project.get("category") == "dingding-city"
        or project.get("series") == "叮叮城故事"
    )
    if is_culture:
        name = (project.get("slug") or project.get("title") or project.get("person") or "成片").strip()
        # 文件名安全：把路径分隔符换成全角，避免被当成目录
        name = name.replace("/", "／").replace("\\", "＼")
        return name or "成片"
    person = (project.get("person") or "人物").strip() or "人物"
    return f"{person}_生平短片"


def parse_motion(text: str) -> dict:
    """从运镜提示词解析本地渲染的运镜类型（仅做相机运动，不做真实物理运动）。

    返回 {"kind": ...}，kind ∈ zoom_in / zoom_out / drift
      - zoom_in : 缓慢推近（默认，最安全，接近原行为）
      - zoom_out: 缓慢拉远（揭示更多环境）
      - drift   : 固定微放大 + 缓慢正弦平移（手持/呼吸感，适合「摇/移/平移/凝视」）
    """
    t = (text or "").lower()
    if any(k in t for k in ("推", "拉近", "推进", "向前", "zoom in", "近景", "特写")):
        return {"kind": "zoom_in"}
    if any(k in t for k in ("拉", "拉远", "退远", "拉开", "后退", "zoom out", "远景", "全景")):
        return {"kind": "zoom_out"}
    if any(k in t for k in ("摇", "移", "平移", "横移", "手持", "缓慢", "凝视", "漂移", "晃动")):
        return {"kind": "drift"}
    # 没有明确相机运动，但含真实运动词（飞驰/行走/航拍）→ drift 增加一点动感
    if any(k in t for k in video_plan.AI_MOTION_KEYWORDS):
        return {"kind": "drift"}
    # 默认：缓慢推近（带一点漂移让其「活」起来）
    return {"kind": "zoom_in"}


def _zoompan_clip(image_path: str, out_path: str, seconds: float,
                  motion: dict, aspect: str | None = None) -> tuple[bool, str]:
    """纯 2D 相机运动（Ken Burns）。作为视差渲染不可用时的兜底。"""
    W, H, FPS_ = compose.canvas(aspect)
    frames = max(30, int(seconds * FPS_))
    kind = motion.get("kind", "zoom_in")

    # 先放大到 2 倍画布再裁切，给运镜留足余量（横竖屏通用）
    base = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W * 2}:{H * 2},")

    if kind == "zoom_in":
        z0, z1 = 1.0, 1.18
    elif kind == "zoom_out":
        z0, z1 = 1.18, 1.0
    else:  # drift：固定微放大 + 缓慢平移
        z0 = z1 = 1.12

    fd = max(2, frames - 1)
    sm = (f"(min(1,on/{fd}))*(min(1,on/{fd}))*(3-2*(min(1,on/{fd})))")
    zexpr = f"lerp({z0},{z1},{sm})"

    if kind == "drift":
        period = max(2, frames // 3)
        xexpr = f"iw/2-(iw/zoom/2)+sin(on/{period}*6.2831)*0.045*iw"
        yexpr = f"ih/2-(ih/zoom/2)+cos(on/{period}*6.2831)*0.040*ih"
    else:
        xexpr = "iw/2-(iw/zoom/2)"
        yexpr = "ih/2-(ih/zoom/2)"

    vf = (
        base
        + f"zoompan=z='{zexpr}'"
        + f":x='{xexpr}'"
        + f":y='{yexpr}'"
        + f":d={frames}"
        + f":s={W}x{H}:fps={FPS_}"
        + f",trim=duration={seconds:.2f},setpts=PTS-STARTPTS"
    )
    return compose._run([
        "-loop", "1", "-i", image_path,
        "-filter_complex", vf,
        "-t", f"{seconds:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        out_path,
    ])


def _cinematic_clip(image_path: str, out_path: str, seconds: float,
                    motion: dict, aspect: str | None = None) -> tuple[bool, str]:
    """整图电影感运镜 + 氛围动态层（本地 ffmpeg 渲染，0 积分）。

    分三层叠加：
      - 主运镜：推近 / 拉远（smoothstep 缓动）+ 低频平移 + 高频微抖（手持的不完美感）
      - 氛围层：柔和光晕缓慢漂移 + 稀疏浮尘浮动（画面里真的有元素在动）
      - 调色层：胶片颗粒 + 光影呼吸 + 暗角 + 微增饱和对比

    不做前背景分离 —— 多人/复杂场景抠图会在背景残留人物轮廓形成
    「灵魂出窍」式重影，已实测否决（详见 CHANGELOG 2026-09-17）。
    """
    W, H, FPS = compose.canvas(aspect)
    N = max(30, int(seconds * FPS))
    FD = max(2, N - 1)
    sm = f"(min(1,on/{FD}))*(min(1,on/{FD}))*(3-2*(min(1,on/{FD})))"
    kind = (motion or {}).get("kind", "zoom_in")

    if kind == "zoom_out":
        zexpr = f"lerp(1.08,1.0,{sm})"
    elif kind == "drift":
        zexpr = "1.05"
    else:
        zexpr = f"lerp(1.0,1.08,{sm})"

    # 低频漂移周期（慢，营造推轨感）+ 高频微抖（手持呼吸，振幅约 1.5px @1080p）
    D1 = max(30, int(seconds * FPS * 1.6))
    amp = 1.0 if kind == "drift" else 0.6
    xexpr = (f"iw/2-(iw/zoom/2)+{0.007 * amp:.4f}*iw*sin(on/{D1}*6.2831)"
             f"+1.8*sin(on/2.7*6.2831)")
    yexpr = (f"ih/2-(ih/zoom/2)+{0.006 * amp:.4f}*ih*cos(on/{D1}*6.2831)"
             f"+1.4*cos(on/3.3*6.2831)")

    cache_dir = os.path.dirname(out_path)
    layers = atmos.ensure_layers(cache_dir, W, H)
    dw, dh = layers["dust_size"]
    fw, fh = layers["flare_size"]
    # 摆幅留出余量，保证叠加层始终盖满画面（不会露边）
    fx = max(10, (fw - W) // 2 - 20)
    fy = max(10, (fh - H) // 2 - 18)
    dxa = max(8, (dw - W) // 2 - 14)
    dya = max(8, (dh - H) // 2 - 10)

    vf = (
        f"[0:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W * 2}:{H * 2},"
        f"zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}'"
        f":d={N}:s={W}x{H}:fps={FPS},setsar=1[base];"
        f"[2:v]format=rgba,fps={FPS}[flare];"
        f"[1:v]format=rgba,fps={FPS}[dust];"
        # 光晕：缓慢横移 + 轻微起伏
        f"[base][flare]overlay="
        f"x='(W-w)/2+{fx}*sin(t/11*6.2831)'"
        f":y='(H-h)/2+{fy}*cos(t/13*6.2831)':eval=frame[o1];"
        # 浮尘：更慢的漂移（周期长，观感接近缓慢浮动）
        f"[o1][dust]overlay="
        f"x='(W-w)/2+{dxa}*sin(t/17*6.2831)'"
        f":y='(H-h)/2+{dya}*cos(t/23*6.2831)':eval=frame[o2];"
        # 胶片颗粒 + 光影呼吸 + 调色
        f"[o2]noise=alls=6:allf=t+u,"
        f"eq=brightness='0.014*sin(t/2.6)':saturation=1.07:contrast=1.05:eval=frame,"
        f"vignette=PI/4:0.26[out]"
    )
    return compose._run([
        "-loop", "1", "-framerate", str(FPS), "-i", image_path,
        "-loop", "1", "-framerate", str(FPS), "-i", layers["dust"],
        "-loop", "1", "-framerate", str(FPS), "-i", layers["flare"],
        "-filter_complex", vf,
        "-map", "[out]",
        "-t", f"{seconds:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        out_path,
    ])


def image_to_clip(image_path: str, out_path: str, seconds: float = 6.0,
                  motion: dict | None = None,
                  aspect: str | None = None) -> tuple[bool, str]:
    """图片 -> 电影感视频片段（本地 ffmpeg 渲染，0 积分）。

    主路线：整图电影运镜 + 氛围动态层（光晕 / 浮尘）+ 胶片颗粒 + 暗角调色。
    不做前背景分离（多人场景抠图会产生「灵魂出窍」式重影，已实测否决）。
    片段时长上限 10s，交由 compose.build_scene_clip 平滑慢放填满旁白，
    既保证镜头连续（不定格），又避免长时段逐帧 zoompan 过慢。
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    motion = motion or parse_motion("")
    seconds = max(2.0, min(float(seconds), 10.0))

    ok, err = _cinematic_clip(image_path, out_path, seconds, motion, aspect)
    if ok:
        return True, ""

    return _zoompan_clip(image_path, out_path, seconds, motion, aspect)


def _estimate_duration(text: str) -> float:
    """没有配音时按中文语速估算时长（约 4.6 字/秒）。"""
    n = len((text or "").strip())
    return max(3.0, n / 4.6)


def _to_seconds(v) -> float:
    """把剧本里的 duration（"10" / "10s" / "10 秒" / 10）转成秒，失败返回 0。"""
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else 0.0


def _clip_duration(s: dict, has_audio: bool) -> float:
    """单个分镜的目标时长。

    优先级：旁白音频时长 > 剧本 duration > 视频本身时长 > 按字数估算。
    后三者是「视频自带配音（不选旁白音色）」场景的时长来源 —— 此时
    必须用剧本里写好的 8/10/14 秒，否则会按旁白字数瞎猜。
    """
    if has_audio:
        return min(compose.probe_duration(s["_audio"]) + 0.6, 20.0)
    declared = _to_seconds(s.get("duration"))
    if declared > 0:
        return min(max(declared, 1.5), 20.0)
    vid = compose.probe_duration(s.get("_vid") or "")
    if vid > 0:
        return min(vid, 20.0)
    return min(_estimate_duration(s.get("narration", "")) + 0.6, 20.0)


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

    # 画布比例（项目级）：竖屏 9:16 / 横屏 16:9
    aspect = config.normalize_aspect(project.get("aspect"))
    crop_bottom = int(project.get("crop_bottom") or 0)

    # 字幕开关（项目级）：视频自带字幕 / 不需要字幕时设为 False，
    # 跳过「生成 + 烧录」自配字幕，直接透传视频原画面（避免双层字幕）。
    # 默认 True 保持旧行为（仍烧录旁白字幕）。
    burn_subtitles = bool(project.get("burn_subtitles", True))

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
    jobs.update(job_id, 0, f"共 {len(usable)} 个分镜（{config.aspect_conf(aspect)['label']}）")

    # ---- 1. 配音 -------------------------------------------------------
    # voice 为空 = 「不使用旁白（沿用视频自带音色）」：
    #   不生成 TTS，合成时保留每条视频的原声音轨。
    voice = (project.get("voice") or "").strip()
    rate = project.get("rate") or config.DEFAULT_RATE
    tts_on = bool(voice)
    for i, s in enumerate(usable):
        jobs.update(job_id, int(i / total * 70), f"配音 {i+1}/{len(usable)}")
        apath = os.path.join(audio_dir, f"{s['index']:02d}.mp3")
        narration = (s.get("narration") or "").strip()
        if tts_on and narration and not os.path.exists(apath):
            try:
                tts.synthesize(narration, apath, voice, rate, "+0%")
            except Exception:
                pass
        s["_audio"] = apath if (tts_on and narration and os.path.exists(apath)) else None

    # ---- 2. 逐分镜合成片段 ---------------------------------------------
    clips: list[str] = []
    for i, s in enumerate(usable):
        jobs.update(job_id, 70 + int((i + 1) / total * 25), f"合成片段 {i+1}/{len(usable)}")

        # 时长：旁白优先，其次剧本 duration（视频自带配音场景的关键）
        dur = _clip_duration(s, bool(s["_audio"]))

        # 视频源：优先 AI 视频，否则图片推近。
        # 本地运镜视频时长与旁白对齐（seconds=dur），保证 ratio≈1，
        # 避免 build_scene_clip 因短视频触发 tpad 定格导致片段后段静止。
        src_video = s["_vid"]
        if not src_video:
            if not s["_img"]:
                continue
            kb = os.path.join(clips_dir, f"{s['index']:02d}_kb.mp4")
            if not os.path.exists(kb):
                ok, err = image_to_clip(
                    s["_img"], kb, seconds=dur,
                    motion=parse_motion(s.get("video_prompt", "")),
                    aspect=aspect,
                )
                if not ok:
                    continue
            src_video = kb

        ass_path = os.path.join(subs_dir, f"{s['index']:02d}.ass")
        if burn_subtitles:
            compose.build_ass([(0.0, dur, s.get("narration", ""))], ass_path, aspect=aspect)
        else:
            ass_path = None  # 不烧录字幕：透传视频自带画面（含其自带字幕）

        clip = os.path.join(clips_dir, f"{s['index']:02d}.mp4")
        # keep_original_audio：没配旁白音色时，沿用视频自带音轨，而不是灌静音
        ok, err = compose.build_scene_clip(
            src_video, s["_audio"], dur, ass_path, clip,
            aspect=aspect,
            crop_bottom=crop_bottom,
            keep_original_audio=not tts_on,
        )
        if not ok:
            jobs.fail(job_id, f"分镜 {s['index']} 合成失败: {err}")
            raise RuntimeError(f"分镜 {s['index']} 合成失败: {err}")
        clips.append(clip)

    if not clips:
        raise RuntimeError("片段合成全部失败")

    # ---- 3. 片头 -------------------------------------------------------
    final = os.path.join(clips_dir, "_body.mp4")
    # 项目级开关：project["with_title"]=false 时不出片头（片段自身已带角标/字幕时用）
    with_title = bool(with_title and project.get("with_title", True))
    if with_title and usable:
        jobs.update(job_id, 96, "生成片头")
        title_clip = os.path.join(clips_dir, "00_title.mp4")
        bg = usable[0]["_img"]
        ok, err = compose.build_title_clip(
            project.get("title") or project["person"],
            project["person"],
            2.6, title_clip, bg_image=bg,
            aspect=aspect,
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
    # 横屏成片单独命名，避免与同一项目的竖屏成片互相覆盖
    suffix = "_16x9" if aspect == "landscape" else ""
    out_name = f"{output_basename(project)}{suffix}.mp4"
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
        "name": out_name,
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
            project["output_name"] = result.get("name") or os.path.basename(result["output"])
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

    voice = (project.get("voice") or "").strip()
    if not voice:
        # 音色为「不使用」：视频自带配音，本条链路直接跳过
        jobs.finish(job_id, {"count": 0, "skipped": "旁白音色设置为「不使用（沿用视频原声）」"})
        return job_id

    def _run():
        audio_dir = os.path.join(pdir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
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
