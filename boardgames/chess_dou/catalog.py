"""Atlas slots are rank - 1, never inferred from a display name."""
ATLAS = "dou-beastgirls.webp"
COVER = "cover-dou.webp"
TERRAIN = "dou-terrain.webp"
NAMES = ("鼠", "猫", "狗", "狼", "豹", "虎", "狮", "象")
COLOURS = ("#bc454b", "#256f99")
TRAITS = ("圆耳银发", "橘发猫耳", "金色垂耳", "灰发狼耳",
          "豹纹披肩", "橘黑虎纹", "金色鬃发", "大耳象牙饰")


def identity(code):
    if code in range(1, 9):
        return 0, code
    if code in range(11, 19):
        return 1, code - 10
    return None


def can_act(st, me, room=None, connected=True):
    return bool(connected and me in (st.get("players") or [])
                and me in (room or {}).get("players", st.get("players") or [])
                and st.get("turn_uid") == me and st.get("winner_uid") is None
                and (room or {}).get("status", "playing") == "playing"
                and me not in (room or {}).get("spectators", []))


def water_rectangles(water):
    """Merge identical adjacent row runs: exact water cells, no tile seams."""
    out, previous = [], {}
    for y, row in enumerate(water):
        current, x = {}, 0
        while x < len(row):
            if not row[x]:
                x += 1
                continue
            start = x
            while x < len(row) and row[x]:
                x += 1
            key = start, x - start
            rect = previous.get(key)
            if rect is None:
                rect = [start, y, x - start, 1]
                out.append(rect)
            else:
                rect[3] += 1
            current[key] = rect
        previous = current
    return out
