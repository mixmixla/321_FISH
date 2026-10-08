# -*- coding: utf-8 -*-
"""test_runs.py —— 富文本分段与布局（R11，纯函数无 tk）。"""
from widgets.runs import (tag_entities, wrap_segments, line_width,
                          normalize_url, MENTION, LINK, PLAIN)
import pytest


def test_tag_entities_mentions():
    segs = tag_entities("hi @小明 开会 @小刚 end")
    kinds = [k for _, k in segs]
    assert kinds.count(MENTION) == 2
    assert any(t == "@小明" and k == MENTION for t, k in segs)
    assert any(t == "@小刚" and k == MENTION for t, k in segs)


def test_tag_entities_links():
    segs = tag_entities("看 https://a.com/b 和 www.example.org")
    assert any(t == "https://a.com/b" and k == LINK for t, k in segs)
    assert any(t == "www.example.org" and k == LINK for t, k in segs)


def test_tag_entities_ordering_merges_plain():
    segs = tag_entities("A@用户B https://x.com C")
    merged = "".join(t for t, _ in segs)
    assert merged == "A@用户B https://x.com C"
    kinds = [k for t, k in segs if t in ("@用户B", "https://x.com")]
    assert kinds == [MENTION, LINK]


def test_tag_entities_no_match_all_plain():
    segs = tag_entities("普通文本")
    assert segs == [("普通文本", PLAIN)]


def test_wrap_basic_single_line():
    m = lambda s: len(s)            # 每字符 1 单位宽
    segs = [("hello", PLAIN)]
    lines = wrap_segments(segs, 100, m)
    assert lines == [[("hello", PLAIN)]]


def test_wrap_breaks_at_width():
    m = lambda s: len(s)
    segs = [("a b c d e", PLAIN)]
    lines = wrap_segments(segs, 3, m)      # 宽 3，词间需空格
    joined = [" ".join(t for t, _ in ln) for ln in lines]
    assert all(len(x) <= 5 for x in joined)   # 词最长 1 + 空格，3 字宽容 1 个 2字?
    assert " ".join(joined) == "a b c d e"


def test_wrap_cjk_hard_split():
    m = lambda s: len(s)
    segs = [("中文长串无空格", PLAIN)]
    lines = wrap_segments(segs, 3, m)
    joined = "".join(t for t, _ in sum(lines, []))
    assert joined == "中文长串无空格"
    assert all(len(t) <= 3 for t, _ in sum(lines, []))


def test_wrap_keeps_link_entity_in_kind():
    segs = tag_entities("看 https://a.com/x 吧")     # 先标实体再布局（真实流程）
    m = lambda s: len(s)
    lines = wrap_segments(segs, 200, m)
    flattened = sum(lines, [])
    assert any(t == "https://a.com/x" and k == LINK for t, k in flattened)


def test_line_width_and_normalize():
    m = lambda s: len(s)
    assert line_width([("ab", PLAIN), ("cd", PLAIN)], m) == 5   # 2+1+2
    assert normalize_url("www.x.com") == "http://www.x.com"
    assert normalize_url("https://x.com") == "https://x.com"


@pytest.mark.parametrize("text", ["UX 中文 😀", "one two three", "甲\n乙 😀", "a  b\tc"])
@pytest.mark.parametrize("width", [3, 100])
def test_three_field_runs_match_two_field_text_without_repeating(text, width):
    two = wrap_segments([(text, LINK)], width, lambda t: len(t))
    three = wrap_segments([(text, LINK, "https://example.invalid")], width, lambda t: len(t))
    assert [[s[:2] for s in line] for line in three] == two
    assert all(s[2] == "https://example.invalid" for line in three for s in line)


@pytest.mark.parametrize("text", ["  UX  中文 😀\tend ", "\n甲\n\n乙\n", "中English😀超宽段", "   "])
@pytest.mark.parametrize("width", [1, 4, 100])
def test_exact_layout_preserves_every_character_and_blank_line(text, width):
    lines = wrap_segments([(text, LINK, "https://example.invalid")], width,
                          lambda t: len(t), preserve_whitespace=True)
    restored = "".join("".join(s[0] for s in line) + ("\n" if line.hard_break else "")
                       for line in lines)
    assert restored == text
    assert all(line_width(line, lambda t: len(t)) <= width for line in lines)
    assert all(s[2] == "https://example.invalid" for line in lines for s in line)


def test_exact_layout_does_not_insert_spaces_between_adjacent_entities():
    lines = wrap_segments([("看", PLAIN), ("这里", LINK, "https://example.invalid"), ("。", PLAIN)],
                          100, lambda t: len(t), preserve_whitespace=True)
    assert "".join(s[0] for s in lines[0]) == "看这里。"
    assert line_width(lines[0], lambda t: len(t)) == 4


def test_msg_cache_separates_href_and_segment_arity_in_both_orders():
    from types import SimpleNamespace
    from widgets.msg_list import MsgList
    for order in ((None, "https://a.invalid", "https://b.invalid"),
                  ("https://b.invalid", "https://a.invalid", None)):
        widget = SimpleNamespace(_font_sig="synthetic", _wrap_cache={},
                                 _WRAP_CACHE_MAX=10, _meas_kind=lambda t, k: len(t))
        for href in order:
            segment = ("same label", LINK, href) if href else ("same label", LINK)
            lines = MsgList._wrap_lines(widget, [segment], 100)
            assert "".join(s[0] for s in lines[0]) == "same label"
            assert all((s[2] if len(s) > 2 else None) == href for line in lines for s in line)
