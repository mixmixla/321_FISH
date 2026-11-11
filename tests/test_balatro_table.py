"""MP poker objects preserve private cards, exact IDs, and authoritative results."""
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import client
from boardgames.jokers import desktop as jt
from boardgames.jokers.catalog import CORE_ORDER, JOKERS
from boardgames.jokers.web import WEB_JS
from games_pkg.balatro import BalatroGame, BalatroSoloGame, CORE_JOKERS
from games_pkg.rooms import RoomManager
from test_card_table_tk import Canvas


def room():
    manager=RoomManager({'balatro':BalatroGame});manager._seed_for=lambda room:3
    r=manager.create(7,'balatro');manager.join(8,r.room_id);manager.start(7,r.room_id)
    return manager,r


def ui_for(r,me=7,pv=None):
    sent=[];ui={'game':'balatro','state':r.gs.snapshot(),'room':r.summary(),'me':me,'connected':True,
                '_room_context':(r.room_id,r.round_no),'submit':sent.append,'repaint':lambda:None}
    jt.paint(Canvas(),ui['state'],me,str,ui['submit'],ui['repaint'],ui,r.gs.private(me) if pv is None else pv,480,400)
    return ui,sent


def choose(ui,kind,value=None):
    rect=next(h for h in ui['jt_hits'] if h[-2]==kind and (value is None or h[-1]==value))
    jt.click(ui,(rect[0]+rect[2])/2,(rect[1]+rect[3])/2)


def test_public_result_reveals_only_consumed_cards_and_copies_them():
    g=BalatroGame([7,8],seed=3);card=dict(g.private(7)['hand'][0])
    assert g.snapshot()['last_play'] is None and 'hand' not in g.snapshot()
    assert g.private(7)['owner_uid']==7 and g.private(8)['owner_uid']==8 and g.private(99) is None
    g.act(7,{'op':'select','cid':card['id']})
    assert g.private(7)['preview']['name'] and g.snapshot()['last_play'] is None
    g.act(7,{'op':'play'})
    last=g.snapshot()['last_play'];assert last['uid']==7 and last['cards']==[card]
    assert all(c['id']!=card['id'] for c in g.private(7)['hand'])
    assert last['points']==g.snapshot()['score']['7'] and g.snapshot()['plays_left']['7']==1
    last['cards'][0]['c']='?';last['effects'].append('fake')
    assert g.snapshot()['last_play']['cards']==[card] and 'fake' not in g.snapshot()['last_play']['effects']


def test_discard_counts_are_server_values_and_solo_scope_stays_unchanged():
    g=BalatroGame([7,8],seed=3);before=g.private(7)['hand'];g.act(7,{'op':'discard','cid':before[0]['id']})
    assert g.snapshot()['discards_left']['7']==2 and len(g.private(7)['hand'])==8
    assert before[0]['id'] not in [c['id'] for c in g.private(7)['hand']]
    assert g.snapshot()['blind_targets']=={'7':60,'8':67}
    solo=BalatroSoloGame([7],seed=3)
    assert solo.snapshot()['blind_target']==300 and 'blind_targets' not in solo.snapshot()
    assert 'last_play' not in solo.snapshot() and 'owner_uid' not in solo.private(7)


def test_role_art_is_exactly_the_eight_multiplayer_abilities():
    assert set(CORE_ORDER)==CORE_JOKERS
    assert [JOKERS[k]['index'] for k in CORE_ORDER]==list(range(8))
    assert all(JOKERS[k]['file']=='balatro-jokers-core.webp' for k in CORE_ORDER)


def test_multiplayer_joker_effects_and_preview_do_not_change_the_scoring_chain():
    g=BalatroGame([7,8],seed=3);g._jokers[7]=['pair','heart']
    pair=[{'c':'5','s':'h','id':0},{'c':'5','s':'s','id':1}]
    g._hand[7]=pair+[{'c':'K','s':'c','id':2}]
    for card in pair:g.act(7,{'op':'select','cid':card['id']})
    before_rng=g.rng.getstate();preview=g.private(7)['preview']
    assert preview['type']=='pair' and g.rng.getstate()==before_rng
    g.act(7,{'op':'play'});last=g.snapshot()['last_play']
    assert last['points']==preview['base']*2+30
    assert last['effects']==['对子王×2','红心暖手+30']


def test_native_ended_table_keeps_public_jokers_and_never_shows_held_cards():
    _,r=room();ui,_=ui_for(r);ui['room']['status']='ended';ui['state'].update(done=True,winner=7)
    jt.paint(Canvas(),ui['state'],7,str,lambda action:None,lambda:None,ui,None,480,400)
    assert len([h for h in ui['jt_hits'] if h[-2]=='inspect'])==2
    assert not [h for h in ui['jt_hits'] if h[-2] in ('card','play','discard_mode')]
    ui['state'].update(done=False,winner=None);cv=Canvas()
    jt.paint(cv,ui['state'],7,str,lambda action:None,lambda:None,ui,None,480,400)
    assert any(kw.get('text')=='本局已结束' for name,args,kw in cv.calls if name=='create_text')


def test_native_pick_discard_pile_settlement_and_read_only_inspector():
    manager,r=room();ui,sent=ui_for(r);pv=r.gs.private(7);cid=pv['hand'][0]['id']
    assert len([h for h in ui['jt_hits'] if h[-2]=='card'])==8
    choose(ui,'inspect');assert not sent and ui['jt_inspect'] in CORE_JOKERS
    jt.key(ui,'Escape');choose(ui,'card',cid)
    assert sent==[{'op':'select','cid':cid}]
    # The same private frame cannot send a duplicate selection.
    choose(ui,'card',cid);assert len(sent)==1
    manager.handle_action(7,r.room_id,sent[0]);ui,sent=ui_for(r);choose(ui,'play')
    assert sent==[{'op':'play'}]
    # A physical discard pile arms a mode; selecting it alone never mutates rules.
    manager,r=room();ui,sent=ui_for(r);choose(ui,'discard_mode');assert not sent
    choose(ui,'card',r.gs.private(7)['hand'][1]['id']);assert sent[0]['op']=='discard'


@pytest.mark.parametrize('viewer',[8,99])
def test_native_never_draws_another_players_private_cards(viewer):
    _,r=room();ui,sent=ui_for(r,viewer,pv=r.gs.private(7))
    assert not [h for h in ui['jt_hits'] if h[-2] in ('card','play','discard_mode')]
    assert not jt.private(ui)


@pytest.mark.parametrize('mismatch',['room','state','private','uid','game','disconnected'])
def test_final_guard_drops_stale_or_foreign_callbacks(mismatch):
    _,r=room();pv=r.gs.private(7);st=r.gs.snapshot();sent=[]
    core=SimpleNamespace(uid=7,connected=True,game_room=r.summary(),game_state=st,game_private=pv,
                         game_action=lambda *args:sent.append(args))
    ui={'game':'balatro','_room_context':(r.room_id,r.round_no),'state':st,'_jt_private':pv,'me':7}
    if mismatch=='room':ui['_room_context']=('old-room',r.round_no)
    elif mismatch=='state':ui['state']=dict(st)
    elif mismatch=='private':ui['_jt_private']=dict(pv)
    elif mismatch=='uid':ui['me']=8
    elif mismatch=='game':ui['game']='balatro_solo'
    else:core.connected=False
    client.GameWindow._do_action(SimpleNamespace(core=core),{'op':'select','cid':pv['hand'][0]['id']},ui)
    assert not sent


def test_graphic_web_controls_and_privacy(tmp_path):
    g=BalatroGame([7,8],seed=3);initial={'state':g.snapshot(),'private':g.private(7)}
    cid=g.private(7)['hand'][0]['id'];g.act(7,{'op':'select','cid':cid})
    selected={'state':g.snapshot(),'private':g.private(7)};g.act(7,{'op':'play'})
    played={'state':g.snapshot(),'private':g.private(7)}
    p=tmp_path/'jokers.json';p.write_text(json.dumps({'js':WEB_JS,'initial':initial,'selected':selected,'played':played}),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('balatro_table_probe.cjs')),str(p)],
                          capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'private_cards_hidden' in result.stdout


def test_primary_multiplayer_entry_has_no_legacy_action_forms():
    assert client._actions_for('balatro',None)==[]
    assert client._actions_for('balatro_solo',None)  # Deferred variant remains untouched.
