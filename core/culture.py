"""企业文化专栏（叮叮城故事）：角色圣经解析 + 剧本导出 + 交付自检。

这一层只做「读」：把 dingding-city/ 下的权威 md 和 project.json 转成
前端能直接渲染的结构，以及导演 / 剪辑要的导出文件（Markdown / SRT / CSV）。
不写任何项目文件，避免和产线脚本抢 data。
"""
from __future__ import annotations

import csv
import io
import os
import re
from urllib.parse import quote

from . import config

DINGDING_DIR = os.path.join(config.ROOT, "dingding-city")
BIBLE_FILE = os.path.join(DINGDING_DIR, "角色圣经.md")
AVATAR_DIR = os.path.join(DINGDING_DIR, "avatars")
_AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# 角色名 → 文件名（stem）别名，放官方图时可用英文名/简写
_AVATAR_ALIASES = {
    "tt虎": ["tt-hu", "tt", "tthu", "tt虎绿幕"],
    "猫老板": ["cat-boss", "catboss", "boss-cat", "mao"],
    "小助手": ["robot", "assistant", "helper"],
    "兔妈妈": ["rabbit", "rabbit-mom", "tu"],
}


def _find_avatar_in(folder: str, name: str) -> str | None:
    """在单个目录里按角色名找图：stem 精确 → 别名 → 包含匹配。"""
    if not name:
        return None
    try:
        files = [
            f for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in _AVATAR_EXTS
        ]
    except OSError:
        return None
    key = name.strip().lower()
    cands = [key] + [a.lower() for a in _AVATAR_ALIASES.get(key, [])]
    by_stem = {os.path.splitext(f)[0].strip().lower(): f for f in files}
    for c in cands:
        if c in by_stem:
            return os.path.join(folder, by_stem[c])
    for stem, f in by_stem.items():
        if any(c and c in stem for c in cands):
            return os.path.join(folder, f)
    return None


def episode_avatar_dir(project: dict | None) -> str | None:
    """每一集可以有自己的定妆照：avatars/<project.slug>/。

    同一角色在不同集里的造型/毛色会变（EP.01 的猫老板偏灰蓝、EP.02 偏浅），
    所以按集覆盖，找不到再回落到系列通用图。
    """
    slug = (project or {}).get("slug")
    if not slug:
        return None
    d = os.path.join(AVATAR_DIR, slug)
    return d if os.path.isdir(d) else None


def avatar_path(name: str, project: dict | None = None) -> str | None:
    """按角色名找头像：本集目录优先，其次 dingding-city/avatars/ 通用图。"""
    if not name:
        return None
    ep_dir = episode_avatar_dir(project)
    for folder in ([ep_dir] if ep_dir else []) + [AVATAR_DIR]:
        p = _find_avatar_in(folder, name)
        if p:
            return p
    return None


def _cast_names(project: dict | None, names: list[str]) -> list[str]:
    """本集出场角色名。project.cast 优先；否则从旁白/标题里认角色名。"""
    if not project:
        return []
    explicit = project.get("cast") or []
    if isinstance(explicit, str):
        explicit = [x for x in re.split(r"[、,，/\s]+", explicit) if x]
    if explicit:
        return [str(x).strip() for x in explicit if str(x).strip()]
    text = " ".join(
        f"{s.get('title') or ''} {s.get('narration') or ''}"
        for s in (project.get("scenes") or [])
    )
    return [n for n in names if n and n in text]


# --------------------------------------------------------------------------
# Markdown 轻解析（只覆盖角色圣经这种固定写法，不求通用）
# --------------------------------------------------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _split_h2(md: str) -> list[tuple[str, str]]:
    """按二级标题切块，返回 [(标题, 正文)]。"""
    parts = re.split(r"(?m)^##\s+", md)
    out = []
    for p in parts[1:]:
        lines = p.splitlines()
        if not lines:
            continue
        out.append((lines[0].strip(), "\n".join(lines[1:])))
    return out


def _parse_table(block: str) -> list[dict[str, str]]:
    """抓块内第一张 markdown 表格，返回 [{列名: 值}]。"""
    rows: list[list[str]] = []
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    if len(rows) < 2:
        return []
    head = rows[0]
    out = []
    for r in rows[1:]:
        item = {}
        for i, key in enumerate(head):
            item[key.strip("* ")] = r[i] if i < len(r) else ""
        out.append(item)
    return out


def _first_fence(block: str) -> str:
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", block, re.S)
    if not m:
        return ""
    # 英文 prompt 常按行硬折，拼成一段便于整段复制
    return " ".join(x.strip() for x in m.group(1).splitlines() if x.strip())


def _bullets_after(block: str, keyword: str) -> list[str]:
    """取 keyword 之后（到下一个空行段落结束前）的 `- ` 列表。"""
    idx = block.find(keyword)
    if idx < 0:
        return []
    tail = block[idx + len(keyword):]
    out = []
    for line in tail.splitlines():
        s = line.strip()
        if not s:
            if out:
                break
            continue
        if s.startswith("- "):
            out.append(re.sub(r"\*\*(.+?)\*\*", r"\1", s[2:]).strip())
        elif out:
            break
    return out


def load_characters(project: dict | None = None) -> dict:
    """解析角色圣经.md → 角色卡 / 视觉体系 / 色调映射 / 产线红线。

    传 project 时额外标注「本集是否出场」和「本集定妆照」：
    不同集里同一角色的造型/毛色并不完全一致，头像必须按集取，
    否则会出现「EP.01 里贴的是 EP.02 的角色」。
    """
    md = _read_text(BIBLE_FILE)
    characters, world, moods, guards = [], [], [], []
    for title, body in _split_h2(md):
        m = re.match(r"(\d+)[.、]\s*(.+)", title)
        num = int(m.group(1)) if m else 99
        raw_name = m.group(2) if m else title
        # 「TT虎（主角 · 全片锁死）」→ 名字 TT虎、备注 主角 · 全片锁死
        nm = re.match(r"(.+?)[（(](.+?)[）)]\s*$", raw_name)
        name, note = (nm.group(1).strip(), nm.group(2).strip()) if nm else (raw_name.strip(), "")

        if num <= 4:
            traits = []
            for row in _parse_table(body):
                k = row.get("维度") or next((v for k, v in row.items() if v), "")
                v = row.get("规范") or next((val for key, val in row.items() if key not in ("维度",)), "")
                if k:
                    traits.append({"k": _md_inline(k), "v": _md_inline(v)})
            av = avatar_path(name, project)
            has_avatar = bool(av)
            # 带 mtime 版本号，换图后浏览器不会拿 10 分钟旧缓存
            ver = int(os.path.getmtime(av)) if av and os.path.exists(av) else 0
            ep_dir = episode_avatar_dir(project)
            is_episode_shot = bool(ep_dir and av and os.path.dirname(av) == ep_dir)
            q = f"v={ver}" + (f"&project={quote(str(project.get('id') or project.get('slug')))}" if project else "")
            characters.append({
                "name": name,
                "note": note,
                "order": num,
                "traits": traits,
                "prompt_en": _first_fence(body),
                "redlines": _bullets_after(body, "红线"),
                "body_md": body.strip(),
                "image": f"/api/culture/avatar/{quote(name)}?{q}" if has_avatar else "",
                "has_image": has_avatar,
                "image_source": "episode" if is_episode_shot else ("series" if has_avatar else ""),
            })
        elif "视觉" in title:
            for row in _parse_table(body):
                keys = list(row.keys())
                if len(keys) < 2:
                    continue
                world.append({"scene": row[keys[0]], "notes": _md_inline(row[keys[1]])})
        elif "色调" in title:
            for row in _parse_table(body):
                keys = list(row.keys())
                if len(keys) < 3:
                    continue
                moods.append({"emotion": row[keys[0]], "tone": row[keys[1]], "example": row[keys[2]]})
        elif "产线" in title or "约束" in title:
            for line in body.splitlines():
                s = line.strip()
                if s.startswith("- "):
                    guards.append(_md_inline(s[2:]))
    names = [c["name"] for c in characters]
    cast = _cast_names(project, names)
    for c in characters:
        c["on_stage"] = (c["name"] in cast) if project else None
    characters.sort(key=lambda c: (0 if c["on_stage"] else 1, c["order"]))
    return {
        "source": "dingding-city/角色圣经.md",
        "exists": bool(md),
        "characters": characters,
        "cast": cast,
        "episode": (project or {}).get("title", ""),
        "world": world,
        "moods": moods,
        "guards": guards,
    }


def _md_inline(s: str) -> str:
    """去掉最常见的行内 markdown 记号，保留可读文本。"""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s.strip()


# --------------------------------------------------------------------------
# 剧本派生数据
# --------------------------------------------------------------------------

def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_CJK = re.compile(r"[\u3400-\u9fff]")
_ALNUM = re.compile(r"[A-Za-z0-9]+")


def count_spoken(text: str) -> int:
    """有效口播字数：中日韩字符按 1 字，连续字母数字算 1 个词。标点不计。"""
    t = text or ""
    return len(_CJK.findall(t)) + len(_ALNUM.findall(t))


def scene_meta(p: dict) -> list[dict]:
    """逐镜算入点/出点/语速，供剧本视图与 SRT / CSV 共用。"""
    scenes = p.get("scenes") or []
    out, t = [], 0.0
    for i, s in enumerate(scenes):
        dur = _f(s.get("duration"), 0.0)
        words = count_spoken(s.get("narration", ""))
        out.append({
            "index": s.get("index", i + 1),
            "title": s.get("title", ""),
            "duration": dur,
            "start": t,
            "end": t + dur,
            "words": words,
            "rate": round(words / dur, 2) if dur > 0 else 0.0,
        })
        t += dur
    return out


def _tc(sec: float, sep: str = ",") -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _mmss(sec: float) -> str:
    sec = max(0.0, float(sec))
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _ep_info(p: dict) -> dict:
    title = p.get("title", "")
    epno = (re.search(r"EP\.?\s*(\d+)", title, re.I) or [None, ""])[1] if title else ""
    kw = ""
    if "·" in title:
        kw = re.sub(r"^EP\.?\s*\d+\s*", "", title.split("·")[-1]).strip()
    total = sum(_f(s.get("duration")) for s in (p.get("scenes") or []))
    return {"epno": epno, "keyword": kw, "total": total}


def build_script_md(p: dict) -> str:
    """导出导演通读版剧本（Markdown）。"""
    info = _ep_info(p)
    metas = scene_meta(p)
    aspect = "横屏 16:9" if (p.get("aspect") or "") == "landscape" else "竖屏 9:16"
    lines = [
        f"# {p.get('title') or p.get('person', '未命名')}",
        "",
        f"> {info['keyword'] or '企业文化'} · {len(metas)} 镜 · 总时长 {_mmss(info['total'])} · {aspect}"
        f" · 配音 {'关' if p.get('burn_subtitles') is False else '开'}",
        "",
    ]
    if p.get("ending_subtitle"):
        lines += [f"> 点题字幕：{p['ending_subtitle']}", ""]

    lines += ["| 镜 | 标题 | 时长 | 时间码 | 语速 |", "|---|---|---|---|---|"]
    for s, m in zip(p.get("scenes") or [], metas):
        lines.append(
            f"| {m['index']} | {m['title']} | {m['duration']:g}s | "
            f"{_mmss(m['start'])}–{_mmss(m['end'])} | {m['rate']} 字/秒 |"
        )
    lines.append("")

    for s, m in zip(p.get("scenes") or [], metas):
        lines += [
            f"## 第{m['index']}镜 · {s.get('title', '')}",
            "",
            f"- **时长**：{m['duration']:g}s（{_mmss(m['start'])}–{_mmss(m['end'])}）",
            f"- **旁白**：{s.get('narration', '')}",
            f"- **音效**：{s.get('sound', '')}",
            "",
            "<details><summary>画面提示词</summary>",
            "",
            f"```\n{s.get('image_prompt', '')}\n```",
            "",
            "</details>",
            "",
            "<details><summary>运镜提示词</summary>",
            "",
            f"```\n{s.get('video_prompt', '')}\n```",
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines)


def _wrap_sub(text: str, per_line: int = 20) -> str:
    """字幕折行：优先在标点后断开，每行不超过 per_line 字，最多两行。"""
    t = (text or "").strip()
    if len(t) <= per_line:
        return t
    # 找最靠近中点的标点位置
    mid = len(t) // 2
    best = -1
    for m in re.finditer(r"[，。！？；、…—,.!?;]", t):
        if abs(m.end() - mid) < abs(best - mid) if best >= 0 else True:
            best = m.end()
    if best <= 0:
        best = per_line
    return t[:best].strip() + "\n" + t[best:].strip()


def build_srt(p: dict) -> str:
    """按分镜时长估算的字幕文件（剪辑 / 配音对轴用）。"""
    metas = scene_meta(p)
    blocks = []
    for i, (s, m) in enumerate(zip(p.get("scenes") or [], metas), 1):
        text = (s.get("narration") or "").strip()
        if not text:
            continue
        blocks.append(
            f"{i}\n{_tc(m['start'])} --> {_tc(m['end'])}\n{_wrap_sub(text)}\n"
        )
    return "\n".join(blocks)


SHOTLIST_COLUMNS = [
    ("index", "镜号"),
    ("title", "标题"),
    ("start", "入点"),
    ("end", "出点"),
    ("duration", "时长(秒)"),
    ("words", "字数"),
    ("rate", "语速(字/秒)"),
    ("narration", "旁白"),
    ("sound", "音效"),
    ("image_path", "分镜图"),
    ("video_path", "分镜视频"),
    ("audio_path", "旁白音频"),
    ("image_prompt", "画面提示词"),
    ("video_prompt", "运镜提示词"),
]


def build_shotlist_csv(p: dict) -> str:
    """剪辑单：镜号 / 时间码 / 文案 / 音效 / 素材路径。带 BOM，Excel 直接打开不乱码。"""
    metas = scene_meta(p)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([c[1] for c in SHOTLIST_COLUMNS])
    for s, m in zip(p.get("scenes") or [], metas):
        row = []
        for key, _ in SHOTLIST_COLUMNS:
            if key == "start":
                row.append(_tc(m["start"], sep="."))
            elif key == "end":
                row.append(_tc(m["end"], sep="."))
            elif key in ("index", "duration", "words", "rate"):
                row.append(m[key] if key != "duration" else f"{m['duration']:g}")
            else:
                row.append(s.get(key, ""))
        w.writerow(row)
    return "\ufeff" + buf.getvalue()


# --------------------------------------------------------------------------
# 交付自检（母版「剧本生成规范_v2」硬约束的可执行版）
# --------------------------------------------------------------------------

_LOCKED_CAM = "locked-off static camera"
_TT_DNA = "tt-hu"


def check_delivery(p: dict) -> dict:
    scenes = p.get("scenes") or []
    metas = scene_meta(p)
    total = sum(m["duration"] for m in metas)
    items: list[dict] = []

    def add(key, label, status, detail, bad=None):
        items.append({
            "key": key, "label": label, "status": status,
            "detail": detail, "scenes": bad or [],
        })

    # 1 镜数
    n = len(scenes)
    add("scenes", "镜数 = 12", "pass" if n == 12 else "fail",
        f"当前 {n} 镜" + ("，符合母版 A 档结构" if n == 12 else "，母版要求 12 镜"))

    # 2 总时长
    ok = 120 <= total <= 180
    add("duration", "总时长 120–180 秒", "pass" if ok else "fail",
        f"当前 {total:g} 秒（{_mmss(total)}）")

    # 3 单镜时长
    bad = [m["index"] for m in metas if not (10 <= m["duration"] <= 13)]
    add("scene-duration", "单镜 10–13 秒（A 档）", "pass" if not bad else "warn",
        "全部在区间内" if not bad else f"{len(bad)} 镜超出：{', '.join('第%d镜' % i for i in bad)}",
        bad)

    # 4 语速
    bad = [m["index"] for m in metas if m["rate"] > 4.3]
    worst = max(metas, key=lambda m: m["rate"], default=None)
    add("speech-rate", "每镜语速 ≤ 4.3 字/秒", "pass" if not bad else "fail",
        (f"最高 {(worst['rate'] if worst else 0)} 字/秒（第{worst['index']}镜）" if worst else "无分镜")
        + ("" if not bad else f"，超限 {len(bad)} 镜"),
        bad)

    # 5 运镜锁死
    bad = [m["index"] for m, s in zip(metas, scenes)
           if not (s.get("video_prompt") or "").strip().lower().startswith(_LOCKED_CAM)]
    add("locked-camera", "运镜提示词以 Locked-off static camera 开头", "pass" if not bad else "fail",
        "全部锁死机位" if not bad else f"{len(bad)} 镜未以该句开头", bad)

    # 6 角色 DNA 一致
    bad = [m["index"] for m, s in zip(metas, scenes)
           if "TT虎" in (s.get("narration") or "") and _TT_DNA not in (s.get("image_prompt") or "").lower()]
    add("char-dna", "TT虎 出镜镜次含角色特征句", "pass" if not bad else "fail",
        "出镜镜次均带 TT-Hu 特征句" if not bad else f"{len(bad)} 镜旁白提到 TT虎 但提示词缺特征句", bad)

    # 7 屏幕不乱码字
    bad = [m["index"] for m, s in zip(metas, scenes)
           if "no readable text" not in (s.get("image_prompt") or "").lower()]
    add("no-text", "画面禁止可读文字（no readable text）", "pass" if not bad else "warn",
        "全部已声明" if not bad else f"{len(bad)} 镜提示词缺该约束", bad)

    # 8 无人类
    bad_nar = [m["index"] for m, s in zip(metas, scenes) if "人类" in (s.get("narration") or "")]
    bad_img = []
    for m, s in zip(metas, scenes):
        ip = (s.get("image_prompt") or "")
        # 允许 "NO human hands / no humans" 这类否定写法
        hits = re.findall(r"(?<!no )(?<!NO )\bhumans?\b", ip)
        if hits:
            bad_img.append(m["index"])
    bad = sorted(set(bad_nar) | set(bad_img))
    add("no-human", "只有动物、无人类出镜", "pass" if not bad else "fail",
        "未发现人类描述" if not bad else f"{len(bad)} 镜涉及人类", bad)

    # 9 数字写中文
    bad = [m["index"] for m, s in zip(metas, scenes) if re.search(r"\d", s.get("narration") or "")]
    add("cn-number", "旁白数字写中文", "pass" if not bad else "warn",
        "旁白无阿拉伯数字" if not bad else f"{len(bad)} 镜旁白含阿拉伯数字", bad)

    # 10 无英文缩写（角色名 TT虎 / TT-Hu 属专有名词，先剔掉再查）
    bad = []
    for m, s in zip(metas, scenes):
        txt = re.sub(r"TT[\s-]?(虎|Hu)?", "", s.get("narration") or "")
        if re.search(r"[A-Za-z]", txt):
            bad.append(m["index"])
    add("no-latin", "旁白不含英文缩写", "pass" if not bad else "warn",
        "旁白无英文缩写" if not bad else f"{len(bad)} 镜旁白含英文字母", bad)

    # 11 点题字幕
    sub = (p.get("ending_subtitle") or "").strip()
    add("ending", "结尾点题字幕", "pass" if sub else "warn",
        f"「{sub}」" if sub else "未设置 ending_subtitle")

    # 12 画幅
    add("aspect", "画幅 横屏 16:9", "pass" if p.get("aspect") == "landscape" else "warn",
        "横屏 1920×1080" if p.get("aspect") == "landscape" else f"当前 {p.get('aspect') or 'portrait'}")

    # 13 素材完整度
    miss_i = [m["index"] for m, s in zip(metas, scenes) if not s.get("image_path")]
    miss_v = [m["index"] for m, s in zip(metas, scenes) if not s.get("video_path")]
    miss_a = [m["index"] for m, s in zip(metas, scenes) if not s.get("audio_path")]
    status = "pass" if not (miss_i or miss_v or miss_a) else "warn"
    add("assets", "素材齐备（图 / 视频 / 配音）", status,
        f"图缺 {len(miss_i)} · 视频缺 {len(miss_v)} · 配音缺 {len(miss_a)}", miss_i or miss_v)

    passed = sum(1 for i in items if i["status"] == "pass")
    failed = sum(1 for i in items if i["status"] == "fail")
    warned = sum(1 for i in items if i["status"] == "warn")
    worst = max((m["rate"] for m in metas), default=0)
    return {
        "items": items,
        "summary": {
            "scenes": n,
            "total_duration": round(total, 1),
            "total_mmss": _mmss(total),
            "avg_rate": round(sum(m["words"] for m in metas) / total, 2) if total else 0,
            "max_rate": worst,
            "passed": passed, "failed": failed, "warned": warned,
            "missing": {"image": len(miss_i), "video": len(miss_v), "audio": len(miss_a)},
        },
        "scenes": [
            {"index": m["index"], "title": m["title"], "duration": m["duration"],
             "start": round(m["start"], 3), "end": round(m["end"], 3),
             "words": m["words"], "rate": m["rate"],
             "has_image": bool(s.get("image_path")),
             "has_video": bool(s.get("video_path")),
             "has_audio": bool(s.get("audio_path"))}
            for m, s in zip(metas, scenes)
        ],
    }
