"""Canonical export, readable semantic states and accessible native controls."""
import json
from pathlib import Path
import tkinter as tk

import pytest
from ui_design import color, design_tokens, icon_svg
from widgets.design_controls import IconButton
import theme


def contrast(a,b):
    def light(value):
        parts=[int(value[n:n+2],16)/255 for n in (1,3,5)]
        lin=lambda c:c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
        return sum(lin(c)*w for c,w in zip(parts,(0.2126,0.7152,0.0722)))
    a,b=sorted((light(a),light(b)))
    return (b+0.05)/(a+0.05)


def test_runtime_export_is_the_canonical_json():
    # The gate copies runtime sources, not docs. This fixed digest binds the
    # packed export to the separately checked canonical document bytes.
    import hashlib
    exported=(json.dumps(design_tokens(),ensure_ascii=False,indent=2)+'\n').encode()
    assert hashlib.sha256(exported).hexdigest()=='a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078'


@pytest.mark.parametrize('dark',[False,True])
def test_text_status_and_primary_controls_have_readable_contrast(dark):
    for foreground,background in [('text','surface'),('text_secondary','background'),
                                  ('text','selected_background'),('on_accent','accent'),
                                  ('waiting','waiting_background'),('error','error_background'),
                                  ('success','success_background'),('navigation_text','navigation')]:
        assert contrast(color(foreground,dark),color(background,dark))>=4.5,(foreground,background,dark)


def test_skin_copy_and_outline_icon_do_not_use_platform_emoji():
    sk=theme.get_skin('mist')
    assert sk['window_bg']==color('background')
    assert sk['decorative_background'] is False
    assert theme.msg_colors(sk)['decorative_background'] is False
    assert theme.DEFAULT_SKIN=='mist'
    svg=icon_svg('attach')
    assert 'viewBox="0 0 24 24"' in svg and 'aria-hidden="true"' in svg
    assert 'polyline' in svg


def test_named_native_button_keeps_keyboard_and_disabled_semantics():
    root=tk.Tk()
    calls=[]
    button=IconButton(root,icon='send',text='发送',command=lambda:calls.append(1),palette=theme.get_skin('mist'),role='primary')
    button.pack()
    root.update_idletasks()
    try:
        assert button.cget('takefocus') in (True,'1',1)
        assert button.cget('text')=='发送' and str(button.cget('image'))
        button._keyboard(None)
        assert calls==[1]
        button['state']='disabled'
        button._keyboard(None)
        assert calls==[1]
        button.set_palette(theme.get_skin('mist_dark'))
        assert button.cget('fg')==color('on_accent',True)
        assert button.cget('disabledforeground')==color('disabled_text',True)
        button.set_palette(theme.get_skin('apple_dark'))
        assert button.cget('disabledforeground')==theme.get_skin('apple_dark')['sub']
    finally:
        root.destroy()


def test_web_export_includes_complete_states_fonts_and_radii():
    from ui_design import web_variables,web_chat_css
    tokens=design_tokens()
    variables=web_variables()
    for role,value in tokens['colors'].items():
        assert '--ux-'+role.replace('_','-')+':'+value in variables
    assert '--r3:'+str(tokens['radius']['message'])+'px' in variables
    assert '--body-font:'+str(tokens['font']['web_body_px'])+'px' in variables
    css=web_chat_css()
    assert 'button:disabled' in css and '--ux-disabled-text' in css
