"""Gem table confirmation, colour identity and real transaction contracts."""
import copy

import pytest

import client_gameui as cu
from boardgames import card_table_tk as table
from test_card_table_tk import Canvas, _room, _ui, _paint, _click, _nav, _command


def _focused(room, ui, private=None, index=0):
    _paint(room, ui, private if private is not None else room.gs.private(7))
    _click(ui, ui['gc_cards'][index])
    _paint(room, ui, private if private is not None else room.gs.private(7))


@pytest.mark.parametrize('width,height', [(480, 400), (472, 365), (1000, 650), (900, 540)])
def test_portrait_market_has_three_tiers_bank_and_nobles_without_overlap(width, height):
    _, room = _room('gemcity')
    ui, _ = _ui(room)
    _paint(room, ui, room.gs.private(7), width, height)
    assert [r[4] for r in ui['gc_cards']] == [3]*4 + [2]*4 + [1]*4
    assert len(ui['gc_bank']) == 5 and not ui['gc_reserve']
    for x0, y0, x1, y1, *_ in ui['gc_cards']:
        assert 0 <= x0 < x1 <= width and 57 <= y0 < y1 <= height-83
        assert .70 < (x1-x0)/(y1-y0) < .74
    assert max(r[2] for r in ui['gc_cards']) < min(r[0] for r in ui['gc_bank'])
    assert _nav(ui, 'nobles')


def test_only_new_art_set_and_matching_colour_row_can_show_a_painting(monkeypatch):
    asked = []
    monkeypatch.setattr(table, 'art', lambda cv, filename, index, *a, **kw: asked.append((filename, index)) or True)
    for tier in (1, 2, 3):
        for i in range(20):
            card = {'tier':tier, 'art_set':'jewel-v2', 'art':i,
                    'disc':table.COLORS[i//4], 'title':f'本色画作{i}', 'pts':tier, 'cost':{'d':2}}
            table._development(Canvas(), card, (0, 0, 90, 125))
            assert asked[-1] == (f'gemcity-tier{tier}.webp', i)
    assert len(asked) == 60
    for metadata in ({}, {'art_set':'old'}, {'art_set':'jewel-v2', 'art':False},
                     {'art_set':'jewel-v2', 'art':4}):
        card = {'tier':1, 'art':0, 'title':'黄晶矿场', 'disc':'o', 'pts':0,
                'cost':{'r':2}, **metadata}
        cv = Canvas()
        table._development(cv, card, (0, 0, 90, 125))
        assert len(asked) == 60
        assert table._gc_name(card) == '黑玛瑙·1级发展卡'
        labels = [kw.get('text') for name, _, kw in cv.calls if name == 'create_text']
        assert '黄晶矿场' not in labels


def test_selection_never_buys_and_old_confirmation_cannot_buy_replaced_card():
    _, room = _room('gemcity')
    ui, sent = _ui(room)
    ui['state']['tokens']['7'] = {**dict.fromkeys(table.COLORS, 8), 'g':2}
    _focused(room, ui)
    assert not sent
    command = _command(ui, 'buy')
    newer = copy.deepcopy(ui['state'])
    newer['market']['3'][0]['title'] = 'a different rule card'
    ui['state'] = newer
    _click(ui, command)
    assert not sent


@pytest.mark.parametrize('change', ['turn', 'funds', 'membership', 'winner', 'connected'])
def test_confirmation_rechecks_current_turn_funds_and_membership(change):
    _, room = _room('gemcity')
    ui, sent = _ui(room)
    ui['state'] = copy.deepcopy(ui['state'])
    ui['state']['tokens']['7'] = {**dict.fromkeys(table.COLORS, 8), 'g':2}
    _focused(room, ui)
    command = _command(ui, 'buy')
    if change == 'turn': ui['state']['turn_uid'] = 8
    elif change == 'funds': ui['state']['tokens']['7'] = dict.fromkeys((*table.COLORS, 'g'), 0)
    elif change == 'membership': ui['room']['players'] = [8]
    elif change == 'winner': ui['state']['winner_uid'] = 8
    else: ui['connected'] = False
    _click(ui, command)
    assert not sent


def test_bank_requires_confirmation_and_real_take_keeps_supply_balanced():
    _, room = _room('gemcity')
    ui, sent = _ui(room)
    game = room.gs
    initial = copy.deepcopy(game.bank)
    for color in ('o', 'd', 'r'):
        _paint(room, ui, game.private(7))
        _click(ui, next(r for r in ui['gc_bank'] if r[-1] == color))
    assert not sent and ui['gc_sel'] == ['o', 'd', 'r']
    _paint(room, ui, game.private(7))
    _click(ui, ui['gc_take'])
    assert sent == [{'op':'take', 'colors':['o','d','r']}]
    game.act(7, sent[0])
    for color in (*table.COLORS, 'g'):
        assert game.bank[color] + sum(t[color] for t in game.tokens.values()) == initial[color]


def test_reserve_limit_and_read_only_waiting_card_art():
    _, room = _room('gemcity')
    ui, sent = _ui(room)
    private = {'reserved':[copy.deepcopy(room.gs.market[1][0]) for _ in range(3)]}
    _focused(room, ui, private)
    assert not any(isinstance(r[-1], tuple) and r[-1][:2] == ('command','reserve') for r in ui['gc_navigation'])
    ui['state'] = {**ui['state'], 'turn_uid':8}
    _paint(room, ui, private)
    _click(ui, _command(ui, 'detail'))
    _paint(room, ui, private)
    assert ui['gc_detail'] is not None and not sent
    assert not any(isinstance(r[-1], tuple) and r[-1][:2] == ('command','buy') for r in ui['gc_navigation'])


def test_confirmed_blue_card_purchase_pays_real_gems_and_gold_and_grants_blue():
    _, room = _room('gemcity')
    game = room.gs
    card = {'tier':1, 'art_set':'jewel-v2', 'art':16, 'disc':'s', 'pts':1,
            'title':'钴蓝矿井', 'cost':{'o':1, 'd':1, 'r':0, 'e':0, 's':0}}
    game.market[1][0] = card
    totals = copy.deepcopy(game.bank)
    for color in ('o', 'g'):
        game.tokens[7][color] = 1
        game.bank[color] -= 1
    ui, sent = _ui(room)
    _focused(room, ui, index=8)
    assert not sent
    _click(ui, _command(ui, 'buy'))
    assert sent == [{'op':'buy', 'tier':1, 'idx':0}]
    game.act(7, sent[0])
    assert game.discount[7] == {'o':0, 'd':0, 'r':0, 'e':0, 's':1}
    assert game.score[7] == 1 and game.private(7)['collection'] == [card]
    assert game.tokens[7]['o'] == game.tokens[7]['g'] == 0
    for color in (*table.COLORS, 'g'):
        assert game.bank[color] + sum(t[color] for t in game.tokens.values()) == totals[color]


def test_real_deck_counts_follow_only_the_market_tier_that_refills():
    _, room = _room('gemcity')
    ui, sent = _ui(room)
    cv = _paint(room, ui, room.gs.private(7))
    labels = [kw.get('text') for name, _, kw in cv.calls if name == 'create_text']
    assert room.gs.snapshot()['deck_left'] == {'1':16, '2':16, '3':16}
    assert labels.count('16') == 3
    _focused(room, ui)
    _click(ui, _command(ui, 'reserve'))
    room.gs.act(7, sent[0])
    ui['state'] = copy.deepcopy(room.gs.snapshot())
    cv = _paint(room, ui, room.gs.private(7))
    labels = [kw.get('text') for name, _, kw in cv.calls if name == 'create_text']
    assert room.gs.snapshot()['deck_left'] == {'1':16, '2':16, '3':15}
    assert labels.count('16') == 2 and labels.count('15') == 1


def test_jewel_source_keeps_alpha_and_only_gold_is_wild():
    table._gc_jewel_source.cache_clear()
    for color in (*table.COLORS, 'g'):
        image = table._gc_jewel_source(color)
        assert image.mode == 'RGBA' and image.size == (128, 128)
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((64, 64))[3] > 240
    assert 'g' not in table.COLORS
