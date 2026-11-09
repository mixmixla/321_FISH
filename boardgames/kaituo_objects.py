"""Alpha-preserving Kaituo sprite crops and the two live dice faces."""
from collections import OrderedDict
from functools import lru_cache
from boardgames.gallery import resource_path

LAND = "economy-kaituo-terrain-v2.webp"
HARBOUR = "kaituo-merchant.webp"
GOODS = "kaituo-goods.webp"
MODELS = "kaituo-models.webp"
PIPS = {1: [(50, 50)], 2: [(28, 28), (72, 72)],
        3: [(28, 28), (50, 50), (72, 72)],
        4: [(28, 28), (72, 28), (28, 72), (72, 72)],
        5: [(28, 28), (72, 28), (50, 50), (28, 72), (72, 72)],
        6: [(28, 25), (72, 25), (28, 50), (72, 50), (28, 75), (72, 75)]}


@lru_cache(maxsize=19)
def _source(file, index):
    from PIL import Image
    with Image.open(resource_path(file)) as asset:
        image = asset.convert("RGBA")
    if file == HARBOUR:
        return image
    side = image.width // 3
    x, y = index % 3 * side, index // 3 * side
    return image.crop((x, y, x+side, y+side))


def sprite(canvas, file, index, rect):
    if not isinstance(getattr(canvas, "_w", None), str):
        return
    from PIL import Image, ImageOps, ImageTk
    x0, y0, x1, y1 = rect
    size = max(2, round(x1-x0)), max(2, round(y1-y0))
    cache = getattr(canvas, "_kt_images", None)
    if cache is None:
        cache = canvas._kt_images = OrderedDict()
    key = file, index, size
    if key not in cache:
        try:
            source = _source(file, index)
        except (OSError, ValueError):
            return
        if file == LAND:
            image = ImageOps.fit(source, size, Image.Resampling.LANCZOS, centering=(.5, .27))
        else:
            image = ImageOps.contain(source, size, Image.Resampling.LANCZOS)
        cache[key] = ImageTk.PhotoImage(image, master=canvas)
        while len(cache) > 150:
            cache.popitem(last=False)
    cache.move_to_end(key)
    canvas.create_image((x0+x1)/2, (y0+y1)/2, image=cache[key])


def die(canvas, x, y, size, value):
    canvas.create_rectangle(x+3, y+4, x+size+3, y+size+4, fill="#ae9a6f", outline="")
    canvas.create_rectangle(x, y, x+size, y+size, fill="#fff9e8", outline="#c5b58d")
    for px, py in PIPS.get(value, ()):
        cx, cy, radius = x+size*px/100, y+size*py/100, size*.076
        canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, fill="#314c47", outline="")
