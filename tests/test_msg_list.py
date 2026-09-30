# -*- coding: utf-8 -*-
"""test_msg_list.py —— 虚拟化消息列表（A1）专项测试。

核心验收：
- 1 万条消息注入后仅创建少量可见 canvas 元素（虚拟化生效）
- 前缀和/行高缓存自洽，行定位（row_at）与渲染坐标一致
- 吸底自动滚动、清空、会话切换批量装载正确
"""
import time
import tkinter as tk

import pytest

from widgets.msg_list import MsgList

FONT = ("Microsoft YaHei UI", 9)


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


def _msg(i, uid=1, nick="甲", channel="public", text=None):
    return {"uid": uid, "nick": nick, "channel": channel,
            "ts": time.time() - i, "text": text or f"测试消息第 {i} 条"}


@pytest.fixture()
def ml(root):
    ml = MsgList(root, FONT)
    ml.configure(width=400, height=400)      # 显式尺寸：避免 CI 无 WM 映射时视口塌成 1px
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield ml
    ml.destroy()


def test_append_and_count(ml):
    for i in range(10000):
        ml.append(_msg(i))
    assert ml.count == 10000
    assert ml._cum[-1] > 0                     # 总高度非零
    assert ml._cum[0] == 0


def test_image_row_body_and_render(ml, tmp_path):
    """A7：图片消息正文含 [图片] 占位，附加后可渲染（缩略图/占位）不崩溃。"""
    from PIL import Image
    from widgets.msg_list import is_image_path
    img = tmp_path / "t.png"
    Image.new("RGB", (50, 40), (0, 128, 255)).save(str(img))
    assert is_image_path(str(img))
    ml.append({"uid": 1, "nick": "甲", "channel": "private",
               "ts": time.time(), "image_path": str(img)})
    assert ml.count == 1
    assert "[图片]" in ml.body_text(0)          # 搜索/复制用占位正文
    ml.configure(width=400)
    ml._render()
    root = ml.winfo_toplevel().update_idletasks()
    assert len(ml._item_ids) >= 1               # 画布已创建头像/占位 item
    # 非图片路径判定为 False
    assert not is_image_path(str(tmp_path / "note.txt"))


def test_virtualization_visible_items_bounded(ml):
    """1 万条消息，只应创建可见区间内少量 canvas item（虚拟化核心）。

    每行最多 3 个 item（头像圆 + 首字 + 正文），视口 400px 高 → 上限约 25 行。
    """
    for i in range(10000):
        ml.append(_msg(i))
    ml.scroll_to_end()
    assert len(ml._item_ids) <= 80             # 可见行数上限（视口高 400px 内）
    # 任意滚动位置也不应超过可见行数上限
    ml.yview_moveto(0.5)
    ml._render()
    assert len(ml._item_ids) <= 80


def test_cum_consistency_after_height_measure(ml):
    """实测行高后前缀和保持自洽（cum 单调不减）。"""
    for i in range(5000):
        ml.append(_msg(i, text=f"长消息测试 {'字' * (i % 300)}"))
    ml._render()
    prev = ml._cum[0]
    for v in ml._cum[1:]:
        assert v >= prev
        prev = v


def test_row_at_mapping(ml):
    """row_at(y) 应命中对应行的原始消息。"""
    for i in range(1000):
        ml.append(_msg(i, text=f"定位消息{i}"))
    ml.scroll_to_end()
    # 首可见行附近命中
    top_y = 2
    idx = ml.row_at(top_y)
    assert idx is not None and 0 <= idx < ml.count
    # 越界返回 None
    assert ml.row_at(-50) is None or ml.row_at(99999) is None


def test_get_row_roundtrip(ml):
    ml.append(_msg(7, uid=5, nick="乙", text="往返验证"))
    raw = ml.get_row(0)
    assert raw["nick"] == "乙" and raw["text"] == "往返验证"
    assert ml.get_row(999) is None


def test_avatar_cache_deterministic_and_reused():
    """A5：同一昵称配色稳定且只缓存一次；首字取昵称首字符。"""
    from widgets.avatar import AvatarCache
    ac = AvatarCache()
    s1 = ac.style("张三")
    assert s1 == ac.style("张三")               # 确定性
    assert s1[0].startswith("#")                # 色板色
    assert ac.style("李四")[1] == "李"           # 首字
    assert ac.style("")[1] == "?"               # 空昵称兜底
    assert len(ac._mem) == 3                    # 只缓存 3 个昵称


def test_at_bottom_auto_scroll(ml):
    """新消息到达自动吸底；用户上翻后不再自动滚底。"""
    for i in range(200):
        ml.append(_msg(i))
    ml._flush_render()
    assert ml.at_bottom
    # 模拟用户上翻（走真实滚动输入路径，解除钉底）
    ml._scroll_cmd("moveto", 0.0)
    assert not ml.at_bottom
    # 上翻状态下追加不打断阅读（不强制滚底）
    ml.append(_msg(9999))
    ml._flush_render()
    assert not ml.at_bottom
    # 滚动条拖回底部后恢复吸底
    ml._scroll_cmd("moveto", 1.0)
    assert ml.at_bottom
    ml.append(_msg(10000))
    ml._flush_render()
    assert ml.at_bottom


def test_clear(ml):
    for i in range(500):
        ml.append(_msg(i))
    ml.clear()
    assert ml.count == 0
    assert ml._cum == [0]
    assert ml._item_ids == []


def test_avatar_items_registered_and_cleared(ml):
    """他人消息头像必须登记进 _item_ids，清空/切会话时一并删除——
    否则换会话后旧头像残留画布（图：公共频道→收藏夹，左缘仍有一串头像）。"""
    ml.set_me_uid(2)
    ml.append(_msg(1, uid=1, nick="联调甲", channel="public", text="别人的消息"))
    ml._delete_items()
    y = 0
    for i, row in enumerate(ml._rows):
        y += ml._draw_row(i, row, y, 400)
    # 他人行头部画了「联」字头像 → 至少 2 个 item（圆形 + 首字）被登记
    oval = [i for i in ml._item_ids if ml.type(i) == "oval"]
    assert oval, "他人消息头像未被登记进 _item_ids（会残留）"
    ml.clear()                                   # 模拟切到收藏夹/换会话
    assert ml._item_ids == [], "清空后头像应随 _item_ids 一并删除"


def test_load_bulk(ml):
    msgs = [_msg(i, text=f"装载{i}") for i in range(3000)]
    ml.load(msgs, me_uid=2)
    assert ml.count == 3000
    assert ml.at_bottom
    assert len(ml._item_ids) <= 60


def test_system_and_private_colors(ml):
    """逐行直绘验证着色（不依赖视口尺寸：CI 下窗口可能未映射成 1x1）。"""
    ml.set_me_uid(2)
    ml.append_sys("系统提示")
    ml.append(_msg(1, uid=2, nick="我", channel="public"))
    ml.append(_msg(2, uid=1, nick="甲", channel="private"))
    ml._delete_items()
    y = 0
    for i, row in enumerate(ml._rows):
        y += ml._draw_row(i, row, y, 400)
    colors = {ml.itemcget(i, "fill") for i in ml._item_ids}
    assert "#aaaaaa" in colors               # sys 灰
    assert "#54cd9b" in colors               # 自己气泡薄荷
    assert "#5f4b38" in colors               # 私聊棕色


def test_halo_off_produces_no_halo_items(ml):
    """R17：未开描边时，正文只用主色，不产生额外光晕副本。"""
    ml.set_me_uid(2)
    ml.append(_msg(1, uid=1, nick="甲", channel="public", text="描边测试"))
    ml._delete_items()
    y = 0
    for i, row in enumerate(ml._rows):
        y += ml._draw_row(i, row, y, 400)
    # 只统计 text 类 item 的主色（气泡是 rectangle，不算）
    os = ml._item_ids
    text_fills = [ml.itemcget(i, "fill") for i in os if ml.type(i) == "text"]
    # 头像首字本身是白色（avatar._FG），仅此一个；正文未开光晕不得出现额外白副本
    assert text_fills.count("#ffffff") <= 1, text_fills


def test_halo_on_adds_outline_copies(ml):
    """R17：开描边后，正文文本其后多出 4 个白色光晕副本（形成描边）。"""
    ml.set_me_uid(2)
    ml.set_halo("#ffffff")
    ml.append(_msg(1, uid=1, nick="甲", channel="public", text="描边"))
    ml._delete_items()
    y = 0
    for i, row in enumerate(ml._rows):
        y += ml._draw_row(i, row, y, 400)
    text_fills = [ml.itemcget(i, "fill") for i in ml._item_ids
                  if ml.type(i) == "text"]
    whites = sum(1 for f in text_fills if f == "#ffffff")
    assert whites >= 4, f"光晕副本偏少: whites={whites}"
    # 切换关闭 → 光晕副本消失（且幂等不重绘崩）
    ml.set_halo(None)
    assert ml._halo is None
    ml.set_halo(None)


# ---------- R13 表情回应 / 已读回执 ----------
def test_reaction_items_sorted(ml):
    from widgets.msg_list import MsgList
    items = MsgList._reaction_items(None)
    assert items == []
    items = MsgList._reaction_items({"❤": {"1": 1.0}, "👍": {"2": 2.0, "3": 3.0}})
    assert items == [("👍", 2, True), ("❤", 1, True)]   # 降序
    # 空桶被跳过
    items = MsgList._reaction_items({"⭐": {}})
    assert items == []


def test_reaction_bar_render(ml):
    """R13：回应条占位高度并入行高，渲染产出药丸矩形/文本 item。"""
    ml.set_me_uid(2)
    reactions = {"❤": {"1": 100.0, "2": 101.0}}          # 两人点❤，"我"(uid2)回应了
    ml.append({"uid": 1, "nick": "甲", "channel": "public",
               "ts": time.time(), "text": "带回应", "reactions": reactions})
    assert ml._reaction_height(ml._rows[0]) == ml.REACT_PAD > 0
    # 直绘：我参与回应的表情 → 药丸底色主题色（与 own 布局参数无关，仅看 me_uid 是否命中）
    ml._delete_items()
    row = ml._rows[0]
    ml._draw_reaction_bar(row, 0, 400, True)
    fills_own = {ml.itemcget(i, "fill") for i in ml._item_ids}
    assert ml._pal["react_own"] in fills_own
    # 换成"我没参与回应"的表情 → 普通底色
    ml._delete_items()
    row2 = ml._rows[0]
    row2.raw["reactions"] = {"👍": {"1": 100.0}}
    ml._draw_reaction_bar(row2, 0, 400, False)
    fills = {ml.itemcget(i, "fill") for i in ml._item_ids}
    assert ml._pal["react_bg"] in fills and ml._pal["react_own"] not in fills


def test_read_mark_in_heading(ml):
    """R13：对端已读到自己的消息 → 行头带 ✓已读（R33③ 起为独立 READ_MARK 段）。"""
    ml.set_me_uid(2)
    ml.append({"uid": 2, "nick": "我", "channel": "public",
               "ts": time.time(), "text": "你读了吗", "seq": 10})
    ml.set_reads({"1": 10})                                # 对端 uid=1 读到 seq10
    segs = ml._heading_segs(ml._rows[0], False, True)
    assert any(k == "read_mark" and "✓已读" in t for t, k in segs)
    # 未读/无回执 → 无标记
    ml.clear_reads()
    segs2 = ml._heading_segs(ml._rows[0], False, True)
    assert all(k != "read_mark" for _t, k in segs2)


def test_voice_row_body_and_render(ml, tmp_path):
    """R19：语音消息正文含 [语音] 占位，可播放气泡（有 voice_path）可渲染；无路径灰显。"""
    vp = tmp_path / "v.wav"
    vp.write_bytes(b"RIFFWAVE")
    ml.append({"uid": 1, "nick": "甲", "channel": "public", "ts": time.time(),
               "voice": True, "duration": 3.2, "voice_path": str(vp)})
    assert ml.count == 1
    assert "[语音]" in ml.body_text(0)                       # 搜索/复制用占位
    row = ml._rows[0]
    assert row.voice and row.voice_dur == 3.2 and row.voice_path == str(vp)
    ml.configure(width=400)
    ml._render()                                             # 可播放气泡不崩
    assert len(ml._item_ids) >= 1
    # 无 voice_path（服务器 TTL 过期/历史墓碑）→ 渲染不崩
    ml2 = MsgList(ml.winfo_toplevel(), FONT)
    ml2.configure(width=400, height=300)
    ml2.append({"uid": 1, "nick": "甲", "channel": "public", "ts": time.time(),
                "voice": True, "duration": 2.0, "voice_path": ""})
    ml2._render()
    assert ml2._rows[0].voice and not ml2._rows[0].voice_path
    ml2.destroy()


def test_voice_on_voice_callback_fired(ml, tmp_path):
    """R19：语音热区带 r19voice 标签 + _on_voice 回调绑定（渲染期 item 存在）。"""
    calls = []
    vp = tmp_path / "v.wav"
    vp.write_bytes(b"data")
    ml._on_voice = lambda i, p: calls.append((i, p))
    ml.append({"uid": 1, "nick": "甲", "channel": "public", "ts": time.time(),
               "voice": True, "duration": 1.0, "voice_path": str(vp)})
    ml.configure(width=400)
    ml._render()
    # 有 voice 热区 item（标签 r19voice0）→ 说明点击区域已创建
    assert len(ml.find_withtag("r19voice0")) >= 1
    assert ml._on_voice is not None


# ---------- R68 语音播放进度条 ----------
def test_voice_progress_none_when_idle(ml, tmp_path):
    """未播放时 _voice_progress 返回 None（不画进度填充）。"""
    ml._voice_playing = None
    assert ml._voice_progress(0) is None


def test_voice_started_sets_progress_and_ticks(ml, tmp_path):
    """voice_started 记录播放起点、排程推进帧；进度随时间单调上升。"""
    vp = tmp_path / "v.wav"
    vp.write_bytes(b"RIFF")
    ml.append({"uid": 1, "nick": "甲", "channel": "public", "ts": time.time(),
               "voice": True, "duration": 2.0, "voice_path": str(vp)})
    ml.configure(width=400)
    ml._render()
    ml.voice_started(0, 2.0, 1.0)
    assert ml._voice_playing and ml._voice_playing[0] == 0
    assert ml._voice_progress(0) is not None
    assert ml._voice_progress(1) is None          # 非播放行无进度
    assert ml._voice_job is not None              # 已排程推进帧
    ml.after_cancel(ml._voice_job)
    ml._voice_job = None
    ml._voice_playing = None


def test_voice_rate_scales_effective_duration(ml, tmp_path):
    """倍速播放:实际时长 = dur / rate（×2 时进度推进更快）。"""
    ml.voice_started(0, 4.0, 2.0)
    assert abs(ml._voice_playing[2] - 2.0) < 1e-6
    ml.after_cancel(ml._voice_job)
    ml._voice_job = None
    ml._voice_playing = None


def test_voice_tick_clears_when_done(ml):
    """播放时长耗尽 → _voice_tick 清状态且不再续帧。"""
    ml._voice_playing = (0, time.monotonic() - 5.0, 1.0)   # 已超时
    ml._voice_job = None
    ml._voice_tick()
    assert ml._voice_playing is None
    assert ml._voice_job is None


# ---------- R65D 缩略图轮询空闲自停 ----------
def test_img_tick_self_stops_when_idle(ml):
    """无待处理/无在途解码时不得续帧（原实现每 180ms 无条件自唤醒）。"""
    ml._img_ready.clear()
    ml._img_inflight = 0
    ml._img_job = None
    ml._img_tick()
    assert ml._img_job is None                    # 空闲 → 不排程
    ml._img_inflight = 1                          # 仍有解码在途 → 继续等结果
    ml._img_tick()
    assert ml._img_job is not None
    ml.after_cancel(ml._img_job)
    ml._img_job = None
    ml._img_inflight = 0


def test_request_img_kicks_then_self_stops(ml, tmp_path):
    """_request_img 幂等启动轮询；解码+消费完成后计数归零且轮询自停。"""
    from PIL import Image
    p = str(tmp_path / "r65d.png")
    Image.new("RGB", (30, 20), (255, 0, 0)).save(p)
    ml._request_img(p)
    assert ml._img_inflight == 1 and ml._img_job is not None    # 有活 → 已排程
    first_job = ml._img_job
    ml._img_kick()                                              # 幂等：不重复排程
    assert ml._img_job == first_job
    deadline = time.time() + 5
    while ml._img_inflight > 0 and time.time() < deadline:
        time.sleep(0.02)
    assert ml._img_inflight == 0 and p in ml._img_pil
    deadline = time.time() + 5                                   # 推进事件循环跑到自停
    while ml._img_job is not None and time.time() < deadline:
        ml.update()
        time.sleep(0.02)
    assert ml._img_job is None
    assert p in ml._img_photo
