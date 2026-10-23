#!/usr/bin/env python3
"""以守护进程方式批量生成一个系列（脱离 WorkBuddy 会话，长时间跑不被回收）。

用法：
    <PY> start_series.py series/ming-emperors
    <PY> start_series.py series/ming-emperors --from EP.03 --force

要点：
1. start_new_session=True —— 脱离当前会话，不会被回收
2. 剥离 HTTP_PROXY —— 否则 edge-tts 联网配音会 NETWORK_UNREACHABLE
3. 日志落 logs/series-<slug>.log，状态落 series/<slug>/.state.json
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = "/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python"

if len(sys.argv) < 2:
    sys.exit("用法: start_series.py <series_dir> [run_series 参数...]")

series_arg = sys.argv[1]
extra = sys.argv[2:]
series_dir = series_arg if os.path.isabs(series_arg) else os.path.join(ROOT, series_arg)
slug = os.path.basename(series_dir.rstrip("/"))

LOG = os.path.join(ROOT, "logs", f"series-{slug}.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)

env = dict(os.environ)
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    env.pop(k, None)
env["NO_PROXY"] = "localhost,127.0.0.1"
env["no_proxy"] = "localhost,127.0.0.1"
env["PYTHONUNBUFFERED"] = "1"

logf = open(LOG, "a", buffering=1)
proc = subprocess.Popen(
    [PY, "scripts/run_series.py", series_arg, *extra],
    cwd=ROOT,
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=logf,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
try:
    with open(os.path.join(series_dir, ".run.pid"), "w") as f:
        f.write(str(proc.pid))
except Exception:
    pass
print(f"pid={proc.pid} series={slug} log={LOG}")
