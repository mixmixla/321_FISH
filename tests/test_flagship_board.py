"""Pure board input/feedback contracts; no Tk window or real input devices."""
import pytest
from types import SimpleNamespace

import client_gameui as ui_module


def board_ui(game="gomoku", can_move=True):
    rows, cols = (15, 15) if game == "gomoku" else (6, 7)
    sent = []
    state = {"board": [[0] * cols for _ in range(rows)], "players": [7, 8],
             "turn_uid": 7, "winner_uid": None, "draw": False, "last_move": None}
    ui = {"game": game, "ox": 20, "oy": 60, "cell": 20, "n": cols,
          "rows": rows, "cols": cols, "state": state, "can_move": can_move,
          "me": 7, "submit": sent.append}
    return ui, sent


@pytest.mark.parametrize(("x", "y", "expected"), [
    (20, 60, (0, 0)), (32, 60, (1, 0)), (10, 60, (0, 0)),
    (9.9, 60, None), (310, 60, None), (309.9, 60, (14, 0)),
    (20, 49.9, None), (20, 50, (0, 0)), (20, 350, None),
])
def test_gomoku_click_and_hover_share_intersection_geometry(x, y, expected):
    ui, sent = board_ui()
    ui_module.handle_click(ui, x, y)
    assert ui_module._cell_of(ui, x, y) == expected
    assert sent == ([] if expected is None else [{"x": expected[0], "y": expected[1]}])


def test_occupied_intersection_is_not_submitted():
    ui, sent = board_ui()
    ui["state"]["board"][0][0] = 1
    ui_module.handle_click(ui, 20, 60)
    assert not sent


@pytest.mark.parametrize("game", ["gomoku", "connect4"])
def test_read_only_player_or_spectator_never_submits(game):
    ui, sent = board_ui(game, can_move=False)
    ui_module.handle_click(ui, 40, 80)
    assert not sent


@pytest.mark.parametrize(("x", "y", "valid"), [
    (20, 40, True), (159.9, 179.9, True), (20, 39.9, False),
    (20, 180, False), (19.9, 60, False), (160, 60, False),
])
def test_connect4_click_is_limited_to_board_and_column_hint(x, y, valid):
    ui, sent = board_ui("connect4")
    ui_module.handle_click(ui, x, y)
    assert bool(sent) is valid


def test_connect4_full_column_cannot_submit():
    ui, sent = board_ui("connect4")
    for row in ui["state"]["board"]:
        row[0] = 1
    ui_module.handle_click(ui, 25, 70)
    assert not sent


def test_connect4_prompt_strip_shares_column_geometry_with_click():
    ui, sent = board_ui("connect4")
    # One row immediately above the board is the same clickable column hint.
    assert ui_module._cell_of(ui, 25, 45) == (0, -1)
    ui_module.handle_click(ui, 25, 45)
    assert sent == [{"col": 0}]
    sent.clear()
    assert ui_module._cell_of(ui, 25, 39.9) is None
    ui_module.handle_click(ui, 25, 39.9)
    assert not sent


@pytest.mark.parametrize("direction", [(1, 0), (0, 1), (1, 1), (1, -1)])
@pytest.mark.parametrize("needed", [4, 5])
def test_win_line_uses_maximal_run_through_last_move(direction, needed):
    dx, dy = direction
    state = {"board": [[0] * 15 for _ in range(15)], "players": [7, 8],
             "winner_uid": 8, "last_move": [5 + dx, 7 + dy], "draw": False}
    expected = [(5 + i * dx, 7 + i * dy) for i in range(needed + 1)]
    for x, y in expected:
        state["board"][y][x] = 2
    assert ui_module.flagship_win_line(state, needed) == expected


@pytest.mark.parametrize("change", [{"draw": True}, {"winner_uid": None},
                                    {"last_move": [-1, 0]}, {"last_move": None}])
def test_draw_or_invalid_result_never_invents_a_win_line(change):
    state = {"board": [[1] * 5], "players": [7, 8], "winner_uid": 7,
             "last_move": [2, 0], "draw": False}
    state.update(change)
    assert ui_module.flagship_win_line(state, 5) == []


def test_color_is_independent_of_whose_turn_it_is():
    state = {"players": [7, 8], "turn_uid": 8, "winner_uid": None, "draw": False}
    nick = lambda uid: f"玩家{uid}"
    assert "执白" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "轮到你" in ui_module.flagship_status("gomoku", state, 8, nick)
    state["turn_uid"] = 7
    assert "执白" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "等待" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "观战" in ui_module.flagship_status("gomoku", state, 99, nick)
    assert "执黄" in ui_module.flagship_status("connect4", state, 8, nick)


def test_flagship_can_move_requires_current_player_context():
    room = {"status": "playing", "players": [7, 8], "spectators": []}
    state = {"turn_uid": 7, "winner_uid": None, "draw": False}
    assert ui_module.flagship_can_move(room, state, 7, True)
    assert not ui_module.flagship_can_move(room, state, 8, True)
    assert not ui_module.flagship_can_move(
        {**room, "spectators": [7]}, state, 7, True)
    assert not ui_module.flagship_can_move(room, state, 7, False)
    assert not ui_module.flagship_can_move(
        room, {**state, "winner_uid": 7}, 7, True)


def test_client_action_gate_rechecks_round_turn_and_connection():
    from client import GameWindow

    sent = []
    core = SimpleNamespace(
        game_room={"room_id": "r1", "round": 2, "status": "playing",
                   "game": "gomoku", "players": [7, 8], "spectators": []},
        game_state={"turn_uid": 7, "winner_uid": None, "draw": False},
        uid=7, connected=True,
        game_action=lambda rid, action: sent.append((rid, action)),
    )
    host = SimpleNamespace(core=core)
    ui = {"_room_context": ("r1", 2)}
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert sent == [("r1", {"x": 3, "y": 4})]

    sent.clear()
    ui["_room_context"] = ("r1", 1)       # late callback from old round
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert not sent

    ui["_room_context"] = ("r1", 2)
    core.game_state["turn_uid"] = 8         # off-turn player
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert not sent


def test_desktop_game_entry_map_keeps_unverified_games_available():
    from client import _desktop_game_status

    # CC-03 已为围棋/拉密/克苏鲁跑团等 11 款桌游补齐桌面操作入口，
    # 它们现在是“已放开但标注未验证”，不再被只读门禁拦下（见 #1/#6/#7）。
    assert _desktop_game_status("go")[0] == "unverified"
    assert _desktop_game_status("rummikub")[0] == "unverified"
    assert _desktop_game_status("coc")[0] == "unverified"
    assert _desktop_game_status("balatro")[0] == "unverified"
    assert _desktop_game_status("gomoku")[0] == "flagship"
    # 未验证状态必须携带可展示给用户的说明文案（UI 读 note）
    assert _desktop_game_status("go")[1]


# ---------- 放开后三款游戏的桌面真实输入路径（全 headless）----------

def test_go_desktop_click_submits_nearest_intersection():
    """#1/#8：围棋已放开，单击交叉点直接提交 {"x","y"}（GoGame.act 契约）。"""
    sent = []
    board = [[0] * 19 for _ in range(19)]
    ui = {"game": "go", "ox": 0.0, "oy": 0.0, "cell": 10.0, "n": 19,
          "state": {"board": board, "over": False, "winner_uid": None},
          "submit": sent.append}
    ui_module.handle_click(ui, 30.0, 40.0)
    assert sent == [{"x": 3, "y": 4}]
    sent.clear()
    board[4][3] = 1                       # 交叉点已有子 → 不重复落子
    ui_module.handle_click(ui, 30.0, 40.0)
    assert not sent


def test_coc_desktop_click_submits_chosen_card():
    """#8：克苏鲁跑团已放开，点手牌卡提交 {"op":"choose_card","card_id"}。"""
    sent = []
    ui = {"game": "coc", "cards": [(10, 20, 30, 40, "c1")],
          "submit": sent.append}
    ui_module.handle_click(ui, 25, 30)
    assert sent == [{"op": "choose_card", "card_id": "c1"}]
    sent.clear()
    ui_module.handle_click(ui, 100, 100)  # 空白区不提交
    assert not sent


def test_rummikub_desktop_click_toggles_selection():
    """#8：拉密已放开，点手牌切换 sel["rmk"] 高亮集合（出牌由按钮提交）。"""
    repainted = []
    ui = {"game": "rummikub",
          "cards": [(0, 0, 10, 10, "c1"), (12, 0, 22, 10, "c2")],
          "submit": lambda _a: None,
          "repaint": lambda: repainted.append(1)}
    ui_module.handle_click(ui, 5, 5)             # 选中 c1
    assert ui["sel"]["rmk"] == ["c1"]
    ui_module.handle_click(ui, 15, 5)            # 追加选中 c2
    assert set(ui["sel"]["rmk"]) == {"c1", "c2"}
    ui_module.handle_click(ui, 5, 5)             # 取消 c1
    assert ui["sel"]["rmk"] == ["c2"]
    assert repainted


# ---------- 拉密桌面交互：#6 双棋盘选择来源 / #7 弹窗后上下文复核（全 headless）----

def _rummikub_host(sent, lobby_ui, focus_ui=None, game_room=None):
    """构造只带 _submit_sel 所需属性的合成宿主（不建 Tk 窗口）。"""
    from client import GameWindow

    core = SimpleNamespace(
        game_room=game_room or {"room_id": "r1", "round": 1,
                                "game": "rummikub", "status": "playing"},
        game_state={}, uid=7,
        game_meta={"rummikub": {"label": "拉密"}},
        game_action=lambda rid, action: sent.append((rid, action)),
    )

    class _Board:
        def __init__(self, ui):
            self._cv_ui = ui

        def active(self):
            return True

    host = SimpleNamespace(
        core=core, _cv_ui=lobby_ui, _last_board_ui=lobby_ui, win=None,
        act_hint=SimpleNamespace(config=lambda **_k: None),
    )
    host._board_win = _Board(focus_ui) if focus_ui is not None else None
    host._board_uis = lambda: GameWindow._board_uis(host)
    host._room_ctx = lambda: GameWindow._room_ctx(host)
    host._cur_game = lambda: "rummikub"
    host._do_action = (
        lambda action, src=None: GameWindow._do_action(host, action, src))
    return host, core


def test_board_uis_prefers_last_operated_then_focus_then_lobby():
    """#6：候选顺序 = 最近操作棋盘 → 可见专注窗 → 大厅内嵌，且去重。"""
    from client import GameWindow

    lobby, focus = {"sel": {}}, {"sel": {}}
    host, _ = _rummikub_host([], lobby, focus)
    assert GameWindow._board_uis(host) == [lobby, focus]
    host._last_board_ui = focus          # 最近操作改为专注窗
    assert GameWindow._board_uis(host) == [focus, lobby]


def test_submit_sel_reads_selection_from_the_operated_board():
    """#6：大厅选中、专注窗为空时按按钮，仍取大厅那份选择
    （旧码固定取 active 专注窗的 ui → 误报“先在棋盘上点选要出的牌”）。"""
    from client import GameWindow

    sent = []
    lobby = {"sel": {"rmk": ["c1", "c2"]}}
    focus = {"sel": {"rmk": []}}
    host, _ = _rummikub_host(sent, lobby, focus)
    host._last_board_ui = lobby
    GameWindow._submit_sel(host, {"op": "meld", "sel_key": "rmk"})
    assert sent[-1][1] == {"op": "meld", "tiles": ["c1", "c2"]}
    # 提交后两份棋盘的同名勾选都被清空，避免旧选择残留
    assert "rmk" not in lobby["sel"] and "rmk" not in focus["sel"]


def test_submit_sel_ignores_stale_selection_on_the_other_board():
    """#6：专注窗留有旧选择但用户实际在大厅操作 → 提交大厅那份，不误取旧牌。"""
    from client import GameWindow

    sent = []
    lobby = {"sel": {"rmk": ["c1"]}}
    focus = {"sel": {"rmk": ["stale"]}}
    host, _ = _rummikub_host(sent, lobby, focus)
    host._last_board_ui = lobby
    GameWindow._submit_sel(host, {"op": "meld", "sel_key": "rmk"})
    assert sent[-1][1]["tiles"] == ["c1"]


def test_submit_sel_discards_stale_context_after_row_dialog(monkeypatch):
    """#7：接续弹窗为模态等待，期间对局被替换 → 复核上下文后丢弃旧选择，
    不再把旧牌提交到新房间；上下文未变时正常提交。"""
    import widgets.dialogbox as dialogbox
    from client import GameWindow

    sent = []
    lobby = {"sel": {"rmk": ["c1", "c2"]}}
    host, core = _rummikub_host(sent, lobby)

    def _ask_switching_room(*_a, **_k):
        core.game_room = {"room_id": "r2", "round": 1,
                          "game": "rummikub", "status": "playing"}
        return "1"

    monkeypatch.setattr(dialogbox, "ask_string", _ask_switching_room)
    GameWindow._submit_sel(host, {"op": "extend", "sel_key": "rmk",
                                  "need_row": True})
    assert not sent                                  # 旧选择未落到新房间
    assert "rmk" not in lobby["sel"]                 # 陈旧选择已清理

    lobby["sel"] = {"rmk": ["c1"]}
    monkeypatch.setattr(dialogbox, "ask_string", lambda *_a, **_k: "2")
    GameWindow._submit_sel(host, {"op": "extend", "sel_key": "rmk",
                                  "need_row": True})
    assert sent and sent[-1][1] == {"op": "extend", "tiles": ["c1"], "row": 1}
