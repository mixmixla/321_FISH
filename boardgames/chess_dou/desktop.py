"""Readable beast-girl pieces on the exact server grid, with canvas-owned images."""
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from .catalog import ATLAS, COVER, TERRAIN, NAMES, COLOURS, identity, can_act, water_rectangles

ART_ROOT = Path(__file__).resolve().parents[2] / "assets" / "boardgame" / "gallery"


@lru_cache(maxsize=3)
def source(name):
    from PIL import Image
    with Image.open(ART_ROOT / name) as pixels:
        return pixels.convert("RGB")


def photo(cv, name, size, rank=0):
    from PIL import Image, ImageTk, ImageOps
    cache = getattr(cv, "_dou_photos", None)
    if cache is None:
        cache = cv._dou_photos = OrderedDict()
    key = name, size, rank
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    pixels = source(name)
    if rank:
        cols = 2 if name == TERRAIN else 4
        col, row = (rank - 1) % cols, (rank - 1) // cols
        tw, th = pixels.width / cols, pixels.height / 2
        # Remove the thin atlas divider; preserve the full head and ear silhouettes.
        pixels = pixels.crop((round(col * tw + 2), round(row * th + 2),
                              round((col + 1) * tw - 2), round((row + 1) * th - 2)))
    pixels = ImageOps.fit(pixels, size, Image.Resampling.LANCZOS)
    value = ImageTk.PhotoImage(pixels, master=cv)
    cache[key] = value
    # A render uses eight rank images and one cover; bounded across resizes.
    while len(cache) > 20:
        cache.popitem(last=False)
    return value


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    cv._dou_ui = ui
    if not getattr(cv, "_dou_keys_bound", False):
        for key in ("Up", "Down", "Left", "Right", "Return", "space", "Escape"):
            cv.bind("<" + key + ">", lambda event: keyboard(cv, event.keysym), add="+")
        cv._dou_keys_bound = True
    cv.configure(background="#edf3e8")
    players = st.get("players") or []
    seat = players.index(me) if me in players else -1
    mine = ("你执红方", "你执蓝方")[seat] if seat >= 0 else "旁观者 · 只读"
    winner = st.get("winner_uid")
    status = f"{nick(winner)} 获胜" if winner is not None else (
        "轮到你" if st.get("turn_uid") == me and seat >= 0 else f"等待 {nick(st.get('turn_uid'))}")
    cv.create_rectangle(0, 0, w, 56, fill="#173e37", outline="")
    cv.create_text(14, 16, anchor="w", text="斗兽棋 · 兽娘森境", fill="#fff3ce",
                   font=("Microsoft YaHei UI", 12, "bold"))
    cv.create_text(14, 39, anchor="w", text=mine + "  ·  " + status[:26],
                   fill="#e0eddd", font=("Microsoft YaHei UI", 10))
    side_w = 205 if w >= 730 else 0
    available = w - side_w
    cell = min((available - 42) / 7, (h - 100) / 9)
    cell = max(5, cell)
    ox, oy = (available - 7 * cell) / 2 + 7, 72 + max(0, (h - 100 - 9 * cell) / 2)
    ui.update(game="dou", ox=ox, oy=oy, cell=cell, n=9, rows=9, cols=7,
              state=st, me=me, submit=submit, repaint=repaint, dou_priv=priv or {},
              dou_state=st, dou_context=ui.get("_room_context"))
    board, water = st.get("board") or [], st.get("water") or []
    dens = {tuple(pos): int(side) for side, pos in (st.get("dens") or {"0": [3, 0], "1": [3, 8]}).items()}
    traps = {tuple(pos): int(side) for side, squares in (st.get("traps") or {}).items() for pos in squares}
    # One continuous clearing; each actual river is one continuous texture patch.
    cv.create_image(ox, oy, anchor="nw", image=photo(cv, TERRAIN, (max(1, round(7*cell)), max(1, round(9*cell))), 1), tags="dou-forest")
    for rx, ry, rw, rh in water_rectangles(water):
        cv.create_image(ox+rx*cell, oy+ry*cell, anchor="nw", image=photo(cv, TERRAIN, (max(1, round(rw*cell)), max(1, round(rh*cell))), 2), tags="dou-river")
    for x in range(7):
        cv.create_text(ox + (x + .5) * cell, oy - 9, text=chr(65 + x), fill="#4b6454", font=("Arial", 8))
    selected = ui.get("sel") or {}
    targets = [m["to"] for m in (priv or {}).get("legal", [])
               if m.get("from") == [selected.get("fx"), selected.get("fy")]]
    for y in range(9):
        cv.create_text(ox - 10, oy + (y + .5) * cell, text=str(y + 1), fill="#4b6454", font=("Arial", 8))
        for x in range(7):
            x0, y0 = ox + x * cell, oy + y * cell
            in_water = bool(y < len(water) and x < len(water[y]) and water[y][x])
            terrain = COLOURS[dens[(x, y)]] if (x, y) in dens else ("#8dcede" if in_water else "#dce8bf")
            if (x, y) in dens or (x, y) in traps:
                tile = 4 if (x, y) in dens else 3
                side = max(1, round(cell + 1))
                cv.create_image(x0 + cell / 2, y0 + cell / 2, image=photo(cv, TERRAIN, (side, side), tile), tags="dou-terrain")
            cv.create_rectangle(x0, y0, x0 + cell, y0 + cell, outline="#76967a", width=1)
            if (x, y) in dens:
                cv.create_rectangle(x0 + 1, y0 + cell * .63, x0 + cell - 1, y0 + cell - 1, fill=COLOURS[dens[(x,y)]], outline="")
                cv.create_text(x0 + cell / 2, y0 + cell * .8, text="营", fill="white", font=("Microsoft YaHei UI", max(8, int(cell * .23)), "bold"))
            if (x, y) in traps:
                cv.create_rectangle(x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell - 3,
                                    outline=COLOURS[traps[(x, y)]], dash=(3, 2), width=2)
                cv.create_rectangle(x0, y0, x0 + 13, y0 + 13, fill="#fff0ba", outline="")
                cv.create_text(x0 + 6, y0 + 6, text="陷", fill=COLOURS[traps[(x, y)]], font=("Microsoft YaHei UI", 7, "bold"))
            code = board[y][x] if y < len(board) and x < len(board[y]) else 0
            piece = identity(code)
            if piece:
                side, rank = piece
                gap = max(2, cell * .055)
                size = max(1, round(cell - gap * 2))
                cv.create_image(x0 + cell / 2, y0 + cell / 2, image=photo(cv, ATLAS, (size, size), rank), tags="dou-character")
                cv.create_rectangle(x0 + gap, y0 + gap, x0 + cell - gap, y0 + cell - gap,
                                    outline=COLOURS[side], width=max(2, cell * .045))
                label_h = max(10, cell * .24)
                cv.create_rectangle(x0 + gap, y0 + cell - gap - label_h, x0 + cell - gap, y0 + cell - gap, fill=COLOURS[side], outline="")
                cv.create_text(x0 + cell / 2, y0 + cell - gap - label_h / 2,
                               text=f"{NAMES[rank-1]} {rank}", fill="white", font=("Microsoft YaHei UI", max(7, int(cell * .17)), "bold"))
                # Small terrain markers stay visible when a character occupies a trap/den.
                if (x, y) in traps or (x, y) in dens:
                    mark = "陷" if (x, y) in traps else "营"
                    cv.create_rectangle(x0, y0, x0 + 13, y0 + 13, fill="#fff0ba", outline="")
                    cv.create_text(x0 + 6, y0 + 6, text=mark, fill="#59452a", font=("Microsoft YaHei UI", 7))
            if selected.get("game") == "dou" and [x, y] == [selected.get("fx"), selected.get("fy")]:
                cv.create_rectangle(x0 + 1, y0 + 1, x0 + cell - 1, y0 + cell - 1, outline="#f7b92d", width=3)
            if [x, y] in targets:
                cv.create_oval(x0 + cell * .32, y0 + cell * .32, x0 + cell * .68, y0 + cell * .68,
                               outline="#254e38", fill="#fbe294", width=2, tags="dou-legal")
    last = st.get("last_move")
    if last:
        x, y = last[1]
        cv.create_rectangle(ox + x * cell + 1, oy + y * cell + 1, ox + (x + 1) * cell - 1,
                            oy + (y + 1) * cell - 1, outline="#f59822", width=2, tags="dou-last")
    if ui.get("dou_cursor") is not None:
        x, y = ui["dou_cursor"]
        cv.create_rectangle(ox + x * cell + 3, oy + y * cell + 3, ox + (x + 1) * cell - 3,
                            oy + (y + 1) * cell - 3, outline="#6844c5", width=2, dash=(2, 2), tags="dou-cursor")
    cv.create_text(available / 2, h - 13, text="点己方兽娘 → 金色落点  ·  红/蓝边框表阵营", fill="#3b5945", font=("Microsoft YaHei UI", 9))
    if not side_w and ox >= 98 and h >= 300:
        # A compact landscape window has spare side gutters: inspect the actual
        # selected character at a readable size instead of stretching the grid.
        preview = None
        if selected.get("game") == "dou" and "fx" in selected:
            preview = identity(board[selected["fy"]][selected["fx"]])
        owner, rank = preview or (max(0, seat), 1)
        size = min(105, int(ox - 24))
        px, py = 10, 100
        cv.create_image(px, py, anchor="nw", image=photo(cv, ATLAS, (size, size), rank), tags="dou-preview")
        cv.create_rectangle(px, py, px + size, py + size, outline=COLOURS[owner], width=2)
        cv.create_text(px + size / 2, py - 14, text="选中角色" if preview else "森境图鉴", fill="#365742", font=("Microsoft YaHei UI", 9))
        cv.create_text(px + size / 2, py + size + 16, text=f"{NAMES[rank-1]} · 等级 {rank}", fill=COLOURS[owner], font=("Microsoft YaHei UI", 10, "bold"))
        abilities = ("可入河\n陆上能吃象", "灵巧近身", "忠诚护卫", "灰狼卫士", "斑纹猎手", "横纵跳河", "横纵跳河", "高阶力量\n不能吃鼠")
        cv.create_text(px + size / 2, py + size + 51, text=abilities[rank-1], fill="#365742", justify="center", font=("Microsoft YaHei UI", 9))
        right = ox + 7 * cell + 14
        cv.create_text(right + size / 2, py + 22, text="红营 D1\n蓝营 D9", justify="center", fill="#365742", font=("Microsoft YaHei UI", 9))
        cv.create_text(right + size / 2, py + 75, text="虚线为陷阱\n占敌营获胜", justify="center", fill="#365742", font=("Microsoft YaHei UI", 9))
    if side_w:
        left = w - side_w + 8
        cv.create_image(left, 72, anchor="nw", image=photo(cv, COVER, (185, 185)), tags="dou-cover")
        lines = ["森境图鉴", "鼠1  猫2  狗3  狼4", "豹5  虎6  狮7  象8", "", "红营 D1 · 蓝营 D9", "虚线：该阵营的陷阱", "敌陷阱内等级归零", "", "森境行棋规则", "双河 · 狮虎横纵跳", "仅鼠入河 · 鼠能吃象", "同级可吃 · 占敌营获胜"]
        for index, text in enumerate(lines):
            cv.create_text(left + 2, 274 + index * 19, text=text, anchor="nw", fill="#335543", font=("Microsoft YaHei UI", 10 if index else 12, "bold" if index == 0 else "normal"))


def click(ui, x, y):
    st, me = ui.get("state") or {}, ui.get("me")
    if (st is not ui.get("dou_state") or ui.get("_room_context") != ui.get("dou_context")
            or not can_act(st, me, ui.get("room"), ui.get("connected", True))):
        return
    ox, oy, cell = (ui.get(k) for k in ("ox", "oy", "cell"))
    if None in (ox, oy, cell) or not (ox <= x < ox + 7 * cell and oy <= y < oy + 9 * cell):
        return
    cx, cy = int((x - ox) / cell), int((y - oy) / cell)
    code = st["board"][cy][cx]
    selected = ui.setdefault("sel", {})
    piece = identity(code)
    seat = st["players"].index(me)
    if piece and piece[0] == seat:
        if selected == {"game": "dou", "fx": cx, "fy": cy}:
            selected.clear()
        else:
            selected.update(game="dou", fx=cx, fy=cy)
    elif selected.get("game") == "dou" and "fx" in selected:
        move = {"fx": selected["fx"], "fy": selected["fy"], "tx": cx, "ty": cy}
        legal = ui.get("dou_priv", {}).get("legal")
        if legal is not None and not any(m.get("from") == [move["fx"], move["fy"]]
                                        and m.get("to") == [cx, cy] for m in legal):
            return
        selected.clear()
        ui["submit"](move)
    ui["repaint"]()


def keyboard(cv, key):
    if getattr(cv, "_gkey", None) != "dou":
        return None
    ui = cv._dou_ui
    cursor = ui.setdefault("dou_cursor", [0, 0])
    delta = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}.get(key)
    if delta:
        ui["dou_cursor"] = [max(0, min(6, cursor[0] + delta[0])), max(0, min(8, cursor[1] + delta[1]))]
    elif key in ("Return", "space"):
        click(ui, ui["ox"] + (cursor[0] + .5) * ui["cell"], ui["oy"] + (cursor[1] + .5) * ui["cell"])
        return "break"
    elif key == "Escape":
        ui.setdefault("sel", {}).clear()
    ui["repaint"]()
    return "break"
