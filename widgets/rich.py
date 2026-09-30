# -*- coding: utf-8 -*-
"""widgets/rich.py —— 富文本 Markdown 解析（对标 TG 内联格式）。

输入 Telegram 风格内联标记，输出有序二维段 [(text, kind, href)]：
    **粗体**   → (inner, "bold")
    *斜体*     → (inner, "italic")
    `代码`     → (inner, "code")                    # 等宽 + 底色
    ||剧透||   → (inner, "spoiler")                 # R70A：点击揭示（默认遮盖）
    [文字](url) → (label, "link", url)              # 可点链接
    其余文本    → 复用 runs.tag_entities 识别 @提及 / #话题 / 裸链接

对外核心接口：``parse(text)``。纯函数、无 tk 依赖，便于单测与双端共用逻辑。
段种类常量沿用 runs.py（PLAIN/MENTION/LINK/HASHTAG），新增 BOLD/ITALIC/CODE/SPOILER。
"""
import re

from widgets import runs

# 新增富文本段种类（并列于 runs.PLAIN 等）
BOLD = "bold"
ITALIC = "italic"
CODE = "code"
SPOILER = "spoiler"      # R70A：||隐藏|| → 遮盖 + 点击揭示

# 一次扫描抓取所有内联标记（* 斜体 / ** 粗体 / ` 代码 / ||剧透|| / [label](url)）
# R70A：spoiler 放在 `` 代码 之后，且 `` 代码 优先级更高——正则从左到右匹配，
# 落在代码段内的 ``||x||`` 会先被 `[^`]+` 整段吃掉，自然不误判为剧透。
_MARK = re.compile(
    r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\|\|[^|\n]+\|\|"
    r"|\[[^\]\n]+\]\([^()\s]+\))")

_LINK = re.compile(r"^\[([^\[\]()\n]+)\]\s*\(\s*([^()\s]+)\s*\)$")


def _classify(match: str) -> tuple | None:
    """解析单个标记串 → (inner, kind, href)；不识别则 None。"""
    if match.startswith("**") and match.endswith("**"):
        return (match[2:-2], BOLD, None)
    if match.startswith("*") and match.endswith("*"):
        return (match[1:-1], ITALIC, None)
    if match.startswith("`") and match.endswith("`"):
        return (match[1:-1], CODE, None)
    if match.startswith("||") and match.endswith("||"):
        return (match[2:-2], SPOILER, None)
    lm = _LINK.match(match)
    if lm:
        return (lm.group(1), runs.LINK, lm.group(2))
    return None


def parse(text: str) -> list:
    """把正文切成二维段 [(text, kind, href)]。

    - 标记段：BOLD/ITALIC/CODE 用两种不同字体、LINK 可点（跳转 href）。
    - 字面段：再跑 runs.tag_entities 保 @提及/#话题/裸链接 高亮。
    """
    if not text:
        return []
    parts = _MARK.split(text)                 # 奇偶交替：偶=字面，奇=标记
    out: list = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:                        # 标记段
            cls = _classify(part)
            if cls:
                out.append(cls)
            else:                             # 标记闭合不匹配 → 当字面
                out.extend(_tag_literal(part))
        else:                                 # 字面段
            out.extend(_tag_literal(part))
    return out


def _tag_literal(text: str) -> list:
    """字面段实体检测：复用 runs.tag_entities → 统一为 (text, kind, None)。"""
    return [(t, k, None) for t, k in runs.tag_entities(text)]


def plain_text(segs: list) -> str:
    """还原纯文本（转发/回复快照/搜索用）：拼接所有段文本。"""
    return "".join(seg[0] for seg in segs)


# ---- 供网页端后端/其它模块做白名单清洗时复用 ----
ALLOWED_KINDS = (runs.PLAIN, runs.MENTION, runs.LINK, runs.HASHTAG,
                 BOLD, ITALIC, CODE, SPOILER)