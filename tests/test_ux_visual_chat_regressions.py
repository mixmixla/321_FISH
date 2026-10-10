"""Visual entry contracts over actual widgets, not a protocol acceptance suite."""
import json
import tkinter as tk
import time

import pytest
from config import CFG
from client import ChatWindow
from client_core import ClientCore


@pytest.fixture
def isolated_features(monkeypatch):
    for name in ('hardware_enabled','discovery_enabled','global_hotkeys_enabled','tray_enabled'):
        monkeypatch.setattr(CFG,name,False)


@pytest.fixture(autouse=True)
def features(isolated_features):
    pass


@pytest.fixture
def app(tmp_path):
    assert not CFG.hardware_enabled and not CFG.discovery_enabled
    core=ClientCore(nick='视觉合成',history_dir=str(tmp_path/'history'))
    window=ChatWindow(core,prefs_path=str(tmp_path/'prefs.json'))
    window.root.geometry('680x480')
    window.show_main()
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        window.root.update()
        if window.entry.winfo_width()>1 and window.entry.winfo_y()>0:
            break
        time.sleep(.01)
    yield window
    window.quit_app()


def test_fresh_entry_is_mist_and_opaque(app):
    assert app._skin_name=='mist'
    assert app._chat_alpha==1.0


def test_navigation_has_visible_names(app):
    labels={w.cget('text') for w in app.icon_bar.winfo_children() if isinstance(w,tk.Button)}
    assert {'消息','桌游','设置'} <= labels


def test_initial_session_list_uses_the_selected_skin(app):
    assert app.roster_list._pal['bg']==app._skin['list_bg']
    assert app.group_list._pal['fg']==app._skin['fg']


def test_compose_region_keeps_input_space_and_clear_target(app):
    assert int(app.entry.cget('height'))>=3
    assert app._toolbar_bar.winfo_y()<app.entry.winfo_y()
    assert app._send_btn.master is not app._toolbar_bar
    assert app._compose_target.cget('text')=='发送到：公共频道'
    assert app.entry.winfo_width()>250
    assert app._send_btn.winfo_width()>=64
    assert app.msg_list.winfo_height()>=120


def test_navigation_selection_follows_action_and_chat_return(app):
    app._navigate('game',lambda:None)
    assert app._navigation_buttons['game']._nav_selected
    assert not app._navigation_buttons['chat']._nav_selected
    app._switch_view('public',None)
    assert app._navigation_buttons['chat']._nav_selected
    assert not app._navigation_buttons['game']._nav_selected


def test_skin_switch_updates_fonts_and_surfaces(app):
    from ui_design import body_font
    app._on_skin_change('apple')
    assert app._f[0]!=body_font()[0]
    assert app._session_frame.cget('bg')==app._skin['list_bg']
    app._on_skin_change('mist_dark')
    assert app._f[0]==body_font()[0]
    assert app.msg_list._font.cget('family')==body_font()[0]
    assert app._compose_target.cget('bg')==app._skin['panel_bg']


@pytest.mark.parametrize('panel',['contacts','moments','settings','game'])
def test_closing_auxiliary_panel_restores_chat_selection(app,panel):
    if panel=='contacts':
        app._open_contacts_panel()
        app._contacts_win.destroy()
    elif panel=='moments':
        app._open_moments()
        app._moments_win.destroy()
    elif panel=='settings':
        app._on_settings()
        app._close_settings()
    else:
        app.open_game()
        app._game_win.hide()
    assert app._navigation_buttons['chat']._nav_selected
    assert all(not button._nav_selected for name,button in app._navigation_buttons.items() if name!='chat')


def test_short_history_is_not_clipped_after_window_grows(app):
    samples=[(2,'小周','上午的任务都处理好了，分享一下今天的计划。'),
             (1,'我','收到。我把重点整理进工作表，下午一起看。'),
             (3,'陈同学','会议是 15:00，我先准备好资料。'),
             (2,'小周','这是一条比较长的消息，用来检查中文换行、消息留白和窗口缩小时的阅读体验。')]
    rows=[{'seq':i,'uid':uid,'nick':nick,'channel':'public','text':text,'ts':1791518400+i*60} for i,(uid,nick,text) in enumerate(samples,1)]
    app.msg_list.load(rows,me_uid=1)
    app.root.update()
    app.root.geometry('1000x700')
    for _ in range(5):
        app.root.update()
        time.sleep(.02)
    assert app.msg_list._cum[-1]<app.msg_list.winfo_height()
    assert app.msg_list._first_visible==0
    assert app.msg_list.canvasy(0)<=1


def test_explicit_existing_skin_and_opacity_remain_selected(tmp_path):
    path=tmp_path/'prefs.json'
    path.write_bytes(json.dumps({'skin':'apple','chat_alpha':0.91}).encode())
    core=ClientCore(nick='视觉合成',history_dir=str(tmp_path/'history'))
    window=ChatWindow(core,prefs_path=str(path))
    try:
        assert window._skin_name=='apple'
        assert window._chat_alpha==0.91
        assert json.loads(path.read_bytes())['skin']=='apple'
    finally:
        window.quit_app()
