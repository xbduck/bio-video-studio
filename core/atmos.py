"""氛围动态层：浮尘 / 光晕（纯 numpy + PIL 生成，ffmpeg 叠加，0 积分）。

为什么需要它
------------
本地渲染只能做「相机运动」（整张图缩放/平移），画面内的元素本身不会动，
所以观感容易像 PPT / 动态相册。叠加一层**真的在动**的环境元素
（柔和光晕缓慢漂移、稀疏浮尘上浮），能在不消耗积分的前提下明显削弱这种观感。

为什么不做前背景分离（2.5D 视差）
--------------------------------
已实测否决：多人/复杂场景下背景里会残留人物轮廓，虚化后形成「灵魂出窍」式
重影（详见 CHANGELOG 2026-09-17）。抠图能力保留在 `matte.py`，仅适用于
「单一主体 + 干净背景」的素材，当前流水线不使用。

层图一次生成、按尺寸缓存，后续渲染直接复用。
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DUST_SCALE = 1.25    # 浮尘层相对画面的尺寸倍数（留出平动余量，避免露边）
FLARE_SCALE = 1.60   # 光晕层倍数


def _scaled(w: int, h: int, k: float) -> tuple[int, int]:
    return int(round(w * k)), int(round(h * k))


def dust_layer(out_path: str, w: int, h: int, count: int = 170,
               seed: int = 7, tint: tuple = (255, 245, 230),
               amax: int = 100) -> str:
    """稀疏浮尘：随机小亮点，模糊后成一粒粒柔和光点（透明底 RGBA）。"""
    rng = np.random.default_rng(seed)
    xs = rng.integers(0, w, count)
    ys = rng.integers(0, h, count)
    rs = rng.uniform(0.8, 2.6, count)
    br = rng.uniform(0.25, 1.0, count)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x, y, r, b in zip(xs, ys, rs, br):
        a = int(max(0, min(255, amax * float(b))))
        rr = float(r)
        d.ellipse([float(x) - rr, float(y) - rr, float(x) + rr, float(y) + rr],
                  fill=(int(tint[0]), int(tint[1]), int(tint[2]), a))
    img = img.filter(ImageFilter.GaussianBlur(0.9))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def flare_layer(out_path: str, w: int, h: int, seed: int = 3,
                tint: tuple = (255, 222, 175), amax: int = 30) -> str:
    """柔和光晕：一个大椭圆径向渐变（模拟窗外光线流动 / 镜头光斑）。"""
    rng = np.random.default_rng(seed)
    cx = float(rng.uniform(0.38, 0.68))
    cy = float(rng.uniform(0.18, 0.36))
    rx, ry = 0.42, 0.26

    x = np.arange(w, dtype=np.float32)[None, :]
    y = np.arange(h, dtype=np.float32)[:, None]
    dx = (x - cx * w) / (rx * w)
    dy = (y - cy * h) / (ry * h)
    r = np.sqrt(dx * dx + dy * dy)
    alpha = (np.clip(1.0 - r, 0.0, 1.0) ** 2.0 * amax).astype(np.uint8)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0] = int(tint[0])
    rgba[..., 1] = int(tint[1])
    rgba[..., 2] = int(tint[2])
    rgba[..., 3] = alpha
    img = Image.fromarray(rgba, "RGBA").filter(ImageFilter.GaussianBlur(10))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def ensure_layers(cache_dir: str, w: int, h: int) -> dict:
    """按画面尺寸生成/复用氛围层。

    返回 {"dust": 路径, "flare": 路径, "dust_size": (w,h), "flare_size": (w,h)}
    """
    dw, dh = _scaled(w, h, DUST_SCALE)
    fw, fh = _scaled(w, h, FLARE_SCALE)
    dust = os.path.join(cache_dir, f"_dust_{dw}x{dh}.png")
    flare = os.path.join(cache_dir, f"_flare_{fw}x{fh}.png")
    if not os.path.exists(dust):
        dust_layer(dust, dw, dh)
    if not os.path.exists(flare):
        flare_layer(flare, fw, fh)
    return {"dust": dust, "flare": flare,
            "dust_size": (dw, dh), "flare_size": (fw, fh)}
