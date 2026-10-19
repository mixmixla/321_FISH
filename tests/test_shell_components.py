# -*- coding: utf-8 -*-
"""共用外壳新组件：桩画布安全、分区字典契约、键名外置（不得硬编码 azul_*）。"""
from pathlib import Path

from boardgames import shell
from client_gameui import _shade

ROOT = Path(__file__).resolve().parents[1]

FAKE_KEYS = {
    "board": "fake_board",
    "tile": "fake_tile_{c}",
    "wall_cell": "fake_wall_{c}",
    "floor": "fake_floor",
    "chip": "fake_chip",
    "marker": "fake_marker_{c}",
    "color": {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0",
              "y": "#E0B33C", "k": "#3A3A3A"},
}


class _Stub:
    """最小画布桩：任何绘制入口都记录调用并返回 None（不实例化 tk / ImageTk）。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append((name, a, k))
            return None
        return _call


def test_table_falls_back_to_flat_color_without_key():
    cv = _Stub()
    shell.table(cv, 800, 600)
    assert any(n == "create_rectangle" for n, _a, _k in cv.calls)


def test_layout_returns_zone_dict_and_legacy_scalars():
    d = shell.layout(1280, 720, n_players=3)
    for key in ("info", "left", "center", "right", "cell", "cols", "rows",
                "top_h", "base_y", "avh", "rw", "wlx", "wcell"):
        assert key in d, key
    for key in ("info", "left", "center", "right"):
        x0, y0, x1, y1 = d[key]
        assert x1 > x0 and y1 > y0
    assert d["right"][0] >= d["center"][2]
    assert d["info"][3] <= d["left"][1]


def test_info_bar_renders_without_any_key():
    cv = _Stub()
    shell.info_bar(cv, 900, shell.HEADER_H, shell.INFO_H, 3, "P7", 21,
                   {"7": 5, "8": 3}, 7)
    assert cv.calls
    # 未给 bg_key → 走矢量回退底色 + 分隔线（桩画布绝不触碰 ImageTk）
    kinds = [n for n, _a, _k in cv.calls]
    assert "create_rectangle" in kinds and "create_line" in kinds
    # 轮次/回合/袋剩与各玩家分数都真的进了 create_text
    txt = [str(v) for a in _create_text_args(cv) for v in a]
    assert any("第 3 轮" in t for t in txt)
    assert any("回合 → P7" in t for t in txt)
    assert any("袋剩 21" in t for t in txt)
    assert "5" in txt and "3" in txt
    # 自己（me="7"）的分数走强调色分支，他人的用常规前景色
    sc_fill = {k.get("text"): k.get("fill") for n, _a, k in cv.calls
               if n == "create_text" and k.get("text") in ("5", "3")}
    assert sc_fill["5"] != sc_fill["3"]


def test_factory_disc_draws_plate_and_tiles():
    cv = _Stub()
    tiles = [{"c": "r"}, {"c": "b"}, {"c": "r"}]
    shell.factory_disc(cv, 120, 160, 44, tiles, plate_key="fake_plate",
                       tile_key="fake_tile_{c}", colors=FAKE_KEYS["color"])
    assert cv.calls
    ovals = [k for n, _a, k in cv.calls if n == "create_oval"]
    assert sum(k.get("outline") == "#2E4A63" for k in ovals) == 1   # 盘底圆一次
    assert sum(k.get("outline") == "#000" for k in ovals) == 3      # 3 块花砖各一次
    centers = [((a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0)
               for n, a, k in cv.calls
               if n == "create_oval" and k.get("outline") == "#000"]
    assert len(set(centers)) == 3                                   # 环形均布，互不重叠
    fills = [k.get("fill") for n, _a, k in cv.calls if n == "create_rectangle"]
    assert _shade("#F7FAFC", 0.32) in fills                         # 普通工厂盘盘底
    assert _shade("#D2534F", 0.32) in fills                         # 花砖按 colors 取色（r）
    assert _shade("#4A7DE0", 0.32) in fills                         # 花砖按 colors 取色（b）

    holes = _Stub()
    shell.factory_disc(holes, 120, 160, 40, tiles, center=True,
                       plate_key="fake_plate_c", tile_key="fake_tile_{c}")
    assert holes.calls
    hovals = [k for n, _a, k in holes.calls if n == "create_oval"]
    assert sum(k.get("outline") == "#2E4A63" for k in hovals) == 1  # 中央池盘底一次
    assert sum(k.get("outline") == "#000" for k in hovals) == 3     # 3 块花砖各一次
    hfills = [k.get("fill") for n, _a, k in holes.calls
              if n == "create_rectangle"]
    assert _shade("#FFF6D8", 0.32) in hfills                        # center=True 暖黄瓷盘
    assert _shade("#888", 0.32) in hfills                           # 未给 colors → 灰默认


def test_board_panel_draws_rows_wall_floor_and_score():
    cv = _Stub()
    shell.board_panel(cv, 0, 0, 384, 288, "P7",
                      rows={"0": ["r"], "1": ["b", "b"]},
                      wall={"0,0": "b"}, floor=["k", "r"], score=5,
                      keys=FAKE_KEYS, wall_expected=lambda r, c: "rwbyk"[(c - r) % 5],
                      active=True)
    assert cv.calls
    assert any(n == "create_text" for n, _a, _k in cv.calls)


def test_score_ring_places_one_marker_per_player():
    cv = _Stub()
    shell.score_ring(cv, 500, 300, 90, {"7": 5, "8": 30}, 7,
                     markers={"7": "b", "8": "k"}, ring_key="fake_ring",
                     marker_key="fake_marker_{c}", colors=FAKE_KEYS["color"])
    assert cv.calls
    ovals = [(a, k) for n, a, k in cv.calls if n == "create_oval"]
    assert sum(k.get("outline") == "#101E2C" for _a, k in ovals) == 1
    marks = [a for a, k in ovals if k.get("outline") == "#0E1B28"]
    assert len(marks) == 2                       # 2 个玩家 → 恰好 2 枚棋子
    hl = [a for a, k in ovals if k.get("outline") == "#FFD977"]
    assert len(hl) == 1                          # 只有当前玩家带高亮环
    ctr = lambda a: ((a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0)
    assert ctr(marks[0]) != ctr(marks[1])        # 分数不同 → 落位不同
    assert abs(ctr(hl[0])[0] - ctr(marks[0])[0]) < 1e-6
    assert abs(ctr(hl[0])[1] - ctr(marks[0])[1]) < 1e-6   # 高亮环落在 me="7" 那枚
    fills = [k.get("fill") for n, _a, k in cv.calls if n == "create_rectangle"]
    assert _shade("#24405A", 0.32) in fills      # 轨道盘底回退色
    assert _shade("#4A7DE0", 0.32) in fills      # markers["7"]="b" 的棋子色
    assert _shade("#3A3A3A", 0.32) in fills      # markers["8"]="k" 的棋子色


def _create_text_args(cv):
    # _text 经 cv.create_text(x, y, text=s, ...) 传文本，text 是关键字参数；
    # 并入 text 后断言才能观察到行号/角标文本（否则只能看到 (x, y) 坐标）。
    return [a + (k.get("text"),) for n, a, k in cv.calls if n == "create_text"]


def test_board_panel_has_no_row_labels_and_keeps_note():
    """BGA 式板面：不再画 1~5 行号；空地板槽显示 -1/-1/-2/-2/-2/-3/-3。"""
    compact = _Stub()
    shell.board_panel(compact, 0, 0, 384, 288, "P7", rows={}, wall={}, floor=[],
                      score=0, keys=FAKE_KEYS, active=False, compact=True,
                      note="地板 3")
    txt = [str(v) for a in _create_text_args(compact) for v in a]
    assert "1" not in txt and "2" not in txt and "5" not in txt
    assert any("地板 3" in t for t in txt)
    assert "-1" in txt and "-2" in txt and "-3" in txt   # 地板扣分刻度

    wide = _Stub()
    shell.board_panel(wide, 0, 0, 384, 288, "P7", rows={}, wall={}, floor=[],
                      score=0, keys=FAKE_KEYS, active=False)
    wtxt = [str(v) for a in _create_text_args(wide) for v in a]
    assert "1" not in wtxt and "5" not in wtxt           # 宽板同样不画行号
    assert "-1" in wtxt and "-3" in wtxt


def test_shell_does_not_hardcode_azul_keys():
    src = (ROOT / "boardgames" / "shell.py").read_text(encoding="utf-8")
    assert "azul_" not in src
