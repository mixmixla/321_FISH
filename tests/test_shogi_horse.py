import pytest

from games_pkg.shogi import B, K, PROM_B, R, SYM, ShogiGame, piece_type


@pytest.mark.parametrize("side", [0, 1])
def test_promoted_bishop_has_a_horse_face_and_can_step_sideways(side):
    game = ShogiGame([11, 22])
    game.board = [[0] * 9 for _ in range(9)]
    game.board[8][8], game.board[0][8] = K, K + 10
    game.kpos = {0: (8, 8), 1: (8, 0)}
    game.turn = side
    uid, opponent = game.players[side], game.players[1 - side]
    start, end = (3, 2) if side == 0 else (5, 6)
    game.board[start][2] = B + 10 * side
    game.board[end][0] = R + 10 * (1 - side)
    game.act(uid, {"fx": 2, "fy": start, "tx": 3, "ty": end})
    piece = game.board[end][3]
    assert piece == PROM_B + 10 * side
    assert SYM[piece_type(piece)] == "馬"
    ky = game.kpos[1 - side][1]
    game.act(opponent, {"fx": 8, "fy": ky, "tx": 7, "ty": ky})
    game.act(uid, {"fx": 3, "fy": end, "tx": 4, "ty": end})
    assert game.board[end][4] == piece
    game.act(opponent, {"fx": 0, "fy": end, "tx": 4, "ty": end})
    assert game.hand[1 - side] == [B]
