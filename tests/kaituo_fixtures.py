"""Synthetic settlement and score fixtures used only by Kaituo tests/probes."""
from games_pkg.kaituo import KaituoGame, RES_ORDER

SETUP = [((0,0),(0,1)), ((5,5),(5,4)), ((5,3),(4,3)), ((0,2),(0,3))]


def setup_game(players=(11,22)):
    game = KaituoGame(list(players),seed=1)
    for start,end in SETUP:
        game.act(game.snapshot()["turn_uid"], {"op":"setup","i":start[0],"j":start[1],"b_i":end[0],"b_j":end[1]})
    return game


def fund(game):
    game.res[game.players[0]] = dict.fromkeys(RES_ORDER, 12)
    game.turn = 0
    game.rolled = True
    game.robber_pending = False
    return game


def near_win(game):
    fund(game)
    owner, opponent = game.players
    game.board = {point:{"owner":owner,"city":True} for point in ((0,0),(0,2),(0,4),(2,0))}
    game.board[(2,2)] = {"owner":owner,"city":False}
    game.board[(5,5)] = {"owner":opponent,"city":False}
    game.roads = {}
    game.winner = None
    return game
