"""Real Tk widget checks; synthetic model/Core, not native mouse or EXE evidence."""
import threading
import tkinter as tk
from types import SimpleNamespace

import pytest

from client import ChatWindow
from client_core import ClientCore
from retirement_status import RetirementBook, Scope


@pytest.fixture
def app():
    root = tk.Tk()
    root.geometry('900x700')
    instance = ChatWindow.__new__(ChatWindow)
    instance.root, instance._closed = root, False
    instance._f = ('Microsoft YaHei', 10)
    instance._dp = {'win': '#f5f7f6', 'sub': '#58645f', 'fg': '#202b27'}
    instance._admin_reload = None
    instance._append_sys = lambda text: None
    instance._apply_apple_dialog = lambda *args: None
    book = RetirementBook()
    book.connect(Scope('127.0.0.1', 9527, 1), 1)
    calls = []
    instance.core = SimpleNamespace(uid=1, connected=True, is_admin=True, connection_epoch=1,
                                   retirement_scope=Scope('127.0.0.1', 9527, 1),
                                   known={2: {'nick': 'two'}, 7: {'nick': '样例#2'}},
                                   roster={7: {'nick': '样例#2'}},
                                   retirement_snapshot=book.snapshot,
                                   query_admin_retirement=lambda *a, **kw: calls.append(('query', a, kw)),
                                   retry_admin_retirement=lambda ident: calls.append(('retry', ident)),
                                   cancel_admin_retirement=book.cancel,
                                   send_admin_user_del=lambda *a, **kw: calls.append(('delete', a, kw)),
                                   send_admin_force_invis=lambda *a: calls.append(('invis', a)))
    root.update()
    yield instance, book, calls
    instance._closed = True
    for child in root.winfo_children():
        child.destroy()
    root.destroy()


def set_status(book, status):
    request = book.begin(7, nick='样例#2', purpose='query')
    receipt = {'status': status, 'operation_id': 'synthetic-operation-7',
               'target_uid': 7, 'target_nick': '样例#2', 'retryable': status == 'failed',
               'origin': 'restored_valid_json' if status == 'confirmed' else None}
    book.receive({'t': 'admin_user_info', 'uid': 7, 'nick': '样例#2',
                  'request_id': request.request_id, 'retirement': receipt}, 1)


@pytest.mark.parametrize('status', ['pending', 'failed', 'unknown', 'confirmed'])
def test_real_result_widgets_show_server_state_and_action_eligibility(app, status):
    window, book, _ = app
    set_status(book, status)
    window._retirement_results()
    window.root.update()
    ui = window._retirement_ui
    text = ui['detail'].get('1.0', 'end')
    assert '样例#2' in text and 'synthetic-operation-7' in text
    assert ChatWindow._RETIRE_STATES[status] in text
    assert str(ui['buttons']['query'].cget('state')) == 'normal'
    assert str(ui['buttons']['retry'].cget('state')) == ('normal' if status == 'failed' else 'disabled')
    assert str(ui['buttons']['cancel'].cget('state')) == 'disabled'
    if status == 'confirmed':
        assert '从已有保存状态恢复' in text and '内容摘要' not in text


def test_result_reopens_with_history_and_has_manual_query_without_roster(app):
    window, book, calls = app
    set_status(book, 'unknown')
    window.core.known.clear()
    window.core.roster.clear()
    window._retirement_results()
    first = window._retirement_ui['dlg']
    window._retirement_results()
    assert window._retirement_ui['dlg'] is first
    first.destroy()
    window._on_retirement_status({'t': 'retirement_status'})
    assert not first.winfo_exists()  # An automatic receipt must not open a popup.
    window._retirement_results()
    window.root.update()
    ui = window._retirement_ui
    assert ui['table'].get_children()
    ui['target'].insert(0, '样例#2')
    ui['query_button'].invoke()
    assert calls == [('query', ('样例#2',), {})]


def test_cancel_and_offline_controls_do_not_issue_retirement(app):
    window, book, calls = app
    request = book.begin(7, nick='样例#2', purpose='preflight')
    window._retirement_results()
    window._retirement_ui['buttons']['cancel'].invoke()
    assert book.snapshot()[0].phase == 'cancelled' and calls == []
    assert not book.receive({'t': 'admin_user_info', 'uid': 7, 'nick': '样例#2',
                             'request_id': request.request_id}, 1).outbound
    book.disconnect(1)
    window.core.connected = False
    window.core.retirement_scope = None
    window._refresh_retirement_results()
    ui = window._retirement_ui
    assert str(ui['query_button'].cget('state')) == 'disabled'
    assert all(str(button.cget('state')) == 'disabled' for button in ui['buttons'].values())


def test_minimum_result_window_keeps_actions_inside_its_bounds(app):
    window, book, _ = app
    set_status(book, 'failed')
    window._retirement_results()
    ui = window._retirement_ui
    ui['dlg'].geometry('640x480')
    window.root.update()
    dlg = ui['dlg']
    for widget in (*ui['buttons'].values(), ui['query_button'], ui['detail'], ui['footer']):
        assert widget.winfo_rootx() >= dlg.winfo_rootx()
        assert widget.winfo_rootx()+widget.winfo_width() <= dlg.winfo_rootx()+dlg.winfo_width()
        assert widget.winfo_rooty()+widget.winfo_height() <= dlg.winfo_rooty()+dlg.winfo_height()


def test_admin_rows_keep_uid_through_hash_nickname_refresh_and_all_actions(app):
    window, _book, calls = app
    box = tk.Listbox(window.root, exportselection=False)
    box.pack()
    window._reload_admin_rows(box)
    index = next(i for i, row in enumerate(box._admin_rows) if row[0] == 7)
    box.selection_set(index)
    window.core.known[3] = {'nick': 'aaa'}
    window._reload_admin_rows(box)
    assert window._admin_selected(box)[:2] == (7, '样例#2')
    window._admin_clear_uid = lambda uid: calls.append(('clear', uid))
    window._admin_kick = lambda uid: calls.append(('kick', uid))
    window._confirm_del_uid = lambda uid, nick: calls.append(('confirm', uid, nick))
    window._admin_panel_clear(box)
    window._admin_panel_invis(box)
    window._admin_panel_del(box)
    dialog = tk.Toplevel(window.root)
    window._admin_panel_kick(box, dialog)
    assert calls == [('clear', 7), ('invis', (7, True)), ('confirm', 7, '样例#2'), ('kick', 7)]


def test_both_retirement_entry_points_cancel_without_any_request(app, monkeypatch):
    from widgets import dialogbox
    window, _book, calls = app
    confirmations = []
    monkeypatch.setattr(dialogbox, 'ask_yesno', lambda title, text, **kw: confirmations.append(text) or False)
    box = tk.Listbox(window.root)
    window._reload_admin_rows(box)
    box.selection_set(next(i for i, row in enumerate(box._admin_rows) if row[0] == 7))
    window._admin_panel_del(box)
    window._confirm_del_uid(7, '样例#2')
    assert calls == [] and len(confirmations) == 2
    assert confirmations[0] == confirmations[1]
    assert '昵称仍保留' in confirmations[0] and '他人副本不会全部删除' in confirmations[0]


def test_confirmation_cannot_cross_a_reconnect_even_on_same_endpoint(app, monkeypatch):
    from widgets import dialogbox
    window, _book, calls = app

    def reconnect_during_confirmation(*args, **kwargs):
        window.core.connection_epoch = 2
        return True

    monkeypatch.setattr(dialogbox, 'ask_yesno', reconnect_during_confirmation)
    window._confirm_del_uid(7, '样例#2')
    assert calls == [] and not getattr(window, '_retirement_ui', None)


def test_old_epoch_ui_events_are_dropped_before_any_action(app):
    window, _book, calls = app
    window._on_error = lambda event: calls.append(('error', event))
    window._on_welcome = lambda event: calls.append(('welcome', event))
    window._on_state = lambda state: calls.append(('state', state))
    window.core.connection_epoch = 2
    for event in ({'t': 'error', 'code': 'deleted'}, {'t': 'welcome'}, {'t': 'state', 'state': 'online'}):
        window._handle({**event, '_connection_epoch': 1})
    assert calls == []
    window._handle({'t': 'error', 'code': 'deleted', '_connection_epoch': 2})
    assert calls[0][0] == 'error'


def test_core_thread_only_enqueues_result_and_tk_pump_renders_it(app, tmp_path):
    window, _book, _calls = app
    core = ClientCore(nick='synthetic-GUI', history_dir=str(tmp_path/'core'))
    window.core = core
    threads = []
    window._refresh_retirement_results = lambda: threads.append(threading.get_ident())
    worker = threading.Thread(target=core._push_retirement_state)
    worker.start()
    worker.join(2)
    assert not worker.is_alive() and threads == []
    window._handle(core.events.get_nowait())
    assert threads == [threading.get_ident()]
    core.stop()


def test_stopped_epoch_cannot_deliver_late_login_prompt_or_welcome(app, tmp_path):
    from client_core import _Connection
    window, _book, calls = app
    core = ClientCore(nick='synthetic-stopped-login', history_dir=str(tmp_path/'core'))
    connection = _Connection(1, core.host, core.port)
    core._connection, core._epoch = connection, 1
    window.core = core
    window._on_error = lambda event: calls.append(('error', event))
    window._on_welcome = lambda event: calls.append(('welcome', event))
    window._on_state = lambda state: calls.append(('state', state))
    core.drop()  # Connector has not started its next epoch yet.
    try:
        for event in ({'t': 'error', 'code': 'pwd'}, {'t': 'welcome'}, {'t': 'state', 'state': 'online'}):
            window._handle({**event, '_connection_epoch': 1})
        assert calls == []
        core._manual_login_required = True
        window._handle({'t': 'error', 'code': 'deleted', 'manual_login_required': True, '_connection_epoch': 1})
        assert calls[0][0] == 'error'
    finally:
        core.stop()
