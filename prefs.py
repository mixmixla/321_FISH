# -*- coding: utf-8 -*-
"""prefs.py —— 本地偏好持久化（置顶/静音，对标 TG 本地配置）。

运行时存 `~/moeyu_helper/prefs.json`（与历史同目录），脚本运行存项目目录。
结构：{"pinned": ["private:2", "group:7"], "muted": ["private:2"]}
键与本地历史频道键一致（public / private:a:b / group:gid）。
"""
import json
import os
import sys
import threading
import time

# R35 多档案：随账号切换的会话状态键
# R69C11：unread_marks = 手动「标为未读」的会话键（打开会话即自动清除）
_PROFILE_KEYS = ("pinned", "muted", "archived", "drafts", "stars",
                 "unread_marks")


def _prefs_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), "moeyu_helper")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "prefs.json")


class Prefs:
    """线程安全的小型 JSON 偏好存储（读时全量、写时原子替换）。"""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or _prefs_path()
        self._lock = threading.Lock()
        self._data = {"pinned": [], "muted": [], "archived": [], "dnd": False,
                      "interaction_mode": "tg", "stars": [], "unread_marks": []}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                known = ("pinned", "muted", "archived", "stars", "unread_marks")
                for k in known:
                    if isinstance(d.get(k), list):
                        self._data[k] = [str(x) for x in d[k]]
                if isinstance(d.get("dnd"), bool):
                    self._data["dnd"] = d["dnd"]
                # 扩展键（如 r5b 的 hotkeys dict）原样保留，不丢自定义偏好
                for k, v in d.items():
                    if k not in known and k != "dnd":
                        self._data[k] = v
        except (FileNotFoundError, ValueError, OSError):
            pass

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
        except OSError:
            pass                       # 只读目录等极端情况：不阻断功能

    def is_pinned(self, key: str) -> bool:
        with self._lock:
            return key in self._data["pinned"]

    def is_muted(self, key: str) -> bool:
        with self._lock:
            return key in self._data["muted"]

    def muted(self) -> list:
        with self._lock:
            return list(self._data["muted"])

    def toggle_pin(self, key: str) -> bool:
        with self._lock:
            lst = self._data["pinned"]
            if key in lst:
                lst.remove(key)
                val = False
            else:
                lst.append(key)
                val = True
            self._save()
            return val

    def toggle_mute(self, key: str) -> bool:
        with self._lock:
            lst = self._data["muted"]
            if key in lst:
                lst.remove(key)
                val = False
            else:
                lst.append(key)
                val = True
            self._save()
            return val

    def is_archived(self, key: str) -> bool:
        with self._lock:
            return key in self._data["archived"]

    def trusted_nick(self, nick: str) -> bool:
        """该昵称是否已「记住此身份」：登录时跳过身份确认弹窗。"""
        with self._lock:
            return nick in (self._data.get("trusted_nicks") or [])

    def toggle_trust(self, nick: str) -> None:
        """记住/取消「记住此身份」（免确认登录）。"""
        with self._lock:
            lst = self._data.setdefault("trusted_nicks", [])
            if nick in lst:
                lst.remove(nick)
            else:
                lst.append(nick)
            self._save()

    def toggle_archive(self, key: str) -> bool:
        with self._lock:
            lst = self._data["archived"]
            if key in lst:
                lst.remove(key)
                val = False
            else:
                lst.append(key)
                val = True
            self._save()
            return val

    def archived(self) -> list:
        with self._lock:
            return list(self._data["archived"])

    def pinned(self) -> list:
        with self._lock:
            return list(self._data["pinned"])

    # ---------- 星标会话（⭐，置顶之上的更强置顶；对标 TG starred） ----------
    def is_starred(self, key: str) -> bool:
        with self._lock:
            return key in self._data["stars"]

    def toggle_star(self, key: str) -> bool:
        with self._lock:
            lst = self._data["stars"]
            if key in lst:
                lst.remove(key)
                val = False
            else:
                lst.append(key)
                val = True
            self._save()
            return val

    def starred(self) -> list:
        with self._lock:
            return list(self._data["stars"])

    # ---------- R69C11 标为未读（本地标记，打开会话即清） ----------
    def is_unread_mark(self, key: str) -> bool:
        with self._lock:
            return key in self._data["unread_marks"]

    def unread_marks(self) -> list:
        with self._lock:
            return list(self._data["unread_marks"])

    def set_unread_mark(self, key: str, on: bool = True) -> bool:
        """设置/清除「标为未读」标记，返回设置后的状态。"""
        with self._lock:
            lst = self._data["unread_marks"]
            if on and key not in lst:
                lst.append(key)
            elif not on and key in lst:
                lst.remove(key)
            self._save()
            return key in lst

    def toggle_unread_mark(self, key: str) -> bool:
        with self._lock:
            lst = self._data["unread_marks"]
            if key in lst:
                lst.remove(key)
                val = False
            else:
                lst.append(key)
                val = True
            self._save()
            return val

    def get(self, key: str, default=None):
        """通用取值（如 dnd 免打扰开关）。"""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """通用键值写入并持久化。"""
        with self._lock:
            self._data[key] = value
            self._save()

    # ---------- R25D 会话文件夹（对标 TG 聊天文件夹分组） ----------
    def folders(self) -> list:
        """返回 [{"name": str, "keys": [会话键,...]}, ...]；坏数据容错跳过。"""
        with self._lock:
            raw = self._data.get("folders")
            if not isinstance(raw, list):
                return []
            out = []
            for f in raw:
                if not isinstance(f, dict):
                    continue
                name = f.get("name")
                if not isinstance(name, str) or not name:
                    continue
                keys = f.get("keys")
                out.append({"name": name,
                            "keys": [str(k) for k in keys] if isinstance(keys, list) else []})
            return out

    def set_folders(self, folders: list) -> None:
        """整体替换文件夹列表并持久化。"""
        with self._lock:
            self._data["folders"] = folders
            self._save()

    # ---------- R8 账号/无边框（薄封装，底层仍是通用 get/set） ----------
    def default_account(self) -> str | None:
        return self.get("default_account")

    def set_default_account(self, nick: str) -> None:
        self.set("default_account", nick)

    def has_passcode(self) -> bool:
        return bool(self.get("passcode"))

    def passcode(self) -> str | None:
        return self.get("passcode")

    def set_passcode(self, stored: str | None) -> None:
        self.set("passcode", stored)   # None 或 "" = 清除

    def frameless(self) -> bool:
        return bool(self.get("frameless", True))

    def set_frameless(self, b: bool) -> None:
        self.set("frameless", bool(b))

    # ---------- R60 关键词提醒（静音会话例外放行通知） ----------
    def keywords(self) -> list:
        """关键词提醒列表：逗号分隔的原始串解析为去空小写词列表（坏数据容错）。"""
        return parse_keywords(self.get("kw_words", "") or "")

    def set_keywords(self, s: str) -> None:
        """保存关键词提醒原始串（UI 输入，纯文本持久化到 prefs）。"""
        self.set("kw_words", str(s or ""))

    # ---------- 聊天主题（气泡/聊天区配色叠层，独立于全局皮肤） ----------
    def chat_theme(self) -> str:
        """当前聊天主题键（""=跟随皮肤默认）。坏数据回落空串。"""
        v = self.get("chat_theme", "")
        return str(v) if v else ""

    def set_chat_theme(self, key: str) -> None:
        """设置聊天主题键并持久化（""=跟随皮肤默认）。"""
        self.set("chat_theme", str(key or ""))

    # ---------- R30B 免打扰时段 ----------
    def dnd_range(self) -> dict:
        """免打扰时段配置 {"on": bool, "start": "HH:MM", "end": "HH:MM"}（坏数据容错）。"""
        raw = self.get("dnd_range") or {}
        if not isinstance(raw, dict):
            raw = {}
        start = str(raw.get("start") or "23:00")
        end = str(raw.get("end") or "08:00")
        return {"on": bool(raw.get("on")), "start": start, "end": end}

    def set_dnd_range(self, on: bool, start: str, end: str) -> None:
        self.set("dnd_range", {"on": bool(on), "start": str(start),
                               "end": str(end)})

    # ---------- R35 多账号档案（会话状态随档案切换） ----------
    def known_accounts(self) -> list:
        """已知账号列表（profiles 键 + 默认账号去重，按字母序）。"""
        with self._lock:
            accs = set(self._data.get("profiles") or {})
            d = self._data.get("default_account")
            if d:
                accs.add(str(d))
            return sorted(accs)

    def active_account(self) -> str | None:
        return self.get("active_profile")

    def remember_account(self, nick: str) -> None:
        """登记账号并设为默认。首个接入档案体系的账号认领现有顶层会话状态
        （pinned/muted/archived/drafts），老用户升级后无感迁移。"""
        with self._lock:
            profs = self._data.setdefault("profiles", {})
            if not profs:
                profs[nick] = {k: self._data.get(k) for k in _PROFILE_KEYS}
                self._data["active_profile"] = nick
            elif nick not in profs:
                profs[nick] = {}
            self._data["default_account"] = nick
            self._save()

    def switch_profile(self, nick: str) -> None:
        """切换激活档案：换出/换入 pinned/muted/archived/drafts。
        顶层键始终保存当前档案的最新值（与既有读写路径兼容）；
        换出时快照进 profiles，换入时覆盖顶层。"""
        with self._lock:
            profs = self._data.setdefault("profiles", {})
            cur = self._data.get("active_profile")
            if cur and cur != nick:
                profs[cur] = {k: self._data.get(k) for k in _PROFILE_KEYS}
            prof = profs.setdefault(nick, {})
            for k in _PROFILE_KEYS:
                v = prof.get(k)
                if k == "drafts":
                    self._data[k] = dict(v) if isinstance(v, dict) else {}
                else:
                    self._data[k] = [str(x) for x in v] if isinstance(v, list) else []
            self._data["active_profile"] = nick
            self._save()


# ---------- R60 关键词解析（纯函数，便于单测） ----------
def parse_keywords(s) -> list:
    """把逗号/中文逗号分隔的关键词串解析为去空白的小写词列表（空项剔除、去重）。"""
    if not s:
        return []
    parts = str(s).replace("，", ",").split(",")
    out = []
    for p in parts:
        p = p.strip().lower()
        if p and p not in out:
            out.append(p)
    return out


# ---------- 功能② 收藏限量（纯函数，便于单测） ----------
def trim_stars(stars: dict, limit: int = 200) -> dict:
    """收藏列表限量：递减并删除「被收藏时间最旧 / seq 最旧」的条目（去重由 dict 键天然保证）。

    改变 `stars` 并返回之；未超限则原样返回。limit<=0 视为清空。
    """
    if not isinstance(stars, dict):
        return stars
    if limit <= 0:
        stars.clear()
        return stars
    if len(stars) <= limit:
        return stars
    for old in sorted(stars, key=lambda s: (stars[s].get("ts", 0) if isinstance(stars[s], dict) else 0, s))[:len(stars) - limit]:
        stars.pop(old, None)
    return stars


# ---------- R69A3 摸鱼报告聚合（纯函数，便于单测） ----------
_FISH_KEYS = ("sec", "games", "msgs")


def fish_add_day(days, day: str, sec: float = 0.0, games: int = 0,
                 msgs: int = 0, keep: int = 60) -> dict:
    """把当日数据累加进 days（{day: {"sec","games","msgs"}}），只保留最近 keep 天。

    返回新的 days（不修改入参），坏数据自动纠正为数值。
    """
    out = dict(days) if isinstance(days, dict) else {}
    rec = out.get(day)
    if not isinstance(rec, dict):
        rec = {"sec": 0.0, "games": 0, "msgs": 0}
    rec = {"sec": float(rec.get("sec", 0) or 0) + float(sec),
           "games": int(rec.get("games", 0) or 0) + int(games),
           "msgs": int(rec.get("msgs", 0) or 0) + int(msgs)}
    out[day] = rec
    if keep > 0 and len(out) > keep:
        for k in sorted(out)[:-keep]:
            out.pop(k, None)
    return out


def fish_summary(days, today: str, window: int = 7) -> dict:
    """汇总报告：今日 + 最近 window 天（含今日）三项合计。"""
    days = days if isinstance(days, dict) else {}
    week_keys = sorted(days)[-window:] if window > 0 else sorted(days)

    def _sum(ks):
        sec = games = msgs = 0.0
        for k in ks:
            r = days.get(k) or {}
            sec += float(r.get("sec", 0) or 0)
            games += int(r.get("games", 0) or 0)
            msgs += int(r.get("msgs", 0) or 0)
        return sec, games, msgs

    t = _sum([today])
    w = _sum(week_keys)
    return {"today": {"sec": t[0], "games": t[1], "msgs": t[2]},
            "week": {"sec": w[0], "games": w[1], "msgs": w[2]},
            "week_days": len(week_keys)}


# ---------- R30B 免打扰时段（纯函数，便于单测） ----------
def in_dnd_range(rng, now=None) -> bool:
    """判断当前时刻是否落在免打扰时段内。
    rng = {"on": bool, "start": "HH:MM", "end": "HH:MM"}；支持跨天
    （start > end 视为隔夜区间，如 23:00~08:00）；坏数据/未开启一律 False。"""
    if not isinstance(rng, dict) or not rng.get("on"):
        return False

    def _min(s):
        try:
            h, m = str(s).split(":")
            h, m = int(h), int(m)
        except (ValueError, AttributeError):
            return None
        return h * 60 + m if (0 <= h <= 23 and 0 <= m <= 59) else None

    a, b = _min(rng.get("start")), _min(rng.get("end"))
    if a is None or b is None:
        return False
    lt = time.localtime(now if now is not None else time.time())
    cur = lt.tm_hour * 60 + lt.tm_min
    if a == b:
        return True                            # 起止相同 = 全天免打扰
    if a < b:
        return a <= cur < b
    return cur >= a or cur < b                 # 跨天（如 23:00~08:00）
