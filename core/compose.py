"""ffmpeg 合成：字幕烧录、音画对齐、片头、BGM、拼接。

画布尺寸由项目级 aspect 决定（见 config.ASPECTS）：
    portrait  → 1080x1920 竖屏 30fps（短视频平台）
    landscape → 1920x1080 横屏 30fps（企业宣传片 / 大屏 / 手机横屏）
所有素材统一「等比放大到铺满画布 + 居中裁切」，避免变形。
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

from . import config

# 默认画布（竖屏），仅为向后兼容保留；实际尺寸请用 canvas(aspect)
WIDTH, HEIGHT, FPS = 1080, 1920, 30


def canvas(aspect: str | None = None) -> tuple[int, int, int]:
    """按项目比例返回 (宽, 高, 帧率)。"""
    c = config.aspect_conf(aspect)
    return int(c["width"]), int(c["height"]), FPS


def get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        exe = which("ffmpeg")
        if not exe:
            raise RuntimeError("未找到 ffmpeg，请先安装依赖：pip install imageio-ffmpeg")
        return exe


FFMPEG = None


def ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = get_ffmpeg()
    return FFMPEG


# --------------------------------------------------------------------------
# 探测与工具
# --------------------------------------------------------------------------


def probe_duration(path: str) -> float:
    if not path or not os.path.exists(path):
        return 0.0
    try:
        r = subprocess.run(
            [ffmpeg(), "-i", path],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
        if m:
            h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mnt * 60 + s
    except Exception:
        pass
    return 0.0


def has_audio_stream(path: str) -> bool:
    """判断素材是否自带音轨（用于「旁白用视频原声」的降级判断）。

    视频大模型产出的片段有时是无音轨的，直接 [1:a] 引用会让 ffmpeg 报错。
    """
    if not path or not os.path.exists(path):
        return False
    try:
        r = subprocess.run(
            [ffmpeg(), "-i", path],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return "Audio:" in (r.stderr or "")
    except Exception:
        return False


def _esc(path: str, base: str | None = None) -> str:
    """返回适合 ffmpeg filter 引用的路径。
    若提供 base 则输出相对路径（避免 Windows 盘符冒号被误解析为选项），
    否则输出绝对路径并转义冒号。
    """
    if base:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
        return rel.replace("\\", "/")
    p = os.path.abspath(path).replace("\\", "/")
    return p.replace(":", "\\:")


def _run(args: list[str], cwd: str | None = None) -> tuple[bool, str]:
    r = subprocess.run(
        [ffmpeg(), "-y", *args],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        cwd=cwd,
    )
    if r.returncode != 0:
        return False, (r.stderr or "")[-2000:]
    return True, ""


# --------------------------------------------------------------------------
# 字幕
# --------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])")


def split_lines(text: str, max_chars: int = 18) -> list[str]:
    """把旁白切成适合短视频的字幕行。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p for p in _SPLIT_RE.split(text) if p.strip()]

    lines: list[str] = []
    for p in parts:
        while len(p) > max_chars:
            cut = max_chars
            for sep in ("，", "、", ",", " "):
                idx = p.rfind(sep, 0, max_chars)
                if idx > max_chars * 0.5:
                    cut = idx + 1
                    break
            lines.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            lines.append(p)
    return lines or [text]


def ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def build_ass(segments: list[tuple[float, float, str]], out_path: str,
              aspect: str | None = None) -> str:
    """segments: [(start, end, text)]，按字数把长句再拆成多行。

    关键修复：单行字数由字号 + 画布宽度自动反算，保证任意字号/任意画布
    （竖屏 1080 / 横屏 1920）下字幕都不会超出屏幕。
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    W, H, _ = canvas(aspect)
    conf = config.aspect_conf(aspect)

    # 可用宽度（减去左右安全边距），再按 SUBTITLE_FIT 留余量
    usable = W - 2 * conf["sub_lr"]
    # 一行中文约 1em 宽；取整后至少保留 8 字，避免过短句子被切太碎
    max_chars = max(8, int(usable * config.SUBTITLE_FIT / conf["sub_size"]))

    rows: list[tuple[float, float, str]] = []
    for start, end, text in segments:
        lines = split_lines(text, max_chars)
        if not lines:
            continue
        span = max(0.4, end - start)
        weights = [max(1, len(l)) for l in lines]
        total_w = sum(weights)
        cur = start
        for line, w in zip(lines, weights):
            d = span * (w / total_w)
            rows.append((cur, cur + d, line))
            cur += d

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{config.SUBTITLE_FONT},{conf["sub_size"]},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,1,{config.SUBTITLE_OUTLINE},{config.SUBTITLE_SHADOW},2,{conf["sub_lr"]},{conf["sub_lr"]},{conf["sub_v"]},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{_ass_escape(t)}\n"
        for s, e, t in rows
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + body)
    return out_path


# --------------------------------------------------------------------------
# 单片段：视频 + 旁白 + 字幕
# --------------------------------------------------------------------------


def build_scene_clip(
    video_path: str,
    audio_path: str | None,
    duration: float,
    ass_path: str,
    out_path: str,
    aspect: str | None = None,
    crop_bottom: int = 0,
    keep_original_audio: bool = False,
) -> tuple[bool, str]:
    """把一个分镜的视频、旁白（或原声）、字幕合成一个片段。

    参数
    ----
    aspect              : portrait / landscape，决定画布尺寸与字幕版式
    crop_bottom         : 先裁掉画面底部 N 像素（去「豆包 AI 生成」这类水印条），
                          再做等比放大铺满画布；0 表示不裁
    keep_original_audio : 没有旁白音频时，是否沿用视频自带音轨
                          （AI 视频自带配音时用，避免整条配音轨变静音）

    采用两步法避免 ffmpeg 7.1 在 filter_complex 中
    同时使用 subtitles + setpts 时的段错误崩溃：
      Step A — 视频缩放/变速 → 临时文件
      Step B — 烧字幕 + 混音 → 最终片段
    """
    W, H, _fps = canvas(aspect)
    src_dur = probe_duration(video_path) or 5.0
    target = max(1.5, duration)

    base = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(base, exist_ok=True)

    # ---- Step A: 视频预处理（去水印条 / 缩放 / 变速 / fps） ----
    vchain: list[str] = []
    cb = max(0, min(int(crop_bottom or 0), 400))
    if cb:
        vchain.append(f"crop=iw:ih-{cb}:0:0")
    vchain += [
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos",
        f"crop={W}:{H}",
        "setsar=1",
    ]
    ratio = target / src_dur
    if ratio > 1.05:
        if ratio <= 3.0:
            vchain.append(f"setpts=PTS*{ratio:.4f}")
        else:
            vchain.append("setpts=PTS*3.0")
            vchain.append(f"tpad=stop_mode=clone:stop_duration={target - 3.0 * src_dur:.3f}")
    vchain.append(f"fps={_fps}")

    mid = os.path.join(base, f"_mid_{os.path.basename(out_path)}")
    vf_a = ",".join(vchain)
    ok, err = _run([
        "-i", video_path,
        "-vf", vf_a,
        "-t", f"{target:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an",
        mid,
    ], cwd=base)
    if not ok:
        return False, f"视频预处理失败: {err}"

    # ---- Step B: 烧字幕 + 混音 ----
    # ass_path 为 None / 不存在 = 不烧录字幕（视频自带字幕或不要字幕时透传）。
    has_sub = bool(ass_path) and os.path.exists(ass_path)
    if has_sub:
        vf_b = f"[0:v]subtitles=filename={_esc(ass_path, base)}[vout]"
    else:
        # 无字幕：纯透传（[0:v][vout] 是非法语法，必须带滤镜名）
        vf_b = "[0:v]copy[vout]"

    args_b = ["-y", "-i", mid]
    if audio_path and os.path.exists(audio_path):
        # 有旁白：旁白优先（原声被替换）
        args_b += ["-i", audio_path]
        afilter = f"apad,atrim=0:{target:.3f},asetpts=N/SR/TB"
    elif keep_original_audio and has_audio_stream(video_path):
        # 无旁白 + 视频自带音轨：沿用原声
        args_b += ["-i", video_path]
        pre = ""
        if abs(ratio - 1.0) > 0.05:
            # 画面被慢放/快放，原声用 atempo 反向补偿，保持同步
            tempo = max(0.5, min(2.0, 1.0 / ratio))
            pre = f"atempo={tempo:.4f},"
        afilter = f"{pre}apad,atrim=0:{target:.3f},asetpts=N/SR/TB"
    else:
        args_b += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        afilter = f"atrim=0:{target:.3f},asetpts=N/SR/TB"

    args_b += [
        "-filter_complex", f"{vf_b};[1:a]{afilter}[aout]",
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{target:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        out_path,
    ]
    ok, err = _run(args_b, cwd=base)
    # 保留临时文件，避免沙盒批量删除触发安全确认；可手动清理 _mid_*。
    # for f in (mid,):
    #     try:
    #         if f and os.path.exists(f):
    #             os.remove(f)
    #     except OSError:
    #         pass
    return ok, err


def build_title_clip(title: str, subtitle: str, duration: float, out_path: str,
                     bg_image: str | None = None,
                     aspect: str | None = None) -> tuple[bool, str]:
    """片头：黑底（或背景图）+ 大标题 + 副标题。"""
    base_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(base_dir, exist_ok=True)

    W, H, FPS_ = canvas(aspect)
    conf = config.aspect_conf(aspect)

    # 跨平台字体：优先使用 config 探测到的中文字体文件
    font = config.TITLE_FONT_FILE
    if not font or font == "sans-serif":
        # 探测失败时，回退到当前系统实际可用的字体
        import shutil as _shutil
        for fallback in ("Arial", "Helvetica", "DejaVuSans"):
            if _shutil.which("fc-match"):
                import subprocess as _sp
                r = _sp.run(["fc-match", "-f", "%{file}", fallback],
                            capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    font = r.stdout.strip()
                    break
            else:
                font = fallback
                break
    font = _esc(font)

    if bg_image and os.path.exists(bg_image):
        src = ["-loop", "1", "-i", bg_image, "-t", f"{duration:.2f}"]
        vbase = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W}:{H},setsar=1,fps={FPS_},"
            f"eq=brightness=-0.22:contrast=1.15,"
        )
    else:
        src = ["-f", "lavfi", "-i",
               f"color=c=0x0d0b08:s={W}x{H}:d={duration:.2f}:r={FPS_}"]
        vbase = "[0:v]"

    # 标题/副标题字号按文字长度反算，确保不超出画面（留安全边距）。
    # CJK 字符近似按 1em 宽估算，取保守值，宁可偏小也不溢出。
    _title_margin = conf["title_margin"]
    _title_usable = W - 2 * _title_margin
    title_fs = min(int(H * 0.10), int(_title_usable / max(1, len(title))))
    title_fs = max(28, title_fs)
    sub_fs = max(22, int(title_fs * 0.55))
    if subtitle:
        # 副标题同时受「画面宽度」和「不超过标题字号」两个约束
        sub_fs = min(sub_fs, int((W - 2 * _title_margin) / max(1, len(subtitle))))
        sub_fs = max(20, sub_fs)

    # 竖屏时标题略高于画面中心；横屏时居中即可，避免文字贴边
    y_title = "(h-th)/2-60" if H > W else "(h-th)/2-30"
    y_sub = "(h-th)/2+140" if H > W else "(h-th)/2+70"

    vf = (
        vbase
        + f"drawtext=fontfile={font}:text='{_drawtext_esc(title)}':fontsize={title_fs}"
        + ":fontcolor=0xF5E9D0:borderw=3:bordercolor=0x000000@0.55"
        + f":x=(w-tw)/2:y={y_title}"
        + f",drawtext=fontfile={font}:text='{_drawtext_esc(subtitle)}':fontsize={sub_fs}"
        + ":fontcolor=0xD8CBB4:borderw=2:bordercolor=0x000000@0.5"
        + f":x=(w-tw)/2:y={y_sub}"
        + f",fade=t=in:st=0:d=0.6"
    )

    args = [
        *src,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex", f"{vf}[vout];[1:a]atrim=0:{duration:.2f}[aout]",
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        out_path,
    ]
    return _run(args, cwd=base_dir)


def _drawtext_esc(text: str) -> str:
    """drawtext 的 text 参数转义。"""
    t = (text or "").replace("\\", "").replace("'", "")
    t = t.replace(":", "\\:").replace("%", "\\%").replace(",", "\\,")
    return t


# --------------------------------------------------------------------------
# 拼接 / BGM / 封面
# --------------------------------------------------------------------------


def concat_clips(clips: list[str], out_path: str) -> tuple[bool, str]:
    if not clips:
        return False, "没有可拼接的片段"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    list_file = os.path.join(os.path.dirname(out_path), "_concat.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c).replace(chr(92), '/')}'\n")
    ok, err = _run([
        "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", out_path,
    ])
    # 保留 concat 列表，避免沙盒批量删除触发安全确认。
    # try:
    #     if os.path.exists(list_file):
    #         os.remove(list_file)
    # except OSError:
    #     pass
    return ok, err


def add_bgm(video_path: str, bgm_path: str, volume: float, out_path: str) -> tuple[bool, str]:
    if not bgm_path or not os.path.exists(bgm_path):
        return False, "BGM 文件不存在"
    dur = probe_duration(video_path) or 0.0
    fade_out_start = max(0.0, dur - 2.5)
    achain = [
        f"volume={volume:.3f}",
        "afade=t=in:st=0:d=1.5",
    ]
    if fade_out_start > 1.5:
        achain.append(f"afade=t=out:st={fade_out_start:.3f}:d=2.5")
    args = [
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        f"[1:a]{','.join(achain)}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    return _run(args)


def extract_cover(video_path: str, out_path: str, at: float = 1.0) -> tuple[bool, str]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return _run([
        "-ss", f"{at:.2f}", "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_path,
    ])


def extract_frame(video_path: str, out_path: str,
                  at: float | None = None,
                  ratio: float = 0.4) -> tuple[bool, str]:
    """从视频里抽一帧存成图片，用作分镜首帧 / 缩略图。

    at 给定时按秒数抽取；否则按 ratio 取视频比例位置（默认 40%，
    避开开头淡入、结尾淡出和运镜刚起幅的过渡帧）。
    抽帧位置用 -ss 前置定位，速度快且不依赖全解，代价是可能落在
    最近的关键帧上（对分镜缩略图完全够用）。
    """
    if not video_path or not os.path.exists(video_path):
        return False, "视频文件不存在"

    if at is None:
        dur = probe_duration(video_path)
        at = max(0.2, dur * ratio) if dur > 1.0 else 1.0

    ok, err = extract_cover(video_path, out_path, at=float(at))
    if ok and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return True, ""
    # 前置 -ss 抽不到（极短视频 / 时长探测偏差）时，退化为从 0 秒解一帧
    if float(at) > 0:
        return extract_cover(video_path, out_path, at=0.0)
    return False, err or "抽帧失败"
