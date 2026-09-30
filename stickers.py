# -*- coding: utf-8 -*-
"""表情包系统：内置表情包（code -> emoji）+ 短代码展开。

- sticker 字段：客户端"一键发表情"（服务器只校验 code 是否在包内）
- 文本短代码：消息里写 `:smile:` 客户端渲染时展开为 😀（服务器原样存储）

包本身是纯文本 Unicode emoji，零图片资源，跨平台无依赖。

R35 贴纸商店：STICKER_PACKS 按 pack_id 分组（常用/心情/办公/摸鱼），
客户端可按包订阅（STICKER_SUB），商店目录 = STICKER_PACKS 合集。
兼容层：STICKER_PACK 仍为全部条目平铺，STICKER_BY_CODE / is_valid 不变。
"""
import re

# R35：按包分组（pack_id 唯一；items 引用下方 STICKER_PACK 的 code）
STICKER_PACKS = [
    {"pack_id": "basic", "name": "常用", "items": [
        "smile", "laugh", "like", "ok", "sad", "cry"]},
    {"pack_id": "mood", "name": "心情", "items": [
        "cool", "angry", "surprise", "love", "clap"]},
    {"pack_id": "office", "name": "办公", "items": [
        "pc", "tea", "money", "win"]},
    {"pack_id": "fun", "name": "摸鱼", "items": [
        "fish", "zzz", "fire"]},
]

STICKER_PACK = [
    {"code": "smile", "emoji": "😀", "label": "微笑"},
    {"code": "laugh", "emoji": "😂", "label": "笑哭"},
    {"code": "cool", "emoji": "😎", "label": "得意"},
    {"code": "angry", "emoji": "😠", "label": "生气"},
    {"code": "cry", "emoji": "😭", "label": "大哭"},
    {"code": "surprise", "emoji": "😱", "label": "震惊"},
    {"code": "love", "emoji": "❤️", "label": "爱心"},
    {"code": "like", "emoji": "👍", "label": "点赞"},
    {"code": "clap", "emoji": "👏", "label": "鼓掌"},
    {"code": "tea", "emoji": "☕", "label": "喝茶"},
    {"code": "fish", "emoji": "🐟", "label": "摸鱼"},
    {"code": "zzz", "emoji": "💤", "label": "睡觉"},
    {"code": "money", "emoji": "💰", "label": "发财"},
    {"code": "fire", "emoji": "🔥", "label": "加油"},
    {"code": "ok", "emoji": "👌", "label": "好的"},
    {"code": "sad", "emoji": "😢", "label": "难过"},
    {"code": "win", "emoji": "🏆", "label": "冠军"},
    {"code": "pc", "emoji": "💻", "label": "干活"},
]

STICKER_BY_CODE = {s["code"]: s for s in STICKER_PACK}

DEFAULT_SUBS = ["basic"]             # R35：默认订阅（未自选时的初始包）

_SHORTCODE_RE = re.compile(r":([A-Za-z0-9_]+):")

# R30C 自定义表情包：文本短代码用双冒号 `[:code:]`，与内置 emoji 单冒号区分
_CUSTOM_RE = re.compile(r"\[:([A-Za-z0-9_]{1,24}):\]")


def is_valid(code: str) -> bool:
    """sticker 字段是否合法（在包内）"""
    return code in STICKER_BY_CODE


def shop_catalog() -> list:
    """R35 商店目录：包列表（含条目完整信息），供 STICKER_SHOP 回帧直接序列化。"""
    packs = []
    for p in STICKER_PACKS:
        items = [dict(STICKER_BY_CODE[c], code=c) for c in p["items"]
                 if c in STICKER_BY_CODE]
        packs.append({"pack_id": p["pack_id"], "name": p["name"],
                      "items": items})
    return packs


def valid_pack_id(pack_id: str) -> bool:
    return any(p["pack_id"] == pack_id for p in STICKER_PACKS)


def codes_in_text(text: str) -> list:
    """提取文本里出现的所有短代码（供 UI 提示）"""
    return _SHORTCODE_RE.findall(text)


def expand_shortcodes(text: str) -> str:
    """文本里的 `:code:` 短代码展开为 emoji（未知 code 原样保留）。"""
    return _SHORTCODE_RE.sub(
        lambda m: (STICKER_BY_CODE[m.group(1)]["emoji"]
                   if m.group(1) in STICKER_BY_CODE else m.group(0)),
        text or "")


# ---------- R30C 自定义表情包 ----------
def is_valid_custom_code(code: str) -> bool:
    """自定义贴纸短码：1~24 位字母/数字/下划线"""
    return bool(_CUSTOM_RE.fullmatch(f"[:{(code or '').strip()}:]"))


def custom_tokens(text: str) -> list:
    """提取文本里出现的所有自定义贴纸短码（按出现顺序）"""
    return _CUSTOM_RE.findall(text or "")


def is_custom_sticker_text(text: str) -> str | None:
    """整条消息就是单个自定义贴纸短码 → 返回 code；否则 None。
    只有独立成条的贴纸才走图片渲染（与 TG 贴纸一致），混排保持文本。"""
    t = (text or "").strip()
    if not t:
        return None
    m = _CUSTOM_RE.fullmatch(t)
    return m.group(1) if m else None
