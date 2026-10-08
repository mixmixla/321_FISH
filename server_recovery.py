"""Strict Store formats and explicit recovery; no application/network side effects.

The control file is an identity floor, not a receipt for a complete snapshot.
All callers retain their original files on errors.  Hub integration owns t0,
business cleanup and the shared writer, not the JSON or OS-lock primitives here.
"""
from __future__ import annotations

import copy
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid

from server_store import ReadResult, SaveResult, ServerStore, encode_state


class StoreError(RuntimeError):
    """A diagnostic code and schema path, never a private field value."""

    def __init__(self, code: str, field: str = 'store'):
        self.code, self.field = code, field
        super().__init__(f'{code}: {field}')


def _bad(path):
    raise StoreError('invalid_schema', path)


def _obj(value, path, *, allowed=None, required=()):
    if not isinstance(value, dict):
        _bad(path)
    if allowed is not None and set(value) - set(allowed):
        _bad(path + '.unknown_field')
    if set(required) - set(value):
        _bad(path + '.missing_field')
    return value


def _text(value, path, *, nonempty=False, limit=None):
    if (not isinstance(value, str) or (nonempty and not value.strip())
            or (limit is not None and len(value) > limit)
            or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)):
        _bad(path)
    return value


def _integer(value, path, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        _bad(path)
    return value


def _number(value, path):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        _bad(path)
    return value


def _flag(value, path, *, legacy_int=False):
    if type(value) is bool:
        return value
    if legacy_int and type(value) is int and value in (0, 1):
        return value
    _bad(path)


def _array(value, path):
    if not isinstance(value, list):
        _bad(path)
    return value


def _id(value, path, *, key=False, minimum=1):
    if key and isinstance(value, str):
        if not re.fullmatch(r'0|[1-9][0-9]*', value):
            _bad(path)
        value = int(value)
    return _integer(value, path, minimum)


def _id_map(value, path, *, minimum=1):
    value = _obj(value, path)
    out = {}
    for key, child in value.items():
        uid = _id(key, path + '.key', key=True, minimum=minimum)
        if str(uid) in out:
            _bad(path + '.collision')
        out[str(uid)] = child
    return out


def _ids(value, path, *, minimum=1):
    values = [_id(v, path + '.item', minimum=minimum)
              for v in _array(value, path)]
    if len(values) != len(set(values)):
        _bad(path + '.duplicate')
    return values


def _conversation(value, path, *, bus=False):
    _text(value, path, nonempty=True)
    if value == ('all' if bus else 'public'):
        return value
    if re.fullmatch(r'group:[1-9][0-9]*|private:[1-9][0-9]*:[1-9][0-9]*', value):
        if value.startswith('private:'):
            _, left, right = value.split(':')
            if int(left) > int(right):
                _bad(path)
        return value
    _bad(path)


def _channel_target(record, path):
    channel = record.get('channel')
    if channel not in ('public', 'private', 'group'):
        _bad(path + '.channel')
    if channel == 'public':
        if record.get('to') is not None:
            _bad(path + '.to')
    else:
        _id(record.get('to'), path + '.to')


def strict_json(payload: bytes, *, field='state') -> dict:
    """Reject duplicate keys, nonfinite constants and invalid UTF-8/Unicode."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError('nonfinite constant')

    try:
        if not isinstance(payload, bytes):
            raise TypeError('bytes required')
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=invalid_constant)
        if not isinstance(value, dict):
            raise ValueError('object required')
        # The encoder's walk checks escaped surrogates and overflowing floats.
        from server_store import _validate_json_value
        _validate_json_value(value, set())
        return value
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise StoreError('invalid_json', field) from None


def read_required(store: ServerStore, field: str) -> ReadResult:
    result = store.read_bytes_result()
    if result.status != 'bytes':
        code = 'incomplete_store' if result.status == 'missing' else 'read_error'
        raise StoreError(code, field)
    return result


def _store_id(value, path):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        _bad(path)
    return value


def _retirements(value, path):
    from bots import BOT_BY_UID
    out = _id_map(value, path)
    names, ops = set(), set()
    for key, rec in out.items():
        _obj(rec, path + '.record', allowed=('nick', 'retired_at', 'operation_id'),
             required=('nick', 'retired_at', 'operation_id'))
        nick = _text(rec['nick'], path + '.nick', nonempty=True)
        op = _text(rec['operation_id'], path + '.operation_id', nonempty=True)
        _number(rec['retired_at'], path + '.retired_at')
        if int(key) in BOT_BY_UID or nick in names or op in ops:
            _bad(path + '.identity_conflict')
        names.add(nick)
        ops.add(op)
    return out


def validate_control(value: dict) -> dict:
    value = copy.deepcopy(value)
    _obj(value, 'control', allowed=('format_version', 'store_id', 'phase',
                                   'bootstrap', 'intents'),
         required=('format_version', 'store_id', 'phase', 'bootstrap', 'intents'))
    if type(value['format_version']) is not int or value['format_version'] != 1:
        raise StoreError('unsupported_format', 'control.format_version')
    _store_id(value['store_id'], 'control.store_id')
    if value['phase'] not in ('bootstrap', 'ready'):
        _bad('control.phase')
    boot = _obj(value['bootstrap'], 'control.bootstrap',
                allowed=('kind', 'source_sha256', 'source_length'),
                required=('kind', 'source_sha256', 'source_length'))
    if boot['kind'] == 'new':
        if boot['source_sha256'] is not None or boot['source_length'] is not None:
            _bad('control.bootstrap.source')
    elif boot['kind'] == 'legacy':
        if (not isinstance(boot['source_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', boot['source_sha256'])):
            _bad('control.bootstrap.source_sha256')
        _integer(boot['source_length'], 'control.bootstrap.source_length', 0)
    else:
        _bad('control.bootstrap.kind')
    value['intents'] = _retirements(value['intents'], 'control.intents')
    return value


_COLLECTIONS = (
    'nick_to_uid', 'known', 'retired', 'groups', 'reads', 'blocks', 'drafts',
    'scheds', 'pins', 'burn', 'polls', 'group_files', 'tasks', 'fish_board',
    'moments', 'moment_covers', 'custom_stickers', 'sticker_pack_meta',
)
_COUNTERS = ('uid_seq', 'gid_seq', 'gf_seq', 'task_seq', 'pid_seq')


def validate_state(value: dict, *, store_id: str | None = None,
                   legacy: bool = False) -> dict:
    """Return an independent normalized state, without reading resource files.

    Only documented legacy defaults are supplied. Stored display references
    are not treated as authorization identities or recursively rewritten.
    """
    from bots import BOT_BY_UID
    from server_store import _validate_json_value
    try:
        _validate_json_value(value, set())
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise StoreError('invalid_schema', 'state.json_value') from None
    state = copy.deepcopy(_obj(value, 'state', allowed=(*_COLLECTIONS, *_COUNTERS,
                                                       'bus', '_store')))
    if '_store' in state:
        meta = _obj(state['_store'], 'state._store',
                    allowed=('format_version', 'store_id'),
                    required=('format_version', 'store_id'))
        if type(meta['format_version']) is not int or meta['format_version'] != 1:
            raise StoreError('unsupported_format', 'state._store.format_version')
        _store_id(meta['store_id'], 'state._store.store_id')
        if legacy:
            raise StoreError('already_versioned', 'state._store')
        if store_id is not None and meta['store_id'] != store_id:
            raise StoreError('store_mismatch', 'state._store')
    elif not legacy:
        raise StoreError('incomplete_store', 'state._store')
    for name in _COLLECTIONS:
        if name == 'retired' and state.get(name, {}) is None:
            state[name] = {}
        state.setdefault(name, {})
        _obj(state[name], 'state.' + name)
    for name in _COUNTERS:
        if name in state:
            _integer(state[name], 'state.' + name, 1 if name in ('uid_seq', 'gid_seq') else 0)

    mapping = state['nick_to_uid']
    mapped_uids = set()
    for nick, uid in mapping.items():
        _text(nick, 'state.nick_to_uid.key', nonempty=True)
        _id(uid, 'state.nick_to_uid.value')
        if uid in BOT_BY_UID:
            _bad('state.nick_to_uid.bot_uid')
        if uid in mapped_uids:
            _bad('state.nick_to_uid.uid_collision')
        mapped_uids.add(uid)
    known = state['known'] = _id_map(state['known'], 'state.known')
    for key, profile in known.items():
        path = 'state.known.record'
        _obj(profile, path, allowed=('nick', 'last_online', 'pwd', 'sign', 'avatar',
                                    'invisible', 'status', 'remarks', 'type'), required=('nick',))
        nick = _text(profile['nick'], path + '.nick', nonempty=True)
        if int(key) in BOT_BY_UID:
            if nick != BOT_BY_UID[int(key)].nick or profile.get('type') != 'bot':
                _bad(path + '.bot')
        elif mapping.get(nick) != int(key) or profile.get('type', '') not in ('', 'user'):
            _bad(path + '.identity')
        if 'last_online' in profile:
            _number(profile['last_online'], path + '.last_online')
        for field in ('pwd', 'sign', 'avatar'):
            if field in profile:
                _text(profile[field], path + '.' + field)
        if 'invisible' in profile:
            _flag(profile['invisible'], path + '.invisible', legacy_int=True)
        if profile.get('status', '') not in ('', 'online', 'away', 'busy'):
            _bad(path + '.status')
        if 'remarks' in profile:
            profile['remarks'] = _id_map(profile['remarks'], path + '.remarks')
            for remark in profile['remarks'].values():
                _text(remark, path + '.remarks.value', limit=24)
    state['retired'] = _retirements(state['retired'], 'state.retired')
    for key, rec in state['retired'].items():
        if (key in known or mapping.get(rec['nick']) != int(key)
                or any(nick != rec['nick'] and uid == int(key) for nick, uid in mapping.items())):
            _bad('state.retired.identity')

    groups = state['groups'] = _id_map(state['groups'], 'state.groups')
    for key, group in groups.items():
        path = 'state.groups.record'
        _obj(group, path, allowed=('gid', 'name', 'owner', 'admins', 'members',
                                 'mutes', 'announce', 'announce_mode', 'invite',
                                 'kind', 'public', 'slow'), required=('owner', 'members', 'name'))
        group.setdefault('gid', int(key))
        if _id(group['gid'], path + '.gid') != int(key):
            _bad(path + '.gid')
        owner = _id(group['owner'], path + '.owner')
        members = group['members'] = _id_map(group['members'], path + '.members')
        for nick in members.values():
            _text(nick, path + '.members.value')
        admins = group['admins'] = sorted(_ids(group.setdefault('admins', []), path + '.admins'))
        mutes = group['mutes'] = _id_map(group.setdefault('mutes', {}), path + '.mutes')
        if (str(owner) not in members or any(str(uid) not in members for uid in admins)
                or set(mutes) - set(members)):
            _bad(path + '.membership')
        for deadline in mutes.values():
            _number(deadline, path + '.mutes.value')
        _text(group['name'], path + '.name')
        for field in ('announce', 'invite', 'kind'):
            _text(group.setdefault(field, ''), path + '.' + field)
        for field in ('announce_mode', 'public'):
            _flag(group.setdefault(field, 0), path + '.' + field, legacy_int=True)
        _integer(group.setdefault('slow', 0), path + '.slow', 0)

    for conv, raw in state['reads'].items():
        _conversation(conv, 'state.reads.key')
        cursor = state['reads'][conv] = _id_map(raw, 'state.reads.record')
        for seq in cursor.values():
            _integer(seq, 'state.reads.record.value', 0)
    state['blocks'] = _id_map(state['blocks'], 'state.blocks')
    for uid, blocked in state['blocks'].items():
        state['blocks'][uid] = sorted(_ids(blocked, 'state.blocks.record'))
    for key, draft in state['drafts'].items():
        if not isinstance(key, str) or '|' not in key:
            _bad('state.drafts.key')
        uid, conv = key.split('|', 1)
        _id(uid, 'state.drafts.key.uid', key=True)
        _conversation(conv, 'state.drafts.key.conversation')
        _obj(draft, 'state.drafts.record', allowed=('text', 'ts'))
        _text(draft.setdefault('text', ''), 'state.drafts.record.text')
        _number(draft.setdefault('ts', 0), 'state.drafts.record.ts')
    state['scheds'] = _id_map(state['scheds'], 'state.scheds')
    for mine in state['scheds'].values():
        for rid, sched in _obj(mine, 'state.scheds.owner').items():
            _text(rid, 'state.scheds.record.key', nonempty=True)
            path = 'state.scheds.record'
            _obj(sched, path, allowed=('channel', 'to', 'text', 'fire_at', 'created'),
                 required=('text', 'fire_at'))
            sched.setdefault('channel', 'public')
            sched.setdefault('to', None)
            _channel_target(sched, path)
            _text(sched['text'], path + '.text', nonempty=True)
            _number(sched['fire_at'], path + '.fire_at')
            _number(sched.setdefault('created', 0), path + '.created')

    _validate_messages(state)
    _validate_collections(state)
    human_ids = [uid for uid in mapping.values() if uid not in BOT_BY_UID]
    human_ids += [int(uid) for uid in known if int(uid) not in BOT_BY_UID]
    minimums = {'uid_seq': max(human_ids, default=0) + 1,
                'gid_seq': max(map(int, groups), default=0) + 1,
                'gf_seq': max((int(r['fid']) for records in state['group_files'].values()
                               for r in records), default=0),
                'task_seq': max((r['tid'] for records in state['tasks'].values()
                                 for r in records), default=0),
                'pid_seq': max(map(int, state['moments']), default=0)}
    for name, minimum in minimums.items():
        if name == 'uid_seq':
            # An old, valid retirement could reserve a high, not-yet-issued
            # UID without advancing the allocator. Preserve every identity
            # and normalize only the next unused allocation floor.
            state[name] = max(state.get(name, minimum), minimum)
            continue
        if state.setdefault(name, minimum) < minimum:
            _bad('state.' + name + '.allocation_floor')
    return state


def _validate_messages(state):
    """Message bodies keep JSON extensions; authority-bearing fields are typed."""
    bus = state.setdefault('bus', {})
    _obj(bus, 'state.bus', allowed=('seq', 'channels'))
    _integer(bus.setdefault('seq', 0), 'state.bus.seq', 0)
    channels = _obj(bus.setdefault('channels', {}), 'state.bus.channels')
    max_seq = 0
    seen_sequences = set()
    for key, messages in channels.items():
        _conversation(key, 'state.bus.channels.key', bus=True)
        for message in _array(messages, 'state.bus.channels.messages'):
            _obj(message, 'state.bus.message', required=('seq', 'uid', 'channel'))
            seq = _integer(message.get('seq'), 'state.bus.message.seq', 1)
            if seq in seen_sequences:
                _bad('state.bus.message.duplicate_seq')
            seen_sequences.add(seq)
            max_seq = max(max_seq, seq)
            if 'uid' in message:
                _integer(message['uid'], 'state.bus.message.uid', 0)
            for field in ('nick', 'text'):
                if field in message:
                    _text(message[field], 'state.bus.message.' + field)
            if 'ts' in message:
                _number(message['ts'], 'state.bus.message.ts')
            if 'channel' in message:
                _channel_target(message, 'state.bus.message')
                channel, uid, to = message['channel'], message['uid'], message.get('to')
                expected = ('all' if channel == 'public' else f'group:{to}'
                            if channel == 'group' else 'private:' + ':'.join(
                                str(v) for v in sorted((uid, to))))
                if key != expected:
                    _bad('state.bus.message.channel_key')
    if bus['seq'] < max_seq:
        _bad('state.bus.seq.allocation_floor')
    for key, pin in state['pins'].items():
        _conversation(key, 'state.pins.key')
        _obj(pin, 'state.pins.record', allowed=('seq', 'nick', 'text', 'sticker', 'ts'),
             required=('seq',))
        _integer(pin.get('seq'), 'state.pins.record.seq', 1)
        if pin.get('nick') is not None:
            _text(pin['nick'], 'state.pins.record.nick')
        for field in ('text', 'sticker'):
            if field in pin:
                _text(pin[field], 'state.pins.record.' + field)
        if 'ts' in pin:
            _number(pin['ts'], 'state.pins.record.ts')
    state['burn'] = _id_map(state['burn'], 'state.burn')
    for rec in state['burn'].values():
        _obj(rec, 'state.burn.record', allowed=('channel', 'uid', 'to', 'ts', 'pend'),
             required=('channel', 'uid', 'ts'))
        _channel_target(rec, 'state.burn.record')
        _id(rec['uid'], 'state.burn.record.uid')
        _number(rec['ts'], 'state.burn.record.ts')
        rec['pend'] = sorted(_ids(rec.setdefault('pend', []), 'state.burn.record.pend'))
    state['polls'] = _id_map(state['polls'], 'state.polls')
    for poll in state['polls'].values():
        path = 'state.polls.record'
        _obj(poll, path, allowed=('channel', 'to', 'uid', 'question', 'options',
                                 'end', 'votes', 'anonymous', 'multi', 'quiz',
                                 'correct', 'revealed'),
             required=('channel', 'uid', 'question', 'options', 'end'))
        poll.setdefault('to', None)
        _channel_target(poll, path)
        _id(poll['uid'], path + '.uid')
        _text(poll['question'], path + '.question', nonempty=True)
        options = _array(poll['options'], path + '.options')
        if len(options) < 2:
            _bad(path + '.options')
        for option in options:
            _text(option, path + '.options.item', nonempty=True)
        _number(poll['end'], path + '.end')
        for field in ('anonymous', 'multi', 'quiz', 'revealed'):
            _flag(poll.setdefault(field, False), path + '.' + field)
        correct = poll.setdefault('correct', None)
        if poll['quiz']:
            if _integer(correct, path + '.correct', 0) >= len(options):
                _bad(path + '.correct')
        elif correct is not None:
            _bad(path + '.correct')
        votes = poll['votes'] = _id_map(poll.setdefault('votes', {}), path + '.votes')
        for uid, vote in votes.items():
            if type(vote) is int:
                vote = votes[uid] = [vote]
            indices = _ids(vote, path + '.votes.item', minimum=0)
            if (any(v >= len(options) for v in indices)
                    or (not poll['multi'] and len(indices) > 1)):
                _bad(path + '.votes.item')


def _validate_collections(state):
    for field in ('group_files', 'tasks', 'moments', 'moment_covers'):
        state[field] = _id_map(state[field], 'state.' + field)
    fids, tids = set(), set()
    for records in state['group_files'].values():
        for rec in _array(records, 'state.group_files.records'):
            path = 'state.group_files.record'
            _obj(rec, path, allowed=('fid', 'name', 'size', 'ts', 'uid', 'nick'),
                 required=('fid', 'name'))
            fid = _id(rec['fid'], path + '.fid', key=True)
            if not isinstance(rec['fid'], str) or fid in fids:
                _bad(path + '.fid')
            fids.add(fid)
            _text(rec['name'], path + '.name', nonempty=True)
            _integer(rec.setdefault('size', 0), path + '.size', 0)
            _number(rec.setdefault('ts', 0), path + '.ts')
            _integer(rec.setdefault('uid', 0), path + '.uid', 0)
            _text(rec.setdefault('nick', ''), path + '.nick')
    for records in state['tasks'].values():
        for rec in _array(records, 'state.tasks.records'):
            path = 'state.tasks.record'
            _obj(rec, path, allowed=('tid', 'text', 'mode', 'uid', 'ts', 'done',
                                    'assignee', 'closed'), required=('tid', 'text'))
            tid = _id(rec['tid'], path + '.tid')
            if tid in tids:
                _bad(path + '.tid')
            tids.add(tid)
            _text(rec['text'], path + '.text', nonempty=True)
            if rec.setdefault('mode', 'todo') not in ('todo', 'relay', 'checkin'):
                _bad(path + '.mode')
            for field in ('uid', 'assignee', 'closed'):
                _integer(rec.setdefault(field, 0), path + '.' + field, 0)
            _number(rec.setdefault('ts', 0), path + '.ts')
            rec['done'] = _id_map(rec.setdefault('done', {}), path + '.done')
            for ts in rec['done'].values():
                _number(ts, path + '.done.value')
    for game, scores in state['fish_board'].items():
        _text(game, 'state.fish_board.key', nonempty=True)
        scores = state['fish_board'][game] = _id_map(scores, 'state.fish_board.scores')
        for score in scores.values():
            _integer(score, 'state.fish_board.score')
    for key, post in state['moments'].items():
        path = 'state.moments.record'
        _obj(post, path, allowed=('pid', 'uid', 'nick', 'text', 'ts', 'images',
                                 'likes', 'comments'))
        if _id(post.setdefault('pid', int(key)), path + '.pid') != int(key):
            _bad(path + '.pid')
        _integer(post.setdefault('uid', 0), path + '.uid', 0)
        for field in ('nick', 'text'):
            _text(post.setdefault(field, ''), path + '.' + field)
        _number(post.setdefault('ts', 0), path + '.ts')
        for name in _array(post.setdefault('images', []), path + '.images'):
            _safe_filename(name, path + '.images.item')
        _ids(post.setdefault('likes', []), path + '.likes')
        for comment in _array(post.setdefault('comments', []), path + '.comments'):
            cpath = path + '.comment'
            _obj(comment, cpath, required=('uid', 'nick', 'text', 'ts'))
            _id(comment['uid'], cpath + '.uid')
            _text(comment['nick'], cpath + '.nick')
            _text(comment['text'], cpath + '.text', nonempty=True, limit=500)
            _number(comment['ts'], cpath + '.ts')
            if 'rep' in comment:
                rep = _obj(comment['rep'], cpath + '.rep',
                           allowed=('uid', 'nick'), required=('uid', 'nick'))
                if rep['uid'] is not None:
                    _integer(rep['uid'], cpath + '.rep.uid')
                _text(rep['nick'], cpath + '.rep.nick', limit=50)
    image_exts = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp')
    for cover in state['moment_covers'].values():
        path = 'state.moment_covers.record'
        _obj(cover, path, allowed=('mode', 'preset', 'ext'), required=('mode',))
        if cover['mode'] == 'preset':
            if _integer(cover.setdefault('preset', 0), path + '.preset', 0) >= 6:
                _bad(path + '.preset')
            if cover.setdefault('ext', None) not in (None, ''):
                _bad(path + '.ext')
        elif cover['mode'] == 'img':
            if cover.get('ext') not in image_exts:
                _bad(path + '.ext')
            # The existing restore emitted 0; new uploads emit None.
            if cover.setdefault('preset', None) not in (None, 0) or type(cover['preset']) is bool:
                _bad(path + '.preset')
        else:
            _bad(path + '.mode')
    for key, sticker in state['custom_stickers'].items():
        path = 'state.custom_stickers.record'
        _obj(sticker, path, allowed=('code', 'label', 'pack', 'ext', 'order'))
        code = sticker.setdefault('code', key)
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,24}', code) or code != key:
            _bad(path + '.code')
        for field in ('label', 'pack'):
            _text(sticker.setdefault(field, ''), path + '.' + field, limit=16)
        if any(not (ch.isalnum() or ch in '_- ') for ch in sticker['pack']):
            _bad(path + '.pack')
        if sticker.setdefault('ext', 'png') not in (*image_exts, 'json'):
            _bad(path + '.ext')
        _integer(sticker.setdefault('order', 0), path + '.order', 0)
    for pack, meta in state['sticker_pack_meta'].items():
        _text(pack, 'state.sticker_pack_meta.key', limit=16)
        if any(not (ch.isalnum() or ch in '_- ') for ch in pack):
            _bad('state.sticker_pack_meta.key')
        _obj(meta, 'state.sticker_pack_meta.record', allowed=('cover',), required=('cover',))
        if meta['cover'] not in (*image_exts, 'json'):
            _bad('state.sticker_pack_meta.record.cover')


def _safe_filename(value, path):
    _text(value, path, nonempty=True)
    if value in ('.', '..') or any(c in value for c in '\\/:\0'):
        _bad(path)
    return value


def validate_pair(state, control):
    """Validate identities; pending intents may be absent from an old snapshot."""
    control = validate_control(control)
    state = validate_state(state, store_id=control['store_id'])
    intents = control['intents']
    for uid, record in state['retired'].items():
        if intents.get(uid) != record:
            raise StoreError('retirement_conflict', 'state.retired')
    for uid, record in intents.items():
        target = state['nick_to_uid'].get(record['nick'])
        if target not in (None, int(uid)):
            raise StoreError('retirement_conflict', 'control.intents.nick')
        if any(name != record['nick'] and target == int(uid)
               for name, target in state['nick_to_uid'].items()):
            raise StoreError('retirement_conflict', 'control.intents.uid')
    return state, control


class _Overlapped(ctypes.Structure):
    _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                ('hEvent', wintypes.HANDLE)]


class StoreOwner:
    """Lifetime exclusive Windows byte lock, with no create-on-open behavior."""

    def __init__(self, path):
        self.path = Path(path)
        self._handle = None
        self._overlapped = _Overlapped()
        self._api = None

    @property
    def held(self):
        return self._handle is not None

    def acquire(self):
        if self.held:
            raise StoreError('already_owned')
        if os.name != 'nt':
            raise StoreError('unsupported_platform')
        if not self.path.is_file() or self.path.is_symlink():
            raise StoreError('ownership_unavailable', 'owner')
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE)
        api.CreateFileW.restype = wintypes.HANDLE
        api.LockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped))
        api.LockFileEx.restype = wintypes.BOOL
        api.UnlockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.POINTER(_Overlapped))
        api.UnlockFileEx.restype = wintypes.BOOL
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        api.CloseHandle.restype = wintypes.BOOL
        # OPEN_EXISTING, deny delete/replace of the lock pathname while held.
        handle = api.CreateFileW(str(self.path), 0xC0000000, 0x3, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise StoreError('ownership_unavailable', 'owner')
        if not api.LockFileEx(handle, 0x3, 0, 1, 0, ctypes.byref(self._overlapped)):
            api.CloseHandle(handle)
            raise StoreError('store_in_use', 'owner')
        self._api, self._handle = api, handle
        return self

    def close(self):
        if self._handle is not None:
            handle, self._handle = self._handle, None
            try:
                self._api.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(self._overlapped))
            finally:
                self._api.CloseHandle(handle)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()


@dataclass(frozen=True)
class LoadedPair:
    state: dict
    control: dict
    state_bytes: bytes
    control_bytes: bytes


class StoreCoordinator:
    """One owner and writer order for a versioned Store.

    OPENING/RECOVERING cannot serve. Hub supplies the business recovery proof
    before mark_ready. close never writes; shutdown flush remains explicit.
    """

    def __init__(self, root):
        self.root = Path(root).absolute()
        self.owner = StoreOwner(self.root / '.owner.lock')
        self.writer = threading.RLock()
        self.phase = 'OPENING'
        self.state_store = ServerStore(str(self.root / 'state.json'),
                                       create_parent=False, unique_temp=True, replace_retry_budget=0.5)
        self.control_store = ServerStore(str(self.root / 'control.json'),
                                         create_parent=False, unique_temp=True, replace_retry_budget=0.5)
        self._control = None
        self._control_bytes = None

    @property
    def store_id(self):
        return self._control['store_id'] if self._control else None

    @property
    def intents(self):
        return copy.deepcopy(self._control['intents']) if self._control else {}

    def _assert_owned(self):
        if not self.owner.held or self.phase in ('FAILED', 'CLOSED'):
            raise StoreError('store_not_writable')

    def fail(self):
        self.phase = 'FAILED'

    def close(self):
        """Caller must stop/join all users before releasing ownership."""
        self.owner.close()
        if self.phase != 'FAILED':
            self.phase = 'CLOSED'

    def open(self) -> LoadedPair:
        try:
            if not self.root.is_dir():
                raise StoreError('uninitialized')
            # Classify legacy without creating its missing owner sentinel.
            if not (self.root / '.owner.lock').exists():
                state = self.state_store.read_bytes_result()
                control = self.control_store.read_bytes_result()
                if state.status == 'bytes' and control.status == 'missing':
                    raw = strict_json(state.payload)
                    if '_store' not in raw:
                        validate_state(raw, legacy=True)
                        raise StoreError('legacy_requires_adoption')
                if state.status == control.status == 'missing':
                    raise StoreError('uninitialized')
            self.owner.acquire()
            pair = self.read_pair(allow_bootstrap=True)
            if pair.control['phase'] != 'ready':
                raise StoreError('bootstrap_incomplete')
            # LoadedPair is caller-owned; its nested dictionaries must not
            # alias the coordinator's accepted identity floor.
            self._control = copy.deepcopy(pair.control)
            self._control_bytes = pair.control_bytes
            self.phase = 'RECOVERING'
            return pair
        except BaseException:
            self.fail()
            self.close()
            raise

    def read_pair(self, *, allow_bootstrap=False) -> LoadedPair:
        self._assert_owned()
        raw_state = read_required(self.state_store, 'state')
        raw_control = self.control_store.read_bytes_result()
        if raw_control.status == 'missing':
            value = strict_json(raw_state.payload)
            if '_store' not in value:
                validate_state(value, legacy=True)
                raise StoreError('legacy_requires_adoption')
            raise StoreError('incomplete_store', 'control')
        if raw_control.status != 'bytes':
            raise StoreError('read_error', 'control')
        control = validate_control(strict_json(raw_control.payload, field='control'))
        if control['phase'] == 'bootstrap':
            if not allow_bootstrap:
                raise StoreError('bootstrap_incomplete')
            # Bootstrap can still contain the original unversioned legacy bytes.
            raw = strict_json(raw_state.payload)
            state = validate_state(raw, legacy='_store' not in raw,
                                   store_id=control['store_id'])
        else:
            state, control = validate_pair(strict_json(raw_state.payload), control)
        return LoadedPair(state, control, raw_state.payload, raw_control.payload)

    def mark_ready(self, state, *, verify_cleanup=None):
        with self.writer:
            self._assert_owned()
            if self.phase != 'RECOVERING':
                raise StoreError('invalid_phase')
            normalized, _ = validate_pair(state, self._control)
            if normalized['retired'] != self._control['intents']:
                raise StoreError('recovery_required')
            actual = self.read_pair()
            if actual.control_bytes != self._control_bytes:
                self.fail()
                raise StoreError('control_changed')
            if actual.state['retired'] != self._control['intents']:
                raise StoreError('recovery_required')
            # A memory-only tombstone is never a startup proof.  Hub supplies
            # the pure CORE predicate, evaluated against the actual bytes.
            if self._control['intents'] and (verify_cleanup is None or
                    verify_cleanup(actual.state, self.intents) is not True):
                raise StoreError('recovery_required')
            self.phase = 'READY'

    def validate_snapshot(self, state, *, recovery=False, final=False):
        self._assert_owned()
        expected = 'RECOVERING' if recovery else 'QUIESCING' if final else 'READY'
        if recovery and final or self.phase != expected:
            raise StoreError('store_not_writable')
        normalized, _ = validate_pair(state, self._control)
        if normalized['retired'] != self._control['intents']:
            raise StoreError('recovery_required')
        return normalized

    def check_control(self):
        """Under the common writer, before any new authority publication."""
        self._assert_owned()
        try:
            actual = read_required(self.control_store, 'control')
            validate_control(strict_json(actual.payload, field='control'))
            if actual.payload != self._control_bytes:
                raise StoreError('control_changed')
        except StoreError:
            self.fail()
            raise

    def validate_observed_state(self, state):
        self._assert_owned()
        return validate_pair(state, self._control)[0]

    @staticmethod
    def _publish(store, value, previous: bytes | None) -> SaveResult:
        encoded = encode_state(value)
        result = store.save_bytes(encoded.payload)
        observed = store.read_bytes_result()
        if observed.status == 'bytes' and observed.payload == encoded.payload:
            return SaveResult('committed', 'readback', None, False,
                              observed.length, observed.sha256)
        if ((observed.status == 'bytes' and observed.payload == previous)
                or (observed.status == 'missing' and previous is None)):
            return SaveResult('not_committed', result.stage,
                              result.error_code or 'known_predecessor', True,
                              encoded.length, encoded.sha256)
        return SaveResult('uncertain', 'readback', 'authority_unverified', False,
                          encoded.length, encoded.sha256)

    def accept_intent(self, uid: int, record: dict) -> SaveResult:
        """Called inside Hub's continuous writer reservation, before t0."""
        with self.writer:
            self._assert_owned()
            if self.phase != 'READY':
                raise StoreError('store_not_writable')
            uid = str(_id(uid, 'intent.uid'))
            checked = _retirements({uid: copy.deepcopy(record)}, 'intent')[uid]
            try:
                previous = read_required(self.control_store, 'control')
            except StoreError as exc:
                self.fail()
                return SaveResult('uncertain', 'intent_read', 'control_' + exc.code, False)
            if previous.payload != self._control_bytes:
                self.fail()
                return SaveResult('uncertain', 'intent_read', 'control_changed', False)
            if uid in self._control['intents']:
                if self._control['intents'][uid] != checked:
                    raise StoreError('retirement_conflict', 'intent')
                return SaveResult('committed', 'readback', None, False,
                                  previous.length, previous.sha256)
            candidate = copy.deepcopy(self._control)
            candidate['intents'][uid] = checked
            validate_control(candidate)
            result = self._publish(self.control_store, candidate, self._control_bytes)
            if result.effect == 'committed':
                self._control = candidate
                self._control_bytes = encode_state(candidate).payload
            elif result.effect == 'uncertain':
                self.fail()
            return result

    @classmethod
    def initialize_new(cls, root):
        root = Path(root).absolute()
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise StoreError('target_exists') from None
        cls._create_owner(root)
        instance = cls(root)
        try:
            instance.owner.acquire()
            control = {'format_version': 1, 'store_id': uuid.uuid4().hex,
                       'phase': 'bootstrap', 'bootstrap': {'kind': 'new',
                       'source_sha256': None, 'source_length': None}, 'intents': {}}
            instance._write_bootstrap(control, {}, None)
        finally:
            instance.close()

    @staticmethod
    def _create_owner(root):
        path = root / '.owner.lock'
        try:
            with path.open('xb') as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if not path.is_file() or path.is_symlink():
                raise StoreError('ownership_unavailable', 'owner') from None

    @classmethod
    def adopt_legacy(cls, root):
        root = Path(root).absolute()
        if not root.is_dir():
            raise StoreError('uninitialized')
        # Creating an owner is part of this explicit offline operation only.
        cls._create_owner(root)
        instance = cls(root)
        try:
            instance.owner.acquire()
            if instance.control_store.read_bytes_result().status != 'missing':
                raise StoreError('control_already_present')
            source = read_required(instance.state_store, 'state')
            raw = strict_json(source.payload)
            normalized = validate_state(raw, legacy=True)
            instance._backup_legacy(source)
            control = {'format_version': 1, 'store_id': uuid.uuid4().hex,
                       'phase': 'bootstrap', 'bootstrap': {'kind': 'legacy',
                       'source_sha256': source.sha256, 'source_length': source.length},
                       'intents': normalized['retired']}
            instance._write_bootstrap(control, raw, source.payload)
        finally:
            instance.close()

    def _backup_legacy(self, source: ReadResult):
        """Publish complete original bytes without overwriting an older backup.

        An interrupted write can only leave a non-authoritative stage file;
        it cannot reserve the final backup name with a partial payload.
        """
        backup = self.root / ('state.legacy.' + source.sha256 + '.json')
        try:
            existing = backup.read_bytes()
        except FileNotFoundError:
            pass
        except OSError:
            raise StoreError('backup_unavailable') from None
        else:
            if existing != source.payload:
                raise StoreError('backup_conflict')
            return
        temporary = self.root / ('.backup-stage-' + uuid.uuid4().hex)
        stream, created, stage = None, False, 'open'
        try:
            stream = temporary.open('xb')
            created = True
            stage = 'write'
            offset = 0
            while offset < source.length:
                count = stream.write(source.payload[offset:])
                if type(count) is not int or count <= 0 or count > source.length - offset:
                    raise OSError('invalid short write')
                offset += count
            stage = 'flush'
            stream.flush()
            stage = 'fsync'
            os.fsync(stream.fileno())
            stage = 'close'
            stream.close()
            stream = None
            stage = 'publish'
            # Windows rename fails if destination already exists, unlike
            # replace: never clobber an independently present backup.
            os.rename(temporary, backup)
            created = False
            stage = 'readback'
            if backup.read_bytes() != source.payload:
                raise StoreError('backup_unverified')
        except OSError:
            # The rename may have completed before its acknowledgement failed.
            try:
                matches = backup.read_bytes() == source.payload
            except OSError:
                matches = False
            if not matches:
                raise StoreError('backup_write_failed', 'backup.' + stage) from None
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
            if created:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def _write_bootstrap(self, control, original, previous_state):
        validate_control(control)
        result = self._publish(self.control_store, control, None)
        if result.effect != 'committed':
            raise StoreError('bootstrap_write_failed', 'control')
        self._finish_bootstrap(control, original, previous_state)

    def _finish_bootstrap(self, control, original, previous_state):
        state = copy.deepcopy(original)
        state['_store'] = {'format_version': 1, 'store_id': control['store_id']}
        validate_pair(state, control)
        result = self._publish(self.state_store, state, previous_state)
        if result.effect != 'committed':
            raise StoreError('bootstrap_write_failed', 'state')
        previous_control = read_required(self.control_store, 'control').payload
        ready = dict(control, phase='ready')
        result = self._publish(self.control_store, ready, previous_control)
        if result.effect != 'committed':
            raise StoreError('bootstrap_write_failed', 'control')
        self.read_pair()

    @classmethod
    def resume_bootstrap(cls, root):
        instance = cls(root)
        try:
            instance.owner.acquire()
            raw_control = read_required(instance.control_store, 'control')
            control = validate_control(strict_json(raw_control.payload, field='control'))
            if control['phase'] == 'ready':
                instance.read_pair()
                return
            current = instance.state_store.read_bytes_result()
            if current.status == 'read_error':
                raise StoreError('read_error', 'state')
            boot = control['bootstrap']
            if boot['kind'] == 'legacy':
                backup = instance.root / ('state.legacy.' + boot['source_sha256'] + '.json')
                try:
                    source = backup.read_bytes()
                except OSError:
                    raise StoreError('backup_unavailable') from None
                if (len(source) != boot['source_length']
                        or hashlib.sha256(source).hexdigest() != boot['source_sha256']):
                    raise StoreError('backup_conflict')
                original = strict_json(source)
                normalized = validate_state(original, legacy=True)
                if normalized['retired'] != control['intents'] or current.status == 'missing':
                    raise StoreError('bootstrap_conflict')
            else:
                original, source = {}, None
                if control['intents']:
                    raise StoreError('bootstrap_conflict')
            if current.status == 'bytes' and current.payload != source:
                value = strict_json(current.payload)
                validate_state(value, store_id=control['store_id'])
                without_meta = {k: v for k, v in value.items() if k != '_store'}
                if without_meta != original:
                    raise StoreError('bootstrap_conflict')
            instance._finish_bootstrap(control, original, current.payload)
        finally:
            instance.close()

    @classmethod
    def inspect(cls, root):
        instance = cls(root)
        report = {'exclusive': False}
        try:
            try:
                instance.owner.acquire()
                report['exclusive'] = True
            except StoreError as exc:
                report['ownership'] = exc.code
            for field, store in (('state', instance.state_store), ('control', instance.control_store)):
                read = store.read_bytes_result()
                item = {'status': read.status, 'sha256': read.sha256, 'length': read.length}
                if read.status == 'bytes':
                    try:
                        raw = strict_json(read.payload, field=field)
                        if field == 'state':
                            validate_state(raw, legacy='_store' not in raw)
                            item['format'] = 1 if '_store' in raw else 'legacy'
                        else:
                            checked = validate_control(raw)
                            item.update(format=1, phase=checked['phase'],
                                        intent_count=len(checked['intents']))
                    except StoreError as exc:
                        item.update(status=exc.code, field=exc.field)
                report[field] = item
            if report['exclusive']:
                try:
                    pair = instance.read_pair()
                    report['pair'] = 'valid'
                    report['unmaterialized_count'] = len(set(pair.control['intents']) - set(pair.state['retired']))
                except StoreError as exc:
                    report['pair'] = exc.code
            else:
                report['pair'] = 'unverified_without_ownership'
            return report
        finally:
            instance.close()


def maintenance(action, root):
    """Explicit offline operations; never constructs Hub or opens listeners.

    Reports contain classification/hashes only, never state values. An inspect
    result is an observation, not a permit to serve or replace either file.
    """
    operations = {
        'initialize-new': StoreCoordinator.initialize_new,
        'adopt-legacy': StoreCoordinator.adopt_legacy,
        'resume-bootstrap': StoreCoordinator.resume_bootstrap,
        'inspect': StoreCoordinator.inspect,
    }
    operation = operations.get(action)
    if operation is None:
        raise StoreError('invalid_action')
    result = operation(root)
    return {'action': action, 'ok': True,
            'inspection': result if action == 'inspect' else StoreCoordinator.inspect(root)}
