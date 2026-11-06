"""Blokus physical polyomino inventory and seat artwork; real wire rows/columns."""

def parse_cells(values):
    return [tuple(map(int, str(v).split(","))) for v in values]


def mini(cv, cells, rect, color, edge="#ffffff"):
    if not cells:
        return
    rows, cols = max(r for r, c in cells)+1, max(c for r, c in cells)+1
    scale = min((rect[2]-rect[0])/cols, (rect[3]-rect[1])/rows)
    x, y = (rect[0]+rect[2]-cols*scale)/2, (rect[1]+rect[3]-rows*scale)/2
    for r, c in cells:
        cv.create_rectangle(x+c*scale, y+r*scale, x+(c+1)*scale, y+(r+1)*scale,
                            fill=color, outline=edge, width=1, tags="blok-polyomino")


def active(st, me, ui):
    room = ui.get("room") or {}
    return (ui.get("connected", True) is not False and me in st.get("players", [])
            and me in room.get("players", st.get("players", []))
            and me not in room.get("spectators", []) and st.get("winner_uid") is None
            and room.get("status", "playing") == "playing" and st.get("turn_uid") == me)


def placement(st, uid, piece, oi, row, col):
    catalog = (st.get("pieces") or {}).get(piece) or []
    if not 0 <= oi < len(catalog):
        return [], False
    cells = [(row+r, col+c) for r, c in parse_cells(catalog[oi])]
    board, size = st["board"], st.get("size", 20)
    if any(not (0 <= r < size and 0 <= c < size) or board[r][c] is not None for r, c in cells):
        return cells, False
    if (st.get("placed") or {}).get(str(uid), 0) == 0:
        return cells, any((r, c) in {(0, 0), (0, size-1), (size-1, 0), (size-1, size-1)} for r, c in cells)
    same = lambda r, c: 0 <= r < size and 0 <= c < size and board[r][c] == uid
    edge = any(same(r+dr,c+dc) for r,c in cells for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)))
    corner = any(same(r+dr,c+dc) for r,c in cells for dr,dc in ((1,1),(1,-1),(-1,1),(-1,-1)))
    return cells, corner and not edge


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    import client_gameui as cu
    accent = cu.THEME["blokus"][1]
    n = st.get("size") or 20
    ended = st.get("winner_uid") is not None
    ui.update(blok_state=st, blok_context=ui.get("_room_context"))
    title = "角斗士棋"
    title_uid = st.get("winner_uid") if ended else st.get("turn_uid")
    title_name = str(nick(title_uid)) if title_uid is not None else ""
    nick_limit = max(4, int((w - 220) // 20))
    if len(title_name) > nick_limit:
        title_name = title_name[:nick_limit - 1] + "…"
    if ended:
        title = f"🏆 {title_name} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {title_name}"
    # Blokus style sample: a quiet surface with a small piece mark, while
    # the board/player colors retain the game's own identity.
    cu._rrect(cv, 8, 8, w - 8, 44, cu._UXR_BIG, cu._UXC["surface"], cu._PANEL_BD)
    for dx, dy in ((0, 0), (0, 8), (8, 8)):
        cv.create_rectangle(22 + dx, 18 + dy, 28 + dx, 24 + dy,
                            fill=accent, outline="")
    cu._text(cv, 48, 26, title, cu._TXT, cu._FONT_H, anchor="w")
    board = st.get("board") or []
    players = st.get("players") or []
    colors = st.get("colors") or ["#e05555", "#3f6fe0", "#3ba55d", "#e8b93c"]
    accent = colors[players.index(me)] if me in players else accent
    placed = st.get("placed") or {}
    has_piece = st.get("has_piece") or {}
    catalog = st.get("pieces") or {}
    panel_w = max(150, int(w * 0.22))
    cell = max(4, min((w - panel_w - 24) / n, (h - 46 - 24) / n))
    bx = 10
    by = 46 + (h - 46 - n * cell) / 2
    ui.update(ox=bx, oy=by, cell=cell, n=n, game="blokus", cols=n, rows=n)
    cv.create_rectangle(bx - 4, by - 4, bx + n * cell + 4, by + n * cell + 4,
                        fill="#f0ead8", outline="#888", width=2)
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            fill = "#f0ead8"
            if v is not None and v in players:
                ci = players.index(v)
                fill = cu._shade(colors[ci % len(colors)], 0.08) if v != me \
                    else cu._shade(colors[ci % len(colors)], 0.3)
            cv.create_rectangle(bx + x * cell, by + y * cell,
                                bx + (x + 1) * cell, by + (y + 1) * cell,
                                fill=fill, outline="#d8d0b8", width=1)
    # 最近一步标记：本次落子覆盖的格子加金色描边
    for rc in (st.get("last_move") or []):
        try:
            lr, lc = int(rc[0]), int(rc[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= lr < n and 0 <= lc < n:
            cv.create_rectangle(bx + lc * cell + 1, by + lr * cell + 1,
                                bx + (lc + 1) * cell - 1, by + (lr + 1) * cell - 1,
                                outline="#ffd75e", width=2)
    # 右侧面板：战况 + 交互区（选择拼块 / 换方向 / 跳过 / 点棋盘落子）
    px = bx + n * cell + 14
    py = by + 4
    right = w - 12
    panel_width = right - px
    cu._rrect(cv, px - 8, by - 12, w - 4, h - 6, cu._UXR_BIG,
           cu._UXC["surface"], cu._PANEL_BD)
    cu._text(cv, px, py, "战况", cu._TXT, cu._FONT_B, anchor="w")
    py += 20
    seat_h = min(38, max(16, (h-240)/max(1, len(players))))
    from boardgames.card_table_tk import art
    for i, u in enumerate(players):
        col = colors[i % len(colors)]
        ss = seat_h-3
        art(cv, "blokus-artisans.webp", i, 2, 2, (px, py-7, px+ss, py-7+ss))
        if u == st.get("turn_uid") and not ended:
            cv.create_rectangle(px-1, py-8, px+ss+1, py-6+ss, outline="#d4a428", width=2)
        label = "你" if u == me else str(nick(u))[:4]
        cu._text(cv, px+ss+6, py, label, col, (cu._FONT_F[0], 8), anchor="w")
        cu._text(cv, right-2, py, f"{placed.get(str(u), 0)}格", col,
                 (cu._FONT_F[0], 8), anchor="e")
        py += seat_h
    py += 6
    # 每帧重置点击热区，避免残留失效区域
    ui["blok_chips"] = []
    ui["blok_rot"] = None
    ui["blok_pass"] = None
    ui["blok_page_prev"] = None
    ui["blok_page_next"] = None
    my_turn = active(st, me, ui)
    mine = has_piece.get(str(me)) or []
    if my_turn and mine:
        pick = ui.get("blok_pick")
        if pick not in mine:
            pick = mine[0]
            ui["blok_pick"] = pick
            ui["blok_oi"] = 0
            ui["blok_page"] = 0
        ots = list(catalog.get(pick) or [])
        oi = ui.get("blok_oi", 0) % len(ots) if ots else 0
        if ots:
            ui["blok_oi"] = oi
        cu._text(cv, px, py, f"已选 {pick}", cu._TXT, cu._FONT_B, anchor="w")
        cu._text(cv, px, py + 14, f"方向 {oi + 1}/{len(ots)}" if ots else "选择后点棋盘",
              cu._UXC["text_secondary"], (cu._FONT_F[0], 9), anchor="w")
        # A bounded preview shows rotation feedback without pushing controls down.
        if ots:
            cells = []
            for value in ots[oi]:
                try:
                    a, b = map(int, str(value).split(","))
                except (ValueError, TypeError):
                    continue
                cells.append((a, b))
            if cells:
                rows = max(a for a, _ in cells) + 1
                cols = max(b for _, b in cells) + 1
                msz = min(6, 24 / max(rows, cols))
                mx0, my0 = right - cols * msz, py - 5
                for a, b in cells:
                    cv.create_rectangle(mx0 + b * msz, my0 + a * msz,
                                        mx0 + (b + 1) * msz, my0 + (a + 1) * msz,
                                        fill=accent, outline=cu._UXC["surface"])
        py += 28
        # Keep actions anchored above the bottom hint. Page the inventory rather
        # than shrinking click targets or letting four-player inventories overflow.
        actions_y = h - 56
        gap, chh = 4, 24
        cols_n = max(1, int((panel_width + gap) // 46))
        cw = (panel_width - gap * (cols_n - 1)) / cols_n
        rows_fit = max(1, int((actions_y - 8 - py + gap) // (chh + gap)))
        paged = len(mine) > rows_fit * cols_n
        if paged:
            rows_fit = max(1, int((actions_y - 36 - py + gap) // (chh + gap)))
        capacity = rows_fit * cols_n
        ui["blok_capacity"] = capacity
        page_count = (len(mine) + capacity - 1) // capacity
        page = max(0, min(int(ui.get("blok_page", 0)), page_count - 1))
        ui["blok_page"] = page
        chips = []
        cx, cy = px, py
        for idx, nm in enumerate(mine[page * capacity:(page + 1) * capacity]):
            if idx and idx % cols_n == 0:
                cx = px
                cy += chh + gap
            sel = (nm == pick)
            cu._rrect(cv, cx, cy, cx + cw, cy + chh, cu._UXR_CTRL,
                   cu._UXC["selected_background"] if sel else cu._UXC["surface"], accent if sel else cu._PANEL_BD,
                   2 if sel else 1)
            shape = parse_cells((catalog.get(nm) or [[]])[0])
            mini(cv, shape, (cx+3, cy+3, cx+cw-3, cy+chh-3),
                 colors[players.index(me)] if me in players else accent,
                 edge="#fff" if sel else "#c6d4d9")
            chips.append((cx, cy, cx + cw, cy + chh, nm))
            cx += cw + gap
        ui["blok_chips"] = chips
        if paged:
            pager_y = actions_y - 28
            for control_key, label, enabled, x0 in (
                    ("blok_page_prev", "‹", page > 0, px),
                    ("blok_page_next", "›", page + 1 < page_count, right - 28)):
                rect = (x0, pager_y, x0 + 28, pager_y + 24)
                cu._rrect(cv, *rect, cu._UXR_CTRL, cu._UXC["surface"], cu._PANEL_BD)
                cu._text(cv, x0 + 14, pager_y + 12, label,
                      cu._TXT if enabled else cu._UXC["disabled_text"], cu._FONT_B)
                ui[control_key] = rect if enabled else None
            cu._text(cv, (px + right) / 2, pager_y + 12, f"{page + 1}/{page_count}",
                  cu._UXC["text_secondary"], (cu._FONT_F[0], 9))
        bw = (panel_width - 8) / 2
        if ots:
            rot = (px, actions_y, px + bw, actions_y + 28)
            cu._rrect(cv, *rot, cu._UXR_CTRL, cu._UXC["selected_background"], accent)
            cu._text(cv, px + bw / 2, actions_y + 14, f"换向 {oi + 1}/{len(ots)}",
                  cu._TXT, (cu._FONT_F[0], 9))
            ui["blok_rot"] = rot
        pas = (px + bw + 8, actions_y, right, actions_y + 28)
        cu._rrect(cv, *pas, cu._UXR_CTRL, cu._UXC["surface"], cu._PANEL_BD)
        cu._text(cv, (pas[0] + pas[2]) / 2, actions_y + 14, "跳过", cu._TXT,
              (cu._FONT_F[0], 9))
        ui["blok_pass"] = pas
        cu._text(cv, px, h - 14, "选拼块 → 点棋盘", cu._UXC["text_secondary"],
              (cu._FONT_F[0], 9), anchor="w")
    elif ended:
        cu._text(cv, px, py, "对局已结束", "#666666", cu._FONT_F, anchor="w")
    elif st.get("turn_uid") is not None:
        cu._text(cv, px, py, f"等待 {nick(st['turn_uid'])} 落子…", "#666666",
              cu._FONT_F, anchor="w")
    hover = ui.get("_hover")
    if active(st, me, ui) and hover and ui.get("blok_pick"):
        points, valid = placement(st, me, ui["blok_pick"], ui.get("blok_oi", 0), hover[1], hover[0])
        for rr, cc in points:
            if 0 <= rr < n and 0 <= cc < n:
                cv.create_rectangle(bx+cc*cell+1, by+rr*cell+1, bx+(cc+1)*cell-1, by+(rr+1)*cell-1,
                                    fill="", outline="#d4a428" if valid else "#bd4052", width=2)

    if isinstance(getattr(cv, "_w", None), str):
        cv._blokus_key_ui = ui
        if not getattr(cv, "_blokus_keys_bound", False):
            cv._blokus_keys_bound = True
            for keyname in ("r", "p", "bracketleft", "bracketright", "Up", "Down", "Left", "Right", "Return"):
                cv.bind("<KeyPress-"+keyname+">", lambda event, name=keyname: key(cv._blokus_key_ui, name), add="+")
    if ui.get("blok_cursor") and active(st, me, ui):
        col, row = ui["blok_cursor"]
        cv.create_rectangle(bx+col*cell+1, by+row*cell+1, bx+(col+1)*cell-1, by+(row+1)*cell-1,
                            outline="#d4a428", width=2)


def key(ui, value):
    if ui.get("game") != "blokus":
        return
    st = ui.get("state") or {}
    if not active(st, ui.get("me"), ui):
        return "break"
    if value in ("r", "p"):
        rect = ui.get("blok_rot" if value == "r" else "blok_pass")
        if rect:
            click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
    elif value in ("bracketleft", "bracketright"):
        mine = (st.get("has_piece") or {}).get(str(ui.get("me"))) or []
        if mine:
            at = mine.index(ui["blok_pick"]) if ui.get("blok_pick") in mine else 0
            at = (at+(-1 if value == "bracketleft" else 1)) % len(mine)
            ui.update(blok_pick=mine[at], blok_oi=0, blok_page=at//max(1, ui.get("blok_capacity", 1)))
            ui["repaint"]()
    elif value in ("Up", "Down", "Left", "Right"):
        col, row = ui.get("blok_cursor", [0,0])
        dx,dy = {"Up":(0,-1),"Down":(0,1),"Left":(-1,0),"Right":(1,0)}[value]
        ui["blok_cursor"] = [max(0,min(19,col+dx)),max(0,min(19,row+dy))]
        ui["repaint"]()
    elif value == "Return":
        col,row = ui.get("blok_cursor", [0,0])
        click(ui, ui["ox"]+(col+.5)*ui["cell"], ui["oy"]+(row+.5)*ui["cell"])
    return "break"


def click(ui, x, y):
    """角斗士棋：点拼块 chip 选中 / 换方向 / 跳过 / 点棋盘空格落子。

    落子发送 {"op":"place","piece","oi","x","y"}。服务端 blokus._place 中 x
    为行偏移、y 为列偏移（位形已归一化，min r=0/min c=0），而 _cell_of 返回
    (列, 行)，故此处需交换为 (x=行, y=列)。"""
    st = ui.get("state") or {}
    if not active(st, ui.get("me"), ui) or st is not ui.get("blok_state") or ui.get("_room_context") != ui.get("blok_context"):
        return
    for key, delta in (("blok_page_prev", -1), ("blok_page_next", 1)):
        rect = ui.get(key)
        if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            ui["blok_page"] = ui.get("blok_page", 0) + delta
            ui["repaint"]()
            return
    rect = ui.get("blok_rot")
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        ots = (st.get("pieces") or {}).get(ui.get("blok_pick")) or []
        if ots:
            ui["blok_oi"] = (ui.get("blok_oi", 0) + 1) % len(ots)
            ui["repaint"]()
        return
    rect = ui.get("blok_pass")
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        ui["submit"]({"op": "pass"})
        return
    for x0, y0, x1, y1, name in ui.get("blok_chips") or ():
        if x0 <= x <= x1 and y0 <= y <= y1:
            ui["blok_pick"] = name
            ui["blok_oi"] = 0
            ui["repaint"]()
            return
    from client_gameui import _cell_of
    c = _cell_of(ui, x, y)
    if not c:
        return
    name = ui.get("blok_pick")
    if not name or name not in ((st.get("has_piece") or {}).get(str(ui.get("me"))) or []):
        return
    if not placement(st, ui.get("me"), name, ui.get("blok_oi", 0), c[1], c[0])[1]:
        return
    ui["submit"]({"op": "place", "piece": name,
                  "oi": ui.get("blok_oi", 0), "x": c[1], "y": c[0]})



from boardgames.registry import GamePackage, register
register(GamePackage(name="blokus",label="角斗士棋 · 拼筑工坊",rules="games_pkg.blokus:BlokusGame",
    desktop="boardgames.boards_blokus:paint",web_js="boardgames.boards_blokus_web:WEB_JS",web_css="boardgames.boards_blokus_web:WEB_CSS"))
