# -*- coding: utf-8 -*-
"""R39C 本地历史分段懒加载 + 文本度量 LRU 回归：

LocalHistory 分页（单元）：
- page_tail / page_before 翻页边界（空会话/整页/短页/最旧一页）
- page_after 正向窗口；重连回放重复行按 seq 去重（倒扫取新舍旧）
- 索引失效：edit_msg_local / purge_local / merge_in / drop 后翻页读到新数据
- 增量追加：索引已建时 add 不重建索引，page_tail 含新行

ClientCore 包装（集成）：
- _store_chat 落盘 → history_tail / history_page 按 channel 键正确翻页

MsgList 懒加载 + LRU（Tk）：
- 首开只装末页，滚到顶触发 loader 头部插入且视口锚定（不跳回底部）
- 短页 → _hist_done，不再回调；全无 seq 行同样翻尽
- _wrap_lines LRU：同键命中不重测、超上限淘汰最旧
- 3000 行合成：懒加载链路逐页收齐 + 首开耗时显著低于全量装载
"""
import time
import tkinter as tk

import pytest

from client_core import ClientCore, LocalHistory
from widgets.msg_list import MsgList

FONT = ("Microsoft YaHei UI", 9)


# ---------- LocalHistory 分页（单元） ----------

def _hist(tmp_path, n=250, seq_from=1):
    h = LocalHistory(str(tmp_path / "hist"))
    for i in range(seq_from, seq_from + n):
        h.add("public", {"t": "chat", "seq": i, "uid": 1, "nick": "甲",
                         "text": f"消息{i}", "ts": 1000.0 + i})
    return h


def test_page_tail_and_before(tmp_path):
    h = _hist(tmp_path, n=250)                 # seq 1..250
    tail = h.page_tail("public", 100)
    assert [m["seq"] for m in tail] == list(range(151, 251))     # 最新100条，升序
    p2 = h.page_before("public", 151, 100)     # seq<151 的更旧一页
    assert [m["seq"] for m in p2] == list(range(51, 151))
    p3 = h.page_before("public", 51, 100)      # 短页（只剩50条）
    assert [m["seq"] for m in p3] == list(range(1, 51))
    assert h.page_before("public", 1, 100) == []                 # 已到最旧


def test_page_empty_and_bad_key(tmp_path):
    h = LocalHistory(str(tmp_path / "hist"))
    assert h.page_tail("public") == []         # 文件不存在
    assert h.page_before("group:9", 100) == []
    assert h.page_after("public", 0) == []


def test_page_dedup_replay(tmp_path):
    """重连回放会在文件尾追加重复行：翻页按 seq 去重（倒扫首见=最新内容）。"""
    h = _hist(tmp_path, n=10)                  # seq 1..10
    h.add("public", {"t": "chat", "seq": 10, "uid": 1, "nick": "甲",
                     "text": "消息10-回放", "ts": 9999.0})       # 重复 seq=10
    tail = h.page_tail("public", 100)
    seqs = [m["seq"] for m in tail]
    assert seqs == list(range(1, 11))          # 10 只出现一次
    assert tail[-1]["text"] == "消息10-回放"   # 倒扫首见 = 文件尾最新内容


def test_page_after_forward_window(tmp_path):
    h = _hist(tmp_path, n=250)
    out = h.page_after("public", 200, 100)
    assert [m["seq"] for m in out] == list(range(201, 251))
    assert h.page_after("public", 250, 100) == []


def test_index_invalidate_on_edit_and_purge(tmp_path):
    h = _hist(tmp_path, n=30)
    first = h.page_tail("public", 100)         # 建立索引
    assert len(first) == 30
    assert h.edit_msg_local("public", 5, "改过的5") is True
    seqs = {m["seq"]: m for m in h.page_tail("public", 100)}
    assert seqs[5]["text"] == "改过的5"        # 重写后翻页读到新数据
    assert seqs[5].get("edited") is True
    assert h.purge_local("public", 10) == 10   # 丢 seq<=10
    rest = h.page_tail("public", 100)
    assert [m["seq"] for m in rest] == list(range(11, 31))
    assert h.del_msg_local("public", 15) is True
    got = {m["seq"]: m for m in h.page_tail("public", 100)}
    assert got[15]["deleted"] is True and got[15]["text"] == ""


def test_index_invalidate_on_merge_and_drop(tmp_path):
    h = _hist(tmp_path, n=20)
    h.page_tail("public", 100)
    added = h.merge_in({"public": [{"t": "chat", "seq": 21, "uid": 1,
                                    "nick": "甲", "text": "云补", "ts": 3000.0}]})
    assert added == 1
    seqs = [m["seq"] for m in h.page_tail("public", 100)]
    assert seqs == list(range(1, 22))          # 合并重写后仍完整
    h.drop("public")
    assert h.page_tail("public") == []         # 文件删除后为空


def test_index_incremental_append(tmp_path):
    h = _hist(tmp_path, n=100)
    tail1 = h.page_tail("public", 100)         # 建索引
    assert len(tail1) == 100
    idx_before = list(h._index["public"])
    for i in range(101, 106):                  # 索引已建时增量追加
        h.add("public", {"t": "chat", "seq": i, "uid": 1, "nick": "甲",
                         "text": f"新{i}", "ts": 2000.0 + i})
    assert h._index["public"][:len(idx_before)] == idx_before
    tail2 = h.page_tail("public", 100)
    assert [m["seq"] for m in tail2] == list(range(6, 106))
    newer = h.page_after("public", 100, 10)
    assert [m["seq"] for m in newer] == list(range(101, 106))


# ---------- ClientCore 包装（集成） ----------

def _core(tmp_path):
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    return core


def test_clientcore_history_paging(tmp_path):
    core = _core(tmp_path)
    for i in range(1, 231):                    # public 230 条（seq 全局唯一）
        core._store_chat({"t": "chat", "channel": "public", "seq": i,
                          "uid": 1, "nick": "甲", "text": f"pub{i}", "ts": 1.0 * i})
    for i in range(1001, 1031):                # group 独立频道（seq 续全局序列）
        core._store_chat({"t": "chat", "channel": "group", "to": 9, "seq": i,
                          "uid": 2, "nick": "乙", "text": f"g{i}", "ts": 1.0 * i})
    tail = core.history_tail("public", None, 100)
    assert [m["seq"] for m in tail] == list(range(131, 231))
    older = core.history_page("public", None, 131, 100)
    assert [m["seq"] for m in older] == list(range(31, 131))
    gt = core.history_tail("group", 9, 100)
    assert [m["seq"] for m in gt] == list(range(1001, 1031))   # 频道键互不串
    core._history.close()


def test_clientcore_private_e2ee_keys(tmp_path):
    """私聊/密聊键按 uid 对排序归档：两个视角翻到同一份历史。"""
    core = _core(tmp_path)
    core.uid = 5
    for i in range(1, 41):
        core._store_chat({"t": "chat", "channel": "private", "seq": i,
                          "uid": 8, "to": 5, "nick": "乙", "text": f"p{i}",
                          "ts": 1.0 * i})
    a = core.history_tail("private", 8, 100)          # 我的视角
    core.uid = 8
    b = core.history_tail("private", 5, 100)          # 对方视角
    assert [m["seq"] for m in a] == [m["seq"] for m in b] == list(range(1, 41))
    core._history.close()


# ---------- MsgList 懒加载 + LRU（Tk） ----------

@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture()
def ml(root):
    ml = MsgList(root, FONT)
    ml.configure(width=400, height=400)
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield ml
    ml.destroy()


def _msg(seq, text=None):
    return {"t": "chat", "channel": "public", "seq": seq, "uid": 1,
            "nick": "甲", "text": text or f"历史消息第 {seq} 条",
            "ts": time.time() - (10000 - seq)}


def test_wrap_lines_lru_hit_and_evict(ml):
    segs = [("hello world 你好 ", "p")]
    a = ml._wrap_lines(segs, 200)
    b = ml._wrap_lines(segs, 200)
    assert a is b                              # 命中返回同对象（不重测）
    ml._WRAP_CACHE_MAX = 3                     # 实例覆盖上限
    ml._wrap_cache.clear()
    keys = []
    for i in range(5):                         # 超上限：最旧被淘汰，长度不超
        ml._wrap_lines([(f"t{i}", "p")], 100)
        keys.append((ml._font_sig, ((f"t{i}", "p"),), 100))
        assert len(ml._wrap_cache) <= 3
    assert keys[0] not in ml._wrap_cache       # 最旧已淘汰
    assert keys[-1] in ml._wrap_cache


def test_wrap_lines_matches_direct_measure(ml):
    """LRU 结果必须与直接调用 runs.wrap_segments 一致（估算=绘制前提）。"""
    from widgets import runs
    segs = runs.tag_entities("一段长文本测试换行 @某人 https://example.com/x " * 6)
    inner = 240
    assert ml._wrap_lines(segs, inner) == runs.wrap_segments(segs, inner, ml._meas)


def test_lazy_load_top_anchor_and_done(ml):
    all_seqs = list(range(1, 301))

    def loader(before_seq, n):
        calls.append((before_seq, n))
        end = before_seq - 1
        start = max(1, end - n + 1)
        return [_msg(s) for s in range(start, end + 1)] if end > 0 else []

    calls = []
    ml.set_history_loader(loader)
    ml.load([_msg(s) for s in all_seqs[-100:]], me_uid=1)   # 首开只装 201..300
    assert ml.count == 100
    ml.yview_moveto(0.0)
    ml._maybe_load_top()                       # 滚到顶 → 装载 101..200
    assert calls == [(201, 100)]
    assert ml.count == 200
    assert ml.yview()[0] > 0.0                 # 视口锚定：未跳回最顶
    ml.yview_moveto(0.0)
    ml._maybe_load_top()                       # 再翻 1..100
    assert ml.count == 300
    ml.yview_moveto(0.0)
    ml._maybe_load_top()                       # 已到最旧：空页 → 翻尽
    assert calls == [(201, 100), (101, 100), (1, 100)]
    assert ml.count == 300
    assert ml._hist_done is True
    ml.yview_moveto(0.0)
    ml._maybe_load_top()                       # 翻尽后不再回调
    assert len(calls) == 3 and ml.count == 300


def test_lazy_load_overlap_dedup(ml):
    """loader 返回与已装载重叠的 seq：prepend 去重不重复渲染。"""
    tail = [_msg(i) for i in range(201, 301)]
    older = [_msg(i) for i in range(151, 261)]         # 201..260 与 tail 重叠
    ml.set_history_loader(lambda b, n: older)
    ml.load(tail, me_uid=1)
    ml.yview_moveto(0.0)
    ml._maybe_load_top()
    assert ml.count == 150                     # 只补 151..200，重叠 60 行去重
    seqs = [r.raw["seq"] for r in ml._rows]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))


def test_lazy_load_no_seq_rows_done(ml):
    """整屏本地行（无 seq，如失败重发行）：无处可翻，直接置翻尽。"""
    ml.set_history_loader(lambda b, n: pytest.fail("不应回调"))
    ml.load([{"uid": 1, "nick": "甲", "text": "本地行", "ts": time.time(),
              "send_failed": True}], me_uid=1)
    ml.yview_moveto(0.0)
    ml._maybe_load_top()
    assert ml._hist_done is True


def test_lazy_loader_exception_safe(ml):
    def boom(before_seq, n):
        raise RuntimeError("disk boom")
    ml.set_history_loader(boom)
    ml.load([_msg(1)], me_uid=1)
    ml.yview_moveto(0.0)
    ml._maybe_load_top()                       # 异常不崩 UI
    assert ml._hist_done is True and ml.count == 1


def test_three_k_rows_lazy_vs_full(ml):
    """3000 行合成：懒加载链路逐页收齐 + 首开耗时显著低于全量装载。"""
    all_msgs = [_msg(i) for i in range(1, 3001)]

    def loader(before_seq, n):
        end = before_seq - 1
        start = max(1, end - n + 1)
        return all_msgs[start - 1:end] if end > 0 else []

    ml.set_history_loader(loader)
    t0 = time.perf_counter()
    ml.load(all_msgs[-100:], me_uid=1)         # 懒加载首开：仅末页
    t_page = time.perf_counter() - t0
    assert ml.count == 100
    guard = 0
    while not ml._hist_done and guard < 100:   # 逐页滚顶翻完（带防呆上限）
        guard += 1
        ml.yview_moveto(0.0)
        ml._maybe_load_top()
    assert ml.count == 3000
    seqs = [r.raw["seq"] for r in ml._rows]
    assert seqs == list(range(1, 3001))        # 顺序完整无重复
    t1 = time.perf_counter()
    ml.load(all_msgs, me_uid=1)                # 全量装载基线
    t_full = time.perf_counter() - t1
    assert t_page < t_full                     # 100 行首开必须快于 3000 行全量


def test_prepend_cross_day_and_thread_rows(ml):
    """跨天边界 prepend：日期分隔条重算，高度全为正且累计自洽。"""
    old = [{"t": "chat", "channel": "public", "seq": i, "uid": 1, "nick": "甲",
            "text": f"旧{i}", "ts": time.time() - 86400 * 3}
           for i in range(1, 6)]
    new = [{"t": "chat", "channel": "public", "seq": i, "uid": 1, "nick": "甲",
            "text": f"新{i}", "ts": time.time()} for i in range(6, 11)]
    ml.load(new, me_uid=1)
    ml.yview_moveto(0.0)
    n = ml.prepend(old)                        # 直接 prepend（跨天）
    assert n == 5
    assert ml.count == 10
    assert all(h > 0 for h in ml._heights)
    assert ml._cum[-1] == sum(ml._heights)
    assert ml._date_label(0) is not None       # 旧页首行画日期分隔条
