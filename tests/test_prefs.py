# -*- coding: utf-8 -*-
"""prefs 本地偏好单元测试：置顶/静音/归档/免打扰的增删与对象存储行为。"""
import json
import os

from prefs import Prefs, parse_keywords


def _tmp(tmp_path):
    return Prefs(str(tmp_path / "prefs.json"))


def test_archive_toggle_roundtrip(tmp_path):
    p = _tmp(tmp_path)
    assert p.is_archived("private:1:2") is False
    assert p.toggle_archive("private:1:2") is True
    assert p.is_archived("private:1:2") is True
    assert "private:1:2" in p.archived()
    # 取消归档
    assert p.toggle_archive("private:1:2") is False
    assert p.archived() == []


def test_hotkeys_dict_persist_and_override(tmp_path):
    """r5b：快捷键偏好以 dict 存于 prefs，改绑/禁用后可读回。"""
    p = _tmp(tmp_path)
    assert p.get("hotkeys", {}) == {}
    p.set("hotkeys", {"ctrl_f": "<Control-p>", "ctrl_g": None})
    got = p.get("hotkeys", {})
    assert got["ctrl_f"] == "<Control-p>"
    assert got.get("ctrl_g") is None
    # 重开文件仍可读（持久化）
    p2 = Prefs(str(tmp_path / "prefs.json"))
    assert p2.get("hotkeys", {}).get("ctrl_f") == "<Control-p>"


def test_archive_independent_of_mute_and_pin(tmp_path):
    p = _tmp(tmp_path)
    key = "group:7"
    p.toggle_pin(key)
    p.toggle_mute(key)
    p.toggle_archive(key)
    assert p.is_pinned(key) and p.is_muted(key) and p.is_archived(key)
    p.toggle_archive(key)                      # 只动归档，不动另两项
    assert p.is_pinned(key) and p.is_muted(key) and not p.is_archived(key)


def test_persistence_across_reopen(tmp_path):
    path = str(tmp_path / "prefs.json")
    p = Prefs(path)
    p.toggle_archive("private:1:9")
    p.toggle_mute("private:1:9")
    p.set("dnd", True)
    q = Prefs(path)                            # 重新加载
    assert q.is_archived("private:1:9")
    assert q.is_muted("private:1:9")
    assert q.get("dnd", False) is True


def test_ignore_corrupt_file(tmp_path):
    path = str(tmp_path / "prefs.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not valid json")
    p = Prefs(path)                            # 不抛异常，回落到默认
    assert not p.archived() and not p.muted()


def test_account_passcode_frameless(tmp_path):
    """R8：默认账号/解锁码/无边框薄封装持久化到 prefs.json。"""
    p = _tmp(tmp_path)
    assert p.default_account() is None
    assert p.has_passcode() is False
    assert p.frameless() is True               # 默认开
    p.set_default_account("摸鱼一号")
    p.set_passcode("aa:bb")                    # 存 hash 串
    p.set_frameless(False)
    assert p.has_passcode() is True
    assert p.passcode() == "aa:bb"

    q = Prefs(str(tmp_path / "prefs.json"))    # 重开仍可读
    assert q.default_account() == "摸鱼一号"
    assert q.passcode() == "aa:bb"
    assert q.frameless() is False

    q.set_passcode(None)                        # 清除
    assert q.has_passcode() is False


def test_keywords_parse_and_persist(tmp_path):
    """R60：关键词提醒解析（含中文逗号/空白/去重）与 prefs 持久化。"""
    p = _tmp(tmp_path)
    assert p.keywords() == []                   # 默认无关键词
    assert parse_keywords("") == []
    assert parse_keywords(" 任务 , 老板,, 摸鱼 ，老板 ") == ["任务", "老板", "摸鱼"]
    p.set_keywords("Alarm, 汇总，进度")
    assert p.keywords() == ["alarm", "汇总", "进度"]   # 大小写小写化
    q = Prefs(str(tmp_path / "prefs.json"))     # 重开仍可读
    assert q.keywords() == ["alarm", "汇总", "进度"]


def test_chat_theme_persist(tmp_path):
    """聊天主题键：默认空（跟随皮肤）→ 设置/读回/坏数据回落。"""
    p = _tmp(tmp_path)
    assert p.chat_theme() == ""
    p.set_chat_theme("mint")
    assert p.chat_theme() == "mint"
    q = Prefs(str(tmp_path / "prefs.json"))     # 重开仍可读
    assert q.chat_theme() == "mint"
    p.set_chat_theme("")
    assert p.chat_theme() == ""                 # 回"跟随皮肤"


def test_notify_sound_persist(tmp_path):
    """R67 新消息提示音：默认 default，四档 set/get 往返持久化。"""
    p = _tmp(tmp_path)
    assert p.get("notify_sound", "default") == "default"   # 默认档
    for s in ("off", "soft", "default", "ding"):
        p.set("notify_sound", s)
        assert p.get("notify_sound", "default") == s
    q = Prefs(str(tmp_path / "prefs.json"))     # 重开仍可读
    assert q.get("notify_sound", "default") == "ding"