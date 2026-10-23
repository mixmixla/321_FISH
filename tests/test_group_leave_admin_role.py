"""Leaving a group retires its admin role until the current owner grants it again."""
from dataclasses import replace
import sys

from config import CFG
from server import Hub
from test_admin_group_remove_scope import make_session
from test_group_kick_scope import cleanup, running, shutdown, assert_stopped


def test_former_admin_rejoins_as_member_until_owner_grants_role(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    try:
        owner, _ = make_session(hub, 'role-owner')
        member, frames = make_session(hub, 'role-member')
        web, web_frames = make_session(hub, 'role-member', 'web')
        hub.web_tokens['synthetic-role-token'] = web
        for name in ('role-left', 'role-kept'):
            hub._on_group_create(owner, {'name': name, 'public': True})
            hub._on_group_join(member, {'gid': max(hub.groups)})
        left, kept = sorted(hub.groups)
        for gid in (left, kept):
            hub._on_group_set_admin(owner, {'gid': gid, 'target': member.uid, 'enable': True})
        hub.groups[left]['mutes'][member.uid] = 1234567890
        frames.clear()
        web_frames.clear()
        hub._on_group_invite_get(member, {'gid': left})
        assert len([f for f in frames if f.get('t') == 'group_invite' and f.get('gid') == left]) == 1
        frames.clear()
        hub._on_group_leave(member, {'gid': left})
        assert len([f for f in frames if f.get('code') == 'group_removed'
                    and f.get('gid') == left]) == 1
        assert len([f for f in web_frames if f.get('code') == 'group_removed'
                    and f.get('gid') == left]) == 1
        assert hub.session_by_token('synthetic-role-token') is web
        assert hub.groups[left]['mutes'][member.uid] == 1234567890
        assert member.uid in hub.groups[kept]['admins']
        frames.clear()
        hub._on_group_join(member, {'gid': left})
        frames.clear()
        hub._on_group_invite_get(member, {'gid': left})
        assert [f.get('code') for f in frames if f.get('t') == 'error'] == ['perm']
        assert not any(f.get('t') == 'group_invite' and f.get('gid') == left for f in frames)
        assert member.uid not in hub.groups[left]['admins']
        assert hub.groups[left]['mutes'][member.uid] == 1234567890
        frames.clear()
        hub._on_group_invite_get(member, {'gid': kept})
        assert any(f.get('t') == 'group_invite' and f.get('gid') == kept for f in frames)
        hub._on_group_set_admin(owner, {'gid': left, 'target': member.uid, 'enable': True})
        frames.clear()
        hub._on_group_invite_get(member, {'gid': left})
        assert any(f.get('t') == 'group_invite' and f.get('gid') == left for f in frames)
        assert hub._session_is_active(member) and hub._session_is_active(web)
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_real_core_role_is_revoked_on_leave_and_can_be_granted_again(running):
    hub, spawn = running
    owner, owner_events = spawn('role-core-owner')
    member, member_events = spawn('role-core-member')
    assert owner.create_group('role-core', public=True)
    gid = owner_events.wait('group_state', pred=lambda e: e.get('name') == 'role-core')['gid']
    assert member.join_group(gid)
    assert member_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                              and any(m['uid'] == member.uid for m in e['members']))
    assert owner.set_admin(gid, member.uid, True)
    assert member_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                              and member.uid in e.get('admins', []))
    assert member.get_group_invite(gid)
    assert member_events.wait('group_invite', pred=lambda e: e.get('gid') == gid)
    assert member.leave_group(gid)
    assert member_events.wait('error', pred=lambda e: e.get('code') == 'group_removed'
                              and e.get('gid') == gid)
    assert member.join_group(gid)
    assert member_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                              and any(m['uid'] == member.uid for m in e['members']))
    assert member.get_group_invite(gid)
    assert member_events.wait('error', pred=lambda e: e.get('code') == 'perm')
    assert owner.set_admin(gid, member.uid, True)
    assert member_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                              and member.uid in e.get('admins', []))
    assert member.get_group_invite(gid)
    assert member_events.wait('group_invite', pred=lambda e: e.get('gid') == gid)
    assert member.connected and not member._manual_login_required
    assert member.uid in hub.groups[gid]['members']


def test_other_member_leaves_without_changing_owner_or_admin_role(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    try:
        owner, _ = make_session(hub, 'control-owner')
        admin, _ = make_session(hub, 'control-admin')
        ordinary, _ = make_session(hub, 'control-ordinary')
        hub._on_group_create(owner, {'name': 'control', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(admin, {'gid': gid})
        hub._on_group_join(ordinary, {'gid': gid})
        hub._on_group_set_admin(owner, {'gid': gid, 'target': admin.uid, 'enable': True})
        hub._on_group_leave(ordinary, {'gid': gid})
        assert hub.groups[gid]['owner'] == owner.uid
        assert hub.groups[gid]['admins'] == {admin.uid}
        hub._on_group_leave(owner, {'gid': gid})
        assert hub.groups[gid]['owner'] == admin.uid
        assert admin.uid in hub.groups[gid]['members']
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))
