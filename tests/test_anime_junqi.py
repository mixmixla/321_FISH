"""Officer atlas, rectangular counter hit geometry and guarded real decisions."""
import copy
from boardgames.chess_junqi import identity, can_act, click, NAMES
from games_pkg.junqi import JunqiGame
import client_gameui as cu


def test_all_rank_codes_and_guard():
    assert len(NAMES)==12
    for rank in range(12):
        assert identity(10+rank)==(0,rank)
        assert identity(40+rank)==(1,rank)
    assert identity(0) is None
    s=JunqiGame([1,2],seed=3).snapshot()
    assert can_act(s,1) and not can_act(s,2) and not can_act(s,3)
    assert not can_act(s,1,connected=False)
    assert not can_act(s,1,{'status':'ended'})
    assert not can_act(s,1,{'players':[2]})


def test_exact_rectangular_geometry_reselect_and_live_rule_action():
    g=JunqiGame([1,2],seed=3);s=g.snapshot();sent=[]
    ui=dict(game='junqi',state=s,junqi_state=s,me=1,connected=True,room={'status':'playing','players':[1,2]},
            _room_context=('g1',1),junqi_context=(('g1',1),1),sel={},ox=10,oy=20,cell=20,junqi_cw=40,n=10,cols=5,rows=10,
            junqi_legal=g.legal_moves(1),submit=sent.append,repaint=lambda:None)
    mv=ui['junqi_legal'][0];fx,fy=mv['from'];tx,ty=mv['to']
    assert cu._cell_of(ui,10+(fx+.5)*40,20+(fy+.5)*20)==(fx,fy)
    assert cu._cell_of(ui,210,20) is None
    click(ui,10+(fx+.5)*40,20+(fy+.5)*20)
    assert ui['sel']==dict(game='junqi',fx=fx,fy=fy)
    click(ui,10+(tx+.5)*40,20+(ty+.5)*20)
    assert sent==[dict(fx=fx,fy=fy,tx=tx,ty=ty)]
    g.act(1,sent[0])
    ui['state']=g.snapshot();click(ui,10+(fx+.5)*40,20+(fy+.5)*20)
    assert len(sent)==1  # stale rendered snapshot cannot dispatch


def test_flag_and_mine_are_not_selectable_and_stale_room_rejected():
    g=JunqiGame([1,2],seed=3);s=g.snapshot()
    sent=[];ui=dict(game='junqi',state=s,junqi_state=s,me=1,junqi_context=(None,1),
                   ox=0,oy=0,cell=20,junqi_cw=40,sel={},submit=sent.append,repaint=lambda:None)
    for y,row in enumerate(s['board']):
        for x,code in enumerate(row):
            if code in (10,11):click(ui,(x+.5)*40,(y+.5)*20);assert not ui['sel']
    ui['_room_context']=('changed',2);click(ui,20,90)
    assert not sent
