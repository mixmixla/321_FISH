from games_pkg.chengzhu import TERR_CN
from games_pkg.gongfang import GongfangGame
from games_pkg.siji import EFFECT_CN
from ui_design import RESOURCE_ICONS


def test_resource_drawings_match_the_game_labels():
    assert EFFECT_CN["apple"] == "金币"
    assert RESOURCE_ICONS["apple"] == RESOURCE_ICONS["g"]
    # A field has parallel furrows; a forest has a canopy above a single trunk.
    def horizontal_lines(key):
        return sum(op == "line" and len(points) == 2 and points[0][1] == points[1][1]
                   for op, points in RESOURCE_ICONS[key])
    assert TERR_CN["fd"] == "田" and horizontal_lines("fd") >= 2
    assert TERR_CN["fo"] == "林" and horizontal_lines("fo") == 0


def test_workshop_seat_order_and_points_match_its_visible_spots():
    game = GongfangGame([11, 22], seed=2)
    first, second = game.snapshot()["spots"][:2]
    assert all(not spot["exclusive"] for spot in game.snapshot()["spots"])
    game.act(11, {"op": "work", "id": second["id"]})
    game.act(22, {"op": "work", "id": first["id"]})
    assert game.score == {11: second["pts"], 22: first["pts"]}
    while game.round_no == 1:
        game.act(game.snapshot()["turn_uid"], {"op": "pass"})
    assert game.snapshot()["turn_uid"] == 22
