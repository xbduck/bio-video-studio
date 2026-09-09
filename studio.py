"""命令行工具 —— 给 WorkBuddy（我）驱动流水线用，也方便无人值守批处理。

常用：
    python studio.py pending                  列出待处理任务
    python studio.py claim <task_id>          领取任务（标记 running）
    python studio.py set-script <pid> -f s.json   写入剧本
    python studio.py attach <pid> -i 1 --image X.png
    python studio.py attach <pid> -i 1 --video Y.mp4
    python studio.py done <task_id>            完成任务
    python studio.py status <pid>              查看进度
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import compose, store  # noqa: E402


def _print(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_pending(args):
    ts = store.pending_tasks(args.type)
    out = []
    for t in ts:
        p = store.load_project(t["project_id"])
        if not p:
            # 项目已被删除，把孤儿任务标记为 failed，避免阻塞
            store.update_task(t["task_id"], "failed", "项目已删除")
            continue
        item = dict(t)
        item["person"] = p["person"]
        try:
            item["project_dir"] = store.project_dir(t["project_id"])
        except FileNotFoundError:
            store.update_task(t["task_id"], "failed", "项目目录不存在")
            continue
        if t["type"] == "images":
            idxs = t["payload"].get("indices") or []
            item["targets"] = [
                {"index": s["index"], "title": s.get("title", ""),
                 "image_prompt": s.get("image_prompt", "")}
                for s in p.get("scenes", [])
                if (not idxs or s["index"] in idxs) and not s.get("image_path")
            ] if p else []
        elif t["type"] == "videos":
            idxs = t["payload"].get("indices") or []
            item["route"] = (t["payload"].get("route") or "hf").lower()
            item["targets"] = [
                {"index": s["index"], "title": s.get("title", ""),
                 "video_prompt": s.get("video_prompt", ""),
                 "image_file": os.path.join(item["project_dir"],
                                            s["image_path"]) if s.get("image_path") else ""}
                for s in p.get("scenes", [])
                if (not idxs or s["index"] in idxs) and s.get("image_path") and not s.get("video_path")
            ] if p else []
        out.append(item)
    _print(out)


def cmd_claim(args):
    store.update_task(args.task_id, "running")
    for t in store.all_tasks(500):
        if t["task_id"] == args.task_id:
            _print(t)
            return
    print(json.dumps({"error": "task not found"}, ensure_ascii=False))


def cmd_task_done(args):
    store.update_task(args.task_id, "done", args.message or "")
    print("ok")


def cmd_task_fail(args):
    store.update_task(args.task_id, "failed", args.message or "")
    print("ok")


def cmd_list(args):
    _print([{k: v for k, v in p.items() if k != "scenes"} | {"scenes": len(p.get("scenes", []))}
            for p in store.list_projects()])


def cmd_scaffold(args):
    p = store.create_project(args.person, args.title)
    _print({"id": p["id"], "slug": p["slug"], "dir": store.project_dir(p["id"])})


def cmd_set_script(args):
    p = store.load_project(args.project_id)
    if not p:
        print(json.dumps({"error": "project not found"}, ensure_ascii=False))
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data["scenes"] if isinstance(data, dict) else data
    norm = []
    for i, s in enumerate(scenes, 1):
        norm.append({
            "index": int(s.get("index", i)),
            "year": str(s.get("year", "")),
            "age": s.get("age", ""),
            "title": s.get("title", ""),
            "narration": s.get("narration", ""),
            "image_prompt": s.get("image_prompt", ""),
            "video_prompt": s.get("video_prompt", ""),
            "image_path": "", "video_path": "", "audio_path": "",
            "image_status": "pending", "video_status": "pending",
        })
    if isinstance(data, dict):
        p["title"] = data.get("title") or p["title"]
        p["summary"] = data.get("summary") or p["summary"]
        p["style"] = data.get("style") or p["style"]
        if data.get("voice"):
            p["voice"] = data["voice"]
    p["scenes"] = norm
    store.save_project(p)

    # 自动把对应的 script 任务标记完成
    for t in store.pending_tasks("script"):
        if t["project_id"] == args.project_id:
            store.update_task(t["task_id"], "done", f"已生成 {len(norm)} 个分镜")

    _print({"ok": True, "project_id": p["id"], "scenes": len(norm),
            "dir": store.project_dir(p["id"])})


def _resolve(pdir: str, sub: str, hint: str, exts: tuple) -> str:
    """hint 是完整路径则直接返回；否则在 sub 目录下按关键词模糊匹配最新文件。"""
    if os.path.isabs(hint) and os.path.exists(hint):
        return hint
    cand = os.path.join(pdir, hint)
    if os.path.exists(cand):
        return cand

    folder = os.path.join(pdir, sub) if sub else pdir
    if not os.path.isdir(folder):
        return ""
    keys = [k for k in hint.replace("，", ",").split(",") if k.strip()] or [hint]
    matches = []
    for fn in os.listdir(folder):
        low = fn.lower()
        if not low.endswith(exts):
            continue
        if all(k.strip()[:6] in fn for k in keys):
            matches.append(os.path.join(folder, fn))
    if not matches:
        return ""
    matches.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return matches[0]


def cmd_attach(args):
    pdir = store.project_dir(args.project_id)
    p = store.load_project(args.project_id)
    if not p:
        print(json.dumps({"error": "project not found"}, ensure_ascii=False))
        sys.exit(1)

    if args.bgm:
        ext = os.path.splitext(args.bgm)[1] or ".mp3"
        dst = os.path.join(pdir, f"bgm{ext}")
        shutil.copy(args.bgm, dst)
        p["bgm_path"] = f"bgm{ext}"
        store.save_project(p)
        _print({"ok": True, "bgm": dst})
        return

    if not args.index:
        print(json.dumps({"error": "--index 必填"}, ensure_ascii=False))
        sys.exit(1)

    scene = next((s for s in p["scenes"] if s["index"] == args.index), None)
    if not scene:
        print(json.dumps({"error": f"分镜 {args.index} 不存在"}, ensure_ascii=False))
        sys.exit(1)

    if args.image:
        src = _resolve(pdir, "images", args.image, (".png", ".jpg", ".jpeg", ".webp"))
        if not src:
            print(json.dumps({"error": f"找不到图片: {args.image}"}, ensure_ascii=False))
            sys.exit(1)
        ext = os.path.splitext(src)[1] or ".png"
        dst = os.path.join(pdir, "images", f"{args.index:02d}{ext}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.move(src, dst)
        scene["image_path"] = f"images/{args.index:02d}{ext}"
        scene["image_status"] = "done"

    if args.video:
        src = _resolve(pdir, "videos", args.video, (".mp4", ".mov", ".webm", ".mkv"))
        if not src:
            print(json.dumps({"error": f"找不到视频: {args.video}"}, ensure_ascii=False))
            sys.exit(1)
        ext = os.path.splitext(src)[1] or ".mp4"
        dst = os.path.join(pdir, "videos", f"{args.index:02d}{ext}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.move(src, dst)
        scene["video_path"] = f"videos/{args.index:02d}{ext}"
        scene["video_status"] = "done"

    store.save_project(p)
    _print({"ok": True, "index": args.index,
            "image": scene.get("image_path"), "video": scene.get("video_path")})


def cmd_status(args):
    p = store.load_project(args.project_id)
    if not p:
        print(json.dumps({"error": "project not found"}, ensure_ascii=False))
        sys.exit(1)
    rows = []
    for s in p.get("scenes", []):
        rows.append({
            "index": s["index"], "year": s.get("year", ""), "title": s.get("title", ""),
            "image": bool(s.get("image_path")), "video": bool(s.get("video_path")),
            "audio": bool(s.get("audio_path")),
        })
    _print({
        "id": p["id"], "person": p["person"], "title": p.get("title"),
        "dir": store.project_dir(p["id"]),
        "output": p.get("output_path", ""),
        "scenes": rows,
    })


def cmd_render(args):
    from core import render as _r
    result = _r.render_project(args.project_id, not args.no_title, not args.no_bgm)
    _print(result)


def cmd_probe(args):
    _print({"duration": compose.probe_duration(args.file)})


def main():
    ap = argparse.ArgumentParser(description="生平短片工厂 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pending", help="列出待处理任务")
    p.add_argument("--type", choices=["script", "images", "videos"])
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("claim")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("done")
    p.add_argument("task_id")
    p.add_argument("message", nargs="?", default="")
    p.set_defaults(func=cmd_task_done)

    p = sub.add_parser("fail")
    p.add_argument("task_id")
    p.add_argument("message", nargs="?", default="")
    p.set_defaults(func=cmd_task_fail)

    p = sub.add_parser("list")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("scaffold", help="仅创建项目")
    p.add_argument("person")
    p.add_argument("--title")
    p.set_defaults(func=cmd_scaffold)

    p = sub.add_parser("set-script")
    p.add_argument("project_id")
    p.add_argument("-f", "--file", required=True)
    p.set_defaults(func=cmd_set_script)

    p = sub.add_parser("attach")
    p.add_argument("project_id")
    p.add_argument("-i", "--index", type=int)
    p.add_argument("--image")
    p.add_argument("--video")
    p.add_argument("--bgm")
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("status")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("render")
    p.add_argument("project_id")
    p.add_argument("--no-title", action="store_true")
    p.add_argument("--no-bgm", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("probe")
    p.add_argument("file")
    p.set_defaults(func=cmd_probe)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
