"""Art follows ability identity; ranks/suits/effect values are never baked in."""
from games_pkg.balatro import JOKER_DEFS

CORE_ORDER = ("pair", "flush", "straight", "sf", "four", "full", "heart", "spade")
JOKER_ART = {key: ("balatro-jokers-core.webp", index) for index, key in enumerate(CORE_ORDER)}
JOKERS = {key: {"name": JOKER_DEFS[key][0], "desc": JOKER_DEFS[key][1], "file": file, "index": index}
          for key, (file, index) in JOKER_ART.items()}
