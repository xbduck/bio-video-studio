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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import compose, config, jobs, render, store, tts

app = FastAPI(title="生平短片工厂", version="1.0")


# --------------------------------------------------------------------------
# 项目
# --------------------------------------------------------------------------

class CreateProjectIn(BaseModel):
    person: str
    title: str | None = None


class ProjectPatchIn(BaseModel):
    title: str | None = None
    summary: str | None = None
    style: str | None = None
    voice: str | None = None
    rate: str | None = None
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
    p = store.create_project(person, body.title)
    store.enqueue("script", p["id"], {"person": person})
    return {"id": p["id"], "person": p["person"], "slug": p["slug"]}


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
    for k, v in body.dict(exclude_none=True).items():
        p[k] = v
    store.save_project(p)
    return {"ok": True}


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
                break

    data = base64.b64decode(body.data.split(",")[-1])
    with open(abs_path, "wb") as f:
        f.write(data)

    store.save_project(p)
    return {"ok": True, "url": "/" + store.rel(abs_path)}


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
# 静态资源
# --------------------------------------------------------------------------

app.mount("/projects", StaticFiles(directory=config.PROJECTS_DIR), name="projects")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")


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
