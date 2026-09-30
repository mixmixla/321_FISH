# -*- coding: utf-8 -*-
"""R9 全局搜索纯函数单测：扫磁盘全量命中/大小写/跨会话分组/会话名解析/容错。"""
import json
import os

from widgets.global_search import (_display_name, _parse_key, _safe_to_key,
                                   scan_all, MessageIndex, load_index,
                                   search_messages)


def _write(tmp_path, fname: str, msgs: list):
    p = tmp_path / fname
    with open(p, "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return str(tmp_path)


def test_safe_to_key_roundtrip():
    assert _safe_to_key("public.jsonl") == "public"
    assert _safe_to_key("private_1_2.jsonl") == "private:1:2"
    assert _safe_to_key("group_7.jsonl") == "group:7"


def test_parse_key_channels():
    assert _parse_key("public") == ("public", None)
    assert _parse_key("private:1:2") == ("private", (1, 2))
    assert _parse_key("group:7") == ("group", 7)


def test_scan_hits_across_sessions(tmp_path):
    d = str(tmp_path)
    _write(tmp_path, "public.jsonl",
           [{"seq": 1, "text": "今晚例会取消了", "ts": 111},
            {"seq": 2, "text": "周末看球", "nick": "甲", "ts": 112}])
    _write(tmp_path, "private_3_9.jsonl",
           [{"seq": 1, "text": "记得提交周报", "nick": "乙", "ts": 201}])
    _write(tmp_path, "group_7.jsonl",
           [{"seq": 1, "text": "周报记得交哦", "nick": "丙", "ts": 301}])
    roster = {9: {"uid": 9, "nick": "乙"}, 3: {"uid": 3, "nick": "我"}}
    groups = {7: {"gid": 7, "name": "部门群"}}
    res = scan_all(d, "周报", roster, groups, me_uid=3)
    # 命中 2 个会话：私聊乙(1条) + 部门群(1条)；公共无
    assert sorted(r["name"] for r in res) == ["乙", "部门群"]
    by = {r["name"]: r for r in res}
    assert by["乙"]["ch"] == "private" and by["乙"]["first"]["nick"] == "乙"
    assert by["部门群"]["ch"] == "group"
    assert by["部门群"]["name"] == "部门群"


def test_case_insensitive(tmp_path):
    d = _write(tmp_path, "public.jsonl",
               [{"text": "GoLang 并发模型"}, {"text": "golang 教程"}])
    assert len(scan_all(d, "golang", {}, {}, None)) == 1


def test_empty_query_returns_none(tmp_path):
    d = _write(tmp_path, "public.jsonl", [{"text": "x"}])
    assert scan_all(d, "", {}, {}, None) == []
    assert scan_all(d, "   ", {}, {}, None) == []


def test_missing_dir(tmp_path):
    assert scan_all(str(tmp_path / "no_such"), "x", {}, {}, None) == []


def test_corrupt_lines_skipped(tmp_path):
    p = tmp_path / "public.jsonl"
    p.write_text('{"text": "好"}\nnot json\n{"text": "好家伙"}\n',
                 encoding="utf-8")
    assert len(scan_all(str(tmp_path), "好", {}, {}, None)) == 1


def test_display_name_fallback():
    assert _display_name("public", {}, {}, None) == "公共频道"
    assert _display_name("private:1:2", {}, {}, 1) == "私聊 #2"
    u = {2: {"uid": 2, "nick": "乙"}}
    assert _display_name("private:1:2", u, {}, 1) == "乙"
    g = {7: {"gid": 7, "name": "部门群"}}
    assert _display_name("group:7", {}, g, None) == "部门群"
    assert _display_name("group:8", {}, g, None) == "群 8"
    # me_uid=None 时 private 对端取低端，无 roster 回退
    assert _display_name("private:1:2", {}, {}, None).startswith("私聊")


# ---------- R9+ 消息级内存索引 ----------

def test_index_search_case_insensitive_and_ts_order(tmp_path):
    d = str(tmp_path)
    _write(tmp_path, "public.jsonl",
           [{"seq": 2, "text": "GoLang 并发模型", "ts": 200},
            {"seq": 1, "text": "golang 教程", "ts": 100}])
    _write(tmp_path, "group_7.jsonl",
           [{"seq": 1, "text": "今天讲 golang 吗", "nick": "丙", "ts": 300}])
    idx = load_index(d)
    assert len(idx) == 3
    hits = idx.search("golang")
    assert len(hits) == 3
    # 按 ts 倒序：300 → 200 → 100
    assert [h["ts"] for h in hits] == [300, 200, 100]


def test_index_incremental_add(tmp_path):
    idx = load_index(str(tmp_path))       # 空目录
    assert len(idx) == 0
    idx.add("public", {"seq": 9, "text": "晚点吃什么", "ts": 500, "nick": "我"})
    idx.add("public", {"seq": 8, "text": "", "ts": 400})          # 无正文 → 跳过
    assert len(idx) == 1
    hits = idx.search("吃什么")
    assert len(hits) == 1 and hits[0]["seq"] == 9


def test_search_messages_across_sessions(tmp_path):
    d = str(tmp_path)
    _write(tmp_path, "public.jsonl", [{"seq": 1, "text": "周报整理", "ts": 111}])
    _write(tmp_path, "private_3_9.jsonl",
           [{"seq": 1, "text": "记得交周报了", "nick": "乙", "ts": 201}])
    roster = {9: {"uid": 9, "nick": "乙"}, 3: {"uid": 3, "nick": "我"}}
    res = search_messages(d, "周报", roster, {}, me_uid=3)
    # 消息级跨会话：两条命中都返回，且附会话名
    assert len(res) == 2
    assert {r["name"] for r in res} == {"公共频道", "乙"}
    by_name = {r["name"]: r for r in res}
    assert by_name["乙"]["ch"] == "private" and by_name["乙"]["to"] == (3, 9)
    assert by_name["乙"]["seq"] == 1 and by_name["乙"]["nick"] == "乙"
    # 空查询 → 无结果
    assert search_messages(d, "", {}, {}, None) == []
    assert search_messages(str(tmp_path / "no_such"), "x", {}, {}, None) == []


def test_scan_all_backward_compat(tmp_path):
    """旧 per-会话聚合 API 保持不变（GUI 改版不破坏既有行为）。"""
    d = _write(tmp_path, "public.jsonl", [{"seq": 1, "text": "周报", "ts": 1}])
    r = scan_all(d, "周报", {}, {}, None)
    assert len(r) == 1 and r[0]["count"] == 1