"""本地前景抠图（u2net + onnxruntime，0 积分）。

把图片中的主体（人物）从背景分离出来，返回带 alpha 的 RGBA，
供 render 做 2.5D 景深视差。模型文件放在项目 models/u2net.onnx。
"""
from __future__ import annotations

import os
import threading

import numpy as np
from PIL import Image, ImageFilter
import onnxruntime as ort

_LOCK = threading.Lock()
_SESS = None
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "u2net.onnx"
)


def _session() -> ort.InferenceSession:
    global _SESS
    if _SESS is None:
        with _LOCK:
            if _SESS is None:
                if not os.path.exists(_MODEL_PATH):
                    raise FileNotFoundError(f"未找到抠图模型: {_MODEL_PATH}")
                _SESS = ort.InferenceSession(
                    _MODEL_PATH, providers=["CPUExecutionProvider"]
                )
    return _SESS


def remove_bg(image_path: str) -> Image.Image | None:
    """返回 RGBA（前景不透明、背景透明），失败返回 None。"""
    try:
        src = Image.open(image_path).convert("RGB")
    except Exception:
        return None
    w, h = src.size
    if w < 4 or h < 4:
        return None

    # u2net 固定 320x320 输入
    im = src.resize((320, 320), Image.BILINEAR)
    arr = np.asarray(im, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)[None]  # NCHW, (1,3,320,320)

    sess = _session()
    try:
        out = sess.run(None, {sess.get_inputs()[0].name: arr})[0][0, 0]  # (320,320)
    except Exception:
        return None

    # u2net 输出是 logits，需 min-max 归一化（rembg 同款做法），
    # 直接用 sigmoid 会把 mask 挤在中段，抠不干净。
    mi, ma = float(out.min()), float(out.max())
    if ma - mi < 1e-6:
        return None
    mask = (np.clip((out - mi) / (ma - mi), 0, 1) * 255).astype(np.uint8)
    m = Image.fromarray(mask, "L").resize((w, h), Image.BILINEAR)
    # 羽化边缘，避免硬切
    m = m.filter(ImageFilter.GaussianBlur(3))
    rgba = src.copy()
    rgba.putalpha(m)
    return rgba


def cache_key(image_path: str) -> str:
    import hashlib

    return hashlib.md5(image_path.encode("utf-8")).hexdigest()


def remove_bg_cached(image_path: str, cache_dir: str) -> str | None:
    """抠图并缓存前景 PNG，返回缓存路径（失败返回 None）。

    缓存按图片路径 md5，避免重渲染时重复抠图。
    """
    os.makedirs(cache_dir, exist_ok=True)
    fg_path = os.path.join(cache_dir, f"_fg_{cache_key(image_path)}.png")
    if os.path.exists(fg_path):
        return fg_path
    rgba = remove_bg(image_path)
    if rgba is None:
        return None
    rgba.save(fg_path, "PNG")
    return fg_path
