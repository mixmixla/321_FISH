"""Desktop card faces consume the real engines' public/private string formats."""
import random

import pytest

import client_gameui as cu
from games_pkg.blackjack import _card_str as poker_string
from games_pkg.gongfang import GongfangGame
from games_pkg.uno import _build_deck, _card_str as uno_string


class Canvas:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@pytest.fixture
def drawn(monkeypatch):
    faces, labels = [], []
    monkeypatch.setattr(cu, "_card_face", lambda cv, *args, **kwargs: faces.append(kwargs))
    monkeypatch.setattr(cu, "_text", lambda cv, x, y, text, *args, **kwargs:
                        labels.append((str(text), args[0] if args else None)))
    return faces, labels


PALETTE = {"red": "#e05555", "yellow": "#f2c94c", "green": "#4a9b5f", "blue": "#4a7de0"}


@pytest.mark.parametrize("color,value,symbol", [
    ("red", 7, "7"), ("yellow", 7, "7"), ("green", 7, "7"), ("blue", 7, "7"),
    ("yellow", "skip", "跳过"), ("green", "reverse", "反转"), ("blue", "draw2", "+2"),
])
def test_uno_real_number_and_action_strings_keep_color_and_symbol(drawn, color, value, symbol):
    deck = _build_deck(random.Random(10))
    card = next(c for c in deck if c["color"] == color and c["value"] == value)
    faces, labels = drawn
    cu._draw_uno_card(Canvas(), 0, 0, 64, 92, uno_string(card), PALETTE, cu._FONT_B)
    assert faces[-1]["face"] == PALETTE[color]
    assert labels[-1][0] == symbol


@pytest.mark.parametrize("value,title", [("wild", "万能"), ("wild4", "万能+4")])
def test_uno_real_wild_cards_keep_dark_face_and_full_label(drawn, value, title):
    card = next(c for c in _build_deck(random.Random(10)) if c["value"] == value)
    faces, labels = drawn
    cu._draw_uno_card(Canvas(), 0, 0, 64, 92, uno_string(card), PALETTE, cu._FONT_B, selected=True)
    assert faces[-1]["face"] == "#2c2c2c" and faces[-1]["selected"] is True
    assert labels[-1][0] == title


@pytest.mark.parametrize("suit,rank", [(s, "10") for s in ("♠", "♥", "♦", "♣")]+[("♠", "A"), ("♦", "K")])
def test_poker_engine_rank_and_suit_stay_intact(drawn, suit, rank):
    faces, labels = drawn
    cu._draw_poker(Canvas(), 0, 0, poker_string((suit, rank)))
    assert [s for s, color in labels] == [rank, suit]
    assert all(color == ("#c0392b" if suit in ("♥", "♦") else "#1b1b1b") for _, color in labels)
    assert not faces[-1].get("back")


def test_poker_hidden_card_does_not_reveal_rank_or_suit(drawn):
    faces, labels = drawn
    cu._draw_poker(Canvas(), 0, 0, poker_string(("♥", "10")), face_down=True)
    assert faces[-1]["back"] is True and labels == []


@pytest.mark.parametrize("legacy_marker", [False, True])
def test_workshop_displays_real_points_and_occupancy_without_first_player_promise(drawn, legacy_marker):
    game = GongfangGame([7, 8], seed=10)
    spot = game.spots[0]
    points = spot["pts"]
    faces, labels = drawn
    def paint():
        labels.clear()
        state = game.snapshot()
        # Old snapshots could mark this unused flag True. Neither form gives
        # a first-player benefit; point values and ownership stay authoritative.
        state["spots"] = [dict(s, exclusive=legacy_marker) for s in state["spots"]]
        cu._p_gongfang(Canvas(), state, 8, lambda u: f"玩家{u}",
                      lambda a: None, lambda: None, {}, None, 800, 560)
        return [s for s, _ in labels]
    text = paint()
    assert "空闲" in text and f"+{points} 分" in text
    assert not any("先手" in s for s in text)
    game.act(7, {"op": "pass"})
    game.act(8, {"op": "work", "id": spot["id"]})
    text = paint()
    assert "玩家8" in text and game.score[8] == points
    assert not any("先手" in s for s in text)


@pytest.mark.parametrize("side,code,y", [(0, 10, 7), (1, 20, 1)])
def test_shogi_promoted_bishop_keeps_glyph_side_font_and_normal_move(monkeypatch, side, code, y):
    from games_pkg.shogi import ShogiGame
    game = ShogiGame([7, 8], seed=10)
    game.board[y][1] = code
    game.turn = side
    actor = game.players[side]
    pieces, lettering, sent = [], [], []
    original = cu._shogi_piece
    def piece(cv, cx, cy, cell, symbol, dark, *args, **kwargs):
        pieces.append((symbol, dark))
        return original(cv, cx, cy, cell, symbol, dark, *args, **kwargs)
    monkeypatch.setattr(cu, "_shogi_piece", piece)
    monkeypatch.setattr(cu, "_text", lambda cv, x, y, text, color, font, **kwargs:
                        lettering.append((text, color, font)))
    ui = {"game": "shogi", "me": actor, "sel": {}, "submit": sent.append, "repaint": lambda: None}
    cu._p_shogi(Canvas(), game.snapshot(), actor, str, sent.append, lambda: None, ui, None, 640, 560)
    assert [(s, dark) for s, dark in pieces if s == "馬"] == [("馬", side == 1)]
    assert next(row for row in lettering if row[0] == "馬") == (
        "馬", "#1b1b1b" if side == 1 else "#c0392b", (cu._FONT_B[0], int(ui["cell"]*0.40)))
    for x in (1, 2):
        cu.handle_click(ui, ui["ox"]+(x+0.5)*ui["cell"], ui["oy"]+(y+0.5)*ui["cell"])
    assert sent == [{"fx": 1, "fy": y, "tx": 2, "ty": y}]
    game.act(actor, sent[0])
    assert game.board[y][2] == code and game.board[y][1] == 0


def test_shogi_empty_selection_still_supports_hand_piece_drop():
    from games_pkg.shogi import G, ShogiGame
    game = ShogiGame([7, 8], seed=10)
    game.hand[0] = [G]
    sent = []
    ui = {"game": "shogi", "me": 7, "sel": {}, "submit": sent.append, "repaint": lambda: None}
    cu._p_shogi(Canvas(), game.snapshot(), 7, str, sent.append, lambda: None, ui, None, 640, 560)
    rect = ui["hands"][0]
    cu.handle_click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    assert ui["sel"] == {"game": "shogi", "drop": G} and not sent
    cu.handle_click(ui, ui["ox"]+4.5*ui["cell"], ui["oy"]+4.5*ui["cell"])
    assert sent == [{"op": "drop", "t": G, "x": 4, "y": 4}]
    game.act(7, sent[0])
    assert game.board[4][4] == G and not game.hand[0]
