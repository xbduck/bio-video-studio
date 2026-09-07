#!/usr/bin/env bash
# 生平短片工厂 · macOS / Linux 启动脚本
set -euo pipefail

cd "$(dirname "$0")"

# Python 解释器：优先使用项目专属虚拟环境
PY="/Users/lingmf/.workbuddy/binaries/python/envs/biostudio/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

echo "  生平短片工厂 · 启动中..."
echo "  Python: $PY"
echo

# 依赖自检
if ! "$PY" -c "import fastapi, uvicorn, edge_tts, imageio_ffmpeg" 2>/dev/null; then
  echo "  正在安装依赖..."
  "$PY" -m pip install -q fastapi uvicorn edge-tts imageio-ffmpeg
fi

exec "$PY" app.py "$@"
