"""生视频路线规划：根据运镜提示词判断哪些分镜需要视频大模型（真实物理运动），
其余走本地渲染（ffmpeg 推/拉/摇/移），从而把「混合」路线的 AI 条数压到最低。

这是 hf / ai / mix 三条路线的唯一决策源，前端提示词与 studio.py 命令行共用，
避免两边关键词规则不一致导致「该省没省」。
"""
from __future__ import annotations

# 命中这些关键词 → 需要真实物理运动，才值得消耗积分用视频大模型
AI_MOTION_KEYWORDS = [
    "开车", "行驶", "驾驶", "奔驰", "飞驰", "车流", "列车", "高铁", "火车", "地铁",
    "行走", "散步", "漫步", "奔跑", "跑步", "赛跑", "追逐", "奔跑", "赶路",
    "航拍", "俯冲", "拉升", "盘旋", "飞行", "起飞", "降落", "无人机", "云海",
    "翻滚", "坠落", "跳跃", "冲锋", "骑马", "划船", "游泳", "舞蹈", "跳舞", "起舞",
    "海浪", "波涛", "潮水", "流水", "瀑布", "水流", "浪花",
    "烟雾", "燃烧", "爆炸", "火焰", "烈火", "风沙", "飘雪", "大雪", "倾盆", "大雨",
    "旗帜", "飘扬", "飘动", "随风", "人群", "拥挤", "涌动", "挥手", "鼓掌", "奔走",
    "倒下", "倒塌", "崩塌", "碎裂", "开火", "射击", "战火", "厮杀", "冲锋陷阵",
    "云卷", "星云", "扩散", "喷发", "沸腾",
]

# 命中这些 → 明确是本地相机运动或静态，绝不消耗积分
LOCAL_MOTION_KEYWORDS = [
    "推", "拉", "摇", "移", "平移", "横移", "推进", "拉近", "拉远",
    "俯拍", "仰拍", "俯视", "仰视", "凝视", "沉思", "静默", "静立",
    "特写", "近景", "中景", "远景", "全景", "静态", "定格", "淡入", "淡出",
    "叠化", "缓慢", "微动", "不动", "站", "坐", "立",
]

# 单条视频大模型积分区间（1080P / 5s，参考当前 VideoGen 计费）
CREDIT_PER_CLIP_LOW = 50
CREDIT_PER_CLIP_HIGH = 100


def needs_ai_video(text: str) -> bool:
    """判断一条运镜提示词是否需要视频大模型。

    策略：命中「真实物理运动」关键词 → 需要 AI；
    但若明确是本地相机运动/静态，则除非同时出现强物理运动词，否则走本地。
    """
    t = (text or "").lower()
    has_local = any(k in t for k in LOCAL_MOTION_KEYWORDS)
    has_ai = any(k in t for k in AI_MOTION_KEYWORDS)
    if has_local and not has_ai:
        return False
    return has_ai


def plan_videos(scenes: list[dict], route: str) -> dict:
    """为给定路线产出分镜规划。

    route:
      hf  -> 全部本地渲染（0 积分）
      ai  -> 全部视频大模型
      mix -> 自动挑选：仅真实运动镜头用 AI，其余本地
    返回 {route, ai_indices, local_indices, ai_count, total,
          estimate_low, estimate_high, note}
    """
    route = (route or "hf").lower()
    if route not in ("hf", "ai", "mix"):
        route = "hf"

    indices = [s["index"] for s in scenes]
    total = len(scenes)

    if route == "hf":
        ai: list[int] = []
        local = indices
    elif route == "ai":
        ai = indices
        local = []
    else:  # mix
        ai = [s["index"] for s in scenes if needs_ai_video(s.get("video_prompt", ""))]
        local = [i for i in indices if i not in ai]

    ai_count = len(ai)
    est_low = ai_count * CREDIT_PER_CLIP_LOW
    est_high = ai_count * CREDIT_PER_CLIP_HIGH

    if route == "hf":
        note = "全部本地渲染，0 积分"
    elif route == "ai":
        note = f"全部用视频大模型，约 {est_low}~{est_high} 积分"
    else:
        note = (f"混合：仅 {ai_count}/{total} 条真实运动镜头用模型"
                f"（约 {est_low}~{est_high} 积分），其余本地渲染")

    return {
        "route": route,
        "ai_indices": ai,
        "local_indices": local,
        "ai_count": ai_count,
        "total": total,
        "estimate_low": est_low,
        "estimate_high": est_high,
        "note": note,
    }
