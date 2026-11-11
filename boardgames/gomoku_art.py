# -*- coding: utf-8 -*-
"""Gomoku-only bitmap layers; geometry, rules and input remain with the host.

Call draw_board BEFORE the existing grid/coordinates, draw_stone at each actual
intersection, then draw_last_move AFTER all pieces. False means the host should
use its existing vector fallback. Importing this module never creates Tk objects.
"""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from pathlib import Path


ART_DIR = Path(__file__).resolve().parent.parent / "assets" / "boardgame" / "gallery"
BOARD_NAME = "gomoku-board.webp"
STONES_NAME = "gomoku-stones.png"
# Each 256px atlas cell contains a 224px generated stone, black then white.
STONE_FILL = 224 / 256
_PHOTO_LIMIT = 6


@lru_cache(maxsize=3)
def _source(name):
    try:
        from PIL import Image
        with Image.open(ART_DIR / name) as image:
            return image.convert("RGBA")
    except (ImportError, OSError, ValueError):
        return None


def _photo(cv, name, size, value=0):
    """Tk-thread only; two decoded sources and <=6 PhotoImages per canvas."""
    import tkinter as tk

    if not isinstance(cv, tk.Canvas):
        return None
    try:
        from PIL import Image, ImageTk, ImageOps
        cache = getattr(cv, "_gomoku_art_photos", None)
        if cache is None:
            cache = cv._gomoku_art_photos = OrderedDict()
        key = (name, size, value)
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        source = _source(name)
        if source is None:
            return None
        if value == -1:
            source=source.crop((0,0,round(source.width*.43),source.height))
            source=ImageOps.fit(source,size,Image.Resampling.LANCZOS,centering=(.5,.3))
        elif value:
            half = source.width // 2
            left = (value - 1) * half
            source = source.crop((left, 0, left + half, source.height))
        photo = ImageTk.PhotoImage(source.resize(size, Image.Resampling.LANCZOS), master=cv)
        cache[key] = photo
        while len(cache) > _PHOTO_LIMIT:
            cache.popitem(last=False)
        return photo
    except (ImportError, OSError, ValueError, tk.TclError):
        return None


def draw_board(cv, x0, y0, x1, y1):
    """Paste the blank wood underlay into the existing board rectangle."""
    if x1 <= x0 or y1 <= y0:
        return False
    size = (max(1, round(x1 - x0)), max(1, round(y1 - y0)))
    photo = _photo(cv, BOARD_NAME, size)
    if photo is None:
        return False
    cv.create_image(x0, y0, image=photo, anchor="nw", tags="_gomoku_art_board")
    return True


def draw_host(cv, width):
    """Keep the visible anime player outside all playable intersections."""
    cv.create_rectangle(8,48,width-8,122,fill='#fff7e9',outline='#d3bc8d')
    photo=_photo(cv,'cover-gomoku.webp',(92,68),-1)
    if photo is not None:
        cv.create_image(11,51,image=photo,anchor='nw',tags='_gomoku_art_host')
    cv.create_text(114,70,text='五子棋 · 棋馆',font=('Microsoft YaHei UI',12,'bold'),fill='#55452d',anchor='w')
    cv.create_text(114,96,text='点击交叉点，恰好五连获胜',font=('Microsoft YaHei UI',9),fill='#6b6255',anchor='w')
    return photo is not None


def draw_stone(cv, cx, cy, radius, value):
    """Draw black (1) / white (2); visible diameter matches 2*radius."""
    if value not in (1, 2) or radius <= 0:
        return False
    side = max(1, round(2 * radius / STONE_FILL))
    photo = _photo(cv, STONES_NAME, (side, side), value)
    if photo is None:
        return False
    cv.create_image(cx, cy, image=photo, anchor="center", tags="_gomoku_art_stone")
    return True


def draw_last_move(cv, cx, cy, radius):
    """Red centre + ivory rim reads on either colour, even at compact sizes."""
    if radius <= 0:
        return
    dot = max(2.2, min(4.0, radius * 0.25))
    cv.create_oval(cx - dot, cy - dot, cx + dot, cy + dot,
                   fill="#d72f36", outline="#fff3df", width=1,
                   tags="_gomoku_art_last")


# Inject once before the existing gomoku renderer. This helper only paints art;
# its onload callback requests the host's WHOLE synchronous paint pass.
WEB_JS = r"""
const createGomokuArtPainter = (() => {
  const sources = new Map();
  function source(name) {
    if (sources.has(name)) return sources.get(name);
    const entry = {image:new Image(), ready:false, settled:false, waiters:new Set()};
    sources.set(name, entry);
    entry.image.onload = () => {
      entry.settled = true;
      entry.ready = entry.image.naturalWidth > 0;
      for (const notify of entry.waiters) notify();
      entry.waiters.clear();
    };
    entry.image.onerror = () => {entry.settled=true;entry.waiters.clear();};
    entry.image.src = '/game-art/' + name;
    return entry;
  }
  return function createGomokuArtPainter(cv, repaint) {
    const ctx = cv.getContext('2d');
    const board = source('gomoku-board.webp?v=anime-v1'), stones = source('gomoku-stones.png?v=anime-v1');
    let pending = false;
    const refresh = () => {
      if (pending || !cv.isConnected) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        if (cv.isConnected) repaint();
      });
    };
    for (const entry of [board, stones])
      if (!entry.settled) entry.waiters.add(refresh);
    return {
      board(x, y, width, height) {
        ctx.save();
        ctx.fillStyle = '#edc88c'; ctx.fillRect(x,y,width,height);
        if (board.ready) ctx.drawImage(board.image,x,y,width,height);
        ctx.restore();
      },
      stone(cx, cy, radius, value) {
        if (value !== 1 && value !== 2) return;
        ctx.save();
        if (stones.ready) {
          const half=stones.image.naturalWidth/2, side=radius*2/(224/256);
          ctx.drawImage(stones.image,(value-1)*half,0,half,stones.image.naturalHeight,
                        cx-side/2,cy-side/2,side,side);
        } else {
          ctx.beginPath();ctx.arc(cx,cy,radius,0,Math.PI*2);
          ctx.fillStyle=value===1?'#11151b':'#fff5e3';
          ctx.strokeStyle=value===1?'#080b0f':'#796959';
          ctx.lineWidth=1;ctx.fill();ctx.stroke();
        }
        ctx.restore();
      },
      last(cx, cy, radius) {
        const dot=Math.max(2.2,Math.min(4,radius*0.25));
        ctx.save();ctx.beginPath();ctx.arc(cx,cy,dot,0,Math.PI*2);
        ctx.fillStyle='#d72f36';ctx.strokeStyle='#fff3df';ctx.lineWidth=1;
        ctx.fill();ctx.stroke();ctx.restore();
      }
    };
  };
})();
"""
