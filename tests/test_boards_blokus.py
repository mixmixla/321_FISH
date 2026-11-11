"""Physical inventory, rule-equivalent preview and stale input boundaries."""
import copy
from types import SimpleNamespace
import pytest
import client_gameui as cu
from boardgames import boards_blokus as board
from games_pkg.blokus import BlokusGame
from games_pkg.base import GameRuleError


class Canvas:
    def __init__(self): self.calls=[]
    def __getattr__(self,name):
        return lambda *args,**kwargs:self.calls.append((name,args,kwargs))


def scene(game,me=7):
    sent=[];ui=dict(game="blokus",state=game.snapshot(),me=me,connected=True,
                   room=dict(status="playing",players=game.players),_room_context=("synthetic",1),submit=sent.append)
    cv=Canvas()
    def paint():
        cu.render(cv,"blokus",ui["state"],me,str,sent.append,paint,ui,None,472,360)
    ui["repaint"]=paint;paint()
    return cv,ui,sent


@pytest.mark.parametrize("after_first",[False,True])
def test_preview_matches_authoritative_engine_for_catalog_corners_and_contacts(after_first):
    game=BlokusGame([7,8],seed=1)
    if after_first:
        game.act(7,dict(op="place",piece="M",oi=0,x=19,y=0))
        game.act(8,dict(op="place",piece="M",oi=0,x=0,y=19))
    st=game.snapshot()
    for piece in st["has_piece"]["7"]:
        for oi in range(len(st["pieces"][piece])):
            for row,col in ((0,0),(19,0),(0,19),(19,19),(17,1),(5,5)):
                clone=copy.deepcopy(game)
                try:
                    clone.act(7,dict(op="place",piece=piece,oi=oi,x=row,y=col));valid=True
                except GameRuleError:
                    valid=False
                cells,preview=board.placement(st,7,piece,oi,row,col)
                assert preview==valid,(piece,oi,row,col)
                if valid:
                    assert sorted(cells)==sorted((r,c) for (r,c),u in clone.board.items() if game.board.get((r,c))!=u)


def test_inventory_contains_actual_catalog_cell_shapes_without_raw_labels():
    game=BlokusGame([7,8],seed=1);cv,ui,sent=scene(game)
    first=list(ui["blok_chips"])
    cells=[kw for name,args,kw in cv.calls if kw.get("tags")=="blok-polyomino"]
    assert len(cells)==sum(len(game.snapshot()["pieces"][r[4]][0]) for r in first)
    texts=[kw.get("text") for name,args,kw in cv.calls if name=="create_text"]
    assert all(r[4] not in texts for r in first)
    assert not sent


def test_exact_asymmetric_row_column_action_and_input_boundaries():
    game=BlokusGame([7,8],seed=1);cv,ui,sent=scene(game)
    ui["blok_pick"]="M"
    cu.handle_click(ui,ui["ox"]+.5*ui["cell"],ui["oy"]+19.5*ui["cell"])
    assert sent==[dict(op="place",piece="M",oi=0,x=19,y=0)]
    game.act(7,sent.pop());assert game.board[(19,0)]==7
    old=ui["state"];ui["state"]=dict(old)
    board.key(ui,"p");assert not sent
    ui["state"]=old;ui["connected"]=False
    board.key(ui,"p");assert not sent
    for uid in (8,99):
        _,other,events=scene(game,uid)
        if uid==99:
            assert not other["blok_chips"]
            board.key(other,"p");assert not events


def test_legacy_coordinate_form_and_duplicate_pass_are_removed():
    import client
    assert client._actions_for("blokus",None)==[]
