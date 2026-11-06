"""Shared gallery art: strict HTTP names and canvas-owned Tk image lifetime.

Only optimized bitmaps live in assets; no base64 is injected into the chat page.
Pillow/Tk remain lazy so the server and headless callers can import this module.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path


ART_ROOT = Path(__file__).resolve().parents[1] / "assets" / "boardgame" / "gallery"
COVERS = {
    "tielu": "cover-tielu.webp",
    "azul": "cover-azul.webp",
    "tile2048": "cover-tile2048.webp",
    "gomoku": "cover-gomoku.webp",
    "gomoku_solo": "cover-gomoku.webp",
    "gemcity": "cover-gemcity.webp",
    "betrayal": "cover-betrayal.webp",
    "lovelove": "cover-lovelove.webp",
    "rps": "cover-rps.webp",
    "dou": "cover-dou-lobby.webp",
    "junqi": "cover-junqi-lobby.webp",
    "balatro": "cover-balatro.webp",
}
FEATURED = ("tile2048", "gomoku_solo", "tielu", "azul", "gemcity")
ART_FILES = frozenset(COVERS.values()) | {
    "cover-junqi.webp",
    "tile2048-atlas.webp", "gomoku-board.webp", "gomoku-stones.png",
    "gemcity-tier1.webp", "gemcity-tier2.webp", "gemcity-tier3.webp",
    "gemcity-patrons.webp", "lovelove-court.webp",
    "betrayal-rooms.webp", "betrayal-items.webp",
    "betrayal-events.webp", "betrayal-omens.webp",
    "gemcity-jewels.webp", "rps-hands.webp",
    "tielu-coach-cards.webp", "tielu-stations.webp",
    "cover-dou.webp",
    "dou-beastgirls.webp",
    "dou-terrain.webp",
    "junqi-officers.webp",
    "ludo-aviators.webp",
    "ludo-cloud-airports.webp",
    "blokus-artisans.webp",
    "arcade-orchard.webp",
    "arcade-bell.png",
    "arcade-yacht.webp",
    "arcade-atelier.webp",
    "arcade-math.webp",
    "arcade-numbers.webp",
    "balatro-jokers-core.webp",
}
MIME_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".png": "image/png"}


def resource_path(name):
    """Resolve one exact allowlisted filename; reject traversal and outside links."""
    if not isinstance(name, str) or name not in ART_FILES:
        raise FileNotFoundError("Unknown game art")
    root = ART_ROOT.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise FileNotFoundError("Missing game art")
    return path


def read_resource(name):
    """Return bytes + MIME, without needing Pillow or importing a game renderer."""
    path = resource_path(name)
    return path.read_bytes(), MIME_TYPES[path.suffix.lower()]


@lru_cache(maxsize=len(set(COVERS.values())))
def _cover_version(name):
    return sha256(resource_path(name).read_bytes()).hexdigest()[:12]


def cover_url(game):
    """Known cover URL or an empty string for the existing gradient fallback."""
    name = COVERS.get(game)
    if not name:
        return ""
    try:
        return f"/game-art/{name}?v={_cover_version(name)}"
    except OSError:
        return ""


def prioritise(names):
    """Move a short curated list first; preserve all remaining relative order."""
    ranks = {name: index for index, name in enumerate(FEATURED)}
    return sorted(names, key=lambda name: ranks.get(name, len(ranks)))


@lru_cache(maxsize=len(set(COVERS.values())))
def _cover_source(name):
    from PIL import Image
    with Image.open(resource_path(name)) as image:
        return image.convert("RGB")


def paint_cover(canvas, game, width, height):
    """Paint a crop-fit cover; one PhotoImage per canvas, created on its Tk thread."""
    name = COVERS.get(game)
    if not name or not isinstance(getattr(canvas, "_w", None), str):
        return False
    try:
        from PIL import Image, ImageOps, ImageTk
        size = max(1, round(width)), max(1, round(height))
        key = name, size
        cached = getattr(canvas, "_gallery_cover", None)
        if not cached or cached[0] != key:
            pixels = ImageOps.fit(_cover_source(name), size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(pixels, master=canvas)
            canvas._gallery_cover = key, photo
        canvas.create_image(0, 0, anchor="nw", image=canvas._gallery_cover[1],
                            tags="gallery-cover")
        return True
    except (ImportError, OSError, ValueError):
        return False
