#!/usr/bin/env python3
"""等音频批次跑完后，给系列里所有已完成的集生成「配图版」（0 积分）。

用法：
    <PY> scripts/image_pass.py --series series/ming-emperors
    <PY> scripts/image_pass.py --series series/ming-emperors --no-wait   # 不等批次，立刻开始

会跳过：
- 还没生成的集
- 已经存在 `<标题>_配图.mp4` 的集
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def batch_running(slug: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", f"run_series.py series/{slug}"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="批量生成配图版")
    ap.add_argument("--series", required=True)
    ap.add_argument("--sections", type=int, default=12)
    ap.add_argument("--zoom", type=float, default=0.06)
    ap.add_argument("--no-wait", action="store_true", help="不等音频批次")
    args = ap.parse_args()

    series_dir = args.series if os.path.isabs(args.series) else os.path.join(ROOT, args.series)
    slug = os.path.basename(series_dir.rstrip("/"))

    if not args.no_wait:
        while batch_running(slug):
            print("[wait] 音频批次还在跑，30 秒后重试……", flush=True)
            time.sleep(30)

    manifest = read_json(os.path.join(series_dir, "manifest.json"))
    if not manifest:
        sys.exit(f"找不到 manifest: {series_dir}")
    state = read_json(os.path.join(series_dir, ".state.json"), {}) or {}

    for ep in manifest.get("episodes", []):
        eid = ep.get("id")
        st = state.get(eid) or {}
        if st.get("status") != "done":
            print(f"[skip] {eid}：还没生成完成（{st.get('status')}）", flush=True)
            continue
        video = st.get("video") or ""
        if not video or not os.path.isfile(video):
            print(f"[skip] {eid}：成片不存在", flush=True)
            continue
        out = os.path.join(os.path.dirname(video),
                           os.path.splitext(os.path.basename(video))[0] + "_配图.mp4")
        if os.path.isfile(out) and os.path.getsize(out) > 1024 * 1024:
            print(f"[skip] {eid}：配图版已存在", flush=True)
            continue

        print(f"[run ] {eid} 开始生成配图版……", flush=True)
        cmd = [sys.executable, os.path.join(ROOT, "scripts", "add_images.py"),
               "--series", args.series, "--ep", eid,
               "--sections", str(args.sections), "--zoom", str(args.zoom)]
        r = subprocess.run(cmd, cwd=ROOT)
        print(f"[done] {eid} rc={r.returncode}", flush=True)
        time.sleep(5)

    print("[all ] 配图版批处理结束", flush=True)


if __name__ == "__main__":
    main()
