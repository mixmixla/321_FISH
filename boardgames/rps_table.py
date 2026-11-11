"""Presentation of the three simultaneous choices in their wire order."""

from boardgames.card_table_tk import art, hit, text


# Index is the choice sent to RpsGame and the column in the illustration.
HANDS = (("石头", "✊", "#e55d59"), ("布", "✋", "#46b4a8"), ("剪刀", "✌", "#927bd1"))
ATLAS = "rps-hands.webp"


def can_choose(state, uid):
    return (state.get("status") == "collecting" and uid in state.get("players", ())
            and uid not in state.get("submitted", ()))


def click(ui, x, y):
    for choice, rect in enumerate(ui.get("rps_cards", ())):
        if hit(rect, x, y):
            ui["submit"]({"choice": choice})
            return


def paint(cv, state, me, nick, submit, repaint, ui, priv, w, h):
    cv.create_rectangle(0, 0, w, h, fill="#fff8ec", outline="")
    players = state.get("players", ())
    sent = state.get("submitted", ())
    round_no = state.get("round", 0)
    ready = can_choose(state, me)
    room = ui.get("room") or {}
    active = (ready and not ui.get("rps_sending") and ui.get("connected", True)
              and room.get("status", "playing") == "playing")
    matches = state.get("matches") or ()
    byes = state.get("byes") or ()
    summary_rows = len(matches) + bool(byes)
    ui["rps_cards"] = []
    text(cv, 12, 17, "石头剪刀布", 13, "#322e46", bold=True)
    text(cv, w-12, 17, f"第 {round_no+1} 轮  ·  已出拳 {len(sent)}/{len(players)}",
         9, "#504763", "e")
    if me in sent or ui.get("rps_sending"):
        note = "已出拳，等待其他玩家"
    elif me not in players:
        note = "观战中"
    elif active:
        note = "点一张牌出拳，或在棋盘按 1 / 2 / 3"
    else:
        note = "等待本轮出拳"
    text(cv, w/2, 39, note, 9, "#605670", "center")

    scores = state.get("scores") or {}
    score_line = "　".join(f"{nick(uid)} {scores.get(uid, scores.get(str(uid), 0))}"
                         for uid in players)
    start = 53
    result_space = min(98, 22 + 20*summary_rows, h*0.27) if summary_rows else 0
    end = max(start+24, h-result_space-28)
    height = min(305, end-start)
    width = min((w-30)/3, max(56, height*0.64))
    gap = min(10, w*0.016)
    x0 = (w-width*3-gap*2)/2
    for choice, (label, sign, color) in enumerate(HANDS):
        x = x0 + choice*(width+gap)
        rect = x, start, x+width, start+height
        cv.create_rectangle(*rect, fill="#fffdf6", outline=color, width=2)
        image_bottom = max(start+4, rect[3]-25)
        if not art(cv, ATLAS, choice, 3, 1, (x+2,start+2,x+width-2,image_bottom), contain=True):
            text(cv, x+width/2, (start+image_bottom)/2, sign, 18, color, "center")
        text(cv, x+width/2, rect[3]-12, f"{choice+1}  {label}", 10, "#302d43", "center", True)
        if active:
            ui["rps_cards"].append(rect)
    text(cv, w/2, end+13, score_line, 9, "#504763", "center", width=max(50,w-16))
    if not summary_rows:
        return
    y = end+32
    text(cv, 12, y, f"上轮战报 · 第 {round_no} 轮", 9, "#40374d", bold=True)
    def result_hand(value):
        return HANDS[value][0] if type(value) is int and 0 <= value < len(HANDS) else "未出拳"
    rows = []
    for match in matches:
        winner = match.get("winner")
        outcome = f"🏆 {nick(winner)} 胜" if winner not in (None, -1) else "（平）"
        rows.append(f"{nick(match['a'])} {result_hand(match.get('ca'))}　·　"
                    f"{nick(match['b'])} {result_hand(match.get('cb'))}　{outcome}")
    if byes:
        rows.append("、".join(nick(uid) for uid in byes) + " 轮空")
    for line in rows:
        y += 18
        if y > h-5:
            break
        text(cv, 12, y, line, 9, "#504763", width=max(50,w-24))
