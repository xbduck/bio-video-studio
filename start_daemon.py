#!/usr/bin/env python3
"""以守护进程方式启动生平短片工厂服务。

要点：
1. start_new_session=True —— 脱离当前终端会话，不被 WorkBuddy 会话回收
2. 剥离 HTTP_PROXY 等会话级代理 —— 否则 edge-tts 联网配音会 NETWORK_UNREACHABLE
3. 日志落盘到 logs/server.log，便于排查
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = "/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python"
PORT = os.environ.get("STUDIO_PORT", "7799")  # 7788 已被其他项目占用
LOG = os.path.join(ROOT, "logs", "server.log")

os.makedirs(os.path.dirname(LOG), exist_ok=True)

env = dict(os.environ)
# 剥离会话级代理（端口随会话变化，会话结束即失效）
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    env.pop(k, None)
env["NO_PROXY"] = "localhost,127.0.0.1"
env["no_proxy"] = "localhost,127.0.0.1"
env["STUDIO_PORT"] = PORT
env["PYTHONUNBUFFERED"] = "1"

logf = open(LOG, "a", buffering=1)
proc = subprocess.Popen(
    [PY, "app.py", "--no-browser"],
    cwd=ROOT,
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=logf,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)

# 等待服务就绪
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ok = False
for _ in range(40):
    time.sleep(0.5)
    try:
        with opener.open(f"http://127.0.0.1:{PORT}/api/health", timeout=2) as r:
            print("health:", r.read().decode())
            ok = True
            break
    except Exception:
        continue

print(f"pid={proc.pid} port={PORT} ready={ok}")
print(f"log={LOG}")
sys.exit(0 if ok else 1)
