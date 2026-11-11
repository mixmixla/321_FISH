"""Private chess-line atlas helpers. Lazy PIL/Tk; bounded canvas-owned pictures."""
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "assets" / "boardgame" / "gallery"


@lru_cache(maxsize=10)
def source(name):
    from PIL import Image
    with Image.open(ROOT / name) as pixels:
        return pixels.convert("RGB")


def photo(canvas, name, size, slot=0, columns=1, rows=1):
    from PIL import Image, ImageTk, ImageOps
    cache = getattr(canvas, "_chess_photos", None)
    if cache is None:
        cache = canvas._chess_photos = OrderedDict()
    key = name, size, slot, columns, rows
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    pixels = source(name)
    w, h = pixels.width / columns, pixels.height / rows
    x, y = slot % columns, slot // columns
    pixels = pixels.crop((round(x*w+2),round(y*h+2),round((x+1)*w-2),round((y+1)*h-2)))
    value = ImageTk.PhotoImage(ImageOps.fit(pixels,size,Image.Resampling.LANCZOS),master=canvas)
    cache[key] = value
    while len(cache) > 40: cache.popitem(last=False)
    return value
