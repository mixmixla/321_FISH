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


def icon_svg(name, size=20):
    shapes=[]
    for kind, values in ICONS[name]:
        if kind == 'line':
            points=' '.join(f'{x},{y}' for x,y in values)
            shapes.append(f'<polyline points="{points}"/>')
        elif kind == 'rect':
            x,y,w,h,r=values
            shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/>')
        elif kind == 'ellipse':
            x1,y1,x2,y2=values
            shapes.append(f'<ellipse cx="{(x1+x2)/2}" cy="{(y1+y2)/2}" rx="{(x2-x1)/2}" ry="{(y2-y1)/2}"/>')
    return (f'<svg aria-hidden="true" class="ux-icon" width="{int(size)}" height="{int(size)}" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{_TOKENS["icons"]["stroke"]}" '
            'stroke-linecap="round" stroke-linejoin="round">'+''.join(shapes)+'</svg>')


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
