"""Shared, packable export of UX-01.tokens.json and code-native outline icons.

The token prefix is generated from the canonical JSON. Tk and Web consume this
module; tests bind the export back to that JSON, without a runtime file lookup.
"""
import copy
import json

# GENERATED_TOKEN_EXPORT
_TOKENS = json.loads('{\n  "version": 2,\n  "status": "runtime-export-chat-pilot",\n  "direction": "mist-shore",\n  "colors": {\n    "text": "#213336",\n    "text_secondary": "#5F706A",\n    "text_hint": "#667872",\n    "background": "#F2F5F4",\n    "surface": "#FFFFFF",\n    "border": "#E1E8E5",\n    "accent": "#16796C",\n    "accent_hover": "#11685C",\n    "accent_pressed": "#0C554B",\n    "selected_background": "#E5F3EE",\n    "focus": "#16796C",\n    "success": "#167144",\n    "success_background": "#EAF5ED",\n    "waiting": "#77551B",\n    "waiting_background": "#FAF3E2",\n    "error": "#B23B3B",\n    "error_background": "#FCECEC",\n    "disabled_text": "#68756F",\n    "disabled_background": "#EDF0EE",\n    "navigation": "#203D38",\n    "navigation_text": "#CCE0D7",\n    "on_accent": "#FFFFFF"\n  },\n  "spacing": [\n    4,\n    8,\n    12,\n    16,\n    24,\n    32\n  ],\n  "radius": {\n    "control": 7,\n    "panel": 12,\n    "message": 10\n  },\n  "font": {\n    "windows_families": [\n      "Microsoft YaHei UI",\n      "Segoe UI"\n    ],\n    "body_pt": 11,\n    "secondary_pt": 10,\n    "heading_pt": 18,\n    "web_body_px": 14,\n    "web_secondary_px": 12,\n    "line_height": 1.5\n  },\n  "icons": {\n    "size": 20,\n    "stroke": 1.7,\n    "style": "outline"\n  },\n  "opacity": {\n    "default": 1.0,\n    "optional_min": 0.85\n  },\n  "states": [\n    "default",\n    "hover",\n    "pressed",\n    "focus",\n    "selected",\n    "disabled",\n    "loading",\n    "offline",\n    "error",\n    "success",\n    "waiting"\n  ],\n  "implementation": "Canonical source exported to ui_design.py for Tk/Web chat. Other core pages and complete visual acceptance remain pending.",\n  "dark_colors": {\n    "text": "#E5EEE9",\n    "text_secondary": "#B2C3BA",\n    "text_hint": "#A6BBB0",\n    "background": "#15251F",\n    "surface": "#1E3028",\n    "border": "#395246",\n    "accent": "#86CDB3",\n    "accent_hover": "#9BDAC4",\n    "accent_pressed": "#65B296",\n    "selected_background": "#2C4B3C",\n    "focus": "#91DABB",\n    "success": "#8BD8AB",\n    "success_background": "#254632",\n    "waiting": "#E2C786",\n    "waiting_background": "#433922",\n    "error": "#EFA19F",\n    "error_background": "#4C2A2A",\n    "disabled_text": "#A9BBB0",\n    "disabled_background": "#2B3C33",\n    "navigation": "#101E18",\n    "navigation_text": "#CFE2D6",\n    "on_accent": "#15251F"\n  }\n}\n')


def design_tokens():
    return copy.deepcopy(_TOKENS)


def color(role, dark=False):
    return _TOKENS['dark_colors' if dark else 'colors'][role]


def body_font():
    return (_TOKENS['font']['windows_families'][0], _TOKENS['font']['body_pt'])


def mist_skin(reference, dark=False):
    sk = dict(reference)
    roles = {
        'window_bg':'background', 'panel_bg':'surface', 'list_bg':'surface',
        'fg':'text', 'sub':'text_secondary', 'icon_bg':'navigation',
        'accent':'accent', 'input_bg':'surface', 'titlebar_bg':'surface',
        'titlebar_fg':'text_secondary', 'titlebar_btn':'text_secondary',
        'titlebar_close':'error', 'hover_bg':'selected_background',
        'glass_border':'border', 'msg_bg':'background', 'sys':'text_secondary',
        'self':'text', 'priv':'text', 'normal':'text', 'hit':'waiting_background',
        'hit_active':'selected_background', 'bubble_in':'surface',
        'bubble_out':'selected_background', 'bubble_inline':'border',
        'bubble_outline':'border', 'mention':'accent', 'link':'accent',
        'mention_self':'accent', 'link_self':'accent', 'date':'text_secondary',
        'react_bg':'surface', 'react_fg':'text_secondary', 'react_own':'accent',
        'read':'text_secondary', 'unread':'error', 'sel_band':'selected_background',
        'sel_ring':'accent', 'pin_bg':'waiting_background', 'pin_fg':'waiting',
        'ann_bg':'selected_background', 'ann_fg':'accent',
        'voice_bg':'error_background', 'voice_fg':'error',
    }
    sk.update({key:color(role,dark) for key,role in roles.items()})
    sk.update(name='雾岸深色' if dark else '雾岸', family='flat', bubble_r=_TOKENS['radius']['message'],
              bubble_pad_h=14, bubble_pad_v=10, titlebar_h=32,
              traffic_lights=False, decorative_background=False)
    return sk


# Shape coordinates use the same 24-unit view box for SVG and native drawing.
ICONS = {
    'chat': [('rect',(3,4,18,13,2)),('line',[(6,17),(6,21),(11,17)])],
    'people':[('ellipse',(5,3,11,9)),('ellipse',(14,4,19,9)),('line',[(2,20),(2,16),(5,12),(11,12),(14,16),(14,20)]),('line',[(16,12),(20,14),(22,18)])],
    'sheet':[('rect',(4,3,16,18,2)),('line',[(4,9),(20,9)]),('line',[(4,15),(20,15)]),('line',[(10,9),(10,21)]),('line',[(15,9),(15,21)])],
    'game':[('line',[(5,7),(19,7),(22,18),(19,20),(15,16),(9,16),(5,20),(2,18),(5,7)]),('line',[(6,10),(6,14)]),('line',[(4,12),(8,12)]),('ellipse',(15,10,16.5,11.5)),('ellipse',(18,12,19.5,13.5))],
    'settings':[('ellipse',(8,8,16,16)),('line',[(12,2),(12,5)]),('line',[(12,19),(12,22)]),('line',[(2,12),(5,12)]),('line',[(19,12),(22,12)]),('line',[(5,5),(7,7)]),('line',[(17,17),(19,19)]),('line',[(5,19),(7,17)]),('line',[(17,7),(19,5)])],
    'moments':[('rect',(3,5,18,15,2)),('ellipse',(13,8,16,11)),('line',[(4,17),(9,12),(13,16),(16,14),(20,18)])],
    'emoji':[('ellipse',(3,3,21,21)),('ellipse',(8,8,9,9)),('ellipse',(15,8,16,9)),('line',[(7,14),(9,17),(15,17),(17,14)])],
    'attach':[('line',[(9,12),(16,5),(20,5),(21,9),(10,20),(5,20),(3,16),(4,12),(14,2)]),('line',[(8,15),(16,7)])],
    'mic':[('rect',(8,2,8,13,4)),('line',[(4,10),(4,14),(7,18),(17,18),(20,14),(20,10)]),('line',[(12,18),(12,22)]),('line',[(8,22),(16,22)])],
    'more':[('ellipse',(3,10,6,13)),('ellipse',(10,10,13,13)),('ellipse',(17,10,20,13))],
    'send':[('line',[(3,3),(22,12),(3,21),(7,12),(3,3)]),('line',[(7,12),(17,12)])],
    'search':[('ellipse',(3,3,16,16)),('line',[(14,14),(21,21)])],
    'image':[('rect',(3,3,18,18,2)),('ellipse',(14,6,17,9)),('line',[(4,18),(9,12),(14,17),(17,14),(20,18)])],
    'minimize':[('line',[(4,12),(20,12)])],
    'broadcast':[('line',[(4,9),(18,4),(18,19),(4,14),(4,9)]),('line',[(7,15),(9,21),(12,21),(11,16)]),('line',[(21,8),(21,15)])],
}


# Per-game outline geometry, keyed by the canonical GAME_TYPES name. Same
# 24-unit view box and shape tuples as ICONS, so the single source drives both
# the Tk rasteriser and the Web inline SVG. Purely additive: ICONS is untouched.
GAME_ICONS = {
    'guess_number':[('line',[(9,3),(9,21)]),('line',[(15,3),(15,21)]),('line',[(3,9),(21,9)]),('line',[(3,15),(21,15)])],
    'gomoku':[('rect',(3,3,18,18,2)),('line',[(9,3),(9,21)]),('line',[(15,3),(15,21)]),('line',[(3,9),(21,9)]),('line',[(3,15),(21,15)]),('ellipse',(4.5,4.5,9.5,9.5)),('ellipse',(14.5,14.5,19.5,19.5))],
    'rps':[('ellipse',(3,4,8,9)),('ellipse',(3,15,8,20)),('line',[(7,7),(21,20)]),('line',[(7,17),(21,4)])],
    'spy':[('line',[(3,10),(21,10)]),('line',[(8,10),(8,5),(16,5),(16,10)]),('ellipse',(5,13,11,19)),('ellipse',(13,13,19,19)),('line',[(11,16),(13,16)])],
    'uno':[('rect',(3,7,11,14,2)),('rect',(9,3,11,14,2)),('ellipse',(12,7,17,12))],
    'blackjack':[('rect',(4,3,12,18,2)),('ellipse',(8,7,12,11)),('ellipse',(8,13,12,17))],
    'drawguess':[('rect',(3,3,15,15,2)),('line',[(10,15),(21,4)]),('line',[(17,4),(21,4),(21,8)])],
    'connect4':[('rect',(3,4,18,17,2)),('line',[(9,4),(9,21)]),('line',[(15,4),(15,21)]),('line',[(3,10.5),(21,10.5)]),('ellipse',(4,5,8,9)),('ellipse',(10,11.5,14,15.5)),('ellipse',(16,11.5,20,15.5))],
    'othello':[('ellipse',(4,4,20,20)),('ellipse',(9,9,15,15))],
    'calc24':[('rect',(5,2,14,20,2)),('rect',(7,5,10,4,1)),('line',[(8,13),(10,13)]),('line',[(9,12),(9,14)]),('line',[(13,13),(15,13)]),('line',[(13,17),(15,17)]),('line',[(8,17),(10,17)])],
    'matchpairs':[('rect',(3,3,8,8,1)),('rect',(13,3,8,8,1)),('rect',(3,13,8,8,1)),('rect',(13,13,8,8,1))],
    'betrayal':[('line',[(3,11),(12,3),(21,11)]),('line',[(5,11),(5,21),(19,21),(19,11)]),('rect',(10,15,4,6,1))],
    'kaituo':[('line',[(12,3),(20,7),(20,17),(12,21),(4,17),(4,7),(12,3)]),('ellipse',(9.5,9.5,14.5,14.5))],
    'lingdi':[('line',[(6,3),(6,21)]),('line',[(6,4),(19,4),(16,8),(19,12),(6,12)])],
    'tielu':[('line',[(6,21),(9,3)]),('line',[(18,21),(15,3)]),('line',[(7.6,17),(16.4,17)]),('line',[(8.4,10),(15.6,10)])],
    'gongfang':[('rect',(4,3,16,6,1)),('line',[(12,9),(12,18)]),('rect',(9,18,6,3,1))],
    'chengzhu':[('line',[(4,21),(4,8),(8,8),(8,5),(12,5),(12,8),(16,8),(16,5),(20,5),(20,21),(4,21)])],
    'gemcity':[('line',[(7,4),(17,4),(21,10),(12,21),(3,10),(7,4)]),('line',[(3,10),(21,10)]),('line',[(7,4),(10,10)]),('line',[(17,4),(14,10)]),('line',[(10,10),(12,21)]),('line',[(14,10),(12,21)])],
    'siji':[('line',[(12,21),(12,11)]),('line',[(12,15),(6,10)]),('line',[(12,13),(18,8)]),('ellipse',(6,4,18,14))],
    'bolan':[('line',[(3,9),(7,6),(11,9),(15,6),(19,9)]),('line',[(3,15),(7,12),(11,15),(15,12),(19,15)])],
    'azul':[('rect',(3,3,8,8,1)),('rect',(13,3,8,8,1)),('rect',(3,13,8,8,1)),('ellipse',(13,13,21,21))],
    'rummikub':[('rect',(3,8,18,11,2)),('line',[(12,8),(12,19)]),('ellipse',(5.5,11,8.5,14)),('ellipse',(15.5,13,18.5,16))],
    'yahtzee':[('rect',(3,3,18,18,3)),('ellipse',(7,7,9,9)),('ellipse',(15,7,17,9)),('ellipse',(11,11,13,13)),('ellipse',(7,15,9,17)),('ellipse',(15,15,17,17))],
    'nimmt':[('line',[(4,2),(4,9)]),('line',[(20,2),(20,9)]),('ellipse',(6,8,18,20)),('ellipse',(9,12,11,14)),('ellipse',(13,12,15,14)),('line',[(9,17),(15,17)])],
    'davinci':[('rect',(4,10,16,10,2)),('line',[(8,10),(8,6),(12,3),(16,6),(16,10)])],
    'kalah':[('ellipse',(3,5,21,19)),('ellipse',(6,9,10,15)),('ellipse',(14,9,18,15)),('ellipse',(9.5,11,11.5,13))],
    'lovelove':[('line',[(12,20),(4,12)]),('line',[(12,20),(20,12)]),('ellipse',(3,4,12,13)),('ellipse',(12,4,21,13))],
    'halloween':[('ellipse',(3,8,21,21)),('line',[(12,8),(12,4),(16,3)]),('line',[(8,13),(10,15)]),('line',[(10,13),(8,15)]),('line',[(14,13),(16,15)]),('line',[(16,13),(14,15)]),('line',[(9,18),(15,18)])],
    'tictactoe':[('line',[(9,3),(9,21)]),('line',[(15,3),(15,21)]),('line',[(3,9),(21,9)]),('line',[(3,15),(21,15)]),('ellipse',(3.5,3.5,8.5,8.5)),('line',[(15.5,15.5),(20.5,20.5)]),('line',[(20.5,15.5),(15.5,20.5)])],
    'halma':[('line',[(12,2),(15,9),(21,10),(16,15),(18,21),(12,17),(6,21),(8,15),(3,10),(9,9),(12,2)])],
    'checkers':[('ellipse',(4,5,20,14)),('ellipse',(4,11,20,20))],
    'blokus':[('rect',(4,3,7,7,1)),('rect',(11,3,7,7,1)),('rect',(4,10,7,7,1))],
    'ludo':[('rect',(3,3,18,18,2)),('line',[(12,3),(12,21)]),('line',[(3,12),(21,12)]),('ellipse',(5,5,9,9)),('ellipse',(15,5,19,9)),('ellipse',(5,15,9,19)),('ellipse',(15,15,19,19))],
    'xiangqi':[('ellipse',(4,4,20,20)),('rect',(9,9,6,6,1))],
    'chess':[('ellipse',(9,3,15,9)),('line',[(7,20),(17,20)]),('line',[(9,20),(9,14)]),('line',[(15,20),(15,14)]),('line',[(9,14),(15,14)]),('line',[(10.5,9),(13.5,14)])],
    'go':[('rect',(3,3,18,18,2)),('line',[(9,3),(9,21)]),('line',[(15,3),(15,21)]),('line',[(3,9),(21,9)]),('line',[(3,15),(21,15)]),('ellipse',(4,10,8,14))],
    'shogi':[('line',[(12,3),(20,8),(20,19),(4,19),(4,8),(12,3)]),('line',[(9,15),(15,15)])],
    'junqi':[('line',[(6,3),(6,21)]),('line',[(6,4),(20,4),(20,13),(6,13),(6,4)]),('line',[(11,8.5),(15,8.5)])],
    'dou':[('rect',(6,3,11,14,2)),('rect',(3,7,11,14,2)),('ellipse',(7,11,9,13)),('ellipse',(12,11,14,13)),('ellipse',(6,16,8,18))],
    'onewolf':[('line',[(5,4),(8,9)]),('line',[(19,4),(16,9)]),('line',[(5,4),(12,6),(19,4)]),('line',[(8,9),(9,15),(12,19),(15,15),(16,9)]),('line',[(9,15),(12,12),(15,15)]),('ellipse',(10,10,11,11)),('ellipse',(13,10,14,11))],
    'werewolf':[('line',[(4,6),(4,17)]),('ellipse',(4,4,20,18)),('ellipse',(14,6,19,11)),('line',[(6,4),(9,8)]),('line',[(16,4),(13,8)])],
    'avalon':[('line',[(12,3),(20,6),(20,12),(12,21),(4,12),(4,6),(12,3)]),('line',[(12,7),(12,17)]),('line',[(8,11),(16,11)])],
    'liar':[('line',[(3,9),(8,5),(16,5),(21,9),(21,13),(16,17),(8,17),(3,13),(3,9)]),('ellipse',(7,9,10,12)),('ellipse',(14,9,17,12)),('line',[(9,15),(15,15)])],
    'ninja':[('line',[(12,2),(14,10),(22,12),(14,14),(12,22),(10,14),(2,12),(10,10),(12,2)])],
    'coc':[('line',[(2,12),(6,8),(18,8),(22,12),(18,16),(6,16),(2,12)]),('ellipse',(9,9,15,15)),('ellipse',(11,11,13,13)),('line',[(9,16),(7,21)]),('line',[(15,16),(17,21)])],
    'balatro':[('rect',(4,3,13,18,2)),('line',[(10.5,8),(10.5,17)]),('ellipse',(7,8,10,11)),('ellipse',(7,13.5,10,16.5)),('ellipse',(14,8,17,11)),('ellipse',(14,13.5,17,16.5))],
    'balatro_solo':[('rect',(3,4,13,18,2)),('ellipse',(7,8,10,11)),('ellipse',(7,14,10,17)),('line',[(12.5,8),(12.5,17)]),('ellipse',(17,3,22,8))],
}
# Neutral dice fallback for unknown game keys, matching the 24-unit box.
GAME_ICON_FALLBACK=ICONS['game']


def _outline_svg(shapes, size=20):
    rendered=[]
    for kind, values in shapes:
        if kind == 'line':
            points=' '.join(f'{x},{y}' for x,y in values)
            rendered.append(f'<polyline points="{points}"/>')
        elif kind == 'rect':
            x,y,w,h,r=values
            rendered.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/>')
        elif kind == 'ellipse':
            x1,y1,x2,y2=values
            rendered.append(f'<ellipse cx="{(x1+x2)/2}" cy="{(y1+y2)/2}" rx="{(x2-x1)/2}" ry="{(y2-y1)/2}"/>')
    return (f'<svg aria-hidden="true" class="ux-icon" width="{int(size)}" height="{int(size)}" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{_TOKENS["icons"]["stroke"]}" '
            'stroke-linecap="round" stroke-linejoin="round">'+''.join(rendered)+'</svg>')


def icon_svg(name, size=20):
    return _outline_svg(ICONS[name], size)


def game_icon_svg(name, size=20):
    return _outline_svg(GAME_ICONS.get(name, GAME_ICON_FALLBACK), size)


# Role / identity geometry for the hidden-role games (werewolf, onewolf,
# avalon, spy, liar, coc). Keys are semantic role ids, not per-game indexes, so
# all six games share one set. Same 24-unit view box as ICONS/GAME_ICONS.
ROLE_ICONS = {
    'villager':[('ellipse',(8,3,16,11)),('line',[(4,21),(4,17),(6,13),(18,13),(20,17),(20,21)])],
    'civilian':[('ellipse',(3,3,21,21)),('line',[(8,12),(11,15),(16,9)])],
    'werewolf':[('line',[(4,6),(7,3),(10,6)]),('line',[(14,6),(17,3),(20,6)]),('line',[(4,6),(4,12),(12,20),(20,12),(20,6)]),('line',[(8,11),(10,13)]),('line',[(10,11),(8,13)]),('line',[(14,11),(16,13)]),('line',[(16,11),(14,13)]),('line',[(10,17),(14,17)])],
    'seer':[('ellipse',(4,4,20,16)),('line',[(4,11),(20,11)]),('line',[(9,16),(7,21),(17,21),(15,16)])],
    'witch':[('line',[(9,3),(15,3)]),('line',[(10,3),(10,9)]),('line',[(14,3),(14,9)]),('line',[(10,9),(6,17),(18,17),(14,9)]),('line',[(6,17),(18,20),(6,20),(6,17)])],
    'hunter':[('line',[(6,3),(6,21)]),('line',[(6,3),(18,7),(18,17),(6,21)]),('line',[(6,12),(21,12)]),('line',[(18,9),(21,12),(18,15)])],
    'robber':[('line',[(4,10),(20,10)]),('line',[(8,10),(8,4),(16,4),(16,10)]),('line',[(4,10),(4,14),(12,20),(20,14),(20,10)])],
    'insomniac':[('line',[(14,3),(7,6),(4,12),(6,18),(12,21),(18,19),(20,13)]),('line',[(16,4),(21,4),(16,9),(21,9)]),('line',[(17,12),(21,12),(17,16),(21,16)])],
    'loyal':[('line',[(12,3),(19,6),(19,12),(12,21),(5,12),(5,6),(12,3)])],
    'merlin':[('line',[(12,2),(18,14),(6,14),(12,2)]),('line',[(3,14),(21,14)]),('line',[(5,20),(19,20)]),('line',[(9,20),(9,14)]),('line',[(15,20),(15,14)])],
    'assassin':[('line',[(12,2),(14,6),(14,13),(12,16),(10,13),(10,6),(12,2)]),('line',[(8,13),(16,13)]),('line',[(12,16),(12,20)]),('line',[(9,20),(15,20)])],
    'mordred':[('ellipse',(4,4,20,16)),('ellipse',(8,8,10,10)),('ellipse',(14,8,16,10)),('line',[(11,12),(13,12)]),('line',[(8,16),(8,20)]),('line',[(12,16),(12,20)]),('line',[(16,16),(16,20)])],
    'spy':[('line',[(3,10),(21,10)]),('line',[(8,10),(8,5),(16,5),(16,10)]),('ellipse',(5,13,11,18)),('ellipse',(13,13,19,18)),('line',[(11,15.5),(13,15.5)])],
    'detective':[('ellipse',(4,4,17,17)),('line',[(15,15),(21,21)]),('line',[(8,9),(11,11)]),('line',[(11,9),(8,11)])],
    'investigator':[('ellipse',(4,4,17,17)),('line',[(15,15),(21,21)]),('line',[(7,10.5),(14,10.5)]),('line',[(10.5,7),(10.5,14)])],
    'doctor':[('rect',(3,4,18,16,3)),('line',[(12,8),(12,16)]),('line',[(8,12),(16,12)])],
    'reporter':[('rect',(3,5,18,15,2)),('line',[(6,9),(15,9)]),('line',[(6,12),(15,12)]),('line',[(6,15),(12,15)])],
    'naturalist':[('line',[(12,4),(12,20)]),('line',[(12,8),(4,4),(4,12),(12,15)]),('line',[(12,8),(20,4),(20,12),(12,15)]),('line',[(12,16),(7,21)]),('line',[(12,16),(17,21)])],
    'occultist':[('line',[(12,3),(20,8),(20,16),(12,21),(4,16),(4,8),(12,3)]),('line',[(12,8),(12,16)]),('line',[(8,10),(16,14)]),('line',[(16,10),(8,14)])],
    'archaeologist':[('line',[(8,3),(16,3)]),('line',[(12,3),(12,13)]),('line',[(8,13),(16,13)]),('line',[(8,13),(6,18),(12,21),(18,18),(16,13)])],
    'liar':[('line',[(2,10),(6,6),(18,6),(22,10),(18,16),(6,16),(2,10)]),('ellipse',(7,9,10,12)),('ellipse',(14,9,17,12)),('line',[(9,15),(15,15)])],
    'traitor':[('line',[(12,3),(19,6),(19,11),(14,13),(14,8)]),('line',[(12,3),(5,6),(5,11),(10,13),(10,8)])],
    'guard':[('line',[(12,3),(19,6),(19,12),(12,21),(5,12),(5,6),(12,3)]),('line',[(9,11),(15,11)]),('line',[(12,8),(12,15)])],
    'knight':[('line',[(5,20),(5,11),(8,5),(16,5),(19,11),(19,20),(15,20),(15,15),(9,15),(9,20),(5,20)])],
    'minion':[('line',[(4,9),(4,3),(8,7)]),('line',[(20,9),(20,3),(16,7)]),('ellipse',(5,8,19,20)),('ellipse',(8,12,10,14)),('ellipse',(14,12,16,14)),('line',[(9,17),(15,17)])],
    'cultist':[('line',[(12,3),(4,20),(20,20),(12,3)]),('ellipse',(9,10,15,16)),('ellipse',(10.5,12,11.5,13)),('ellipse',(13.5,12,14.5,13))],
}
ROLE_ICON_FALLBACK=ROLE_ICONS['villager']


# Resource / token geometry for the economy games (kaituo, chengzhu, gemcity,
# siji). Terrain keys (fd/fo/mo/wa/gr) and token keys (o/d/r/e/s/g) mirror the
# client-side label maps so the single source stays in sync with each game.
RESOURCE_ICONS = {
    'wood':[('ellipse',(4,8,20,16)),('ellipse',(8,10,16,14))],
    'brick':[('rect',(3,6,18,12,1)),('line',[(3,12),(21,12)]),('line',[(9,6),(9,12)]),('line',[(6,12),(6,18)]),('line',[(14,12),(14,18)])],
    'lamb':[('ellipse',(4,7,18,19)),('ellipse',(15,6,21,12)),('line',[(5,19),(5,21)]),('line',[(9,19),(9,21)]),('line',[(13,19),(13,21)])],
    'wheat':[('line',[(12,21),(12,6)]),('line',[(12,9),(8,6)]),('line',[(12,9),(16,6)]),('line',[(12,13),(8,10)]),('line',[(12,13),(16,10)]),('line',[(12,17),(8,14)]),('line',[(12,17),(16,14)])],
    'ore':[('line',[(4,19),(7,9),(12,5),(18,10),(20,19),(4,19)]),('ellipse',(10,12,14,16))],
    'fd':[('line',[(8,21),(8,14)]),('line',[(8,3),(3,14),(13,14),(8,3)])],
    'fo':[('line',[(3,17),(21,17)]),('line',[(3,21),(21,21)]),('line',[(4,17),(3,21)]),('line',[(10,17),(9,21)]),('line',[(16,17),(15,21)]),('line',[(20,17),(21,21)])],
    'mo':[('line',[(2,20),(9,8),(13,14),(16,9),(22,20),(2,20)])],
    'wa':[('line',[(3,10),(7,7),(11,10),(15,7),(19,10)]),('line',[(3,16),(7,13),(11,16),(15,13),(19,16)])],
    'gr':[('line',[(6,21),(6,12)]),('line',[(6,14),(3,10)]),('line',[(6,14),(9,10)]),('line',[(12,21),(12,9)]),('line',[(12,12),(9,8)]),('line',[(12,12),(15,8)]),('line',[(18,21),(18,12)]),('line',[(18,14),(15,10)]),('line',[(18,14),(21,10)])],
    'crown':[('line',[(3,18),(3,8),(8,13),(12,6),(16,13),(21,8),(21,18),(3,18)])],
    'o':[('line',[(12,3),(20,8),(20,16),(12,21),(4,16),(4,8),(12,3)]),('ellipse',(9,9,15,15))],
    'd':[('line',[(12,4),(20,12),(12,20),(4,12),(12,4)]),('line',[(4,12),(20,12)]),('line',[(12,4),(12,20)])],
    'r':[('line',[(7,4),(17,4),(21,10),(12,21),(3,10),(7,4)]),('line',[(3,10),(21,10)])],
    'e':[('rect',(5,5,14,14,3)),('line',[(5,12),(19,12)]),('line',[(12,5),(12,19)])],
    's':[('ellipse',(4,6,20,18)),('line',[(4,12),(20,12)])],
    'g':[('ellipse',(4,4,20,20)),('ellipse',(9,9,15,15))],
    'crystal':[('line',[(12,3),(19,9),(12,21),(5,9),(12,3)]),('line',[(5,9),(19,9)])],
    'apple':[('ellipse',(4,8,20,21)),('line',[(12,8),(12,4)]),('line',[(12,4),(15,3)])],
    'vt':[('line',[(12,3),(15,9),(21,9),(16,13),(18,20),(12,16),(6,20),(8,13),(3,9),(9,9),(12,3)])],
}
RESOURCE_ICON_FALLBACK=RESOURCE_ICONS['ore']


def role_icon_svg(name, size=20):
    return _outline_svg(ROLE_ICONS.get(name, ROLE_ICON_FALLBACK), size)


def resource_icon_svg(name, size=20):
    return _outline_svg(RESOURCE_ICONS.get(name, RESOURCE_ICON_FALLBACK), size)


def web_variables():
    mapping={'bg':'background','card':'surface','line':'border','txt':'text',
             'dim':'text_secondary','accent':'accent','self':'selected_background',
             'bub-in':'surface','side':'surface','coral':'accent','mint':'accent',
             'focus':'focus','error':'error','waiting':'waiting','success':'success',
             'nav':'navigation','nav-txt':'navigation_text','selected':'selected_background',
             'on-accent':'on_accent'}
    rules=[]
    for mode,dark in [('mist',False),('mist-dark',True)]:
        values=';'.join('--'+k+':'+color(v,dark) for k,v in mapping.items())
        values+=';'+';'.join('--ux-'+role.replace('_','-')+':'+value for role,value in _TOKENS['dark_colors' if dark else 'colors'].items())
        values+=';'+';'.join('--space-'+str(value)+':'+str(value)+'px' for value in _TOKENS['spacing'])
        fonts=_TOKENS['font']
        radii=_TOKENS['radius']
        values+=f';--body-font:{fonts["web_body_px"]}px;--secondary-font:{fonts["web_secondary_px"]}px'
        values+=';--font-family:'+','.join(json.dumps(family) for family in fonts['windows_families'])+',sans-serif'
        values+=f';--r1:{radii["control"]}px;--r2:{radii["panel"]}px;--r3:{radii["message"]}px'
        rules.append(':root[data-theme="'+mode+'"]{'+values+';--blur:none;--shadow-sm:none;--shadow-md:none;--shadow-lg:0 8px 28px #203d381a}')
    return '\n'.join(rules)


def web_chat_css():
    return web_variables() + r'''
:root[data-theme^="mist"] body{background:var(--bg);background-image:none;font-family:var(--font-family);font-size:var(--body-font)}
:root[data-theme^="mist"] button{background:var(--accent);color:var(--on-accent);box-shadow:none;border-radius:var(--r1);font-weight:600}
:root[data-theme^="mist"] button:active{background:var(--ux-accent-pressed)}
:root[data-theme^="mist"] button:disabled{background:var(--ux-disabled-background);color:var(--ux-disabled-text);cursor:not-allowed;box-shadow:none}
:root[data-theme^="mist"] button.ghost{background:var(--card);color:var(--txt);border:1px solid var(--line)}
.ux-icon{display:inline-block;vertical-align:middle;flex-shrink:0;pointer-events:none}
.ux-send-hint{display:none}
button .ux-icon{margin-right:5px}
button:focus-visible,summary:focus-visible,[role=button]:focus-visible,select:focus-visible{outline:2px solid var(--focus,var(--accent));outline-offset:3px}
#uxRail{display:none}
:root[data-theme^="mist"] #uxRail{width:76px;flex-shrink:0;background:var(--nav);color:var(--nav-txt);display:flex;flex-direction:column;align-items:center;gap:12px;padding:20px 8px}
#uxRail .brand{font-size:24px;letter-spacing:-2px;font-weight:750;margin-bottom:18px;color:var(--nav-txt)}
#uxRail button{display:flex;flex-direction:column;gap:7px;align-items:center;justify-content:center;width:60px;min-height:60px;padding:7px 3px;background:transparent;color:var(--nav-txt);font-size:12px;font-weight:400}
#uxRail button.on{background:var(--accent);color:var(--on-accent)}
#uxRail button:hover{background:var(--selected);color:var(--txt)}
#uxRail button .ux-icon{margin:0}
:root[data-theme^="mist"] #side{width:250px;background:var(--card);border-right:1px solid var(--line);backdrop-filter:none;box-shadow:none;padding:12px}
:root[data-theme^="mist"] #side h2{font-size:12px;color:var(--dim);font-weight:600;padding:10px 6px;margin-top:8px;letter-spacing:.02em}
:root[data-theme^="mist"] #side h2:first-child{margin-top:0}
:root[data-theme^="mist"] .item{border:0;border-radius:8px;box-shadow:none;background:transparent;padding:12px 10px;color:var(--txt);margin-bottom:4px}
:root[data-theme^="mist"] .item.on{background:var(--selected);color:var(--txt);border:0;box-shadow:none}
:root[data-theme^="mist"] #side .item.on{background:var(--selected);color:var(--txt);border:0;box-shadow:none}
:root[data-theme^="mist"] #side h2::after{display:none;background:none}
:root[data-theme^="mist"] .item:hover{background:var(--selected);transform:none}
:root[data-theme^="mist"] #head{background:var(--card);border-bottom:1px solid var(--line);border-radius:0;box-shadow:none;backdrop-filter:none;min-height:66px;padding:12px 20px}
:root[data-theme^="mist"] #headTitle{font-size:18px;font-weight:700;color:var(--txt)}
:root[data-theme^="mist"] #headSub{color:var(--dim)}
:root[data-theme^="mist"] #chat{background:var(--bg)}
:root[data-theme^="mist"] #msgs{padding:var(--space-24);background:var(--chat-bg,var(--bg))}
:root[data-theme^="mist"] .msg{margin-bottom:var(--space-16)}
:root[data-theme^="mist"] .msg .bub{border:1px solid var(--line);border-radius:var(--r3);box-shadow:none;padding:var(--space-12) 14px}
:root[data-theme^="mist"]:not([data-chat]) .msg .bub{background:var(--bub-in);color:var(--txt)}
:root[data-theme^="mist"]:not([data-chat]) .msg.self .bub{background:var(--bub-self,var(--self));color:var(--txt);box-shadow:none;border-color:var(--line)}
:root[data-theme^="mist"] .msg .meta{color:var(--dim)}
:root[data-theme^="mist"] .daysep span{background:transparent;color:var(--dim);border:0;box-shadow:none}
:root[data-theme^="mist"] #input{display:grid;grid-template-columns:auto auto auto 1fr auto;gap:8px;background:var(--card);border-top:1px solid var(--line);border-radius:0;padding:12px 18px;box-shadow:none;backdrop-filter:none}
:root[data-theme^="mist"] #input textarea{grid-column:1/-1;grid-row:2;min-height:80px;max-height:200px;margin:0;padding:var(--space-12);background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:var(--r1);font-family:inherit;font-size:var(--body-font);box-shadow:none;resize:vertical}
:root[data-theme^="mist"] #input textarea:focus{border-color:var(--accent);outline:2px solid var(--selected)}
:root[data-theme^="mist"] textarea:disabled,:root[data-theme^="mist"] textarea[readonly],:root[data-theme^="mist"] select:disabled{background:var(--ux-disabled-background);color:var(--ux-disabled-text);opacity:1}
:root[data-theme^="mist"] textarea:disabled,:root[data-theme^="mist"] select:disabled{cursor:not-allowed}
:root[data-theme^="mist"] textarea[readonly]{cursor:text}
:root[data-theme^="mist"] #input button{min-height:36px;padding:7px 10px}
:root[data-theme^="mist"] #input #btnImg,:root[data-theme^="mist"] #input #btnFile{background:var(--card);color:var(--dim);box-shadow:none;min-width:68px}
:root[data-theme^="mist"] #input .compose-tools{grid-column:3;background:var(--card);color:var(--dim)}
:root[data-theme^="mist"] #input .compose-tools summary{min-height:36px;padding:8px;border-radius:7px;cursor:pointer}
:root[data-theme^="mist"] #input #btnSend{grid-row:3;grid-column:5;min-width:88px}
:root[data-theme^="mist"] #input .ux-send-hint{display:block;grid-row:3;grid-column:1/5;color:var(--dim);align-self:center;font-size:var(--secondary-font)}
:root[data-theme^="mist"] #input .toolmenu{background:var(--card);border-color:var(--line);color:var(--txt)}
:root[data-theme^="mist"] #input .toolmenu button{background:var(--card);color:var(--txt)}
:root[data-theme^="mist"] #input .toolmenu button:hover{background:var(--selected)}
:root[data-theme^="mist"] #jumpBottom{background:var(--card);color:var(--accent);border:1px solid var(--line);box-shadow:none}
@media(max-width:900px){:root[data-theme^="mist"] #uxRail{width:60px;padding:14px 4px}:root[data-theme^="mist"] #uxRail button{width:50px}:root[data-theme^="mist"] #side{width:220px}}
@media(max-width:680px){:root[data-theme^="mist"] #uxRail{display:none}:root[data-theme^="mist"] #side{width:min(84vw,300px)}:root[data-theme^="mist"] #msgs{padding:12px}:root[data-theme^="mist"] #head{padding:10px 12px;min-height:58px}:root[data-theme^="mist"] #input{padding:10px}:root[data-theme^="mist"] #input .ux-send-hint{font-size:11px}}
'''
