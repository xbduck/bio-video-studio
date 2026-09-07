"""项目数据模型、读写与任务队列。

项目以 JSON 文件存储，目录结构：

    projects/<slug>/
        project.json      # 元数据 + 分镜
        images/           # 分镜图片
        videos/           # 分镜视频
        audio/            # 旁白音频
        subs/             # 字幕
        output/           # 最终成片
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from typing import Any

from . import config

# --------------------------------------------------------------------------
# 基础读写工具：原子写，避免读到半截文件
# --------------------------------------------------------------------------


def _atomic_write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


# --------------------------------------------------------------------------
# slug / 索引
# --------------------------------------------------------------------------

_ILLEGAL = r'[\\/:*?"<>|\r\n\t]'


def make_slug(name: str) -> str:
    """把人物名转成安全的目录名（保留中日韩文字）。"""
    s = re.sub(_ILLEGAL, "", (name or "").strip())
    s = s.replace(" ", "_")
    s = s.strip(". ")
    return s[:60] or "untitled"


def load_index() -> dict[str, str]:
    """返回 {project_id: slug}。"""
    return _read_json(config.INDEX_FILE, {}) or {}


def save_index(index: dict[str, str]) -> None:
    _atomic_write(config.INDEX_FILE, index)


def resolve_dir(project_id: str) -> str | None:
    index = load_index()
    slug = index.get(project_id)
    if not slug:
        return None
    d = os.path.join(config.PROJECTS_DIR, slug)
    return d if os.path.isdir(d) else None


def register(project_id: str, slug: str) -> None:
    index = load_index()
    index[project_id] = slug
    save_index(index)


# --------------------------------------------------------------------------
# 项目生命周期
# --------------------------------------------------------------------------


def new_project_id() -> str:
    return uuid.uuid4().hex[:8]


def create_project(person: str, title: str | None = None) -> dict:
    """创建空项目。若同名项目已存在则直接返回它。"""
    index = load_index()
    slug = make_slug(person)

    # 同名人物复用同一目录，避免重复生成
    for pid, existing_slug in index.items():
        d = os.path.join(config.PROJECTS_DIR, existing_slug)
        meta = _read_json(os.path.join(d, "project.json"), None)
        if meta and meta.get("person") == person:
            return meta

    project_id = new_project_id()
    # 目录名冲突时加后缀
    final_slug = slug
    n = 2
    while os.path.exists(os.path.join(config.PROJECTS_DIR, final_slug)):
        final_slug = f"{slug}_{n}"
        n += 1

    project = {
        "id": project_id,
        "slug": final_slug,
        "person": person,
        "title": title or f"{person}·一生",
        "summary": "",
        "style": config.DEFAULT_STYLE,
        "voice": config.DEFAULT_VOICE,
        "rate": config.DEFAULT_RATE,
        "bgm_path": "",
        "bgm_volume": 0.18,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenes": [],
    }

    pdir = os.path.join(config.PROJECTS_DIR, final_slug)
    for sub in ("images", "videos", "audio", "subs", "output"):
        os.makedirs(os.path.join(pdir, sub), exist_ok=True)
    _atomic_write(os.path.join(pdir, "project.json"), project)

    register(project_id, final_slug)
    return project


def save_project(project: dict) -> dict:
    d = resolve_dir(project["id"])
    if not d:
        raise FileNotFoundError(f"未知项目: {project['id']}")
    project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _atomic_write(os.path.join(d, "project.json"), project)
    return project


def load_project(project_id: str) -> dict | None:
    d = resolve_dir(project_id)
    if not d:
        return None
    return _read_json(os.path.join(d, "project.json"), None)


def list_projects() -> list[dict]:
    out = []
    for pid in load_index():
        d = resolve_dir(pid)
        if not d:
            continue
        p = _read_json(os.path.join(d, "project.json"), None)
        if p:
            out.append(p)
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


def delete_project(project_id: str) -> bool:
    index = load_index()
    slug = index.pop(project_id, None)
    if not slug:
        return False
    save_index(index)
    d = os.path.join(config.PROJECTS_DIR, slug)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    return True


def project_dir(project_id: str) -> str:
    d = resolve_dir(project_id)
    if not d:
        raise FileNotFoundError(f"未知项目: {project_id}")
    return d


def rel(path: str) -> str:
    """把绝对路径转成相对 ROOT 的 URL 路径（用于静态访问）。"""
    if not path:
        return ""
    p = os.path.abspath(path)
    r = os.path.abspath(config.ROOT)
    if p.startswith(r):
        return p[len(r):].replace("\\", "/").lstrip("/")
    return path.replace("\\", "/")


# --------------------------------------------------------------------------
# 任务队列：网页写入 -> WorkBuddy（我）消费
# --------------------------------------------------------------------------


def enqueue(task_type: str, project_id: str, payload: dict | None = None) -> dict:
    task = {
        "task_id": uuid.uuid4().hex[:12],
        "type": task_type,           # script | images | videos
        "project_id": project_id,
        "payload": payload or {},
        "status": "pending",         # pending | running | done | failed
        "message": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(config.TASKS_DIR, exist_ok=True)
    with open(config.QUEUE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")
    return task


def _load_tasks() -> list[dict]:
    if not os.path.exists(config.QUEUE_FILE):
        return []
    tasks = []
    with open(config.QUEUE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return tasks


def _dump_tasks(tasks: list[dict]) -> None:
    with open(config.QUEUE_FILE, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def pending_tasks(task_type: str | None = None) -> list[dict]:
    ts = [t for t in _load_tasks() if t["status"] == "pending"]
    if task_type:
        ts = [t for t in ts if t["type"] == task_type]
    return ts


def all_tasks(limit: int = 50) -> list[dict]:
    ts = _load_tasks()
    ts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return ts[:limit]


def update_task(task_id: str, status: str, message: str = "") -> None:
    tasks = _load_tasks()
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = status
            t["message"] = message
            t["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            break
    _dump_tasks(tasks)


def clear_finished_tasks() -> int:
    tasks = _load_tasks()
    kept = [t for t in tasks if t["status"] in ("pending", "running")]
    _dump_tasks(kept)
    return len(tasks) - len(kept)
