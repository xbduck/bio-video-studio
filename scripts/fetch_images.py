#!/usr/bin/env python3
"""免费 CC 配图拉取（0 积分）。

优先级：Wikimedia Commons 真实照片 -> Picsum 随机照片兜底。
尊重 HTTPS_PROXY / HTTP_PROXY 环境变量（urllib 自动读取，
这里显式安装 ProxyHandler 以防某些环境下未生效）。

用法：
  from scripts.fetch_images import fetch_image
  path = fetch_image("beef noodle soup", "/abs/cache", "scene_03")
  # -> /abs/cache/scene_03.jpg 或 None
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

WIKI_API = "https://commons.wikimedia.org/w/api.php"
PICSUM = "https://picsum.photos/seed/{seed}/1080/1080"

_UA = "bio-video-studio/1.0 (educational use; contact: local)"


def _install_proxy() -> None:
    try:
        proxy = urllib.request.getproxies()
        if proxy:
            handler = urllib.request.ProxyHandler(proxy)
            urllib.request.install_opener(urllib.request.build_opener(handler))
    except Exception:
        pass


_install_proxy()


def _get_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _download(url: str, dest: str, timeout: int = 40) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def _wiki_candidates(query: str, timeout: int) -> list[str]:
    q = urllib.parse.quote(query)
    api = (
        WIKI_API + "?"
        + urllib.parse.urlencode({
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": "12",
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": "1080",
            "format": "json",
        })
    )
    data = _get_json(api, timeout)
    pages = (data.get("query", {}).get("pages") or {}).values()
    out: list[str] = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        mime = ii.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            continue
        tw = int(ii.get("thumbwidth", 0) or 0)
        th = int(ii.get("thumbheight", 0) or 0)
        if tw < 480 or th < 360:
            continue
        url = ii.get("thumburl")
        if url:
            out.append(url)
    return out


def fetch_image(query: str, cache_dir: str, slug: str, timeout: int = 25) -> str | None:
    """拉取一张与 query 相关的照片，缓存到 cache_dir/<slug>.jpg。失败返回 None。"""
    if not query or not query.strip():
        return None
    os.makedirs(cache_dir, exist_ok=True)
    dest = os.path.join(cache_dir, f"{slug}.jpg")
    if os.path.exists(dest) and os.path.getsize(dest) > 2000:
        return dest  # 命中缓存，省一次网络请求

    # 1) Wikimedia Commons 真实照片
    try:
        cands = _wiki_candidates(query, timeout)
        if cands:
            pick = cands[hashlib.md5(query.encode("utf-8")).digest()[0] % len(cands)]
            if _download(pick, dest, timeout):
                return dest
    except Exception as e:
        print(f"[img] wikimedia 失败({query}): {e}", file=sys.stderr)

    # 2) Picsum 随机照片兜底（保证每镜都有图，但主题不一定匹配）
    try:
        seed = urllib.parse.quote(slug)
        _download(PICSUM.format(seed=seed), dest, timeout)
        if os.path.getsize(dest) > 2000:
            return dest
    except Exception as e:
        print(f"[img] picsum 失败({query}): {e}", file=sys.stderr)
    return None


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "beef noodle soup"
    out = fetch_image(q, "/tmp/img_cache", "test")
    print("saved:", out)
