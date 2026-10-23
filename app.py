"""人物生平短视频工厂 —— 本地 Web 服务。

流程：
    输入人物名 -> (WorkBuddy 写剧本) -> (WorkBuddy 批量生图) -> (WorkBuddy 批量生成视频)
    -> 本地配音 + 字幕 + 合成 -> 成片 MP4
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import threading
import webbrowser
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import compose, config, culture, jobs, render, store, tts, video_plan
from core import series as series_factory

app = FastAPI(title="生平短片工厂", version="1.0")


# --------------------------------------------------------------------------
# 项目
# --------------------------------------------------------------------------

class CreateProjectIn(BaseModel):
    person: str
    title: str | None = None
    aspect: str | None = None      # portrait 竖屏 9:16（默认） | landscape 横屏 16:9


class ProjectPatchIn(BaseModel):
    title: str | None = None
    summary: str | None = None
    style: str | None = None
    voice: str | None = None       # 空字符串 = 不使用旁白（沿用视频自带音色）
    rate: str | None = None
    aspect: str | None = None      # portrait | landscape
    crop_bottom: int | None = None  # 先裁掉画面底部 N 像素（去水印条），0 = 不裁
    burn_subtitles: bool | None = None  # False = 不烧录自配字幕（视频自带/不要字幕）
    bgm_volume: float | None = None


class ScenesIn(BaseModel):
    scenes: list[dict]


class GenerateIn(BaseModel):
    indices: list[int] | None = None   # 空表示全部分镜
    style: str | None = None
    route: str | None = None   # 生视频路线：hf 本地渲染(0积分) | ai 视频大模型 | mix 混合


class AssetIn(BaseModel):
    index: int
    filename: str
    data: str          # base64
    kind: str = "image"  # image | video


class FrameIn(BaseModel):
    at: float | None = None    # 指定秒数抽帧
    ratio: float | None = None  # 或按视频时长百分比（默认 0.4）
    force: bool = False        # 已有图时是否覆盖
    indexes: list[int] | None = None  # 批量：只处理这些镜号，空=全部


@app.get("/api/projects")
def api_list_projects():
    projects = store.list_projects()
    return [
        {
            "id": p["id"],
            "person": p["person"],
            "title": p.get("title", ""),
            "updated_at": p.get("updated_at", ""),
            "scenes": len(p.get("scenes", [])),
            "images": sum(1 for s in p.get("scenes", []) if s.get("image_path")),
            "videos": sum(1 for s in p.get("scenes", []) if s.get("video_path")),
            "audio": sum(1 for s in p.get("scenes", []) if s.get("audio_path")),
            "output_url": p.get("output_url", ""),
            "cover_url": p.get("cover_url", ""),
        }
        for p in projects
    ]


@app.post("/api/projects")
def api_create_project(body: CreateProjectIn):
    person = (body.person or "").strip()
    if not person:
        raise HTTPException(400, "人物名称不能为空")
    p = store.create_project(person, body.title, aspect=body.aspect)
    store.enqueue("script", p["id"], {"person": person})
    return {"id": p["id"], "person": p["person"], "slug": p["slug"],
            "aspect": p.get("aspect", "portrait")}


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


@app.patch("/api/projects/{project_id}")
def api_patch_project(project_id: str, body: ProjectPatchIn):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    patch = body.dict(exclude_none=True)
    if "aspect" in patch:
        patch["aspect"] = config.normalize_aspect(patch["aspect"])
    if "crop_bottom" in patch:
        patch["crop_bottom"] = max(0, min(int(patch["crop_bottom"]), 400))

    old_voice, old_rate = (p.get("voice") or ""), (p.get("rate") or "")
    for k, v in patch.items():
        p[k] = v
    store.save_project(p)

    # 音色/语速变了 → 旧配音全部作废重配，否则一条片子里会混两种音色
    dropped = 0
    if (p.get("voice") or "") != old_voice or (p.get("rate") or "") != old_rate:
        dropped = _drop_audio(p, project_id)
    return {"ok": True, "aspect": p.get("aspect", "portrait"), "audio_dropped": dropped}


def _drop_audio(project: dict, project_id: str) -> int:
    """清空项目的旁白音频（音色/语速变更后调用），返回删除数量。"""
    pdir = store.project_dir(project_id)
    adir = os.path.join(pdir, "audio")
    n = 0
    if os.path.isdir(adir):
        for f in os.listdir(adir):
            if f.lower().endswith((".mp3", ".wav", ".m4a")):
                try:
                    os.remove(os.path.join(adir, f))
                    n += 1
                except OSError:
                    pass
    for s in project.get("scenes", []):
        s["audio_path"] = ""
    store.save_project(project)
    return n


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: str):
    return {"ok": store.delete_project(project_id)}


@app.put("/api/projects/{project_id}/scenes")
def api_save_scenes(project_id: str, body: ScenesIn):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    p["scenes"] = body.scenes
    store.save_project(p)
    return {"ok": True, "count": len(body.scenes)}


@app.post("/api/projects/{project_id}/reset-scene/{index}")
def api_reset_scene(project_id: str, index: int, kind: str = "image"):
    """清空某个分镜的素材，允许重新生成。"""
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    for s in p["scenes"]:
        if s["index"] == index:
            s[f"{kind}_path"] = ""
            s[f"{kind}_status"] = "pending"
            break
    store.save_project(p)
    return {"ok": True}


# --------------------------------------------------------------------------
# 从分镜视频抽帧，补成「分镜图」（视频由外部工具生成、没有配图时用）
# --------------------------------------------------------------------------

def _grab_frame(pdir: str, scene: dict,
                at: float | None = None,
                ratio: float | None = None) -> dict:
    """从某个分镜的视频里抽一帧写成 images/NN.jpg，并回写到分镜。"""
    idx = scene["index"]
    vid = (scene.get("video_path") or "").strip()
    if not vid:
        return {"index": idx, "ok": False, "error": "该分镜还没有视频"}
    vabs = os.path.join(pdir, vid)
    if not os.path.exists(vabs):
        return {"index": idx, "ok": False, "error": f"视频文件找不到：{vid}"}

    # 用 jpg：视频截帧体积约为 png 的 1/6，且只作预览/首帧参考，不参与成片。
    # 刻意不删旧图（可能是用户手动上传的参考图），只把 image_path 指过来。
    rel = f"images/{idx:02d}.jpg"
    abs_out = os.path.join(pdir, rel)
    ok, err = compose.extract_frame(
        vabs, abs_out,
        at=at,
        ratio=0.4 if ratio is None else float(ratio),
    )
    if not ok:
        return {"index": idx, "ok": False, "error": err or "抽帧失败"}

    scene["image_path"] = rel
    scene["image_status"] = "done"
    scene["image_source"] = "video-frame"
    return {
        "index": idx, "ok": True,
        "url": "/" + store.rel(abs_out),
        "at": round(float(at), 2) if at is not None else None,
    }


@app.post("/api/projects/{project_id}/scenes/{index}/frame")
def api_scene_frame(project_id: str, index: int, body: FrameIn | None = None):
    """单镜：从该镜视频抽一帧作为分镜图。"""
    body = body or FrameIn()
    pdir = store.project_dir(project_id)
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    scene = next((s for s in p["scenes"] if s["index"] == index), None)
    if not scene:
        raise HTTPException(404, f"分镜 {index} 不存在")
    if scene.get("image_path") and not body.force:
        return {"ok": False, "skipped": True, "reason": "该分镜已有图片（force=true 可覆盖）",
                "index": index}

    r = _grab_frame(pdir, scene, at=body.at, ratio=body.ratio)
    if r["ok"]:
        store.save_project(p)
    return r


@app.post("/api/projects/{project_id}/frames")
def api_frames_from_videos(project_id: str, body: FrameIn | None = None):
    """批量：给所有「有视频但没图」的分镜抽帧补图。"""
    body = body or FrameIn()
    pdir = store.project_dir(project_id)
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    want = set(body.indexes or [])
    done, skipped, failed = [], [], []
    for s in p["scenes"]:
        if want and s["index"] not in want:
            continue
        if not (s.get("video_path") or "").strip():
            continue
        if s.get("image_path") and not body.force:
            skipped.append(s["index"])
            continue
        r = _grab_frame(pdir, s, at=body.at, ratio=body.ratio)
        (done if r["ok"] else failed).append(r)

    if done:
        store.save_project(p)
    return {
        "ok": True,
        "grabed": [d["index"] for d in done],
        "skipped": skipped,
        "failed": failed,
        "count": len(done),
    }


# --------------------------------------------------------------------------
# 素材上传（手动替换图片 / 视频 / BGM）
# --------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/asset")
def api_upload_asset(project_id: str, body: AssetIn):
    pdir = store.project_dir(project_id)
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    ext = os.path.splitext(body.filename)[1].lower() or ".png"
    if body.kind == "video":
        sub, key = "videos", "video"
        ext = ext if ext in (".mp4", ".mov", ".webm", ".mkv") else ".mp4"
    elif body.kind == "bgm":
        sub, key = "", "bgm"
        ext = ext if ext in (".mp3", ".wav", ".m4a", ".aac") else ".mp3"
    else:
        sub, key = "images", "image"
        ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp") else ".png"

    os.makedirs(os.path.join(pdir, sub) if sub else pdir, exist_ok=True)
    matched = None
    if body.kind == "bgm":
        rel_path = f"bgm{ext}"
        abs_path = os.path.join(pdir, rel_path)
        p["bgm_path"] = rel_path
    else:
        rel_path = f"{sub}/{body.index:02d}{ext}"
        abs_path = os.path.join(pdir, sub, f"{body.index:02d}{ext}")
        for s in p["scenes"]:
            if s["index"] == body.index:
                s[f"{key}_path"] = rel_path.replace("\\", "/")
                s[f"{key}_status"] = "done"
                matched = s
                break

    data = base64.b64decode(body.data.split(",")[-1])
    with open(abs_path, "wb") as f:
        f.write(data)

    # 上传视频时，若该分镜还没有分镜图，自动从刚上传的视频抽一帧填充
    # （外部工具生成的视频本就没有配图，省去事后手动「从视频截帧」）。
    # 已有图片（含手动上传的参考图）不覆盖，需刷新可手动点「从视频截帧」。
    frame_auto = None
    if matched is not None and body.kind == "video" and not matched.get("image_path"):
        frame_auto = _grab_frame(pdir, matched, at=None, ratio=0.4)

    store.save_project(p)
    return {"ok": True,
            "url": "/" + store.rel(abs_path),
            "frame_auto": frame_auto}


# --------------------------------------------------------------------------
# 任务队列（网页下单 -> WorkBuddy 执行）
# --------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/request/script")
def api_request_script(project_id: str):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    t = store.enqueue("script", project_id, {"person": p["person"]})
    return t


@app.post("/api/projects/{project_id}/request/images")
def api_request_images(project_id: str, body: GenerateIn):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    if body.style:
        p["style"] = body.style
        store.save_project(p)
    t = store.enqueue("images", project_id, {"indices": body.indices or []})
    return t


@app.post("/api/projects/{project_id}/request/videos")
def api_request_videos(project_id: str, body: GenerateIn):
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    route = (body.route or "hf").strip().lower()
    if route not in ("hf", "ai", "mix"):
        route = "hf"
    t = store.enqueue("videos", project_id, {"indices": body.indices or [], "route": route})
    return t


@app.get("/api/tasks")
def api_tasks(limit: int = 30):
    return store.all_tasks(limit)


@app.get("/api/projects/{project_id}/video-plan")
def api_video_plan(project_id: str, route: str = "hf"):
    """生视频路线规划：返回哪些分镜需要视频大模型、预估积分。

    前端提示卡与 studio.py 命令行共用，保证挑镜规则一致。
    """
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    route = (route or "hf").strip().lower()
    if route not in ("hf", "ai", "mix"):
        route = "hf"
    scenes = [s for s in p.get("scenes", []) if s.get("image_path") and not s.get("video_path")]
    return video_plan.plan_videos(scenes, route)


# --------------------------------------------------------------------------
# 企业文化专栏：角色档案 / 剧本导出 / 交付自检
# --------------------------------------------------------------------------

@app.get("/api/culture/characters")
def api_culture_characters(project: str | None = None):
    """解析 dingding-city/角色圣经.md → 角色卡 + 视觉体系 + 色调 + 产线红线。

    传 project（项目 id 或 slug）时，额外返回「本集出场」标记和本集定妆照。
    """
    p = store.load_project(project) if project else None
    return culture.load_characters(p)


@app.get("/api/culture/avatar/{name}")
def api_culture_avatar(name: str, project: str | None = None):
    """返回角色头像：本集定妆照（avatars/<slug>/）优先，回落到系列通用图。"""
    p = store.load_project(project) if project else None
    path = culture.avatar_path(name, p)
    if not path:
        raise HTTPException(404, "暂无该角色照片")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/projects/{project_id}/delivery-check")
def api_delivery_check(project_id: str):
    """按母版硬约束逐条自检，返回 pass / warn / fail 与问题镜号。"""
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return culture.check_delivery(p)


_EXPORTERS = {
    "md": ("text/markdown; charset=utf-8", ".md", "剧本"),
    "srt": ("application/x-subrip; charset=utf-8", ".srt", "字幕"),
    "csv": ("text/csv; charset=utf-8", ".csv", "剪辑单"),
}


@app.get("/api/projects/{project_id}/export/{kind}")
def api_export(project_id: str, kind: str):
    """导出剧本 Markdown / 字幕 SRT / 剪辑单 CSV（浏览器直接下载）。"""
    meta = _EXPORTERS.get(kind)
    if not meta:
        raise HTTPException(400, f"不支持的导出类型：{kind}")
    p = store.load_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    media_type, ext, suffix = meta
    if kind == "md":
        content = culture.build_script_md(p)
    elif kind == "srt":
        content = culture.build_srt(p)
    else:
        content = culture.build_shotlist_csv(p)

    base = (p.get("title") or p.get("person") or "script").replace("/", "-")
    fname = f"{base}_{suffix}{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition":
                f"attachment; filename=\"export{ext}\"; filename*=UTF-8''{quote(fname)}"
        },
    )


# --------------------------------------------------------------------------
# 本地执行：配音 / 合成
# --------------------------------------------------------------------------

@app.post("/api/projects/{project_id}/tts")
def api_tts(project_id: str):
    job_id = render.start_tts(project_id)
    return {"job_id": job_id}


@app.post("/api/projects/{project_id}/render")
def api_render(project_id: str, with_title: bool = True, with_bgm: bool = True):
    job_id = render.start_render(project_id, with_title, with_bgm)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id:path}")
def api_job(job_id: str):
    st = jobs.get(job_id)
    if not st:
        raise HTTPException(404, "任务不存在")
    return st


@app.get("/api/voices")
def api_voices():
    return [{"id": v, "name": n} for v, n in tts.VOICES]


class PathIn(BaseModel):
    path: str


@app.post("/api/open-folder")
def api_open_folder(body: PathIn):
    target = os.path.abspath(os.path.join(config.ROOT, body.path))
    root = os.path.abspath(config.ROOT)
    if not target.startswith(root):
        raise HTTPException(400, "路径越界")
    if not os.path.isdir(target):
        raise HTTPException(404, "目录不存在")
    # os.startfile 仅存在于 Windows，macOS / Linux 需走 open / xdg-open
    try:
        import platform
        system = platform.system()
        if system == "Windows":
            os.startfile(target)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", target], check=False)
        else:
            subprocess.run(["xdg-open", target], check=False)
    except Exception as e:
        raise HTTPException(500, f"无法打开: {e}")
    return {"ok": True}


@app.get("/api/health")
def api_health():
    try:
        exe = compose.ffmpeg()
        ffmpeg_ok = os.path.exists(exe)
    except Exception:
        exe, ffmpeg_ok = "", False
    return {
        "ok": True,
        "ffmpeg": ffmpeg_ok,
        "ffmpeg_path": exe,
        "pending_tasks": len(store.pending_tasks()),
    }


# --------------------------------------------------------------------------
# 系列工厂（多集长音频）
# --------------------------------------------------------------------------

class SeriesRunIn(BaseModel):
    only: list[str] | None = None
    from_ep: str | None = None
    force: bool = False


class SeriesCreateIn(BaseModel):
    name: str
    series: str | None = "睡觉听历史"
    topic: str | None = ""
    voice: str | None = None
    rate: str | None = None


class SeriesImageIn(BaseModel):
    ep: str
    sections: int = 12
    zoom: float = 0.06


@app.get("/api/series")
def api_series_list():
    return series_factory.list_series()


@app.post("/api/series")
def api_series_create(body: SeriesCreateIn):
    try:
        return series_factory.create_series(
            body.name,
            series=body.series or "睡觉听历史",
            topic=body.topic or "",
            voice=body.voice or "zh-CN-YunjianNeural",
            rate=body.rate or "-50%",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/series/{slug}/run")
def api_series_run(slug: str, body: SeriesRunIn | None = None):
    body = body or SeriesRunIn()
    try:
        pid = series_factory.run_series(
            slug, only=body.only, from_ep=body.from_ep, force=body.force)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "pid": pid}


@app.get("/api/series/{slug}/log")
def api_series_log(slug: str, lines: int = 40):
    return {"log": series_factory.log_tail(slug, lines)}


@app.post("/api/series/{slug}/images")
def api_series_images(slug: str, body: SeriesImageIn):
    try:
        pid = series_factory.run_images(slug, body.ep, sections=body.sections, zoom=body.zoom)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "pid": pid}


@app.get("/series")
def series_page():
    return FileResponse(os.path.join(config.WEB_DIR, "series.html"))


# --------------------------------------------------------------------------
# 静态资源
# --------------------------------------------------------------------------

app.mount("/projects", StaticFiles(directory=config.PROJECTS_DIR), name="projects")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")


@app.middleware("http")
async def no_cache_project_assets(request, call_next):
    """项目素材（图/视频/音频）不缓存：文件被替换后浏览器必须重新拉取，
    否则同名文件更新后前端仍播放旧版本。"""
    resp = await call_next(request)
    if request.url.path.startswith("/projects/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def main():
    port = int(os.environ.get("STUDIO_PORT", "7799"))  # 7788 已被其他项目占用
    url = f"http://127.0.0.1:{port}"
    print(f"\n  生平短片工厂已启动: {url}\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
