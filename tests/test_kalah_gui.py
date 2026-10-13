"""Actual Tk pointer entry over both natural Kalah turns, no profile or network."""
import tkinter as tk

import pytest

import client_gameui as cu
from games_pkg.kalah import KalahGame


@pytest.mark.parametrize("me,b_turn,expected", [(11, False, set(range(1, 7))),
                                              (22, True, set(range(9, 15)))])
def test_live_tk_both_sides_six_holes(me, b_turn, expected):
    root=tk.Tk();root.geometry("480x400")
    cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill="both",expand=True)
    try:
        root.update()
        game=KalahGame([11,22],seed=1)
        if b_turn:game.act(11,{"hole":1})
        state=game.snapshot();sent=[]
        ui={"state":state,"submit":sent.append,"repaint":lambda:None}
        cu.render(cv,"kalah",state,me,str,sent.append,lambda:None,ui,None,
                  cv.winfo_width(),cv.winfo_height())
        cv.bind("<Button-1>",lambda e:cu.handle_click(ui,e.x,e.y))
        root.update()
        for x,y,_,_ in list(ui["holes"]):
            cv.event_generate("<Button-1>",x=int(x),y=int(y));root.update()
        assert {a["hole"] for a in sent}==expected
    finally:root.destroy()
