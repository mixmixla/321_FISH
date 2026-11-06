"""The painted hand, click and wire value must agree in the actual Tk room."""
from types import SimpleNamespace
import tkinter as tk

import client
from boardgames.rps_table import HANDS
from games_pkg.rps import RpsGame
from test_flagship_gui import _fake_game_core


def test_three_cards_submit_the_pictured_hands_and_only_for_this_round():
    game = RpsGame([7, 8, 9], seed=11)
    core = _fake_game_core("rps")
    core.game_room["players"] = list(game.players)
    core.game_state = game.snapshot()
    root = tk.Tk()
    root.withdraw()
    app = SimpleNamespace(root=root, core=core, _frameless=False,
                          _camo_title=lambda: "Synthetic RPS")
    host = client.GameWindow(app, pal=client._DEFAULT_PAL)
    try:
        host._sync()
        root.update()
        ui, cv = host._cv_ui, host.game_cv
        assert [hand[0] for hand in HANDS] == ["石头", "布", "剪刀"]
        for choice in range(3):
            host._render_canvas()
            root.update()
            assert len(cv.find_withtag("card-illustration")) == 3
            boxes = ui["rps_cards"]
            assert len(boxes) == 3
            x0, y0, x1, y1 = boxes[choice]
            cv.event_generate("<ButtonPress-1>", x=round((x0+x1)/2), y=round((y0+y1)/2))
            host._do_action({"choice": choice}, ui)  # same frame, before a broadcast
            assert core.calls.pop() == ("room-1", {"choice": choice, "round": choice}) and not core.calls
            game.act(7, {"choice": choice})
            assert game.submitted[7] == choice
            # The previous surface is stale while the next state is in flight.
            core.game_state = game.snapshot()
            host._do_action({"choice": 0}, ui)
            assert not core.calls
            host._render_canvas()
            assert ui["rps_cards"] == []
            game.act(8, {"choice": (choice+1)%3})
            game.act(9, {"choice": (choice+2)%3})
            assert game.round == choice+1
            core.game_state = game.snapshot()
        core.uid = 99
        host._render_canvas()
        assert ui["rps_cards"] == []
    finally:
        host.close()
        root.destroy()
