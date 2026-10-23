#!/usr/bin/env python3
"""通用系列批量生成器（长音频系列工厂）。

目录约定（每个系列一个目录，互不干扰）：
    series/<slug>/manifest.json   系列配置：默认音色/语速/BGM + 集数清单
    series/<slug>/ep01.json ...   每集脚本（title / episode / subject / paragraphs）

用法：
    <PY> scripts/run_series.py series/ming-emperors --estimate   # 只估算字数与时长
    <PY> scripts/run_series.py series/ming-emperors               # 全量串行生成（可断点续跑）
    <PY> scripts/run_series.py series/ming-emperors --only EP.02 EP.04
    <PY> scripts/run_series.py series/ming-emperors --from EP.03
    <PY> scripts/run_series.py series/ming-emperors --force       # 已有成片也重跑

设计要点：
- 串行执行（edge-tts 并发会 429），集间默认停 5 秒。
- 每集状态写 series/<slug>/.state.json；已完成的集默认跳过。
- 生成器本身对音频分块做了缓存，重跑只会补没合成的块。
- 字数/时长按 +0% 语速 272 字/分钟线性折算（实测 -28% ≈ 196 字/分钟）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "scripts", "gen_sleep_history.py")
BASE_CPM = 272.0  # +0% 语速下每分钟字数


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pct(value: str) -> float:
    s = (value or "0%").strip().rstrip("%")
    try:
        return float(s) / 100.0
    except ValueError:
        return 0.0


def count_chars(data: dict) -> int:
    total = 0
    for p in data.get("paragraphs", []):
        if isinstance(p, str):
            total += len(p)
        elif isinstance(p, dict):
            total += len(p.get("text") or p.get("title") or "")
    return total


def est_minutes(chars: int, rate: str) -> float:
    cpm = BASE_CPM * (1 + pct(rate))
    return chars / cpm if cpm > 0 else 0.0


def load_state(path: str) -> dict:
    return read_json(path) if os.path.exists(path) else {}


def save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def parse_result(text: str):
    """从生成器输出里取最后一个 {"ok": true, ...} 结果块。"""
    m = None
    for m2 in re.finditer(r'\{\s*"ok":\s*true[^{}]*\}', text):
        m = m2
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="通用系列批量生成器")
    ap.add_argument("series_dir", help="系列目录，如 series/ming-emperors")
    ap.add_argument("--only", nargs="*", default=None, help="只跑指定集，如 --only EP.02 EP.04")
    ap.add_argument("--from", dest="from_ep", default=None, help="从某一集开始，如 --from EP.03")
    ap.add_argument("--force", action="store_true", help="已完成也重跑")
    ap.add_argument("--estimate", action="store_true", help="只估算字数/时长，不生成")
    ap.add_argument("--list", action="store_true", help="列出集数与状态")
    ap.add_argument("--limit-paras", type=int, default=0, help="每集只取前 N 段（试跑）")
    ap.add_argument("--pause", type=float, default=5.0, help="集间停顿秒数")
    args = ap.parse_args()

    sdir = args.series_dir if os.path.isabs(args.series_dir) else os.path.join(ROOT, args.series_dir)
    manifest_path = os.path.join(sdir, "manifest.json")
    if not os.path.isfile(manifest_path):
        sys.exit(f"找不到 manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    defaults = manifest.get("defaults", {})
    slug = manifest.get("slug") or os.path.basename(sdir)
    all_eps = manifest.get("episodes", [])
    state_path = os.path.join(sdir, ".state.json")
    state = load_state(state_path)

    series_name = manifest.get("series") or "系列"
    voice = defaults.get("voice")
    rate_default = defaults.get("rate", "-10%")
    bgm = defaults.get("bgm") or ""

    # 过滤
    eps = list(all_eps)
    if args.from_ep:
        ids = [e.get("id") for e in all_eps]
        pos = ids.index(args.from_ep) if args.from_ep in ids else 0
        eps = all_eps[pos:]
    if args.only:
        want = {x.upper() for x in args.only}
        eps = [e for e in eps if (e.get("id") or "").upper() in want]

    # 读取每集元信息
    rows = []
    for ep in eps:
        ep_path = os.path.join(sdir, ep["file"])
        if not os.path.isfile(ep_path):
            rows.append({"ep": ep, "path": ep_path, "missing": True})
            continue
        data = read_json(ep_path)
        chars = count_chars(data)
        rate = data.get("rate") or rate_default
        rows.append({
            "ep": ep, "path": ep_path, "data": data, "chars": chars,
            "rate": rate, "minutes": est_minutes(chars, rate),
            "title": data.get("title") or ep.get("title") or ep["id"],
        })

    total_chars = sum(r.get("chars", 0) for r in rows)
    total_min = sum(r.get("minutes", 0) for r in rows)

    # 列表 / 估算
    if args.list or args.estimate:
        print(f"系列：{series_name}（{slug}）  共 {len(rows)} 集"
              f"  音色 {voice or '默认'}  语速 {rate_default}")
        print(f"{'集':<7}{'字数':>7}{'预估时长':>10}  状态      标题")
        for r in rows:
            if r.get("missing"):
                print(f"{r['ep'].get('id',''):<7}{'--':>7}{'--':>10}  文件缺失  {r['ep'].get('file')}")
                continue
            st = state.get(r["ep"]["id"], {})
            status = st.get("status", "-")
            if status == "done" and not os.path.exists(st.get("video", "") or ""):
                status = "已跑过(产物丢失)"
            mm, ss = divmod(int(r["minutes"] * 60), 60)
            print(f"{r['ep']['id']:<7}{r['chars']:>7}{mm:>6}分{ss:02d}秒  {status:<9} {r['title']}")
        tm, ts = divmod(int(total_min * 60), 60)
        print(f"\n合计：{total_chars} 字，约 {tm} 分 {ts} 秒（{total_min/60:.1f} 小时）")
        if args.estimate:
            return

    # 执行
    ok_cnt = skip_cnt = fail_cnt = 0
    for r in rows:
        if r.get("missing"):
            print(f"跳过 {r['ep'].get('id')}：文件不存在 {r['ep'].get('file')}")
            fail_cnt += 1
            continue
        ep_id = r["ep"]["id"]
        st = state.get(ep_id, {})
        if not args.force and st.get("status") == "done" and os.path.exists(st.get("video", "") or ""):
            print(f"跳过 {ep_id}：已完成（{st.get('duration_min')} 分钟）")
            skip_cnt += 1
            continue

        cmd = [sys.executable, GEN, r["path"]]
        if voice:
            cmd += [f"--voice={voice}"]
        # 用 --rate= 形式，否则 argparse 会把 -50% 当成选项
        cmd += [f"--rate={r['rate']}"]
        if bgm:
            cmd += [f"--bgm={bgm}"]
        if args.limit_paras:
            cmd += ["--limit-paras", str(args.limit_paras)]

        print(f"\n{'='*60}\n开始 {ep_id}：{r['title']}（{r['chars']} 字，约 {r['minutes']:.0f} 分钟）\n{'='*60}", flush=True)
        t0 = time.time()
        state[ep_id] = {"status": "running", "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "title": r["title"], "chars": r["chars"]}
        save_state(state_path, state)

        buf = []
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, cwd=ROOT)
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            buf.append(line)
        proc.wait()
        elapsed = time.time() - t0
        result = parse_result("".join(buf))

        if proc.returncode == 0 and result and result.get("ok"):
            state[ep_id] = {
                "status": "done",
                "started_at": state[ep_id]["started_at"],
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "title": r["title"], "chars": r["chars"],
                "duration_min": result.get("duration_min"),
                "audio": result.get("audio"), "video": result.get("video"),
                "cover": result.get("cover"), "size_mb": result.get("size_mb"),
                "elapsed_sec": round(elapsed, 1),
            }
            ok_cnt += 1
            print(f"✅ {ep_id} 完成：{result.get('duration_min')} 分钟，用时 {elapsed/60:.1f} 分钟")
        else:
            state[ep_id] = {
                "status": "failed", "title": r["title"], "chars": r["chars"],
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "returncode": proc.returncode, "elapsed_sec": round(elapsed, 1),
            }
            fail_cnt += 1
            print(f"❌ {ep_id} 失败（returncode={proc.returncode}），继续下一集")
        save_state(state_path, state)
        if args.pause:
            time.sleep(args.pause)

    print(f"\n完成：成功 {ok_cnt}，跳过 {skip_cnt}，失败 {fail_cnt}。状态文件：{state_path}")


if __name__ == "__main__":
    main()
