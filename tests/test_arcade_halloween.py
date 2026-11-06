"""Synthetic fruit state, actual Canvas clicks, and seat permission regression."""
from pathlib import Path
import os
import tkinter as tk

import pytest

import client_gameui as gameui
from boardgames import arcade_halloween as table
from games_pkg.halloween import HalloweenGame, FRUITS


class Canvas:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def record(*args, **kwargs): self.calls.append((name, args, kwargs))
        return record


def setup(game, me=7):
    sent = []
    ui = {"game": "halloween", "me": me, "connected": True,
          "room": {"status": "playing", "players": [7, 8], "spectators": [9]},
          "state": game.snapshot(), "submit": sent.append, "repaint": lambda: None}
    return ui, sent


def paint(cv, ui, width=480, height=400):
    gameui.render(cv, "halloween", ui["state"], ui["me"], lambda u: f"合成{u}",
                  ui["submit"], ui["repaint"], ui, None, width, height)


def select(ui, op):
    r = next(r for r in ui["orchard_hits"] if r[-1] == op)
    gameui.handle_click(ui, (r[0]+r[2])/2, (r[1]+r[3])/2)


@pytest.mark.parametrize("width,height", [(320, 300), (480, 400), (820, 590)])
def test_clicks_tracks_and_seat_gates(width, height):
    g = HalloweenGame([7, 8], seed=4)
    ui, sent = setup(g)
    paint(Canvas(), ui, width, height)
    assert [r[-1] for r in ui["orchard_hits"]] == ["flip"]
    assert all(0 <= a < c <= width and 0 <= b < d <= height for a,b,c,d,_ in ui["orchard_hits"])
    select(ui, "flip")
    assert sent.pop() == {"op": "flip"}
    g.act(7, {"op": "flip"}); ui["state"] = g.snapshot()
    paint(Canvas(), ui, width, height)
    assert [r[-1] for r in ui["orchard_hits"]] == ["slap", "pass"]
    table.key_action(ui, "pass"); assert sent.pop() == {"op": "pass"}
    for update in ({"me":8}, {"me":9}, {"connected":False}, {"state":dict(ui["state"],status="ended")}):
        other = dict(ui, **update)
        paint(Canvas(), other, width, height)
        assert other["orchard_hits"] == []
        gameui.handle_click(other, width/2, height-60)
    assert not sent


@pytest.mark.parametrize("fruit", range(5))
def test_each_fruit_counts_one_to_five_and_slap_collects_exact_area(fruit):
    g = HalloweenGame([7,8],seed=2)
    g.stack = {7:[fruit]*9,8:[(fruit+1)%5]*9}
    for n in range(1,6):
        g.act(7,{"op":"flip"})
        assert g.snapshot()["counts"][FRUITS[fruit]] == n
        assert g.snapshot()["area"].count(FRUITS[fruit]) == n
        assert g.snapshot()["can_slap"] == (n==5)
        if n<5:
            g.act(7,{"op":"pass"});g.act(8,{"op":"flip"});g.act(8,{"op":"pass"})
    ui,sent=setup(g);paint(Canvas(),ui);select(ui,"slap")
    assert sent == [{"op":"slap"}]
    g.act(7,sent[0]);assert g.score[7] == 9 and not g.area and g.turn==7
    assert not g.snapshot()['area_cards']
    assert g.snapshot()['last_action']=={'op':'slap_ok','uid':7,'value':9}


def test_production_page_injects_orchard_renderer():
    import web
    page=web._SERVED_PAGE().decode("utf-8")
    assert "@@ARCADE_ORCHARD" not in page
    assert "halloween(box,s){OrchardTable.render(box,s);}" in page
    assert "arcade-orchard.webp" in page


def test_real_canvas_art_and_flip_slap_mouse_events():
    root=tk.Tk();root.geometry("820x590+0+0")
    cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill="both",expand=True)
    g=HalloweenGame([7,8],seed=8);g.stack[7]=[0]*8
    ui,sent=setup(g)
    def redraw():
        ui["state"]=g.snapshot();paint(cv,ui,cv.winfo_width(),cv.winfo_height());root.update()
    def submit(action):sent.append(action);g.act(7,action);redraw()
    ui["submit"]=submit
    cv.bind("<Button-1>",lambda e:gameui.handle_click(ui,e.x,e.y))
    try:
        root.update();redraw()
        if os.environ.get("ARCADE_EVIDENCE_DIR"):
            from arcade_capture import capture
            capture(root,Path(os.environ["ARCADE_EVIDENCE_DIR"])/"halloween-tk-start.png")
        g.area=[0]*4;g.area_owners=[7,8,7,8];g.counts=[4,0,0,0,0];redraw()
        assert len(cv.find_withtag("card-illustration")) >= 10
        for op in ("flip","slap"):
            r=next(r for r in ui["orchard_hits"] if r[-1]==op)
            cv.event_generate("<Button-1>",x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
            if op=="flip":
                assert g.counts[0]==5
                assert [c['uid'] for c in g.snapshot()['area_cards']]==[7,8,7,8,7]
                if os.environ.get("ARCADE_EVIDENCE_DIR"):
                    from arcade_capture import capture
                    capture(root,Path(os.environ["ARCADE_EVIDENCE_DIR"])/"halloween-tk-five.png")
                    root.geometry('480x400');root.update();redraw()
                    capture(root,Path(os.environ['ARCADE_EVIDENCE_DIR'])/'halloween-tk-480-decision.png')
                    root.geometry('820x590');root.update();redraw()
        assert sent==[{"op":"flip"},{"op":"slap"}] and g.score[7]==5
        root.geometry("480x360");root.update();redraw()
        cv.focus_force();root.update();cv.event_generate("<KeyPress-f>");root.update()
        assert sent[-1]=={"op":"flip"} and g.have_flipped
        if os.environ.get("ARCADE_EVIDENCE_DIR"):
            from arcade_capture import capture
            capture(root,Path(os.environ["ARCADE_EVIDENCE_DIR"])/"halloween-tk-small.png")
        g.have_flipped=False;g.stack[7]=[0];g.area=[0]*4;g.area_owners=[7,8,7,8];g.counts=[4,0,0,0,0];redraw()
        select(ui,"flip");select(ui,"slap");assert g.finished and g.winner==7
        assert ui["orchard_hits"]==[]
        if os.environ.get("ARCADE_EVIDENCE_DIR"):
            capture(root,Path(os.environ["ARCADE_EVIDENCE_DIR"])/"halloween-tk-ended.png")
    finally:root.destroy()


def test_legacy_text_buttons_and_public_state_dump_are_removed():
    import client
    from types import SimpleNamespace
    assert client._actions_for("halloween",None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),HalloweenGame([7,8],seed=1).snapshot())==""
