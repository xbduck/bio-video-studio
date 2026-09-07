"""全局路径与运行配置。"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(ROOT, "projects")
TASKS_DIR = os.path.join(ROOT, "tasks")
LOG_DIR = os.path.join(ROOT, "logs")
WEB_DIR = os.path.join(ROOT, "web")

QUEUE_FILE = os.path.join(TASKS_DIR, "queue.jsonl")
INDEX_FILE = os.path.join(PROJECTS_DIR, "_index.json")

# 默认视觉风格，写入剧本时可被覆盖
DEFAULT_STYLE = (
    "cinematic film still, epic historical biopic, warm natural lighting, "
    "shallow depth of field, highly detailed, photorealistic, 35mm anamorphic"
)

# 默认旁白音色（edge-tts）
# 常用中文音色：zh-CN-YunjianNeural(浑厚男声) / zh-CN-YunxiNeural(清朗男声)
#              zh-CN-XiaoxiaoNeural(温柔女声) / zh-CN-YunyangNeural(新闻男声)
DEFAULT_VOICE = "zh-CN-YunjianNeural"
DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"

# --------------------------------------------------------------------------
# 字体（跨平台自动探测）
#
# 原实现硬编码 Windows 的「微软雅黑」，在 macOS / Linux 上 ffmpeg 会
# 因找不到字体而直接失败。这里按平台自动挑选可用的中文字体：
#   - SUBTITLE_FONT : 字体族名，给 libass（subtitles 滤镜）解析用
#   - TITLE_FONT_FILE: 字体文件路径，给 drawtext 滤镜用
# --------------------------------------------------------------------------

# 各平台候选：[(字体族名, 字体文件路径), ...]，按顺序取第一个存在的
_FONT_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "darwin": [
        ("Hiragino Sans GB", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
        ("Heiti SC", "/System/Library/Fonts/STHeiti Medium.ttc"),
        ("STHeiti", "/System/Library/Fonts/STHeiti Light.ttc"),
    ],
    "nt": [
        ("Microsoft YaHei", r"C:\Windows\Fonts\msyhbd.ttc"),
        ("Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttc"),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
    ],
}
# Linux 等其它平台的兜底候选
_FONT_CANDIDATES_OTHER = [
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("Noto Sans CJK SC", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ("WenQuanYi Zen Hei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ("Noto Sans CJK SC", "Noto Sans CJK SC"),   # 交给 fontconfig 自行解析
]


def _resolve_font() -> tuple[str, str]:
    """返回 (字体族名, 字体文件路径)，探测失败时回退到通用 sans-serif。"""
    import platform

    system = platform.system().lower()
    if system == "darwin":
        candidates = _FONT_CANDIDATES["darwin"]
    elif system == "windows":
        candidates = _FONT_CANDIDATES["nt"]
    else:
        candidates = _FONT_CANDIDATES_OTHER

    for family, path in candidates:
        # 路径为纯字体名时（交给 fontconfig 解析），视为可用
        if not os.path.sep in path and not os.path.exists(path):
            if family:
                return family, path
            continue
        if os.path.exists(path):
            return family, path

    return "sans-serif", "sans-serif"


SUBTITLE_FONT, TITLE_FONT_FILE = _resolve_font()

# 字幕样式（单行字数由字号反算，见 core/compose.py:build_ass）
# 修改字号时无需手改字数，compose 会按物理宽度自动算出放得下的字数。
SUBTITLE_SIZE = 54          # 字号（竖屏 1080 宽的推荐值）
SUBTITLE_MARGIN_LR = 90     # 左右安全边距（px）
SUBTITLE_MARGIN_V = 320     # 距底部（px）
SUBTITLE_OUTLINE = 4        # 描边粗细
SUBTITLE_SHADOW = 2         # 阴影深浅
SUBTITLE_FIT = 0.90         # 单行占可用宽度的比例，留 10% 余量防溢出

for _d in (PROJECTS_DIR, TASKS_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)
