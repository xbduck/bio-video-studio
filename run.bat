@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo   生平短片工厂 · 启动中...
echo.
"C:\Users\Administrator\.workbuddy\binaries\python\envs\biostudio\Scripts\python.exe" app.py
if errorlevel 1 (
    echo.
    echo   启动失败：请确认 Python 环境已就绪。
    echo   可运行: pip install fastapi uvicorn edge-tts imageio-ffmpeg
)
pause
