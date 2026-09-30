# -*- coding: utf-8 -*-
"""R72 位置共享：坐标文本解析 + 地图链接生成（纯标准库，无第三方依赖）。

位置消息不需要新信令——geo 字段随 CHAT 透传；本模块只负责两件事：
1. parse(text)：把用户粘贴的各种坐标文本解析成 {lat, lon}
   - "39.9042,116.4074"（国际惯例：纬度,经度）
   - "116.4074,39.9042"（经度,纬度；靠 |值| > 90 自动判别）
   - 高德/百度/腾讯/Google/OSM 分享链接中的坐标参数
   - "geo:39.9042,116.4074"
2. osm_url(lat, lon)：生成 OpenStreetMap 链接（无需 API key，离线内网也能出链接）

歧义处理：两个数都 ≤ 90（如 "20,30"）时无法从数值判断顺序，按国际惯例取
「纬度,经度」，并把 ambiguous=True 回给调用方——由 UI 弹预览让用户一眼确认，
而不是默默按错误顺序发送。
"""
import re
from urllib.parse import urlparse, parse_qs, unquote

LAT_MAX = 90.0
LON_MAX = 180.0

_NUM = r"[-+]?\d{1,3}(?:\.\d+)?"
_PAIR = re.compile(rf"({_NUM})\s*[,，;；]\s*({_NUM})")
_AT = re.compile(rf"@({_NUM}),({_NUM})")
# 明确的经纬度参数名（高德/百度/腾讯/Google/必应/OSM 各家混用，统一收集）
_LAT_KEYS = ("lat", "mlat", "slat", "latitude", "y")
_LON_KEYS = ("lon", "lng", "mlon", "slon", "longitude", "x")
# 成对坐标参数名（值本身是 "a,b"，顺序各家不同，交给 _interpret 判别）
_POS_KEYS = ("position", "coords", "coord", "location", "q", "ll", "center", "pt")


def valid(lat, lon) -> bool:
    """经纬度是否在合法范围内。"""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return abs(lat) <= LAT_MAX and abs(lon) <= LON_MAX


def _interpret(a: float, b: float):
    """把一对数解释成 (lat, lon, ambiguous)。

    国际惯例「纬度,经度」优先；只有一种解释合法时直接采用；两种都合法
    （两个数都 ≤ 90）时返回 ambiguous=True 交由 UI 预览确认。都不合法返回 None。
    """
    if abs(a) > LON_MAX or abs(b) > LON_MAX:
        return None
    ok_direct = abs(a) <= LAT_MAX and abs(b) <= LON_MAX   # a=lat, b=lon
    ok_swap = abs(b) <= LAT_MAX and abs(a) <= LON_MAX     # a=lon, b=lat
    if ok_direct and ok_swap:
        return a, b, True
    if ok_direct:
        return a, b, False
    if ok_swap:
        return b, a, False
    return None


def _mk(lat: float, lon: float, ambiguous: bool, raw: str) -> dict:
    return {"lat": round(float(lat), 6), "lon": round(float(lon), 6),
            "ambiguous": bool(ambiguous), "raw": raw}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pick(q: dict, keys) -> float | None:
    """从 query 字典里按候选键顺序取第一个可解析的数值。"""
    for k in keys:
        for v in q.get(k, ()):
            n = _num(v)
            if n is not None:
                return n
    return None


def _from_url(s: str):
    """从 URL 形态解析（查询参数 / @lat,lon 路径段 / 成对参数值）。"""
    m = _AT.search(s)
    if m:
        r = _interpret(float(m.group(1)), float(m.group(2)))
        if r:
            return _mk(r[0], r[1], r[2], s)
    try:
        q = parse_qs(urlparse(s).query)
    except Exception:
        return None
    lat = _pick(q, _LAT_KEYS)
    lon = _pick(q, _LON_KEYS)
    if lat is not None and lon is not None and valid(lat, lon):
        return _mk(lat, lon, False, s)
    for k in _POS_KEYS:
        for v in q.get(k, ()):
            hit = _from_pair_text(unquote(v))
            if hit:
                hit["raw"] = s
                return hit
    # 百度/高德的路径段形如 /marker/116.4,39.9 或 /poi/39.9,116.4
    body = unquote(s.split("?", 1)[0])
    hit = _from_pair_text(body)
    if hit:
        hit["raw"] = s
        return hit
    return None


def _from_pair_text(s: str):
    """从纯文本里找第一对坐标。"""
    m = _PAIR.search(s or "")
    if not m:
        return None
    r = _interpret(float(m.group(1)), float(m.group(2)))
    if not r:
        return None
    return _mk(r[0], r[1], r[2], s)


def parse(text: str) -> dict | None:
    """解析坐标文本 → {lat, lon, ambiguous, raw}；无法解析返回 None。

    ``ambiguous=True`` 表示「纬度,经度」与「经度,纬度」都合法（两数均 ≤ 90），
    调用方应弹预览让用户确认。
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    lowered = s.lower()
    if "://" in s or lowered.startswith("geo:"):
        hit = _from_url(s)
        if hit:
            return hit
    if lowered.startswith("geo:"):
        s = s[4:]
    return _from_pair_text(s)


def format_pair(lat: float, lon: float) -> str:
    """回显用的「纬度, 经度」文本。"""
    return f"{float(lat):.6f}, {float(lon):.6f}"


def osm_url(lat: float, lon: float, zoom: int = 16) -> str:
    """OpenStreetMap 链接（无 API key，内网/离线也能生成）。"""
    z = max(1, min(19, int(zoom)))
    return (f"https://www.openstreetmap.org/?mlat={float(lat):.6f}"
            f"&mlon={float(lon):.6f}#map={z}/{float(lat):.6f}/{float(lon):.6f}")