# -*- coding: utf-8 -*-
"""widgets/global_search.py —— 全局消息搜索（R9+，对标 TG 顶栏 SearchBox 搜全量历史）。

三部分：
- `scan_all()`：**纯函数**——扫 `history/*.jsonl`（chunk 级磁盘全量），文件名→channel_key
  （`_channel_key` 的 safe 形式反向 `_`→`:`），逐行匹配 `raw.text`（大小写不敏感），
  返回每个会话的命中数 + 首条命中 `(seq,text,ts,nick)`。可单测（保留旧聚合语义）。
- `MessageIndex` / `load_index()` / `search_messages()`：**增量内存消息索引**——
  一次性读入全部历史到内存（磁盘只建一次索引），后续查询只做内存检索并按 ts 倒序，
  返回**跨会话的单条命中消息** `{key,ch,to,name,seq,ts,nick,text,uid,kind}`。可单测。
- D13 过滤增强（纯函数，可单测）：`msg_kind()` 判定消息类型 + `filter_hits()`
  按 发送人 / 类型 / 时间 二次过滤（只作用于已命中的结果，不改检索语义）。
- `GlobalSearchBox(tk.Toplevel)`：自包含结果窗（参考 image_viewer.py，不 `grab_set`），
  顶部搜索框 + Text 结果列表（命中词高亮，跨会话逐条展示），后台 daemon 线程建索引、
  主线程 `after` 轮询渲染；点击/回车回调 `on_pick(ch,to,seq,query)` 交 client 切会话定位到该条。
"""
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import theme

_DEBOUNCE_MS = 260        # 输入停顿后起扫
_POLL_MS = 120            # 主线程轮询完成队列
_RESULT_H = 320
_RESULT_W = 460
_MAX_HITS = 300           # 消息级结果上限（防超大历史刷屏）

# D13 类型过滤：单一来源的「类型 → 中文标签」，GUI 与测试共用
MSG_KIND_LABEL = {
    "text": "文本", "image": "图片", "file": "文件", "voice": "语音",
    "fwd": "合并转发", "poll": "投票", "link": "链接",
    "sticker": "贴纸", "rich": "富文本",
}
_KIND_ORDER = tuple(MSG_KIND_LABEL)       # 下拉展示顺序（稳定，便于测试）
_SOLO_STICKER_RE = re.compile(r"^\[:([A-Za-z0-9_]{1,24}):\]$")
_URL_RE = re.compile(r"https?://", re.IGNORECASE)

_TIME_CHOICES = (("全部时间", None), ("今天", 1), ("近7天", 7), ("近30天", 30))


def _is_dark(skin: str) -> bool:
    """按主题名判断深浅（用于当前项底色的深浅自适应）。"""
    return "dark" in (skin or "").lower()


# ---------- 磁盘扫描纯函数（可单测） ----------

def _safe_to_key(fname: str) -> str:
    """`private_1_2.jsonl` / `group_7.jsonl` / `public.jsonl` -> channel_key。"""
    return fname[:-len(".jsonl")].replace("_", ":")


def _parse_key(key: str) -> tuple:
    """channel_key -> (channel, to) ；private 的 to 为两端 uid 集合，对端判定交给 _display_name。"""
    parts = key.split(":")
    ch = parts[0]
    if ch == "public":
        return ("public", None)
    if ch == "private" and len(parts) == 3:
        return ("private", (int(parts[1]), int(parts[2])))
    if ch == "group" and len(parts) == 2:
        return ("group", int(parts[1]))
    return (ch, None)


def _display_name(key: str, roster: dict, groups: dict, me_uid) -> str:
    """把 channel_key 变成人类可读会话名（roster/groups 查不到就回退）。"""
    if key == "public":
        return "公共频道"
    parts = key.split(":")
    if parts[0] == "private" and len(parts) == 3:
        a, b = int(parts[1]), int(parts[2])
        other = b if (me_uid is not None and a == me_uid) else a
        u = roster.get(other)
        return (u.get("nick") or f"私聊 #{other}") if u else f"私聊 #{other}"
    if parts[0] == "group" and len(parts) == 2:
        gid = int(parts[1])
        g = groups.get(gid)
        return (g.get("name") or f"群 {gid}") if g else f"群 {gid}"
    return key


def scan_all(history_dir: str, query: str, roster=None, groups=None,
             me_uid=None) -> list:
    """全量扫描本地历史。（幂等、无副作用。）

    返回按命中数降序的 list，每项：
      {key, ch, to, name, count, first:{seq,text,ts,nick}}
    """
    q = (query or "").strip().lower()
    roster = roster or {}
    groups = groups or {}
    if not q or not history_dir or not os.path.isdir(history_dir):
        return []
    results = []
    try:
        names = os.listdir(history_dir)
    except OSError:
        return []
    for fn in names:
        if not fn.endswith(".jsonl"):
            continue
        key = _safe_to_key(fn)
        ch, to = _parse_key(key)
        path = os.path.join(history_dir, fn)
        count = 0
        first = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        m = json.loads(line)
                    except ValueError:
                        continue
                    txt = m.get("text")
                    if not isinstance(txt, str):
                        continue
                    if q in txt.lower():
                        if count == 0:
                            first = {"seq": m.get("seq"), "text": txt,
                                     "ts": m.get("ts"), "nick": m.get("nick")}
                        count += 1
        except (FileNotFoundError, OSError, ValueError):
            continue
        if count:
            results.append({
                "key": key, "ch": ch, "to": to,
                "name": _display_name(key, roster, groups, me_uid),
                "count": count, "first": first,
            })
    results.sort(key=lambda r: r["count"], reverse=True)
    return results


# ---------- D13 过滤纯函数（可单测） ----------

def msg_kind(msg: dict) -> str:
    """判定一条消息的类型（D13）；优先级＝附件语义强弱，未识别 → ``text``。

    字段口径与 ``web.py addMsg`` / ``widgets/msg_list.py`` 一致：
    poll / file{kind} / voice / fp / sticker / preview / rich / 正文。
    """
    if not isinstance(msg, dict):
        return "text"
    if msg.get("poll"):
        return "poll"
    f = msg.get("file")
    if isinstance(f, dict):
        return "image" if f.get("kind") == "image" else "file"
    if msg.get("voice"):
        return "voice"
    if msg.get("fp"):
        return "fwd"
    txt = msg.get("text") or ""
    if msg.get("sticker") or _SOLO_STICKER_RE.match(txt.strip()):
        return "sticker"
    if msg.get("preview"):
        return "link"
    if msg.get("rich"):
        return "rich"
    if _URL_RE.search(txt):
        return "link"
    return "text"


def _time_floor(days, now: float):
    """时间下限秒；``days<=1`` 取「今天 0 点」，否则取 ``now-days*86400``。"""
    if days is None:
        return None
    if days <= 1:
        lt = time.localtime(now)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return now - days * 86400.0


def filter_hits(hits, sender=None, kind=None, days=None, now=None) -> list:
    """对命中结果做 发送人/类型/时间 二次过滤（纯函数，参数为 None 即不过滤）。

    保持入参顺序（已是 ts 倒序）；缺 ``ts`` 的结果在启用时间过滤时被剔除。
    """
    if not hits:
        return []
    if sender is None and kind is None and days is None:
        return list(hits)
    now = time.time() if now is None else float(now)
    floor = _time_floor(days, now)
    out = []
    for it in hits:
        if sender is not None and it.get("uid") != sender:
            continue
        if kind is not None and it.get("kind", "text") != kind:
            continue
        if floor is not None:
            try:
                if float(it.get("ts")) < floor:
                    continue
            except (TypeError, ValueError):
                continue
        out.append(it)
    return out


def hit_senders(hits) -> list:
    """从命中聚合发送人下拉项：``[(label, uid), ...]``（按昵称排序、去重）。"""
    seen, out = set(), []
    for it in hits:
        uid = it.get("uid")
        if uid is None or uid in seen:
            continue
        seen.add(uid)
        out.append(((it.get("nick") or "?").strip() + f" (#{uid})", uid))
    out.sort(key=lambda p: p[0])
    return out


def hit_kinds(hits) -> list:
    """从命中聚合类型下拉项：``[(label, kind), ...]``（固定顺序，只列出现过的）。"""
    present = {it.get("kind", "text") for it in hits}
    return [(MSG_KIND_LABEL[k], k) for k in _KIND_ORDER if k in present]


# ---------- 增量内存消息索引（R9+ 消息级） ----------

class MessageIndex:
    """跨会话消息索引：磁盘只建一次，后续查询纯内存检索（按 ts 倒序）。

    ``load(history_dir)`` 全量读入 → ``search(q)`` 检索 → ``add(key, msg)`` 增量追加。
    每项为 ``{"key", "seq", "ts", "nick", "low", "text", "rich", "uid", "kind"}``，
    只保留检索与 D13 过滤所需的最小字段（无正文的消息仍按原语义跳过）。
    """

    __slots__ = ("_items",)

    def __init__(self):
        self._items = []

    def add(self, key: str, msg: dict) -> None:
        txt = msg.get("text")
        if not isinstance(txt, str) or not txt:
            return
        self._items.append({
            "key": key, "seq": msg.get("seq"), "ts": msg.get("ts"),
            "nick": msg.get("nick") or "?", "low": txt.lower(),
            "text": txt, "rich": msg.get("rich"),
            "uid": msg.get("uid"), "kind": msg_kind(msg),   # D13 过滤维度
        })

    def load(self, history_dir: str) -> None:
        """读入 ``history_dir`` 下所有 ``*.jsonl``（文件名 → channel_key）。"""
        if not history_dir or not os.path.isdir(history_dir):
            return
        try:
            names = os.listdir(history_dir)
        except OSError:
            return
        for fn in names:
            if not fn.endswith(".jsonl"):
                continue
            key = _safe_to_key(fn)
            path = os.path.join(history_dir, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            m = json.loads(line)
                        except ValueError:
                            continue
                        self.add(key, m)
            except (FileNotFoundError, OSError, ValueError):
                continue

    def search(self, query: str, limit: int = 300) -> list:
        """大小写不敏感子串匹配，按 ts 倒序返回最多 ``limit`` 条命中。"""
        q = (query or "").strip().lower()
        if not q:
            return []
        out = [it for it in self._items if q in it["low"]]
        out.sort(key=lambda it: it.get("ts") or 0, reverse=True)
        return out[:limit]

    def __len__(self):
        return len(self._items)


def load_index(history_dir: str) -> MessageIndex:
    """建一次内存索引（幂等、无副作用），供多次检索复用。"""
    idx = MessageIndex()
    idx.load(history_dir)
    return idx


def search_messages(history_dir, query, roster=None, groups=None,
                    me_uid=None, limit: int = 300) -> list:
    """消息级跨会话搜索：建索引 → 内存检索 → 附上人类可读会话名。可单测。

    返回按 ts 倒序的 list，每项：
      {key, ch, to, name, seq, ts, nick, text, rich}
    """
    roster = roster or {}
    groups = groups or {}
    hits = load_index(history_dir).search(query, limit)
    for it in hits:
        it["ch"], it["to"] = _parse_key(it["key"])
        it["name"] = _display_name(it["key"], roster, groups, me_uid)
    return hits


# ---------- GUI ----------

class GlobalSearchBox(tk.Toplevel):
    """全局消息级搜索结果窗（R9+）。

    on_pick(ch, to, seq, query)：用户点某条命中，交 client 切换会话、滚动定位并高亮该条。
    第一次输入时后台建一次内存索引；之后逐次查询只做内存检索。Text 结果列表命中词高亮。
    D13：顶部三个下拉（发送人/类型/时间）对已命中结果做二次过滤；非文本命中带类型角标；
    回车跳转后自动前进到下一条命中（结果内连续跳转）。
    """

    _HIT_FG = "#ff7043"      # 命中词——珊瑚高亮
    _ACTIVE_BG = "transparent"

    def __init__(self, master, history_dir, roster=None, groups=None,
                 me_uid=None, skin="office", on_pick=None, font=None):
        sk = theme.get_skin(skin)
        super().__init__(master)
        self._history_dir = history_dir
        self._roster = roster or {}
        self._groups = groups or {}
        self._me_uid = me_uid
        self._skin = sk
        self._on_pick = on_pick
        self._queue = queue.Queue()
        self._run_id = 0
        self._index = None      # 内存索引：首次查询建一次，之后复用

        self.title("全局搜索")
        self.configure(bg=sk["window_bg"])
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.resizable(False, False)

        f = tkfont.Font(root=master, font=font) if font else None
        ef = f or tkfont.nametofont("TkDefaultFont")

        head = tk.Frame(self, bg=sk["window_bg"])
        head.pack(fill="x", padx=8, pady=(8, 4))
        self.entry = tk.Entry(head, font=ef, bg=sk["input_bg"],
                              fg=sk["fg"], relief="flat",
                              highlightthickness=1,
                              highlightbackground=sk.get("glass_border"))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<KeyRelease>", self._debounce)
        self.entry.bind("<Down>", lambda e: self._move(1))
        self.entry.bind("<Up>", lambda e: self._move(-1))
        self.entry.bind("<Return>", lambda e: self._pick_sel())
        self.count_lb = tk.Label(head, text="", bg=sk["window_bg"], fg=sk["sub"],
                                 font=(ef.cget("family"), ef.cget("size") - 2))
        self.count_lb.pack(side="left", padx=(6, 0))

        # D13 过滤条：发送人 / 类型 / 时间（结果内二次过滤，不改检索语义）
        fbar = tk.Frame(self, bg=sk["window_bg"])
        fbar.pack(fill="x", padx=8, pady=(0, 4))
        cb_style = {"state": "readonly", "font": ef, "width": 14}
        self.sender_cb = ttk.Combobox(fbar, values=["全部发送人"], **cb_style)
        self.kind_cb = ttk.Combobox(fbar, values=["全部类型"], **cb_style)
        self.time_cb = ttk.Combobox(
            fbar, values=[t for t, _d in _TIME_CHOICES], **cb_style)
        for cb in (self.sender_cb, self.kind_cb, self.time_cb):
            cb.pack(side="left", padx=(0, 6))
            cb.set(cb.cget("values")[0])
            cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filters())

        body = tk.Frame(self, bg=sk["window_bg"])
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.text = tk.Text(body, bg=sk.get("list_bg", sk["window_bg"]),
                            fg=sk["fg"], relief="flat", wrap="none",
                            highlightthickness=0, borderwidth=0,
                            padx=6, pady=4, cursor="hand2", font=ef,
                            takefocus=False, exportselection=False)
        vsb = tk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)

        # 标签样式
        self.text.tag_configure("dim", foreground=sk.get("sub", sk["fg"]))
        self.text.tag_configure("name", foreground=sk.get("accent", sk["fg"]))
        self.text.tag_configure("hit", foreground=self._HIT_FG,
                                font=(ef.cget("family"), ef.cget("size"), "bold"))
        self.text.tag_configure("active_bg", background="#3a3f44" if _is_dark(skin) else "#f0ebe3")

        self.bind("<Escape>", lambda e: self.destroy())

        self._items = []          # 命中消息项（与 _render 顺序对齐）
        self._raw = []            # D13：未经过滤的原始命中（过滤条的数据源）
        self._cur_q = ""          # D13：当前查询词（过滤重渲染时复用高亮）
        self._sender_map = {}     # D13：发送人下拉 label -> uid
        self._kind_map = {}       # D13：类型下拉 label -> kind
        self._active = -1
        self._after_id = None
        self._center()
        self.entry.focus_set()
        self._poll()

    def _center(self) -> None:
        try:
            master = self.master
            if master.winfo_exists() and master.winfo_ismapped():
                x0 = master.winfo_rootx()
                y0 = master.winfo_rooty()
                w = master.winfo_width()
                h = master.winfo_height()
                self.geometry(f"+{x0 + (w - _RESULT_W) // 2}+{y0 + 40}")
            else:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                self.geometry(f"+{(sw - _RESULT_W) // 2}+{(sh - _RESULT_H) // 2}")
            self.minsize(_RESULT_W, _RESULT_H)
        except tk.TclError:
            pass

    # ---------- 输入防抖 + 后台建索引/检索 ----------
    def _debounce(self, _e=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(_DEBOUNCE_MS, self._start_scan)

    def _start_scan(self) -> None:
        q = self.entry.get()
        self._after_id = None
        self._run_id += 1
        rid = self._run_id
        history_dir = self._history_dir
        roster = dict(self._roster)
        groups = dict(self._groups)
        me_uid = self._me_uid

        def work():
            try:
                idx = self._index or load_index(history_dir)
                self._index = idx                 # 未命中 count 前也缓存（daemon 安全）
                res = idx.search(q, _MAX_HITS)
                out = []
                for it in res:
                    it["ch"], it["to"] = _parse_key(it["key"])
                    it["name"] = _display_name(it["key"], roster, groups, me_uid)
                    out.append(it)
            except Exception:
                out = []
            try:
                self._queue.put((rid, q.lower(), out))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                rid, q, res = self._queue.get_nowait()
                if rid == self._run_id:
                    self._active = 0
                    self._cur_q = q
                    self._raw = list(res)
                    self._refresh_filters()
                    self._apply_filters()
                    continue
        except queue.Empty:
            pass
        try:
            self.after(_POLL_MS, self._poll)
        except tk.TclError:
            pass

    # ---------- D13 过滤条 ----------
    def _set_combo(self, cb, values, keep: bool = True) -> None:
        """刷新下拉候选；旧选择仍在候选里就保留，否则回落到首项。"""
        cur = cb.get()
        cb.configure(values=values)
        if keep and cur in values:
            cb.set(cur)
        else:
            cb.set(values[0])

    def _refresh_filters(self) -> None:
        """按最新原始命中重建三个下拉（保留用户已选项，避免每次输入被重置）。"""
        snd = hit_senders(self._raw)
        self._sender_map = dict(snd)
        self._set_combo(self.sender_cb, ["全部发送人"] + [l for l, _u in snd])
        kds = hit_kinds(self._raw)
        self._kind_map = dict(kds)
        self._set_combo(self.kind_cb, ["全部类型"] + [l for l, _k in kds])
        self._set_combo(self.time_cb, [t for t, _d in _TIME_CHOICES])

    def _apply_filters(self) -> None:
        """按过滤条重渲染（纯过滤；不触发重新检索，索引/命中缓存不动）。"""
        sender = self._sender_map.get(self.sender_cb.get())
        kind = self._kind_map.get(self.kind_cb.get())
        days = dict(_TIME_CHOICES).get(self.time_cb.get())
        res = filter_hits(self._raw, sender=sender, kind=kind, days=days)
        self._render(self._cur_q, res)

    def _render(self, q: str, res: list) -> None:
        self._items = list(res)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        # 重新绑定点击标签（每次渲染先清除旧的 resN tag 绑定）
        if not res:
            self.text.configure(state="disabled")
            tot = len(self._raw)
            self.count_lb.config(
                text=f"无匹配（共 {tot} 条）" if tot else "无结果")
            return
        tot = len(self._raw)
        suffix = f" / 共 {tot}" if tot != len(res) else ""
        self.count_lb.config(
            text=f"{len(res)} 条{suffix} · {len(self._unique_convos(res))} 会话")
        ql = q or ""
        for i, it in enumerate(res):
            self._add_result(i, it, ql)
        self.text.configure(state="disabled")
        # 默认定位首条
        self._activate(0)

    @staticmethod
    def _unique_convos(res: list) -> list:
        seen, uniq = set(), []
        for it in res:
            if it["key"] not in seen:
                seen.add(it["key"])
                uniq.append(it["key"])
        return uniq

    def _add_result(self, i: int, it: dict, ql: str) -> None:
        """写一行结果：会话名·昵称·时刻（dim）+ 摘要（命中词珊瑚高亮）。"""
        tm = ""
        if it.get("ts"):
            try:
                tm = time.strftime("%H:%M", time.localtime(it["ts"]))
            except (ValueError, OSError):
                tm = ""
        nick = (it.get("nick") or "?").strip()
        name = it.get("name") or it["key"]
        k = it.get("kind", "text")          # D13：非文本命中加类型角标
        kb = "" if k == "text" else f"[{MSG_KIND_LABEL.get(k, k)}] "
        title = f"{name} · {nick} · {tm} | {kb}"
        snippet = (it.get("text") or "").replace("\n", " ").strip()
        if len(snippet) > 62:
            snippet = snippet[:62] + "…"

        self.text.insert("end", "\n")
        line_start = self.text.index("end-1c")                    # 新行起点
        self.text.insert("end", "  ")
        self.text.insert("end", title, ("name",))
        off = len("  ") + len(title)
        self.text.insert("end", snippet, (f"res{i}",))
        self.text.insert("end", "\n")
        # 命中词高亮（在摘要片段内定位）
        if ql:
            low = snippet.lower()
            pos = 0
            while True:
                p = low.find(ql, pos)
                if p < 0:
                    break
                a = f"{line_start}+{off + p}c"
                b = f"{line_start}+{off + p + len(ql)}c"
                try:
                    self.text.tag_add("hit", a, b)
                except tk.TclError:
                    pass
                pos = p + max(1, len(ql))
        # 整行（除首行）绑点击 → 选中该条
        try:
            self.text.tag_add(f"res{i}", f"{line_start}+2c", self.text.index("end-1c"))
        except tk.TclError:
            pass
        self.text.tag_bind(f"res{i}", "<Button-1>", lambda e, i=i: self._pick(i))
        self.text.tag_bind(f"res{i}", "<Double-Button-1>", lambda e, i=i: self._pick(i))

    def _activate(self, i: int) -> None:
        """把第 i 条结果的海报行整行加深底（当前项），并滚入视野。"""
        self.text.tag_remove("active_bg", "1.0", "end")
        if i < 0 or i >= len(self._items):
            self._active = -1
            return
        self._active = i
        # 定位该结果行的起点（第 i 条对应 Text 第 2*i 行开头 + 2 字符的缩进）
        line_no = 1 + i * 2
        start = f"{line_no}.2"
        end = f"{line_no + 1}.0"
        try:
            self.text.tag_add("active_bg", start, end)
            self.text.see(start)
        except tk.TclError:
            pass

    def _move(self, d: int) -> None:
        n = len(self._items)
        if not n:
            return "break"
        cur = self._active if self._active >= 0 else 0
        self._activate((cur + d) % n)
        return "break"

    def _pick_sel(self, _e=None):
        i = self._active
        if 0 <= i < len(self._items):
            self._pick(i)
            # D13：回车后自动前进下一条命中（连按回车＝结果内连续跳转）
            if len(self._items) > 1:
                self._move(1)
        return "break"

    def _pick(self, i: int):
        if not (0 <= i < len(self._items)):
            return
        it = self._items[i]
        q = self.entry.get().strip()
        if callable(self._on_pick):
            self._on_pick(it["ch"], it["to"], it["seq"], q)
        return "break"


# 供 client 复用
def open_between(master, core, skin, on_pick, font=None):
    """开启全局搜索窗：从 core 取 history 目录 / roster / groups / me_uid。"""
    return GlobalSearchBox(
        master, core._history._dir if hasattr(core, "_history") else "",
        roster=getattr(core, "roster", {}), groups=getattr(core, "groups", {}),
        me_uid=getattr(core, "uid", None), skin=skin, on_pick=on_pick, font=font)