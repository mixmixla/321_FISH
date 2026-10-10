"""Native accessible buttons using the shared outline icon geometry."""
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
from ui_design import ICONS, color, design_tokens


def icon_image(master, name, tint, size=20):
    scale=4
    image=Image.new('RGBA',(size*scale,size*scale))
    draw=ImageDraw.Draw(image)
    factor=size*scale/24
    width=max(1,round(design_tokens()['icons']['stroke']*factor))
    for kind,values in ICONS[name]:
        if kind=='line':
            points=[(x*factor,y*factor) for x,y in values]
            draw.line(points,fill=tint,width=width,joint='curve')
        elif kind=='rect':
            x,y,w,h,r=values
            draw.rounded_rectangle((x*factor,y*factor,(x+w)*factor,(y+h)*factor), radius=r*factor,outline=tint,width=width)
        else:
            draw.ellipse(tuple(v*factor for v in values),outline=tint,width=width)
    return ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=master)


class IconButton(tk.Button):
    """Keep native Button focus/disabled/invoke semantics and visible labels."""
    def __init__(self, master, *, icon, text, command, palette, role='tool', scale=1, **kw):
        self._icon_name=icon
        self._icon_size=max(16,round(20*scale))
        self._role=role
        self._ready=False
        self._palette=palette
        fonts=design_tokens()['font']
        defaults={'font':(fonts['windows_families'][0],fonts['secondary_pt']),'relief':'flat','bd':0,'padx':8,'pady':6,
                  'takefocus':True,'cursor':'hand2','compound':'left','highlightthickness':1}
        defaults.update(kw)
        super().__init__(master,text=text,command=command,**defaults)
        self._ready=True
        self.set_palette(palette)
        self.bind('<Enter>', self._hover, add='+')
        self.bind('<Leave>', lambda _e:self.set_palette(self._palette), add='+')
        self.bind('<Return>', self._keyboard, add='+')
        self.bind('<ButtonPress-1>', self._pressed, add='+')
        self.bind('<ButtonRelease-1>', lambda _e:self.set_palette(self._palette), add='+')

    def _keyboard(self, _event):
        if self.cget('state') != 'disabled':
            self.invoke()
        return 'break'

    def _hover(self, _event):
        if self.cget('state')!='disabled':
            self.configure(bg=self._hover_bg)

    def _pressed(self, _event):
        if self.cget('state')!='disabled':
            mist=self._palette.get('name','').startswith('雾岸')
            dark=self._palette.get('name')=='雾岸深色'
            self.configure(bg=color('accent_pressed',dark) if mist and self._role=='primary' else self._hover_bg)

    def configure(self, cnf=None, **kw):
        result=super().configure(cnf, **kw)
        changed=set(kw) | (set(cnf) if isinstance(cnf,dict) else set())
        if self._ready and ({'fg','foreground','state'} & changed):
            self._refresh_icon()
        return result

    config=configure

    def _refresh_icon(self):
        tint=self.cget('disabledforeground') if self.cget('state')=='disabled' else self.cget('fg')
        self._icon_photo=icon_image(self,self._icon_name,tint,self._icon_size)
        super().configure(image=self._icon_photo)

    def set_palette(self, palette):
        self._palette=palette
        mist=palette.get('name','').startswith('雾岸')
        dark=palette.get('name')=='雾岸深色'
        if self._role=='primary':
            bg=palette['accent']
            fg=color('on_accent',dark) if mist else '#ffffff'
            hover=color('accent_hover',dark) if mist else palette['accent']
        elif self._role=='navigation':
            bg=palette.get('icon_bg',palette['panel_bg'])
            fg=color('navigation_text',dark) if mist else palette['sub']
            hover=color('accent_pressed',dark) if mist else palette.get('hover_bg',bg)
            if getattr(self, '_nav_selected', False):
                bg=palette['accent']
                fg=color('on_accent',dark) if mist else '#ffffff'
        else:
            bg,fg=palette['panel_bg'],palette['sub']
            hover=palette.get('hover_bg',bg)
        self._hover_bg=hover
        self.configure(bg=bg,fg=fg,activebackground=hover,activeforeground=fg,
                       disabledforeground=color('disabled_text',dark) if mist else palette['sub'],
                       highlightbackground=bg,highlightcolor=palette['accent'])
