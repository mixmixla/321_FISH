"""Actual GameWindow sends: core changes without painting the old canvas."""
import os
from types import SimpleNamespace
import tkinter as tk
import client
from games_pkg.ludo import LudoGame
from test_flagship_gui import _fake_game_core


def test_actual_gamewindow_old_airport_cannot_send_into_replaced_core_context():
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME")
    root=tk.Tk();root.withdraw();core=_fake_game_core("ludo")
    base=LudoGame([7,8],seed=19).snapshot()
    room=dict(room_id="old-airport",round=1,game="ludo",status="playing",players=[7,8],spectators=[])
    core.game_state=base;core.game_room=room
    app=SimpleNamespace(root=root,core=core,_dp=client._DEFAULT_PAL,_frameless=False,_skin={},_camo_title=lambda:"合成旧机场")
    window=None;sent=[]
    try:
        window=client.GameWindow(app,pal=client._DEFAULT_PAL);window._sync();root.update()
        window._spawn_board_win();focus=window._board_win;root.update()
        core.game_action=lambda rid,action:sent.append((rid,action)) or True
        def restore():
            core.uid=7;core.connected=True;core.game_room=room;core.game_state=base
            focus.redraw(force=True);root.update();sent.clear()
            return next(r for r in focus._cv_ui["ludo_hits"] if r[-1]=={"op":"roll"})
        def click(rect):
            focus.game_cv.event_generate("<Button-1>",x=int((rect[0]+rect[2])/2),y=int((rect[1]+rect[3])/2))
        rect=restore();click(rect);assert sent==[("old-airport",{"op":"roll"})]
        cases=("new_room","new_frame","new_round","new_account","removed_member","same_fields_new_room_object","different_game","disconnected")
        for case in cases:
            rect=restore()
            if case=="new_room": core.game_room=dict(room,room_id="new-airport")
            elif case=="new_frame": core.game_state=dict(base)
            elif case=="new_round": core.game_room=dict(room,round=2)
            elif case=="new_account": core.uid=8;core.game_state=dict(base,turn_uid=8)
            elif case=="removed_member": core.game_room=dict(room,players=[8],spectators=[7])
            elif case=="same_fields_new_room_object": core.game_room=dict(room)
            elif case=="different_game": core.game_room=dict(room,game="yahtzee")
            elif case=="disconnected": core.connected=False
            # No Tk update/redraw between replacing Core and the old hit event.
            click(rect)
            assert not sent, (case,sent)
    finally:
        if window: window.close()
        root.destroy()
