# -*- coding: utf-8 -*-
"""R61 四批低风险功能的最小单测：①被引用计数、②收藏限量/去重、③倍速、④头像样式枚举。

只测纯函数/静态逻辑，不依赖 GUI 主循环，跑得快且不被环境（无显示/无音频硬件）影响。
"""
import struct

import pytest


# ---------- ① 被引用聚合计数 ----------
def _quote_rows(pairs):
    """构造假行。pairs: (本行 seq | None, 本行引用的 reply_seq | None)。"""
    class R:
        def __init__(self, seq, reply_seq):
            self.raw = {"seq": seq}
            self.reply_seq = reply_seq
    return [R(s, r) for s, r in pairs]


def test_count_quote_refs_basic():
    from widgets.msg_list import count_quote_refs
    rows = _quote_rows([(1, None), (2, 1), (3, 1), (4, 2)])
    out = count_quote_refs(rows)
    assert out == {1: [1, 2], 2: [3]}          # 1 被引 2 次；2 被引 1 次


def test_count_quote_refs_ignores_missing_target():
    from widgets.msg_list import count_quote_refs
    # 引用指向 seq=99，但历史里没有该条（已删除/未加载）→ 不计
    rows = _quote_rows([(1, None), (2, 99)])
    assert count_quote_refs(rows) == {}


def test_count_quote_refs_zero_and_dedup():
    from widgets.msg_list import count_quote_refs
    rows = _quote_rows([(5, None), (6, None)])            # 无人被引用
    assert count_quote_refs(rows) == {}
    rows2 = _quote_rows([(7, None), (8, 7), (8, 7)])      # 两条 8 都引用 7 → 7 计 2 次
    assert count_quote_refs(rows2) == {7: [1, 2]}


# ---------- ② 收藏限量 / 去重 ----------
def test_trim_stars_keeps_latest_within_limit():
    from prefs import trim_stars
    stars = {i: {"ts": 1000 + i} for i in range(5)}
    trim_stars(stars, limit=200)             # 未超限 → 原样
    assert len(stars) == 5
    trim_stars(stars, limit=3)               # 只留 ts 最大的 3 条
    assert set(stars) == {2, 3, 4}


def test_trim_stars_dedup_by_key_is_structural():
    from prefs import trim_stars
    # 同 seq 重复收藏：dict 键天然去重（覆盖旧快照但不新增条数）
    stars = {10: {"ts": 1}}
    stars[10] = {"ts": 2}
    assert len(stars) == 1
    trim_stars(stars, 200)
    assert stars[10]["ts"] == 2


def test_trim_stars_limit_zero_clears():
    from prefs import trim_stars
    stars = {1: {"ts": 1}, 2: {"ts": 2}}
    trim_stars(stars, 0)
    assert stars == {}


# ---------- ③ 语音倍速：速率解析 + PCM 重采样 ----------
def test_parse_speed():
    import voice_api
    assert voice_api.parse_speed("1.5") == 1.5
    assert voice_api.parse_speed(2.0) == 2.0
    assert voice_api.parse_speed(0.5) == 0.5
    assert voice_api.parse_speed("abc") == 1.0          # 非法回落
    assert voice_api.parse_speed(5.0) == 1.0            # 越界回落
    assert voice_api.parse_speed(None) == 1.0


def _wav16mono(n_samples, rate=8000):
    import array
    pcm = array.array("h", [c for c in range(n_samples)])
    data = pcm.tobytes()
    return (b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVE"
            + b"fmt " + (16).to_bytes(4, "little")
            + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
            + rate.to_bytes(4, "little") + (rate * 2).to_bytes(4, "little")
            + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
            + b"data" + len(data).to_bytes(4, "little") + data)


def test_resample_wav_duration_scales():
    import voice_api
    wav = _wav16mono(8000)                         # 1 秒 @8k
    fast = voice_api.resample_wav(wav, 2.0)       # 2x → 半秒数据
    slow = voice_api.resample_wav(wav, 0.5)       # 0.5x → 2 秒数据
    assert len(fast) < len(wav) < len(slow)
    assert fast[:4] == b"RIFF" and fast[8:12] == b"WAVE"
    # data 块样本数 = 总长 - 44 字节头，再除 2 字节/样本
    assert (len(fast) - 44) // 2 == 4000
    assert (len(slow) - 44) // 2 == 16000


def test_resample_wav_rate1_returns_input():
    import voice_api
    wav = _wav16mono(100)
    assert voice_api.resample_wav(wav, 1.0) is wav


def test_resample_wav_non_16bit_returns_input():
    import voice_api
    wav = _wav16mono(100)
    bad = wav[::2]                                # 截断 → 非合法 WAVE → 降级原样
    assert voice_api.resample_wav(bad, 2.0) == bad


# ---------- ④ 头像相框样式枚举 ----------
def test_parse_frame_enum():
    from widgets.avatar import parse_frame, set_default_frame
    assert parse_frame("ring") == "ring"
    assert parse_frame("gold") == "gold"
    assert parse_frame("glow") == "glow"
    assert parse_frame("none") == "none"
    assert parse_frame("") == ""               # 空串 = 跟随全局默认（默认即 none）
    assert parse_frame("garbage") == "none"       # 坏数据回落
    set_default_frame("gold")
    from widgets.avatar import _DEFAULT_FRAME
    assert _DEFAULT_FRAME == "gold"
    set_default_frame("")                          # 恢复 none