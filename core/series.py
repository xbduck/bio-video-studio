"""系列工厂：读取 series/ 目录、预估时长、创建新系列、启动批跑。

与 core/store.py（生平短片项目）相互独立：系列是「多集长音频」，
目录结构为 series/<slug>/{manifest.json, ep01.json..., .state.json}。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import quote

from . import config

SERIES_DIR = os.path.join(config.ROOT, "series")
BASE_CPM = 272.0  # +0% 语速下每分钟字数


def _read(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _pct(rate: str) -> float:
    s = (rate or "0%").strip().rstrip("%")
    try:
        return float(s) / 100.0
    except ValueError:
        return 0.0


def count_chars(data: dict) -> int:
    total = 0
    for p in (data or {}).get("paragraphs", []):
        if isinstance(p, str):
            total += len(p)
        elif isinstance(p, dict):
            total += len(p.get("text") or p.get("title") or "")
    return total


def est_minutes(chars: int, rate: str) -> float:
    cpm = BASE_CPM * (1 + _pct(rate))
    return chars / cpm if cpm > 0 else 0.0


def _url(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    rel = os.path.relpath(path, config.ROOT).replace(os.sep, "/")
    return "/" + quote(rel, safe="/")


def _image_variant(video: str) -> str:
    """成片旁边是否存在「配图版」：<title>_配图.mp4。"""
    if not video:
        return ""
    cand = os.path.splitext(video)[0] + "_配图.mp4"
    return cand if os.path.isfile(cand) else ""


def _is_running(sdir: str) -> bool:
    pid_file = os.path.join(sdir, ".run.pid")
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        pass
    # 兜底：CLI 启动（start_series.py）可能没有 .run.pid，用进程名匹配
    try:
        r = subprocess.run(
            ["pgrep", "-f", f"run_series.py series/{os.path.basename(sdir)}"],
            capture_output=True, text=True, timeout=3)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _log_path(slug: str) -> str:
    return os.path.join(config.LOG_DIR, f"series-{slug}.log")


def series_dir(slug: str) -> str:
    return os.path.join(SERIES_DIR, slug)


def get_series(slug: str) -> dict | None:
    for s in list_series():
        if s["slug"] == slug or s["dir_name"] == slug:
            return s
    return None


def list_series() -> list[dict]:
    out: list[dict] = []
    if not os.path.isdir(SERIES_DIR):
        return out
    for name in sorted(os.listdir(SERIES_DIR)):
        if name.startswith("_") or name.startswith("."):
            continue
        sdir = os.path.join(SERIES_DIR, name)
        if not os.path.isdir(sdir):
            continue
        manifest = _read(os.path.join(sdir, "manifest.json"))
        if not manifest:
            continue
        out.append(_summary(sdir, name, manifest))
    out.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return out


def _summary(sdir: str, dir_name: str, manifest: dict) -> dict:
    slug = manifest.get("slug") or dir_name
    defaults = manifest.get("defaults") or {}
    rate_default = defaults.get("rate") or "-10%"
    state = _read(os.path.join(sdir, ".state.json"), {}) or {}

    episodes = []
    total_chars = 0
    total_min = 0.0
    done = 0
    failed = 0
    updated = ""
    for ep in manifest.get("episodes", []):
        ep_id = ep.get("id") or ""
        ep_path = os.path.join(sdir, ep.get("file") or "")
        data = _read(ep_path) if os.path.isfile(ep_path) else None
        chars = count_chars(data) if data else 0
        rate = (data or {}).get("rate") or rate_default
        minutes = est_minutes(chars, rate) if chars else 0.0
        total_chars += chars
        total_min += minutes

        st = state.get(ep_id) or {}
        status = st.get("status") or ("idle" if data else "missing")
        video = st.get("video") or ""
        audio = st.get("audio") or ""
        cover = st.get("cover") or ""
        if status == "done" and not (video and os.path.isfile(video)):
            status = "lost"
        if status == "done":
            done += 1
        elif status == "failed":
            failed += 1
        if st.get("finished_at") and st["finished_at"] > updated:
            updated = st["finished_at"]

        episodes.append({
            "id": ep_id,
            "title": (data or {}).get("title") or ep.get("title") or ep_id,
            "subject": (data or {}).get("subject") or "",
            "note": ep.get("note") or "",
            "chars": chars,
            "rate": rate,
            "est_minutes": round(minutes, 1),
            "status": status,
            "duration_min": st.get("duration_min"),
            "elapsed_sec": st.get("elapsed_sec"),
            "started_at": st.get("started_at"),
            "finished_at": st.get("finished_at"),
            "video_url": _url(video),
            "image_video_url": _url(_image_variant(video)),
            "audio_url": _url(audio),
            "cover_url": _url(cover),
            "output_dir": os.path.dirname(video) if video else "",
        })

    running = _is_running(sdir)
    return {
        "slug": slug,
        "dir_name": dir_name,
        "series": manifest.get("series") or "系列",
        "topic": manifest.get("topic") or "",
        "voice": defaults.get("voice") or "",
        "rate": rate_default,
        "episode_count": len(episodes),
        "done_count": done,
        "failed_count": failed,
        "total_chars": total_chars,
        "total_minutes": round(total_min, 1),
        "running": running,
        "updated_at": updated,
        "log_path": _log_path(slug),
        "episodes": episodes,
    }


def _slugify(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", s)
    s = re.sub(r"\s+", "-", s)
    s = s.strip("-._ ")
    return s[:50]


def create_series(name: str, series: str = "睡觉听历史", topic: str = "",
                  voice: str = "zh-CN-YunjianNeural", rate: str = "-50%") -> dict:
    slug = _slugify(name)
    if not slug:
        raise ValueError("系列名不能为空")
    target = os.path.join(SERIES_DIR, slug)
    if os.path.exists(target):
        raise ValueError(f"系列已存在：{slug}")

    template = os.path.join(SERIES_DIR, "_template")
    os.makedirs(SERIES_DIR, exist_ok=True)
    if os.path.isdir(template):
        shutil.copytree(template, target)
    else:
        os.makedirs(target, exist_ok=True)

    manifest = {
        "slug": slug,
        "series": series or "睡觉听历史",
        "topic": topic or slug,
        "defaults": {"voice": voice, "rate": rate, "bgm": "", "bgm_volume": 0.1},
        "episodes": [{"id": "EP.01", "file": "ep01.json", "note": "第一集"}],
    }
    with open(os.path.join(target, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    ep_path = os.path.join(target, "ep01.json")
    ep = _read(ep_path, {}) or {}
    ep.update({
        "series": series or "睡觉听历史",
        "episode": "EP.01",
        "title": f"EP.01 {topic or slug}",
        "subject": "",
    })
    if not ep.get("paragraphs"):
        ep["paragraphs"] = ["在这里写第一段旁白。", "在这里写第二段旁白。"]
    with open(ep_path, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    return get_series(slug) or {"slug": slug}


def run_series(slug: str, only: list[str] | None = None, from_ep: str | None = None,
               force: bool = False) -> int:
    sdir = series_dir(slug)
    if not os.path.isfile(os.path.join(sdir, "manifest.json")):
        raise ValueError(f"系列不存在：{slug}")
    if _is_running(sdir):
        raise ValueError("该系列正在生成中，请稍后再试")

    cmd = [sys.executable, os.path.join(config.ROOT, "start_series.py"), f"series/{slug}"]
    if only:
        cmd += ["--only", *only]
    if from_ep:
        cmd += ["--from", from_ep]
    if force:
        cmd += ["--force"]

    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"
    env["PYTHONUNBUFFERED"] = "1"

    os.makedirs(config.LOG_DIR, exist_ok=True)
    logf = open(_log_path(slug), "a", buffering=1)
    proc = subprocess.Popen(
        cmd, cwd=config.ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(os.path.join(sdir, ".run.pid"), "w") as f:
        f.write(str(proc.pid))
    # 清掉上一次的完成标记，避免前端误判
    return proc.pid


def log_tail(slug: str, lines: int = 40) -> str:
    path = _log_path(slug)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except Exception:
        return ""


def run_images(slug: str, ep_id: str, sections: int = 12, zoom: float = 0.06) -> int:
    """在后台给某一集生成「配图版」（0 积分）。"""
    sdir = series_dir(slug)
    state = _read(os.path.join(sdir, ".state.json"), {}) or {}
    st = state.get(ep_id) or {}
    if st.get("status") != "done":
        raise ValueError(f"{ep_id} 还没生成完成，无法配图")
    video = st.get("video") or ""
    if not (video and os.path.isfile(video)):
        raise ValueError(f"{ep_id} 成片不存在")
    out = os.path.splitext(video)[0] + "_配图.mp4"
    if os.path.isfile(out) and os.path.getsize(out) > 1024 * 1024:
        raise ValueError("配图版已存在，如需重做请先删除")

    log = os.path.join(config.LOG_DIR, f"series-{slug}-images.log")
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"
    env["PYTHONUNBUFFERED"] = "1"

    os.makedirs(config.LOG_DIR, exist_ok=True)
    logf = open(log, "a", buffering=1)
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(config.ROOT, "scripts", "add_images.py"),
         "--series", f"series/{slug}", "--ep", ep_id,
         "--sections", str(sections), "--zoom", str(zoom)],
        cwd=config.ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc.pid
