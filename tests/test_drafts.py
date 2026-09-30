# -*- coding: utf-8 -*-
"""test_drafts.py —— R12 草稿自动保存（会话级 + prefs 持久化）纯逻辑。

不建真实 GUI：用桩对象绑定 ChatWindow 的草稿方法（_save_draft/_restore_draft/
_clear_draft/_persist_drafts），只验证内存 dict 与 prefs 落盘行为。
"""
from client import ChatWindow
from prefs import Prefs


class _FakeEntry:
    """最小 Text 桩：记录 insert 的内容，供 _restore_draft 回填。"""

    def __init__(self):
        self.text = ""

    def delete(self, a, b):
        self.text = ""

    def insert(self, a, s):
        self.text = s

    def see(self, a):
        pass

    def focus_set(self):
        pass


class _Stub:
    """复用 ChatWindow 草稿方法的轻量桩。"""

    def __init__(self, prefs, uid=1):
        self.core = type("C", (), {"uid": uid})()
        self.view = ("public", None)
        self._prefs = prefs
        self._drafts = dict(prefs.get("drafts", {}) or {})
        self._draft_ts: dict = {}              # R29B：草稿时间戳（换端合并用）
        self._push_draft = lambda key: None    # R29B：旧 R12 用例只测本地行为，跳过服务器推送
        self.entry = _FakeEntry()
        # 输入历史状态（_save_draft 浏览历史时的暂存草稿判定）
        self._send_hist: dict = {}
        self._hist_pos: dict = {}
        self._hist_draft: dict = {}
        self._hist_cur = None

    def _pin_key(self, ch, to):
        if ch == "public":
            return "public"
        a, b = sorted((int(self.core.uid), int(to)))
        return f"private:{a}:{b}"

    def _hist_key(self):
        ch, to = self.view
        return self._pin_key(ch, to)

    def _entry_text(self):
        return self.entry.text

    def _bind(self, name):
        return getattr(ChatWindow, name).__get__(self)


def test_save_restore_roundtrip(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    save, restore = s._bind("_save_draft"), s._bind("_restore_draft")

    # 公共频道输入 → 保存；切到私聊不误恢复；切回公共恢复
    s.view = ("public", None)
    s.entry.text = "公共草稿A"
    save()
    assert s._drafts.get("public") == "公共草稿A"

    s.view = ("private", 2)
    s.entry.text = ""
    restore()
    assert s.entry.text == ""                       # 私聊无草稿

    s.view = ("public", None)
    restore()
    assert s.entry.text == "公共草稿A"               # 恢复公共草稿


def test_empty_save_clears_draft(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    save = s._bind("_save_draft")
    s._drafts["public"] = "旧草稿"
    s.view = ("public", None)
    s.entry.text = "   "                            # 仅空白 = 无草稿
    save()
    assert "public" not in s._drafts


def test_save_draft_while_browsing_history(tmp_path):
    """↑ 翻历史且未改动时，切走应保存进入浏览前的暂存草稿。"""
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    save = s._bind("_save_draft")
    s.view = ("public", None)
    s._send_hist["public"] = ["旧消息1", "旧消息2"]
    s._hist_pos["public"] = 0                       # 正停在"旧消息1"
    s._hist_draft["public"] = "我原本打的字"
    s.entry.text = "旧消息1"                        # 未改动
    save()
    assert s._drafts.get("public") == "我原本打的字"


def test_save_draft_browsing_edited_keeps_edit(tmp_path):
    """翻历史后又改了内容 → 保存的是改后的输入。"""
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    save = s._bind("_save_draft")
    s.view = ("public", None)
    s._send_hist["public"] = ["旧消息1"]
    s._hist_pos["public"] = 0
    s._hist_draft["public"] = "原草稿"
    s.entry.text = "旧消息1（改过）"
    save()
    assert s._drafts.get("public") == "旧消息1（改过）"


def test_clear_draft_mem_and_disk(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    p.set("drafts", {"public": "要清的", "group:7": "留着"})
    s = _Stub(p)
    assert "public" in s._drafts
    s._bind("_clear_draft")("public")
    assert "public" not in s._drafts
    assert p.get("drafts", {}) == {"group:7": "留着"}   # 磁盘同步移除


def test_persist_drafts_merges(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    p.set("drafts", {"group:7": "已有"})
    s = _Stub(p)
    s._drafts["public"] = "新草稿"
    s._bind("_persist_drafts")()
    d = p.get("drafts", {})
    assert d["public"] == "新草稿"
    assert d["group:7"] == "已有"


def test_persist_drafts_skips_blank(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    p.set("drafts", {"public": "已有草稿"})
    s = _Stub(p)
    s._drafts["group:7"] = ""                        # 空/空白不落盘
    s._drafts["private:1:2"] = "  "
    s._bind("_persist_drafts")()
    d = p.get("drafts", {})
    assert "public" in d
    assert "group:7" not in d
    assert "private:1:2" not in d


def test_private_key_sorted(tmp_path):
    """私聊 key 排序（与历史存储同键），uid 大小无关。"""
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p, uid=9)
    assert s._pin_key("private", 2) == "private:2:9"
    s2 = _Stub(p, uid=2)
    assert s2._pin_key("private", 9) == "private:2:9"


# ---------- R12 输入历史 ↑/↓ 回显 ----------

def test_record_send_dedup_adjacent(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    rec = s._bind("_record_send")
    s.view = ("public", None)
    rec("A"); rec("B"); rec("B")            # 相邻重复去重
    assert s._send_hist["public"] == ["B", "A"]


def test_record_send_blank_skipped(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    rec = s._bind("_record_send")
    s.view = ("public", None)
    rec("   ")
    assert "public" not in s._send_hist


def test_hist_nav_up_down_clamp(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    nav = s._bind("_hist_nav")
    s._send_hist["public"] = ["新3", "中2", "旧1"]
    s.view = ("public", None)
    assert nav(1) == "break"                # ↑ 首条
    assert s.entry.text == "新3"
    nav(1); assert s.entry.text == "中2"
    nav(1); assert s.entry.text == "旧1"    # 到底钳制
    nav(1); assert s.entry.text == "旧1"    # 越界仍钳在最后一条
    nav(-1); assert s.entry.text == "中2"
    nav(-1); assert s.entry.text == "新3"
    nav(-1); assert s.entry.text == ""      # 退回底部 → 恢复空输入


def test_hist_nav_down_restores_stashed_draft(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    nav = s._bind("_hist_nav")
    s._send_hist["public"] = ["旧消息"]
    s.view = ("public", None)
    s.entry.text = "正在打的字"
    nav(1)
    assert s.entry.text == "旧消息"
    assert s._hist_draft["public"] == "正在打的字"
    nav(-1)
    assert s.entry.text == "正在打的字"     # ↓ 到底恢复进入前的输入


def test_hist_nav_no_history_returns_none(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    s = _Stub(p)
    nav = s._bind("_hist_nav")
    s.view = ("private", 2)
    assert nav(1) is None
    assert s.entry.text == ""
