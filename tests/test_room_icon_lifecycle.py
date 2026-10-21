"""Real Tk / production image factory and lobby refresh; synthetic room data."""
import gc
import time
import tkinter as tk
from types import SimpleNamespace
import weakref

import pytest

from client import GameWindow, _RoomCard, _DEFAULT_PAL


def settle(root):
    # Let the production 1ms child binding run, then collect on Tk's thread.
    until=time.monotonic()+.02
    while time.monotonic()<until:
        root.update()
        time.sleep(.002)
    gc.collect()
    root.update()


def image_names(root):
    return set(root.tk.call('image','names'))


def assert_live(root, card):
    name=str(card._room_icon.cget('image'))
    assert name in image_names(root), f'Label retains {name}, but Tcl image was deleted'
    assert int(root.tk.call('image','width',name))==15
    assert int(root.tk.call('image','height',name))==15
    assert card._room_icon.winfo_ismapped()
    assert any(not int(root.tk.call(name,'transparency','get',x,y))
               for x in range(15) for y in range(15)), 'actual icon pixels are empty'
    return name


def room(room_id=1, game='tictactoe', status='created'):
    return dict(room_id=room_id,game=game,status=status,owner_uid=7,players=[7,8],options={})


def core():
    return SimpleNamespace(uid=7,roster={7:{'nick':'合成房主'}},game_rooms=[],
        game_meta={'tictactoe':{'label':'井字棋','min':2,'max':2}})


def card(parent, data=None, on_click=None):
    data=data or room()
    result=_RoomCard(parent,data['room_id'],data,core(),on_click,None,None)
    result.pack(fill='x')
    return result


@pytest.fixture
def root():
    result=tk.Tk()
    result.geometry('700x500')
    result.update()
    yield result
    result.destroy()
    gc.collect()


@pytest.mark.parametrize('game',['tictactoe','unknown-game'],ids=['known','fallback'])
def test_room_icon_survives_collection_and_native_click(root, game):
    selected=[]
    item=card(root,room(game=game),selected.append)
    settle(root)
    name=assert_live(root,item)
    for _ in range(3):
        gc.collect()
        assert assert_live(root,item)==name
    item.set_selected(True)
    item.set_selected(False)
    item._room_icon.event_generate('<Button-1>',x=5,y=5)
    root.update()
    assert selected==[1]
    assert_live(root,item)


def test_duplicate_room_cards_have_independent_image_lifetimes(root):
    before=image_names(root)
    first=card(root)
    second=card(root)
    settle(root)
    first_name=assert_live(root,first)
    second_name=assert_live(root,second)
    assert first_name!=second_name
    first_ref=weakref.ref(first)
    first.destroy()
    del first
    settle(root)
    assert first_ref() is None
    assert first_name not in image_names(root)
    assert assert_live(root,second)==second_name
    second.destroy()
    del second
    settle(root)
    assert image_names(root)==before


def test_production_room_refresh_and_container_rebuild_do_not_leak(root):
    before=image_names(root)
    # Component host uses the real production filter/refresh/highlight methods;
    # no fake image, patched factory or network/application side effects.
    lobby=GameWindow.__new__(GameWindow)
    lobby.core=core()
    lobby._pal=_DEFAULT_PAL
    lobby._sel_room=1
    lobby.filter_var=tk.StringVar(root,value='全部')
    lobby.sort_var=tk.StringVar(root,value='默认')
    lobby.room_cards={}
    lobby.room_inner=tk.Frame(root)
    lobby.room_inner.pack(fill='both',expand=True)
    old_refs=[]
    old_names=set()
    for index in range(12):
        lobby.core.game_rooms=[room(1,status=('created' if index%2 else 'playing')),
                              room(2,game='unknown-game')]
        lobby._refresh_rooms()
        settle(root)
        assert all(ref() is None for ref in old_refs)
        assert not old_names & image_names(root)
        names={assert_live(root,item) for item in lobby.room_cards.values()}
        assert len(names)==2
        assert image_names(root)==before|names
        assert lobby.room_cards[1]._selected
        old_refs=[weakref.ref(item) for item in lobby.room_cards.values()]
        old_names=names
        if index==5:
            lobby.room_inner.destroy()
            lobby.room_cards={}
            settle(root)
            assert all(ref() is None for ref in old_refs)
            assert image_names(root)==before
            lobby.room_inner=tk.Frame(root)
            lobby.room_inner.pack(fill='both',expand=True)
    lobby.core.game_rooms=[]
    lobby._refresh_rooms()
    settle(root)
    assert all(ref() is None for ref in old_refs)
    assert not lobby.room_cards
    assert image_names(root)==before


def test_room_icon_uses_its_own_interpreter_after_root_rebuild():
    root=tk.Tk()
    root.geometry('700x500')
    first=card(root)
    settle(root)
    try:
        assert_live(root,first)
    finally:
        root.destroy()
    first_ref=weakref.ref(first)
    del first
    gc.collect()
    assert first_ref() is None
    rebuilt=tk.Tk()
    rebuilt.geometry('700x500')
    try:
        before=image_names(rebuilt)
        replacement=card(rebuilt)
        settle(rebuilt)
        assert_live(rebuilt,replacement)
        replacement.destroy()
        del replacement
        settle(rebuilt)
        assert image_names(rebuilt)==before
    finally:
        rebuilt.destroy()
