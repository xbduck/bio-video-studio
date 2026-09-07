"""中文配音：edge-tts。

edge-tts 是免费且音质不错的在线 TTS（微软 Edge 的朗读引擎）。
如果网络不通会抛异常，调用方负责降级为静音轨。
"""
from __future__ import annotations

import asyncio
import os
from typing import Callable

import edge_tts

# 预置音色，前端下拉框用
VOICES = [
    ("zh-CN-YunjianNeural", "云健 · 浑厚男声（叙述感强，推荐）"),
    ("zh-CN-YunyangNeural", "云扬 · 新闻男声（庄重）"),
    ("zh-CN-YunxiNeural", "云希 · 清朗男声（年轻）"),
    ("zh-CN-XiaoxiaoNeural", "晓晓 · 温柔女声"),
    ("zh-CN-XiaoyiNeural", "晓伊 · 活泼女声"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北 · 东北女声（故事感）"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮 · 陕西女声（沧桑故事）"),
]


async def _synth(text: str, voice: str, rate: str, volume: str, out_path: str) -> float:
    """合成语音并落盘，返回音频时长（秒）。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume)

    end_ms = 0.0
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset / duration 单位为 100ns
                end_ms = max(
                    end_ms,
                    (chunk["offset"] + chunk["duration"]) / 10_000_000.0,
                )

    if end_ms <= 0 and os.path.exists(out_path):
        # 兜底：按 mp3 32kbps 单声道估算
        end_ms = os.path.getsize(out_path) / 4000.0
    return end_ms


def synthesize(
    text: str,
    out_path: str,
    voice: str = "zh-CN-YunjianNeural",
    rate: str = "+0%",
    volume: str = "+0%",
) -> float:
    """同步包装。返回音频时长（秒）。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("旁白文本为空")

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_synth(text, voice, rate, volume, out_path))


def synth_scenes(
    scenes: list[dict],
    audio_dir: str,
    voice: str,
    rate: str,
    volume: str,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    """为一个项目的所有分镜生成旁白，写回 scene['audio_path'] / ['duration']。"""
    results = []
    total = len(scenes)
    for i, sc in enumerate(scenes, 1):
        narration = (sc.get("narration") or "").strip()
        out_path = os.path.join(audio_dir, f"{sc['index']:02d}.mp3")
        if progress:
            progress(i, total, f"配音 {i}/{total}")
        if narration:
            dur = synthesize(narration, out_path, voice, rate, volume)
        else:
            dur = 0.0
            if os.path.exists(out_path):
                os.remove(out_path)
        results.append({"index": sc["index"], "path": out_path, "duration": dur})
    return results
