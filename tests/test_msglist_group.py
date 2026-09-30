# -*- coding: utf-8 -*-
"""test_msglist_group.py —— R12 消息分组/日期分隔纯逻辑（无需 tk）。

通过伪造 _rows 数据直接测 MsgList 的静态判定，避免开真实窗口。
"""
import time

from widgets.msg_list import MsgList, _Row

NOW = time.time()


def _row(ts: float, uid: int, channel: str = "public",
         nick: str = "人", text: str = "x") -> _Row:
    return _Row({"ts": ts, "uid": uid, "channel": channel,
                 "nick": nick, "text": text})


class _ML(MsgList):
    """不初始化 tk 组件的空壳：只借用类方法/常量。"""

    def __init__(self):
        self._rows = []
        self._wrap_w = 400
        self._meas_cache = {}


def test_in_group_same_uid_quick():
    ml = _ML()
    ml._rows = [_row(NOW, 1), _row(NOW + 60, 1)]
    assert ml._in_group(1) is True


def test_in_group_same_uid_slow():
    ml = _ML()
    ml._rows = [_row(NOW, 1), _row(NOW + 400, 1)]   # 超 3 分钟窗
    assert ml._in_group(1) is False


def test_in_group_diff_uid():
    ml = _ML()
    ml._rows = [_row(NOW, 1), _row(NOW + 30, 2)]
    assert ml._in_group(1) is False


def test_in_group_diff_channel():
    ml = _ML()
    ml._rows = [_row(NOW, 1, "public"), _row(NOW + 30, 1, "private")]
    assert ml._in_group(1) is False


def test_in_group_sys_breaks():
    ml = _ML()
    ml._rows = [_row(NOW, 1), _Row({"ts": NOW + 30, "text": "s"}, is_system=True),
                _row(NOW + 60, 1)]
    assert ml._in_group(1) is False      # 系统行不并入组
    assert ml._in_group(2) is False      # 系统行之后也不与前一组续


def test_in_group_image_breaks():
    ml = _ML()
    ml._rows = [_row(NOW, 1), _row(NOW + 30, 1, image=True) if False else
                _Row({"ts": NOW + 30, "uid": 1, "channel": "public",
                      "nick": "人", "text": "x", "image_path": "a.png"})]
    assert ml._in_group(1) is False


def test_date_label_cross_day():
    ml = _ML()
    d1 = time.mktime(time.strptime("2026-09-01 10:00:00", "%Y-%m-%d %H:%M:%S"))
    d2 = time.mktime(time.strptime("2026-09-02 10:00:00", "%Y-%m-%d %H:%M:%S"))
    ml._rows = [_row(d1, 1), _row(d2, 1)]
    assert ml._date_label(0) is not None    # 首条非今天 → 有日期条
    assert ml._date_label(1) == "9月2日"    # 跨天 → 新日期


def test_date_label_same_day_none():
    ml = _ML()
    d1 = time.mktime(time.strptime("2026-09-01 10:00:00", "%Y-%m-%d %H:%M:%S"))
    d2 = time.mktime(time.strptime("2026-09-01 12:00:00", "%Y-%m-%d %H:%M:%S"))
    ml._rows = [_row(d1, 1), _row(d2, 1)]
    assert ml._date_label(1) is None        # 同天不重复插日期条


def test_fmt_date_yesterday():
    ts = time.time() - 86400
    assert MsgList._fmt_date(ts) == "昨天"
