"""Physical railway route choices, private tickets and latest-frame submission."""
from types import SimpleNamespace
import copy
import pytest
from boardgames import rail_table_tk as table
from games_pkg.tielu import TieluGame, COLORS
from test_tielu_click import Canvas


def scene(width=480,height=365):
    game=TieluGame([7,8],seed=6);st=copy.deepcopy(game.snapshot());sent=[]
    ui={'room':{'room_id':'rail','round':1,'game':'tielu','status':'playing','players':[7,8]},
        'connected':True,'_room_context':('rail',1),'state':st,'me':7,'submit':sent.append,'repaint':lambda:None}
    cv=Canvas();table.paint(cv,st,7,str,sent.append,lambda:None,ui,game.private(7),width,height,lambda *a:None)
    return game,st,ui,sent,cv


@pytest.mark.parametrize('width,height',[(472,365),(480,400),(1000,650)])
def test_real_routes_have_exact_carriage_counts_and_all_table_entities_fit(width,height):
    game,st,ui,sent,cv=scene(width,height)
    assert ui['tl_coach_count']==sum(r['length'] for r in st['routes'])
    assert len(ui['tl_routes'])==15
    for x0,y0,x1,y1,*_ in ui['tl_entities']:
        assert 0<=x0<x1<=width and 0<=y0<y1<=height
    assert len([r for r in ui['tl_entities'] if r[-1][0]=='color'])==5
    assert {r[-1] for r in ui['tl_entities'] if r[-1][0]=='action'}=={('action','draw'),('action','ticket'),('action','skip')}
    assert sent==[]


def test_selecting_route_and_ticket_is_read_only_until_live_affordable_confirmation():
    game,st,ui,sent,_=scene()
    route=next(r for r in st['routes'] if game.hand[7][r['color']]>=r['length'])
    ui['tl_selected']=table.signature(route)
    table.key(ui,'Return');assert sent==[{'op':'claim','a':route['a'],'b':route['b']}]
    sent.clear();ui['state']=copy.deepcopy(st);ui['state']['routes'].remove(route)
    table.key(ui,'Return');assert sent==[]
    goal=game.private(7)['tickets'][0]
    table.command(ui,('goal',(goal['a'],goal['b'],goal['v'])))
    assert ui['tl_view']=='map' and sent==[]


def test_spectator_cannot_read_injected_private_cards_or_goals_or_send():
    game,st,ui,sent,_=scene();ui['room']['spectators']=[7]
    cv=Canvas();table.paint(cv,st,7,str,sent.append,lambda:None,ui,game.private(7),480,400,lambda *a:None)
    assert table.private(ui)=={}
    assert not any(r[-1][0] in ('color','action') for r in ui['tl_entities'])
    table.key(ui,'d');table.key(ui,'t');assert sent==[]


@pytest.mark.parametrize('changed',['room','snapshot','private','uid','connected','turn','ended'])
def test_game_window_rejects_old_room_private_or_public_frames(changed):
    from client import GameWindow
    game,st,ui,sent,_=scene();private=game.private(7);ui['tl_private']=private
    core=SimpleNamespace(game_room=ui['room'],game_state=st,game_private=private,uid=7,connected=True,game_action=lambda rid,action:sent.append(action) or True)
    host=GameWindow.__new__(GameWindow);host.core=core
    if changed=='room':core.game_room={**ui['room'],'room_id':'other'}
    elif changed=='snapshot':core.game_state=copy.deepcopy(st)
    elif changed=='private':core.game_private=copy.deepcopy(private)
    elif changed=='uid':core.uid=8
    elif changed=='connected':core.connected=False
    elif changed=='turn':st['turn_uid']=8
    else:core.game_room={**ui['room'],'status':'ended'}
    host._do_action({'op':'draw'},ui);assert sent==[]


def test_same_frame_duplicate_is_latched_and_legacy_coordinate_actions_are_gone():
    from client import GameWindow,_GAME_ACTIONS
    game,st,ui,sent,_=scene();private=game.private(7);ui['tl_private']=private
    core=SimpleNamespace(game_room=ui['room'],game_state=st,game_private=private,uid=7,connected=True,game_action=lambda rid,action:sent.append(action) or True)
    host=GameWindow.__new__(GameWindow);host.core=core
    host._do_action({'op':'draw'},ui);host._do_action({'op':'draw'},ui)
    assert sent==[{'op':'draw'}] and _GAME_ACTIONS['tielu']==[]


def test_empty_decks_cannot_be_drawn_with_keyboard_or_table_commands():
    from games_pkg.tielu import TICKETS
    game,st,ui,sent,_=scene();st['ticket_left']=0
    table.key(ui,'d');assert sent==[]
    ui['tl_private']={'hand':{},'tickets':[{'a':a,'b':b,'v':v} for a,b,v in TICKETS]}
    table.key(ui,'t');assert sent==[] and not table.goal_available(ui)


def test_destination_ticket_art_uses_the_two_real_city_ids(monkeypatch):
    game,st,ui,sent,_=scene();ui['tl_view']='goals';asked=[]
    monkeypatch.setattr(table,'art',lambda cv,name,index,*a,**kw:asked.append((name,index)) or True)
    table.paint(Canvas(),st,7,str,sent.append,lambda:None,ui,game.private(7),480,400,lambda *a:None)
    expected=[cid for goal in game.private(7)['tickets'][:2] for cid in (goal['a'],goal['b'])]
    assert [i for name,i in asked if name==table.STATIONS]==expected


def test_terminal_player_badge_shows_total_not_only_route_points():
    game,st,ui,sent,_=scene();game.mine[7]=[(0,1,2)];game.route_deck=[];game.ended();st=game.snapshot()
    cv=Canvas();table.paint(cv,st,7,str,sent.append,lambda:None,ui,None,480,400,lambda *a:None)
    assert '你 '+str(st['final_scores']['7']['total'])+'分' in cv.text
    assert st['final_scores']['7']['total']!=st['score']['7']
