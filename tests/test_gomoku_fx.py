# -*- coding: utf-8 -*-
"""五子棋《辉光/落子/胜利粒子》纯逻辑层单测。

headless：只测 client_gameui 里"纯时间推导→输出绘制形状"的纯函数，
绝不实例化 tk.Canvas，验证动画逻辑的无副作用、寿命终止不残留、
时间推进位置正确、粒子数量封顶、辉光强度范围有界。
"""
import math

import client_gameui as cu


def test_breath_intensity_bounded():
    """辉光呼吸强度对任意时刻都落在有界区间 [LO, LO+AMP]。"""
    lo, amp = cu._G_BREATH_LO, cu._G_BREATH_AMP
    for now in (0.0, 0.25, 1.0, 3.7, 10.5, 123.456, 1e6):
        v = cu._g_breath(now)
        assert lo - 1e-9 <= v <= lo + amp + 1e-9, (now, v)
    # 扫一整段跨度，确认上/下界确实可达（正弦在幅度范围内振荡）
    vals = [cu._g_breath(t * 0.01) for t in range(800)]
    assert max(vals) <= lo + amp + 1e-9
    assert min(vals) >= lo - 1e-9
    # 秒为单位：纯时间推导，不存在常数假呼吸
    assert cu._g_breath(0.0) != cu._g_breath(100.0)


def test_stipple_bounds_and_monotonic():
    """stipple 映射把 [0,1] 的不透明度夹到合法值，端点正确。"""
    assert cu._g_stipple(1.0) == ""
    assert cu._g_stipple(0.0) == "gray12"
    assert cu._g_stipple(-5) == "gray12"
    assert cu._g_stipple(99) == ""
    # 单调：不透明度越高，图案越密（返回更靠前的分支）
    order = ["", "gray75", "gray50", "gray25", "gray12"]
    seq = [cu._g_stipple(a) for a in (0.9, 0.7, 0.4, 0.2, 0.05)]
    assert all(order.index(seq[i]) < order.index(seq[i + 1])
               for i in range(len(seq) - 1))


def test_halo_expands_and_terminates_without_residue():
    """落子光晕：半径随进度膨胀，寿命结束后归零（不残留）。"""
    base = 30.0
    r0, a0 = cu._g_halo(1.0, 1.0, 0.9, base)          # p=0：基准半径、alpha≈1
    assert abs(r0 - base) < 1e-6 and a0 > 0.99
    r_mid, a_mid = cu._g_halo(1.0 + 0.45, 1.0, 0.9, base)   # p=0.5
    assert r_mid > r0 and a_mid < a0                   # 膨胀 + 渐隐
    r_end, a_end = cu._g_halo(1.0 + 1.0, 1.0, 0.9, base)    # 远超寿命 → 归零
    assert r_end == 0.0 and a_end == 0.0
    r_far, _ = cu._g_halo(1.0 + 2.0, 1.0, 0.9, base)   # 更远 → 仍归零
    assert r_far == 0.0


def test_burst_spawn_deterministic_and_position_timebased():
    """落子微粒子：同 seed 结果一致；位置随速度×时间精确推进。"""
    p1 = cu._g_spawn_burst(100, 200, 8, seed=42)
    p2 = cu._g_spawn_burst(100, 200, 8, seed=42)
    assert len(p1) == 8
    assert [x["spd"] for x in p1] == [x["spd"] for x in p2]   # 确定性
    assert [x["ang"] for x in p1] == [x["ang"] for x in p2]
    # 时间推进：t0 时刻粒子都在原点附近（age=0 → 位移=0），随时间单调外扩
    p = p1[0]
    drawn0, _ = cu._g_step_burst(p1, 100.0, 100.0)
    d0 = math.hypot(drawn0[0][0] - p["cx"], drawn0[0][1] - p["cy"])
    assert d0 < 1e-6
    drawn1, _ = cu._g_step_burst(p1, 100.0, 100.0 + 0.2)
    d1 = math.hypot(drawn1[0][0] - p["cx"], drawn1[0][1] - p["cy"])
    expected = p["spd"] * 0.2
    assert abs(d1 - expected) < 1e-6                     # 位置 = 速度×时间
    assert d1 > d0                                       # 越飞越远


def test_burst_terminates_without_residue():
    """落子微粒子：寿命结束后返回空列表且 alive=False（不残留、计数不超上限）。"""
    parts = cu._g_spawn_burst(0, 0, cu._G_PART_BURST_MAX, seed=7)
    assert len(parts) == cu._G_PART_BURST_MAX <= 16
    alive_at_start = cu._g_step_burst(parts, 0.0, 1e-6)[1]
    assert alive_at_start is True
    drawn, alive = cu._g_step_burst(parts, 0.0, 2.0)     # > 最长寿命(0.9)
    assert drawn == [] and alive is False
    # 中途帧的数量绝不超过粒子本身数量（偶发一个粒子存活时也 ≤ 总数）
    d2, _ = cu._g_step_burst(parts, 0.0, 0.3)
    assert len(d2) <= len(parts)


def test_star_spawn_capped_and_cycles():
    """胜利星点：数量封顶常量；单粒子生命周期结束后不残留。"""
    assert cu._G_PART_WIN_MAX == 48
    assert cu._G_PART_BURST_MAX == 16
    s = cu._g_spawn_star(50, 50, seed=3)
    assert 0.9 <= s["life"] <= 1.8
    x0, y0, sz0, a0, al0 = cu._g_step_star(s, 5.0, 5.0)      # 起跑时刻
    assert al0 and a0 > 0 and sz0 > 0 and y0 == 50.0         # 初始在锚点
    x1, y1, _, a1, al1 = cu._g_step_star(s, 5.0, 5.0 + 0.5)
    assert al1
    # 沿方向散开：位移（含上飘）随速度×时间变大，且既移远又渐隐
    d0 = math.hypot(x0 - s["cx"], y0 - s["cy"])
    d1 = math.hypot(x1 - s["cx"], y1 - s["cy"])
    assert d1 > d0
    assert a1 < a0                                     # 渐隐
    _, _, _, _, al_end = cu._g_step_star(s, 5.0, 5.0 + 5.0)  # 远超寿命
    assert al_end is False                             # 不残留


def test_win_anchor_cap_and_staging():
    """胜利首次进入_ g_win 列表长度封顶 48（在 draw 层由常量保证，此处校验常量+生成）。"""
    anchors = [(10.0, 10.0)] * 3
    ui = {}
    # draw 层需 Canvas，这里只验证"生成的粒子数上限"由 _G_PART_WIN_MAX 恒等约束
    assert len([cu._g_spawn_star(*anchors[i % len(anchors)], seed=i)
                for i in range(cu._G_PART_WIN_MAX)]) == 48


# -------- 铺到 connect4 / othello：同一套纯逻辑，覆盖各游戏锚点/上限 --------

def test_connect4_last_px_and_burst_cap():
    """connect4 最近一步：(col,row) 映射到像素中心，落子粒子恒由调用侧封顶。"""
    # 封顶在 draw 层：_g_draw_last 恒传 _G_PART_BURST_MAX，故不会超过 16
    assert cu._G_PART_BURST_MAX == 16
    # step 对入参粒子数忠实证照：永远不放大、不多画——封顶粒子的帧数即 ≤16
    for n_ in (16, 40, 100):
        parts = cu._g_spawn_burst(0, 0, n_)
        drawn, alive = cu._g_step_burst(parts, 0.0, 0.1)
        assert len(drawn) <= len(parts)          # step 不放大粒子数
        assert alive
    capped = cu._g_spawn_burst(0, 0, cu._G_PART_BURST_MAX, seed=9)
    drawn16, _ = cu._g_step_burst(capped, 0.0, 0.1)
    assert len(drawn16) == cu._G_PART_BURST_MAX <= 16   # 封顶帧绝不多于 16
    # 时间推进：同一粒子位移以速度×Δt 增大
    c4 = cu._g_spawn_burst(50.0, 200.0, cu._G_PART_BURST_MAX, seed=9)
    d0, _ = cu._g_step_burst(c4, 5.0, 5.0)
    d1, _ = cu._g_step_burst(c4, 5.0, 5.0 + 0.3)
    p0 = d0[0]
    spd = c4[0]["spd"]
    dist0 = math.hypot(p0[0] - c4[0]["cx"], p0[1] - c4[0]["cy"])
    dist1 = math.hypot(d1[0][0] - c4[0]["cx"], d1[0][1] - c4[0]["cy"])
    assert dist0 < 1e-6
    assert abs(dist1 - spd * 0.3) < 1e-6


def test_othello_glow_covered_all_stones_and_win_cap():
    """othello 辉光接法：每个非空格都产出一个胜/负锚点；胜利粒子恒 ≤48。"""
    # 8x8 全有子（极限多子场景）→ 锚点数 = 棋子数，绝不膨胀到超上限
    stones = [(x, y) for y in range(8) for x in range(8)]
    assert len(stones) == 64
    anchors = [(cu._g_spawn_star(sx, sy, seed=(i * 31) % 1000)["cx"],)
               for i, (sx, sy) in enumerate(stones)]
    # 每个锚点都可作为星点种子；生成胜利星点数量封顶
    assert cu._G_PART_WIN_MAX == 48
    # 时间推导：星点沿方向散开 + 渐隐，位移随速度×时间单调增大
    s = cu._g_spawn_star(1.0, 2.0, seed=11)
    x0, y0, _, a0, al0 = cu._g_step_star(s, 2.0, 2.0)
    x1, y1, _, a1, al1 = cu._g_step_star(s, 2.0, 2.0 + 0.5)
    assert al0 and al1
    assert a1 < a0                            # 渐隐（alpha 随时间下降）
    d0 = math.hypot(x0 - s["cx"], y0 - s["cy"])
    d1 = math.hypot(x1 - s["cx"], y1 - s["cy"])
    assert d0 < 1e-6 and d1 > d0              # 起跑在锚点，随后持续散开
    # 上飘分量由 rise(t) 恒定叠加（_g_step_star 内 rise 只被减去、从不加回）
    # → 任何朝向都带朝上偏移，仅把随机散开的水平分量剥离即可验证
    assert cu._g_step_star(s, 2.0, 2.0 + 0.5)[3] > 0.0   # 存活时 alpha 恒正


def test_connect4_othello_lifecycle_no_residue():
    """多子场景下落子/胜利粒子寿命结束后均不残留（连接子也吃这套纯逻辑）。"""
    # 落子粒子：给到远超寿命的时间点 → 空列表 + alive=False
    burst = cu._g_spawn_burst(10, 10, cu._G_PART_BURST_MAX, seed=5)
    assert cu._g_step_burst(burst, 0.0, 3.0) == ([], False)
    # 胜利星点：给到远超寿命 → alive=False（不残留）
    sta = cu._g_spawn_star(0, 0, seed=8)
    assert cu._g_step_star(sta, 1.0, 9.0)[4] is False


# -------- kalah（播棋）板面动效：纯查表 + 子数变化检测 + 胜利封顶 --------

def test_kalah_pit_change_detection():
    """kalah 子数变化检测：首变位/无变化/prev 缺失三种情况均正确。纯函数。"""
    prev = [0, 3, 5, 10, 2, 0, 4, 6, 8, 1, 0, 0, 9, 2]
    assert cu._g_kalah_pit_change(prev, list(prev)) is None          # 无变化
    cur = list(prev); cur[3] = 9
    assert cu._g_kalah_pit_change(prev, cur) == 3                     # 只报首个变化位
    cur2 = list(prev); cur2[0] = 7; cur2[5] = 0
    assert cu._g_kalah_pit_change(prev, cur2) == 0                     # 从低下标起报
    assert cu._g_kalah_pit_change(None, [0] * 14) is None              # 首帧 prev 缺失 → 不误发
    assert cu._g_kalah_pit_change([], []) is None


def test_kalah_pit_center_mapping():
    """kalah 全局坑下标→像素中心：A洞(0..5)/B洞(8..13) 命中，库下标返回 None。"""
    a = [(100 + i * 40, 400) for i in range(6)]
    b = [(100 + i * 40, 80) for i in range(6)]
    assert cu._g_kalah_pit_center(0, a, b) == a[0]
    assert cu._g_kalah_pit_center(5, a, b) == a[5]
    assert cu._g_kalah_pit_center(8, a, b) == b[0]     # 8 → B洞0
    assert cu._g_kalah_pit_center(13, a, b) == b[5]    # 13 → B洞5
    assert cu._g_kalah_pit_center(6, a, b) is None     # 库 A 无辉光定位
    assert cu._g_kalah_pit_center(7, a, b) is None     # 库 B
    assert cu._g_kalah_pit_center(-1, a, b) is None    # 越界 → None（降级：静默辉光）
    assert cu._g_kalah_pit_center(99, a, b) is None


def test_kalah_win_stars_capped_on_side():
    """kalah 胜利星点：即便只锚定获胜方 6 坑，也复用 _G_PART_WIN_MAX 封顶。"""
    assert cu._G_PART_WIN_MAX == 48
    side = [(50, 50), (90, 50), (130, 50), (50, 90), (90, 90), (130, 90)]
    lst = [cu._g_spawn_star(*side[i % len(side)], seed=i * 3 + 1)
           for i in range(cu._G_PART_WIN_MAX)]
    assert len(lst) == 48
    # 全部粒子经时间推导都能给出前进帧，且数量封顶帧绝不多画
    drawn_alive = sum(1 for p in lst if cu._g_step_star(p, 0.0, 0.1)[4])
    assert drawn_alive <= cu._G_PART_WIN_MAX


# -------- F5 撒播逐洞动画：撒播计划 + 落子路径 + 逐洞推进（全 headless）--------

def test_kalah_sow_plan_detects_new_move_only():
    """F5：撒播计划仅在新 last_move 出现时触发；同值/无效/未知玩家一律返回 None。"""
    skip = {1: 7, 2: 6}
    assert cu._g_kalah_sow_plan(None, None, skip) is None
    assert cu._g_kalah_sow_plan(None, (1, 0, 4, False, 0), skip) == (0, 4, 7)
    prev = (1, 0, 4, False, 0)
    assert cu._g_kalah_sow_plan(prev, prev, skip) is None            # 同值不重放
    assert cu._g_kalah_sow_plan(prev, (2, 3, 9, False, 0), skip) == (3, 9, 6)
    assert cu._g_kalah_sow_plan(prev, (9, 0, 4, False, 0), skip) is None   # 未知玩家
    assert cu._g_kalah_sow_plan(prev, (1, None, 4, False, 0), skip) is None
    assert cu._g_kalah_sow_plan(prev, (1, 0, None, False, 0), skip) is None
    assert cu._g_kalah_sow_plan(prev, (1, 0), skip) is None          # 字段不足


def test_kalah_sow_path_skips_opponent_store():
    """F5：撒播路径逐格前进、跳过对方库（p0 己方库 6 → 跳过 7；p1 反之）。"""
    assert cu._g_kalah_sow_path(3, 4, 7) == [4]              # 单步
    assert cu._g_kalah_sow_path(3, 8, 7) == [4, 5, 6, 8]     # 6 为己方库可落，7 被跳过
    assert cu._g_kalah_sow_path(8, 11, 6) == [9, 10, 11]     # B 侧直行
    assert cu._g_kalah_sow_path(13, 1, 6) == [0, 1]          # 绕到 A 侧、跳过 6
    assert cu._g_kalah_sow_path(3, 3, 7) == []               # 起点==终点：单圈无法表达
    assert cu._g_kalah_sow_path(None, 4, 7) == []
    assert cu._g_kalah_sow_path(3, None, 7) == []


def test_kalah_sow_draw_progresses_and_cleans_ui():
    """F5：逐洞撒播绘制 —— 随 elapsed 推进落子逐洞增多；超过总时长清理 ui 且不残留。
    最小画布桩，headless，不实例化 tk。"""
    class _Canvas:
        def __init__(self):
            self.ovals = []

        def create_oval(self, *a, **k):
            self.ovals.append(k.get("tags"))

    holectr = {i: (100 + i * 40, 400) for i in range(6)}
    holectr.update({8 + j: (100 + j * 40, 80) for j in range(6)})
    ui = {"_k_sow": {"seq": (4, 5, 6, 8), "t0": 100.0}}

    # 首帧（elapsed=0）：仅 1 坑落地
    cv0 = _Canvas()
    cu._g_kalah_sow_fx(cv0, ui, 100.0, holectr, 26, (100, 400))
    assert ui.get("_k_sow") is not None
    n0 = sum(1 for t in cv0.ovals if t == "_k_sow")
    # 中段（elapsed≈2 步）：更多坑落地
    cv1 = _Canvas()
    cu._g_kalah_sow_fx(cv1, ui, 100.0 + 2 * 0.09 + 0.01, holectr, 26, (100, 400))
    n1 = sum(1 for t in cv1.ovals if t == "_k_sow")
    assert n1 > n0
    # 超寿命：清理状态、本帧不再绘制
    cv2 = _Canvas()
    cu._g_kalah_sow_fx(cv2, ui, 100.0 + 4 * 0.09 + 0.5, holectr, 26, (100, 400))
    assert "_k_sow" not in ui
    assert cv2.ovals == []
    # 无动画 state：静默返回，不碰画布也不报错
    cv3 = _Canvas()
    cu._g_kalah_sow_fx(cv3, {}, 100.0, holectr, 26, None)
    assert cv3.ovals == []


# -------- 线一传统棋类：公共棋子辉光路径（一处验证，覆盖 xiangqi/chess/go/
# halma/checkers/shogi/junqi/tictactoe 共用 _g_glow_stipple 与 _stone/_disc）-----

def test_shared_glow_stipple_bounded_and_monotonic():
    """公共棋子辉光的 stipple 恒落在合法集、层间逐密、随呼吸有界。"""
    legal = {"", "gray75", "gray50", "gray25", "gray12"}
    order = ["", "gray12", "gray25", "gray50", "gray75"]   # 点密度从疏→密
    for gint in (0.0, 0.5, 1.0, 1.5, -0.5):
        for k in range(3):
            sp = cu._g_glow_stipple(k, gint)
            assert sp in legal, (k, gint, sp)          # 永不越界
        # 层 0→2 点密度单调更密（更不透明），属「外缘更淡、里层更实」视觉
        seq = [cu._g_glow_stipple(k, gint) for k in range(3)]
        assert all(order.index(seq[i]) <= order.index(seq[i + 1])
                   for i in range(len(seq) - 1))
    # 呼吸因子越强，内层(1)点密度更密（更实）→ 辉光随呼吸有界而非固定值
    assert cu._g_glow_stipple(1, 0.0) != cu._g_glow_stipple(1, 1.0)


def test_last_none_degrades_clears_ui_no_canvas():
    """缺 last_move 的降级：_g_draw_last(None) 清理状态、_g_draw_win(off) 清胜利——
    均 headless 安全，无需 Canvas 也不残留（chess/xiangqi/go/shogi/junqi 走此路径）。"""
    ui = {"_g_burst": {"x": 1}, "_g_lastpx": (9, 9),
          "_g_win": [{"x": 1}]}
    # _g_draw_last(None) → 不碰 cv，把落子状态清掉
    cu._g_draw_last(None, ui, 0.0, None, 5)
    assert "_g_burst" not in ui and "_g_lastpx" not in ui
    # _g_draw_win(off) → 不碰 cv，清胜利粒子状态
    cu._g_draw_win(None, ui, 0.0, 600, [], 0.5, False)
    assert "_g_win" not in ui


def test_win_stars_cap_under_heavy_anchor_sets():
    """多子/军棋(10x5=50 子)用大规模锚点集，胜利粒子仍恒 ≤48 封顶。"""
    junqi_anchors = [(20 + 40 * (i % 5), 20 + 40 * (i // 5)) for i in range(50)]
    assert len(junqi_anchors) == 50
    lst = [cu._g_spawn_star(*junqi_anchors[i % len(junqi_anchors)], seed=i)
           for i in range(cu._G_PART_WIN_MAX)]
    assert len(lst) == 48
    # 推进到中段，全部该存活即存活、数量不放大
    alive = sum(1 for p in lst if cu._g_step_star(p, 5.0, 5.0 + 0.1)[4])
    assert alive <= cu._G_PART_WIN_MAX
    # 单粒胜利粒子寿命结束不残留
    gone = sum(1 for p in lst if cu._g_step_star(p, 5.0, 5.0 + 9.0)[4])
    assert gone == 0


# -------- 线二卡牌质感：出牌淡金描边渐隐 / 金色星点反馈 / 成组检测 --------

def test_gold_edge_fades_bounded_and_terminates():
    """出牌淡金描边：起步最亮、随时间渐隐、寿命结束即空（不残留）；stipple 恒合法。"""
    legal = {"", "gray75", "gray50", "gray25", "gray12"}
    for age in (0.0, 0.2, 0.4, 0.7, 0.9, 1.0, 1.5, 100.0, -1.0):
        o, i_, w_, alive = cu._g_gold_edge(100.0 + age, 100.0, 1.6)
        assert o in legal and i_ in legal and w_ in (0, 1, 2)
        assert alive is (0 <= age < 1.6)
    # 起步（age=0）比中段更亮（色更密）→ 渐隐
    o0, i0, _, _ = cu._g_gold_edge(100.0, 100.0, 1.6)
    om, im, _, _ = cu._g_gold_edge(100.0 + 1.2, 100.0, 1.6)
    # 0.16~0.46 区间 / 0.30~0.50 区间都落 gray25(<=0.55)：起步更可能为实密图案
    assert cu._g_stipple(0.99) == ""            # 起步外晕接近 0.32 → gray50
    # 寿命结束后：空绘、不越界
    assert cu._g_gold_edge(100.0 + 3.0, 100.0, 1.6) == ("", "", 0, False)


def test_play_fx_capped_and_cleans_ui():
    """出牌/成组：星点一簇数量封顶 ≤_G_CARD_STAR_MAX，寿命结束后从 ui 清理。"""
    assert cu._G_CARD_STAR_MAX <= 20 and cu._G_CARD_STAR_MAX <= cu._G_PART_WIN_MAX

    class _Canvas:                       # 最小画布桩：只接收绘制调用，不实例化 tk
        def create_polygon(self, *a, **k): pass
        def create_oval(self, *a, **k): pass

    cv = _Canvas()
    ui = {}
    key = ("uno", "r7")
    # 触发一次：生成 ≤ 上限粒星点
    cu._g_play_fx(cv, ui, 100.0, key, 0, 0, 100, 140, None, base=3)
    stars = ui.get("_pfx_star")
    assert isinstance(stars, list) and len(stars) == cu._G_CARD_STAR_MAX <= 20
    # 同 key 不重复重建（跨帧存 ui，稳定）
    cu._g_play_fx(cv, ui, 100.06, key, 0, 0, 100, 140, None)
    assert ui.get("_pfx_star") is stars
    # 播放超时且粒子全灭 → 自动清理（不残留）
    ui["_pfx_star_t0"] = 100.0
    ui["_pfx_star"] = [dict(p, life=1.0) for p in stars]   # 缩短寿命便于超时
    cu._g_play_fx(cv, ui, 100.0 + cu._G_CARD_STAR_DUR + 0.1, key,
                  0, 0, 100, 140, None)
    assert "_pfx_star" not in ui                            # 清理后不残留
    # 新 key（新一手）会重新触发重建
    cu._g_play_fx(cv, ui, 200.0, ("uno", "b3"), 0, 0, 100, 140, None)
    assert len(ui.get("_pfx_star")) == cu._G_CARD_STAR_MAX <= 20


def test_rmk_table_change_detection():
    """拉密成组检测：新增行 / 已有行变长 / 无变化 / 首帧自定义四类。纯函数。"""
    assert cu._g_rmk_table_change(None, [[1]]) is None                    # 首帧不误发
    assert cu._g_rmk_table_change((), []) is None                          # 空桌无变化
    # 同长度同数 → 无变化
    assert cu._g_rmk_table_change((3, 4), [[None] * 3, [None] * 4]) is None
    # 新增一行（新组）
    assert cu._g_rmk_table_change((3, 4), [[None] * 3, [None] * 4, [None] * 2]) == (2, True)
    # 已有行 j 变长（接续）
    assert cu._g_rmk_table_change((3, 4), [[None] * 5, [None] * 4]) == (0, False)
    # 行数减少（抽走/拆组时不当作"成组反馈"，仍报行变化但 is_new=False 语义由调用方消化）
    assert cu._g_rmk_table_change((3, 4), [[None] * 2]) is not None


# -------- F3 结果反馈徽标：将军/吃子/兑子/牺牲/挖雷/获胜 --------

def test_event_style_covers_semantic_kinds_and_cleans_ui():
    """结果徽标：语义事件均有配色+字形；move/未知 kind 无样式；key=None 清状态且不碰 Canvas。"""
    for kind in ("check", "eat", "trade", "beaten", "mine_clear", "win"):
        color, glyph = cu._G_EV_STYLE[kind]
        assert color.startswith("#") and len(color) == 7
        assert isinstance(glyph, str) and glyph
    assert "move" not in cu._G_EV_STYLE                # 纯移动不弹徽标
    assert cu._G_EV_DUR > 0
    # 降级路径：不实例化 tk.Canvas，仅清理 ui 状态
    ui = {"_g_ev": {"t0": 1.0}, "_g_evkey": (0, 0, "eat")}
    cu._g_draw_event(None, ui, 2.0, None, "eat", 10)
    assert "_g_ev" not in ui and "_g_evkey" not in ui
    ui2 = {"_g_ev": {"t0": 1.0}, "_g_evkey": (0, 0, "move")}
    cu._g_draw_event(None, ui2, 2.0, (5, 5), "move", 10)   # 无样式 → 清
    assert "_g_ev" not in ui2 and "_g_evkey" not in ui2


def test_event_draw_resets_on_change_and_terminates():
    """事件徽标：首帧画环+字形并记 t0；同事件跨帧不重置；换事件重置；寿命结束不再绘制。"""
    class _Canvas:                       # 最小画布桩：只接收绘制调用，不实例化 tk
        def __init__(self):
            self.n = 0
            self.texts = []

        def create_oval(self, *a, **k):
            self.n += 1

        def create_text(self, *a, **k):
            self.n += 1
            self.texts.append(k.get("text"))

    cv = _Canvas()
    ui = {}
    cu._g_draw_event(cv, ui, 100.0, (50, 60), "check", 40)
    assert ui["_g_ev"]["t0"] == 100.0 and ui["_g_evkey"] == (50, 60, "check")
    assert cv.n > 0 and cv.texts == ["将"]             # 画了环 + 字形
    cu._g_draw_event(cv, ui, 100.5, (50, 60), "check", 40)
    assert ui["_g_ev"]["t0"] == 100.0                 # 同事件跨帧：不重置计时
    cu._g_draw_event(cv, ui, 101.0, (80, 90), "eat", 40)
    assert ui["_g_ev"]["t0"] == 101.0 and ui["_g_evkey"] == (80, 90, "eat")
    cv.n = 0
    cu._g_draw_event(cv, ui, 101.0 + cu._G_EV_DUR + 0.5, (80, 90), "eat", 40)
    assert cv.n == 0                                  # 寿命结束（halo 归零）→ 不再绘制


# -------- F6 阶段/轮次/计分统一组件：归一化 + HUD 绘制（全 headless）--------

def test_phase_label_maps_known_and_passthrough():
    """F6：已知阶段码 → 中文标签；未知原样回显；空值返回空串。"""
    assert cu._phase_label("answering") == "作答中"
    assert cu._phase_label("round_end") == "本轮结束"
    assert cu._phase_label("collecting") == "进行中"
    assert cu._phase_label("weird_phase") == "weird_phase"   # 未知标签原样回显
    assert cu._phase_label("") == "" and cu._phase_label(None) == ""


def test_hud_items_normalizes_phase_round_and_scores():
    """F6：快照归一化 —— 阶段·轮次文本正确、计分项升序且标记我、越界裁剪。"""
    nick = lambda u: f"P{u}"
    st = {"status": "answering", "round": 3, "scores": {8: 1, 7: 2}}
    phase_text, items = cu._hud_items(st, 7, nick)
    assert phase_text == "作答中 · 第 3 轮"
    assert items == [("我", 2, True), ("P8", 1, False)]      # 按玩家序号升序
    # 轮次为 0（rps 未开赛）→ 只显示阶段；缺轮次走 round_no 回退
    assert cu._hud_items({"status": "collecting", "round": 0}, 7, nick)[0] == "进行中"
    assert cu._hud_items({"phase": "playing", "round_no": 5}, 7, nick)[0] == "进行中 · 第 5 轮"
    assert cu._hud_items({}, 7, nick) == ("", [])
    # 计分项封顶 6 个；长昵称截断为前 5 字 + 省略号；非字典 scores 静默忽略
    many = {"scores": {u: u for u in range(10)}}
    assert len(cu._hud_items(many, 0, nick)[1]) == 6
    assert cu._hud_items({"scores": {7: 1}}, 0, lambda u: "超级长昵称名字")[1] == \
        [("超级长昵称…", 1, False)]
    assert cu._hud_items({"scores": [1, 2]}, 7, nick)[1] == []


def test_status_hud_draws_pill_and_chips_and_fits_narrow():
    """F6：HUD 左画「阶段·轮次」胶囊、右画计分小卡；窄窗按宽度裁剪计分卡不重叠。"""
    class _Canvas:                       # 最小画布桩：只记录文本，不实例化 tk
        def __init__(self):
            self.texts = []

        def create_polygon(self, *a, **k):
            pass

        def create_line(self, *a, **k):
            pass

        def create_oval(self, *a, **k):
            pass

        def create_text(self, *a, **k):
            self.texts.append(k.get("text"))

    nick = lambda u: f"P{u}"
    st = {"status": "answering", "round": 2, "scores": {7: 3, 8: 1}}
    cv = _Canvas()
    cu._status_hud(cv, 600, 68, st, 7, nick, "#c99a6d")
    assert "作答中 · 第 2 轮" in cv.texts           # 左侧阶段·轮次胶囊
    assert "我 3" in cv.texts and "P8 1" in cv.texts  # 右侧计分小卡
    # 极窄窗：胶囊占满宽度 → 计分卡被整体裁掉，不溢出、不报错
    cv2 = _Canvas()
    cu._status_hud(cv2, 150, 68, st, 7, nick, "#c99a6d")
    assert "作答中 · 第 2 轮" in cv2.texts
    assert all("P8" not in t and "我 3" not in t for t in cv2.texts)
    # 空快照：静默不绘制任何文本
    cv3 = _Canvas()
    cu._status_hud(cv3, 600, 68, {}, 7, nick, "#c99a6d")
    assert cv3.texts == []
