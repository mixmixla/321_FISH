"""Real UNO card IDs, private state, and clicks on the gate's private desktop."""
import copy
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

from boardgames import cards_uno as table
from games_pkg.uno import UnoGame, _build_deck, _card_str


def scene():
    g = UnoGame([7, 8], seed=5)
    cards = _build_deck(random.Random(4))
    pick = lambda color, value: next(c for c in cards if c['color'] == color and c['value'] == value)
    duplicate = [c for c in cards if c['color'] == 'red' and c['value'] == 7]
    g.hands[7] = duplicate + [pick(None, 'wild'), pick(None, 'wild4'), pick('blue', 4)]
    own = {c['id'] for c in g.hands[7]}
    g.hands[8] = [c for c in cards if c['id'] not in own and c['color'] == 'blue'][:7]
    g.discard = [pick('red', 2)]
    used = {c['id'] for h in g.hands.values() for c in h} | {c['id'] for c in g.discard}
    g.deck = [c for c in cards if c['id'] not in used]
    g.current_idx = 0
    g.current_color = 'red'
    return g


class Canvas:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(*args, **kw): self.calls.append((name, args, kw))
        return call


def paint(g, ui=None, uid=7, priv=None, width=472, height=340):
    ui = ui if ui is not None else {}
    sent = ui.setdefault('sent', [])
    ui.update(room={'players': [7, 8], 'spectators': [99], 'status': 'playing'})
    cv = Canvas()
    table.paint(cv, g.snapshot(), uid, str, sent.append, lambda: paint(g, ui, uid, priv, width, height),
                ui, g.private(uid) if priv is None else priv, width, height)
    return ui, cv


def click_action(ui, predicate):
    rect, action = next((r, a) for r, a in ui['uno_hits'] if predicate(a))
    table.click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    return action


def test_duplicate_faces_send_distinct_real_ids_and_server_accepts():
    g = scene()
    for index in (0, 1):
        g = scene()
        cid = g.hands[7][index]['id']
        ui, _ = paint(g)
        click_action(ui, lambda a: a == {'card': cid})
        assert ui['sent'] == [{'card': cid}]
        g.act(7, ui['sent'][0])
        assert g.discard[-1]['id'] == cid
        assert sum(_card_str(c) == '红7' for c in g.hands[7]) == 1


@pytest.mark.parametrize('color', list(table.COLORS))
def test_wild_color_is_required_and_captured_id_survives_duplicates(color):
    g = scene()
    cid = g.hands[7][2]['id']
    ui, _ = paint(g)
    click_action(ui, lambda a: a == ('wild', cid))
    assert not ui['sent']
    assert len(ui['uno_hits']) == 5
    click_action(ui, lambda a: isinstance(a, dict) and a.get('color') == color)
    assert ui['sent'] == [{'card': cid, 'color': color}]
    assert not ui['uno_hits']
    g.act(7, ui['sent'][0])
    assert g.current_color == color


def test_turn_spectator_end_and_incomplete_ids_never_emit_or_reveal_private():
    g = scene()
    private = g.private(7)
    for uid, corrupt in ((99, private), (7, {'hand': ['红7'], 'hand_ids': []}),
                         (7, {'hand': ['红7', '红7'], 'hand_ids': [13, 13]})):
        ui, cv = paint(g, uid=uid, priv=corrupt)
        assert not ui['cards']
        if uid == 99:
            assert not ui['uno_hits']
            assert not any(kw.get('text') == '红7' for _, _, kw in cv.calls)
    g.current_idx = 1
    ui, _ = paint(g)
    assert len(ui['uno_hand']) == 5 and not ui['uno_hits']
    g.phase = 'round_end'
    ui, _ = paint(g)
    assert not ui['uno_hits']


def test_paging_all_108_ids_fits_small_window_and_stale_picker_clears():
    g = scene()
    g.hands[7] = _build_deck(random.Random(4))
    ui, _ = paint(g, width=472, height=304)
    seen = set()
    for _ in range(30):
        for rect, action in ui['uno_hits']:
            assert 0 <= rect[0] < rect[2] <= 472 and 0 <= rect[1] < rect[3] <= 304
        seen.update(cid for cid, _, _ in ui['uno_hand'][ui['uno_page']*ui['uno_per_page']:(ui['uno_page']+1)*ui['uno_per_page']])
        if not any(a == ('page', ui['uno_page']+1) for _, a in ui['uno_hits']): break
        click_action(ui, lambda a: a == ('page', ui['uno_page']+1))
    assert seen == set(range(108))
    g = scene(); ui, _ = paint(g)
    click_action(ui, lambda a: isinstance(a, tuple) and a[0] == 'wild')
    g.current_idx = 1
    ui, _ = paint(g, ui)
    assert 'uno_wild' not in ui and not ui['uno_hits']


def test_private_legal_ids_match_authoritative_rule_including_plus_four_restriction():
    import games_pkg.uno as rules
    g = scene()
    plus4 = next(c['id'] for c in g.hands[7] if c['value'] == 'wild4')
    for c in g.hands[7]:
        candidate = copy.deepcopy(g)
        try:
            candidate.act(7, {'card': c['id'], 'color': 'blue'})
            legal = True
        except rules.GameRuleError:
            legal = False
        assert (c['id'] in g.private(7)['playable_ids']) == legal
    if rules.UNO_ENFORCE_WILD4:
        assert plus4 not in g.private(7)['playable_ids']


def test_draw_count_is_real_public_event_does_not_disclose_draw_and_empty_pile_is_safe():
    g = scene()
    count = len(g.deck)
    drawn = _card_str(g.deck[-1])
    messages = g.act(7, {'draw': True})
    assert all(drawn not in value for value in messages)
    assert g.snapshot()['deck_remaining'] == count-1
    assert len(g.hands[7]) == 6 and len(g.private(7)['hand']) == 6
    g.current_idx = 0; g.deck = []
    assert g.act(7, {'draw': True}) == ['玩家7 无牌可摸，过']
    assert g.current_idx == 1


def test_pending_packet_stays_locked_after_same_snapshot_local_repaint():
    g=scene();st=g.snapshot();priv=g.private(7);ui={};sent=[]
    def redraw():table.paint(Canvas(),st,7,str,sent.append,redraw,ui,priv,472,340)
    redraw();click_action(ui,lambda a:a=={'draw':True});assert sent==[{'draw':True}]
    redraw();assert not ui['uno_hits']


def capture_own_window(widget, path):
    """PrintWindow captures only this synthetic HWND; never reads the screen."""
    from PIL import Image
    user, gdi = ctypes.WinDLL('user32'), ctypes.WinDLL('gdi32')
    user.GetParent.restype = wintypes.HWND
    hwnd = user.GetParent(widget.winfo_id()) or widget.winfo_id()
    user.GetWindowDC.restype = wintypes.HDC
    user.GetWindowDC.argtypes = [wintypes.HWND]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.GetBitmapBits.argtypes = [wintypes.HBITMAP, ctypes.c_long, ctypes.c_void_p]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    rect = wintypes.RECT(); assert user.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right-rect.left, rect.bottom-rect.top
    dc = user.GetWindowDC(hwnd); memory = gdi.CreateCompatibleDC(dc)
    bmp = gdi.CreateCompatibleBitmap(dc, w, h); old = gdi.SelectObject(memory, bmp)
    try:
        assert user.PrintWindow(hwnd, memory, 2)
        pixels = ctypes.create_string_buffer(w*h*4)
        assert gdi.GetBitmapBits(bmp, len(pixels), pixels) == len(pixels)
        image = Image.frombuffer('RGB', (w, h), pixels, 'raw', 'BGRX', 0, 1)
        assert len(image.getcolors(w*h) or []) > 50, 'Empty private-desktop capture'
        image.save(path)
    finally:
        gdi.SelectObject(memory, old); gdi.DeleteObject(bmp); gdi.DeleteDC(memory); user.ReleaseDC(hwnd, dc)


def test_live_gamewindow_wild_draw_and_small_board(tmp_path):
    assert os.environ.get('MOYU_GATE_DESKTOP_NAME'), 'Run GUI through the private-desktop gate'
    import tkinter as tk
    import client
    from games_pkg.rooms import RoomManager
    from test_flagship_gui import _fake_game_core
    root = tk.Tk(); root.withdraw()
    core = _fake_game_core(); core.game_meta = {}; core.game_room = core.game_state = None
    gw = client.GameWindow(SimpleNamespace(root=root, core=core, _frameless=False,
                           _camo_title=lambda: '合成 UNO 牌宴'), pal=client._DEFAULT_PAL)
    manager = RoomManager({'uno': UnoGame}); room = manager.create(7, 'uno')
    manager.join(8, room.room_id); manager.start(7, room.room_id); room.gs = scene()
    actions = []
    def sync():
        core.game_room = copy.deepcopy(room.summary()); core.game_state = room.gs.snapshot()
        core.game_private = room.gs.private(core.uid); gw._sync(); root.update()
    def send(rid, action):
        actions.append(action); manager.handle_action(core.uid, rid, action); sync()
    core.game_action = send
    def event(cv, ui, predicate):
        rect, _ = next((r,a) for r,a in ui['uno_hits'] if predicate(a))
        cv.event_generate('<Button-1>', x=int((rect[0]+rect[2])/2), y=int((rect[1]+rect[3])/2)); root.update()
    try:
        gw.win.geometry('1000x760'); sync()
        assert client._actions_for('uno',None)==[]
        assert not gw.act_btns.winfo_children() and not gw.state_text.winfo_manager()
        assert gw.game_cv.find_withtag('card-illustration')
        capture_own_window(gw.win, tmp_path/'uno-desktop.png')
        event(gw.game_cv, gw._cv_ui, lambda a: isinstance(a, tuple) and a[0] == 'wild')
        assert not actions
        capture_own_window(gw.win, tmp_path/'uno-desktop-picker.png')
        event(gw.game_cv, gw._cv_ui, lambda a: isinstance(a, dict) and a.get('color') == 'green')
        assert len(actions) == 1 and actions[0]['color'] == 'green' and room.gs.current_color == 'green'
        assert not gw._cv_ui['uno_hits']
        room.gs.current_idx = 0; sync()
        before = len(room.gs.hands[7])
        event(gw.game_cv, gw._cv_ui, lambda a: a == {'draw': True})
        assert len(room.gs.hands[7]) == before+1 and actions[-1] == {'draw': True}
        gw._spawn_board_win(); root.update()
        board = gw._board_win; board.win.minsize(480,400); board.win.geometry('480x400'); root.update(); board.redraw()
        assert board.game_cv.find_withtag('card-illustration')
        for rect, _ in board._cv_ui['uno_hits']:
            assert 0 <= rect[0] < rect[2] <= board.game_cv.winfo_width()
            assert 0 <= rect[1] < rect[3] <= board.game_cv.winfo_height()
        capture_own_window(board.win, tmp_path/'uno-desktop-small.png')
        # Play the last real card using Canvas-local keyboard bindings.
        room.gs.hands[7] = [next(c for c in room.gs.hands[7] if c['color'] == 'red')]
        room.gs.current_idx = 0; room.gs.current_color = 'red'; sync(); board.redraw(); root.update()
        board.game_cv.focus_force(); root.update()
        board.game_cv.event_generate('<Right>'); root.update()
        board.game_cv.event_generate('<Return>'); root.update()
        assert room.gs.winner_uid == 7 and room.gs.phase == 'round_end'
        assert not board._cv_ui['uno_hits']
        capture_own_window(board.win, tmp_path/'uno-desktop-finished.png')
        print('UNO_SCREENSHOTS', tmp_path)
    finally:
        gw.close(); root.destroy()
