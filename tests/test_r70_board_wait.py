"""Real encrypted peers with controlled server scheduling; no fabricated boards."""
import json
import threading
import time
import traceback
from functools import wraps

import pytest
import test_r70 as original


def scores(event):
    return {row['nick']: row['score'] for row in event.get('entries', [])}


@pytest.mark.parametrize('order', ['bob_before_alice4', 'alice4_before_bob'])
def test_original_score_snapshot_contract_under_controlled_sender_order(tmp_path, monkeypatch, order):
    trace, errors, hubs, collector_nicks = [], [], [], {}
    cores, supervisors, service_stops = [], [], []
    scheduling_deadline = None
    trace_lock = threading.Lock()
    four_received, allow_four, four_applied, alice_final = (threading.Event() for _ in range(4))
    selected_boards = []

    def record(kind, **fields):
        with trace_lock:
            trace.append({'index': len(trace), 'monotonic_ns': time.monotonic_ns(),
                          'kind': kind, **fields})

    def require(event, label):
        assert scheduling_deadline is not None, 'scheduling deadline not started'
        if not event.wait(max(0.0, scheduling_deadline-time.monotonic())):
            errors.append(label)
            record('fixture_timeout', gate=label)
            raise TimeoutError('controlled scheduling gate: '+label)

    def observe_errors(callback):
        @wraps(callback)
        def observed(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except BaseException:
                error = {'hook': callback.__name__, 'traceback': traceback.format_exc()}
                errors.append(error)
                record('fixture_hook_error', **error)
                raise
        return observed

    def state(hub):
        board = hub._fish_board_payload('gomoku')
        snapshot = hub._snapshot_state()['fish_board'].get('gomoku', {})
        return {'entries': [dict(row) for row in board['entries']],
                'snapshot_scores': dict(snapshot)}

    hub_init, on_score = original.Hub.__init__, original.Hub._on_fish_score
    serve = original.serve_tcp
    send_score = original.ClientCore.send_fish_score
    collector_init, collect, wait = original.Collector.__init__, original.Collector._on, original.Collector.wait

    def init_hub(hub, *args, **kwargs):
        hub_init(hub, *args, **kwargs)
        hubs.append(hub)

    @observe_errors
    def serve_observed(hub, port, stop, start_web):
        supervisors.append(threading.current_thread())
        service_stops.append(stop)
        return serve(hub, port, stop, start_web)

    def send(core, game, score=1):
        nonlocal scheduling_deadline
        if core.nick == 'alice' and game == 'gomoku' and score == 4:
            # One shared budget, started after login/first-board synchronization.
            # This does not extend the original Collector.wait's 3s timeout.
            scheduling_deadline = time.monotonic()+2.0
        if core.nick == 'bob' and game == 'gomoku' and score == 999:
            require(four_received if order == 'bob_before_alice4' else four_applied,
                    'bob_send_after_alice4_received_or_applied')
        record('client_send', nick=core.nick, game=game, score=score)
        result = send_score(core, game, score)
        record('client_send_return', nick=core.nick, game=game, score=score, ok=result)
        return result

    @observe_errors
    def handle(hub, session, header):
        game, score = header.get('game'), header.get('score')
        record('server_received', nick=session.nick, game=game, score=score)
        is_four = session.nick == 'alice' and game == 'gomoku' and score == 4
        if is_four:
            four_received.set()
            if order == 'bob_before_alice4':
                require(allow_four, 'alice4_after_real_intermediate_frame')
        result = on_score(hub, session, header)
        record('server_return', nick=session.nick, game=game, score=score, **state(hub))
        if is_four:
            four_applied.set()
        return result

    def init_collector(collector, core):
        collector_init(collector, core)
        collector_nicks[id(collector)] = core.nick
        cores.append(core)

    @observe_errors
    def on_event(collector, event):
        nick = collector_nicks[id(collector)]
        if event.get('t') != 'fish_board' or event.get('game') != 'gomoku':
            return collect(collector, event)
        rows = [dict(row) for row in event.get('entries', [])]
        record('client_received_board', nick=nick, entries=rows)
        intermediate = scores(event) == {'bob': 100, 'alice': 3}
        if nick == 'bob' and intermediate and order == 'bob_before_alice4':
            # Release only after this actual encrypted frame has arrived.
            # Delay enqueue, not content: Alice receives the real final frame
            # before the original wait is allowed to select the older one.
            allow_four.set()
            require(four_applied, 'alice4_really_applied')
            require(alice_final, 'alice_received_real_final_frame')
        result = collect(collector, event)
        record('client_enqueue_return', nick=nick, entries=rows)
        if nick == 'alice' and scores(event) == {'bob': 100, 'alice': 7}:
            alice_final.set()
        return result

    def observed_wait(collector, *args, **kwargs):
        event = wait(collector, *args, **kwargs)
        if event is not None and event.get('t') == 'fish_board':
            record('wait_returned_board', nick=collector_nicks[id(collector)],
                   entries=[dict(row) for row in event.get('entries', [])])
            if len(event.get('entries', [])) == 2:
                selected_boards.append(scores(event))
        return event

    monkeypatch.setattr(original, 'serve_tcp', serve_observed)
    monkeypatch.setattr(original.Hub, '__init__', init_hub)
    monkeypatch.setattr(original.Hub, '_on_fish_score', handle)
    monkeypatch.setattr(original.ClientCore, 'send_fish_score', send)
    monkeypatch.setattr(original.Collector, '__init__', init_collector)
    monkeypatch.setattr(original.Collector, '_on', on_event)
    monkeypatch.setattr(original.Collector, 'wait', observed_wait)
    target_passed = False
    target_error = target_traceback = None
    final_state = restored_state = None
    cleanup = []
    workers_closed = False

    def attempt(label, action):
        try:
            return action()
        except BaseException:
            error = {'phase': label, 'traceback': traceback.format_exc()}
            errors.append(error)
            record('fixture_diagnostic_or_cleanup_error', **error)
            return None

    def diagnose():
        nonlocal final_state, restored_state
        assert hubs, 'real target Hub was never constructed'
        final_state = state(hubs[0])
        clone = original.Hub(cfg=hubs[0].cfg, audit_dir=str(tmp_path/'diagnostic-restore'))
        clone._restore(hubs[0]._snapshot_state())
        restored_state = state(clone)
        record('diagnostic_final_and_restore', final=final_state, restored=restored_state)
        assert scores(final_state) == scores(restored_state) == {'bob': 100, 'alice': 7}
        assert final_state['snapshot_scores'] == restored_state['snapshot_scores']
        expected_snapshot = {str(row['uid']): row['score'] for row in final_state['entries']}
        assert final_state['snapshot_scores'] == expected_snapshot

    try:
        (tmp_path/'target').mkdir()
        # Execute all original score/cap/order/privacy/invalid-input/snapshot
        # assertions. No copied replacement scenario and no swallowed failure.
        original.test_fish_board_accumulate_cap_order_and_snapshot(tmp_path/'target')
        target_passed = True
    except BaseException as exc:
        target_error, target_traceback = exc, exc.__traceback__
        record('original_target_error', traceback=traceback.format_exc())
    finally:
        allow_four.set()
        try:
            attempt('final_state_and_restore', diagnose)
        finally:
            # A diagnostic/one-resource failure must not skip other owned cleanup
            # or replace the original target assertion in the RED report.
            try:
                for stop in service_stops:
                    attempt('service_stop', stop.set)
                for core in cores:
                    if not core._stop.is_set():
                        attempt('core_stop', core.stop)
                for hub in reversed(hubs):
                    cleanup.append(attempt('hub_shutdown', lambda hub=hub: hub.shutdown(normal=False, timeout=3)))
                for worker in supervisors:
                    attempt('supervisor_join', lambda worker=worker: worker.join(timeout=3))
                workers_closed = bool(supervisors) and all(not worker.is_alive() for worker in supervisors) and all(
                    worker is None or not worker.is_alive()
                    for core in cores for worker in (core._reader, core._heartbeat, core._reconnector))
            finally:
                attempt('write_timeline', lambda: (tmp_path/'timeline.json').write_text(json.dumps({
                    'order': order, 'target_passed': target_passed, 'trace': trace,
                    'selected_boards': selected_boards, 'final_state': final_state,
                    'restored_state': restored_state, 'fixture_errors': errors,
                    'hub_cleanup': cleanup, 'owned_workers_closed': workers_closed},
                    ensure_ascii=False, indent=2)+'\n', encoding='utf-8'))
    if target_error is not None:
        target_error.add_note('Controlled fixture diagnostics are in timeline.json; '
                              f'fixture_errors={len(errors)}, owned_workers_closed={workers_closed}, '
                              f'hub_cleanup={cleanup}')
        raise target_error.with_traceback(target_traceback)
    assert not errors, errors
    assert cleanup and all(cleanup), cleanup
    assert workers_closed, 'owned test workers remain alive'

    assert target_passed
    assert selected_boards == [{'bob': 100, 'alice': 7}]
    assert four_received.is_set() and four_applied.is_set()
    if order == 'bob_before_alice4':
        intermediate = next(row['index'] for row in trace if row['kind'] == 'client_received_board'
                            and row.get('nick') == 'bob' and scores(row) == {'bob': 100, 'alice': 3})
        final_received = next(row['index'] for row in trace if row['kind'] == 'client_received_board'
                              and row.get('nick') == 'alice' and scores(row) == {'bob': 100, 'alice': 7})
        selected = next(row['index'] for row in trace if row['kind'] == 'wait_returned_board'
                        and row.get('nick') == 'bob' and scores(row) == {'bob': 100, 'alice': 7})
        assert intermediate < final_received < selected
    else:
        applied = next(row['index'] for row in trace if row['kind'] == 'server_return'
                       and row.get('nick') == 'alice' and row.get('score') == 4)
        sent = next(row['index'] for row in trace if row['kind'] == 'client_send'
                    and row.get('nick') == 'bob' and row.get('score') == 999)
        assert applied < sent
        assert not any(row['kind'] == 'client_received_board' and scores(row) == {'bob': 100, 'alice': 3}
                       for row in trace)
