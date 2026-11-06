"""Blackjack real cards, hidden dealer, shoe and stop chip."""
import copy
import json
import os
from types import SimpleNamespace

from boardgames import cards_blackjack as table
from games_pkg.blackjack import BlackjackGame
from test_anime_uno import Canvas, capture_own_window


def scene(players=(7,8)):
    g=BlackjackGame(list(players), seed=5); g.phase='playing'; g.round=1
    g.hands={players[0]: [('♠','10'),('♥','5')],players[1]: [('♥','10'),('♠','10')]}
    g.dealer=[('♣','9'),('♦','7')];g.deck=[('♣','9'),('♠','2'),('♥','3')]
    return g


def test_hole_card_and_its_contribution_are_hidden_until_real_settlement():
    g=scene();s=g.snapshot()
    assert s['dealer']==['背牌','7♦'] and s['dealer_value']==7 and s['dealer_hidden']
    assert s['deck_remaining']==3
    assert '9♣' not in json.dumps(s,ensure_ascii=False)
    g.act(7,{'action':'hit'});g.act(7,{'action':'stand'});g.act(8,{'action':'stand'})
    s=g.snapshot()
    assert s['status']=='round_end' and s['dealer']==['9♣','7♦','2♠']
    assert s['dealer_value']==18 and not s['dealer_hidden']
    assert s['results']=={'7':'push','8':'win'} and s['scores'][8]==1


def test_compact_all_players_cards_suits_and_nonmember_actions():
    g=scene();ui={};sent=[]
    def paint(uid=7):
        cv=Canvas();table.paint(cv,g.snapshot(),uid,str,sent.append,lambda:paint(uid),ui,None,472,304);return cv
    cv=paint()
    for rect,_ in ui['bj_hits']:
        assert 0<=rect[0]<rect[2]<=472 and 0<=rect[1]<rect[3]<=304
    labels=[kw.get('text') for _,_,kw in cv.calls]
    assert '10' in labels and '♠' in labels and '♥' in labels and '暗牌' in labels
    for uid in (8,99):
        paint(uid)
        assert all(isinstance(a,tuple) for _,a in ui['bj_hits'])
        for r,_ in list(ui['bj_hits']): table.click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2)
    assert not sent


def test_pending_packet_stays_locked_after_same_snapshot_local_repaint():
    g=scene();st=g.snapshot();ui={};sent=[]
    def redraw():table.paint(Canvas(),st,7,str,sent.append,redraw,ui,None,472,340)
    redraw();r=next(r for r,a in ui['bj_hits'] if a=={'action':'hit'})
    table.click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2);assert sent==[{'action':'hit'}]
    redraw();assert all(isinstance(a,tuple) for _,a in ui['bj_hits'])


def test_live_private_gamewindow_actual_hit_stop_and_reveal(tmp_path):
    assert os.environ.get('MOYU_GATE_DESKTOP_NAME')
    import tkinter as tk
    import client
    from games_pkg.rooms import RoomManager
    from test_flagship_gui import _fake_game_core
    root=tk.Tk();root.withdraw();core=_fake_game_core();core.game_meta={};core.game_room=core.game_state=None
    gw=client.GameWindow(SimpleNamespace(root=root,core=core,_frameless=False,_camo_title=lambda:'合成翡翠牌厅'),pal=client._DEFAULT_PAL)
    manager=RoomManager({'blackjack':BlackjackGame});room=manager.create(7,'blackjack');manager.join(8,room.room_id);manager.start(7,room.room_id);room.gs=scene()
    actions=[]
    def sync():
        core.game_room=copy.deepcopy(room.summary());core.game_state=room.gs.snapshot();core.game_private=None;gw._sync();root.update()
    def send(rid,action):
        actions.append({'uid':core.uid,'action':action});manager.handle_action(core.uid,rid,action);sync()
    core.game_action=send
    def click(cv,ui,op):
        r=next(r for r,a in ui['bj_hits'] if a=={'action':op});cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    try:
        gw.win.geometry('1000x760');sync();assert not gw.act_btns.winfo_children() and not gw.state_text.winfo_manager()
        assert client._actions_for('blackjack',None)==[]
        capture_own_window(gw.win,tmp_path/'blackjack-desktop-start.png')
        click(gw.game_cv,gw._cv_ui,'hit');assert room.gs._hand_value(room.gs.hands[7])==18
        capture_own_window(gw.win,tmp_path/'blackjack-desktop-hit.png')
        gw._spawn_board_win();root.update();board=gw._board_win;board.win.minsize(480,400);board.win.geometry('480x400');root.update();board.redraw()
        capture_own_window(board.win,tmp_path/'blackjack-desktop-small.png')
        board.game_cv.focus_force();root.update();board.game_cv.event_generate('<s>');root.update()
        assert room.gs.players[room.gs.current_idx]==8
        assert all(isinstance(a,tuple) for _,a in board._cv_ui['bj_hits'])
        core.uid=8;sync();board.redraw();click(board.game_cv,board._cv_ui,'stand')
        assert room.gs.phase=='round_end' and not core.game_state['dealer_hidden']
        capture_own_window(board.win,tmp_path/'blackjack-desktop-finished.png')
        (tmp_path/'blackjack-desktop-actions.json').write_text(json.dumps(actions,indent=2),encoding='utf-8')
    finally: gw.close();root.destroy()
