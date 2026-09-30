# -*- coding: utf-8 -*-
"""test_runs.py —— 富文本分段与布局（R11，纯函数无 tk）。"""
from widgets.runs import (tag_entities, wrap_segments, line_width,
                          normalize_url, MENTION, LINK, PLAIN)


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