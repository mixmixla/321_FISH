# -*- coding: utf-8 -*-
"""R49 网页端桌游回归：REST 映射 GAME 帧 + rps 字符串出拳修复 + nicks 映射。

数据通路：网页 POST /api/game → hub.dispatch(GAME_*) → 服务器权威推进 →
SSE 推回 game_list / game_state / game_private（私密只发成员）。
覆盖：
- REST /api/game：create/join/spectate/leave/start/action 全映射 + 鉴权/参数校验；
- REST /api/game_list：大厅初始快照（游戏元数据 + 房间列表）；
- 规则错误经 error 帧（code="game"）异步回推，REST 本身 200；
- rps：桌面端字符串出拳（rock/paper/scissors，大小写/空白兼容）+ snapshot 始终
  携带最近一轮 matches/byes（旧实现结果不可见的修复）；
- game_state 载荷 nicks 字段（uid→昵称，网页端房间渲染依赖）；
- uno private 并行 hand_ids（网页端点牌出牌依赖，桌面端忽略未知键）。
"""
import json
import socket
import threading
import time
import http.client
from dataclasses import replace

import pytest

from config import CFG
from games_pkg import GAME_META
from games_pkg.base import GameRuleError
from games_pkg.rps import RpsGame
from games_pkg.uno import UnoGame
from protocol import MsgType
from server import Hub, serve as serve_tcp
from web import COOKIE_NAME, serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def env(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    tcp_port = _free_port()
    web_port = _free_port()
    stop_tcp = threading.Event()
    stop_web = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, tcp_port, stop_tcp, False),
                     daemon=True).start()
    threading.Thread(target=serve_web, args=(h, web_port, stop_web, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, tcp_port, web_port
    stop_web.set()
    stop_tcp.set()
    time.sleep(0.2)


class _Web:
    """轻量 HTTP 客户端（Cookie 登录态）。"""

    def __init__(self, port):
        self.port = port
        self.cookie = ""
        self.uid = None

    def _post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request("POST", path, json.dumps(body).encode(), headers)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        sc = r.getheader("Set-Cookie") or ""
        conn.close()
        if sc.startswith(f"{COOKIE_NAME}="):
            self.cookie = sc.split(";")[0]
        return r.status, data

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"Cookie": self.cookie} if self.cookie else {}
        conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick):
        status, data = self._post("/api/login", {"nick": nick})
        assert status == 200 and data.get("ok"), data
        self.uid = data["uid"]
        return data

    def game(self, op, **extra):
        return self._post("/api/game", dict(op=op, **extra))


def _capture(h, uid) -> list:
    """打桩 hub 内 Session.send，捕获推送给该会话的所有帧（模拟 SSE 消费端）。"""
    sess = h.sessions[uid]
    box = []
    sess.send = box.append
    return box


def _take(box, t, pred=None):
    """取出第一个匹配帧（从捕获队列移除），没有返回 None。"""
    for i, p in enumerate(box):
        if p.get("t") == t and (pred is None or pred(p)):
            return box.pop(i)
    return None


def _onwire(payload: dict) -> dict:
    """JSON 序列化往返（模拟 SSE/TCP 线上格式：int 键变字符串）。"""
    return json.loads(json.dumps(payload))


# ============ REST /api/game：映射与校验 ============

def test_rest_create_room_and_lobby_snapshot(env):
    """create → 房间建立；大厅快照含游戏元数据与房间；game_state 带 nicks。"""
    h, _tcp, web_port = env
    w = _Web(web_port)
    w.login("甲")
    box = _capture(h, w.uid)
    status, data = w.game("create", game="gomoku")
    assert status == 200 and data["ok"], data

    gs = _take(box, "game_state")
    assert gs is not None, "create 后未收到 game_state"
    room = gs["room"]
    assert room["game"] == "gomoku" and room["status"] == "created"
    assert room["players"] == [w.uid] and room["owner_uid"] == w.uid
    # R49：nicks 映射（uid→昵称），线上格式键为字符串
    nicks = _onwire(gs)["nicks"]
    assert nicks.get(str(w.uid)) == "甲"

    status, lobby = w._get("/api/game_list")
    assert status == 200 and lobby["ok"]
    assert len(lobby["games"]) == len(GAME_META)
    meta = {g["name"]: g for g in lobby["games"]}
    assert "gomoku" in meta and meta["gomoku"]["min"] == 2
    assert any(r["room_id"] == room["room_id"] for r in lobby["rooms"])


def test_rest_unauthenticated_401(env):
    """未登录：/api/game 与 /api/game_list 均 401。"""
    _h, _tcp, web_port = env
    w = _Web(web_port)                      # 不登录
    status, data = w.game("create", game="gomoku")
    assert status == 401 and not data["ok"]
    status, data = w._get("/api/game_list")
    assert status == 401 and not data["ok"]


def test_rest_unknown_op_400(env):
    """未知 op 同步 400，不进 dispatch。"""
    _h, _tcp, web_port = env
    w = _Web(web_port)
    w.login("乙")
    status, data = w.game("teleport")
    assert status == 400 and "未知操作" in data["error"]


def test_rest_action_not_dict_400(env):
    """action 非法（非 dict）同步 400。"""
    _h, _tcp, web_port = env
    w = _Web(web_port)
    w.login("丙")
    status, data = w._post("/api/game", {"op": "action", "room_id": "g1",
                                         "action": "x:7,y:7"})
    assert status == 400 and "动作格式错误" in data["error"]


# ============ REST 全链路：join/start/action ============

def test_rest_join_start_action_full_flow(env):
    """五子棋：建房→加入→开局→落子，公开快照经 SSE 推给双方成员。"""
    h, _tcp, web_port = env
    w1, w2 = _Web(web_port), _Web(web_port)
    w1.login("甲"), w2.login("乙")
    box1 = _capture(h, w1.uid)              # 先打桩再 create，才能捕获推送
    assert w1.game("create", game="gomoku")[1]["ok"]
    rid = _take(box1, "game_state")["room_id"]

    box2 = _capture(h, w2.uid)
    assert w2.game("join", room_id=rid)[1]["ok"]
    assert _take(box2, "game_state")["room"]["players"] == [w1.uid, w2.uid]

    assert w1.game("start", room_id=rid)[1]["ok"]
    st = _take(box2, "game_state", lambda p: p.get("state"))
    assert st is not None and st["room"]["status"] == "playing"
    assert st["state"]["game"] == "gomoku"
    assert st["state"]["turn_uid"] == w1.uid
    assert len(st["state"]["board"]) == 15

    # w1 落子 → w2 收到更新后的棋盘
    assert w1.game("action", room_id=rid, action={"x": 7, "y": 7})[1]["ok"]
    st = _take(box2, "game_state", lambda p: p.get("state"))
    assert st["state"]["board"][7][7] == 1
    assert st["state"]["turn_uid"] == w2.uid


def test_rest_out_of_turn_rule_error_to_sse(env):
    """规则违规：REST 已 200（异步），错误经 error 帧（code=game）回推。"""
    h, _tcp, web_port = env
    w1, w2 = _Web(web_port), _Web(web_port)
    w1.login("甲"), w2.login("乙")
    box1 = _capture(h, w1.uid)
    w1.game("create", game="gomoku")
    rid = _take(box1, "game_state")["room_id"]
    w2.game("join", room_id=rid)
    w1.game("start", room_id=rid)

    assert w1.game("action", room_id=rid, action={"x": 7, "y": 7})[1]["ok"]
    assert w1.game("action", room_id=rid, action={"x": 8, "y": 8})[1]["ok"]
    err = _take(box1, "error", lambda p: p.get("code") == "game")
    assert err is not None, "违规落子未收到 error 帧"
    assert "还没轮到你" in err["text"]


def test_rest_spectate_and_action_denied(env):
    """观战：进观众席、收得到状态，但动作被拒。"""
    h, _tcp, web_port = env
    w1, w2 = _Web(web_port), _Web(web_port)
    w1.login("甲"), w2.login("乙")
    box1 = _capture(h, w1.uid)
    w1.game("create", game="gomoku")
    rid = _take(box1, "game_state")["room_id"]

    box2 = _capture(h, w2.uid)
    assert w2.game("spectate", room_id=rid)[1]["ok"]
    room = _take(box2, "game_state")["room"]
    assert room["players"] == [w1.uid] and room["spectators"] == [w2.uid]

    assert w2.game("action", room_id=rid, action={"x": 7, "y": 7})[1]["ok"]
    err = _take(box2, "error", lambda p: p.get("code") == "game")
    assert err is not None and "观战者不能操作" in err["text"]


def test_rest_leave_updates_room(env):
    """离房：成员列表更新并广播；全员离开后房间关闭。"""
    h, _tcp, web_port = env
    w1, w2 = _Web(web_port), _Web(web_port)
    w1.login("甲"), w2.login("乙")
    box1 = _capture(h, w1.uid)
    w1.game("create", game="gomoku")
    rid = _take(box1, "game_state")["room_id"]

    w2.game("join", room_id=rid)
    assert w2.game("leave", room_id=rid)[1]["ok"]
    _take(box1, "game_state", lambda p: p["room"]["room_id"] == rid)  # join 帧
    room = _take(box1, "game_state", lambda p: p["room"]["room_id"] == rid)["room"]
    assert room["players"] == [w1.uid]

    # 甲离开 → 空房自动关闭，大厅不再列出
    w1.game("leave", room_id=rid)
    _s, lobby = w1._get("/api/game_list")
    assert not any(r["room_id"] == rid for r in lobby["rooms"])


def test_rest_sync_reentry(env):
    """sync：已是成员重进/刷新后补拉状态；非成员与未知房间报错。"""
    h, _tcp, web_port = env
    w1, w2, w3 = _Web(web_port), _Web(web_port), _Web(web_port)
    w1.login("甲"), w2.login("乙"), w3.login("丙")
    box1 = _capture(h, w1.uid)
    w1.game("create", game="gomoku")
    rid = _take(box1, "game_state")["room_id"]
    w2.game("join", room_id=rid)

    # 成员 sync → 收到最新房间状态（页面刷新后的唯一恢复路径）
    box2 = _capture(h, w2.uid)
    assert w2.game("sync", room_id=rid)[1]["ok"]
    gs = _take(box2, "game_state", lambda p: p["room"]["room_id"] == rid)
    assert gs is not None and gs["room"]["players"] == [w1.uid, w2.uid]

    # 对局中途 sync：快照一并补发
    w1.game("start", room_id=rid)
    box3 = _capture(h, w1.uid)
    assert w1.game("sync", room_id=rid)[1]["ok"]
    st = _take(box3, "game_state", lambda p: p.get("state"))
    assert st is not None and st["state"]["game"] == "gomoku"

    # 非成员 sync → error 帧
    box4 = _capture(h, w3.uid)
    assert w3.game("sync", room_id=rid)[1]["ok"]
    err = _take(box4, "error", lambda p: p.get("code") == "game")
    assert err is not None and "你不在该房间" in err["text"]

    # 未知房间 → error 帧
    assert w3.game("sync", room_id="g999")[1]["ok"]
    err = _take(box4, "error", lambda p: p.get("code") == "game")
    assert err is not None and "你不在该房间" in err["text"]


# ============ 桌面端（TCP）兼容：nicks 为附加字段可忽略 ============

class _Cli:
    """TCP 加密客户端。"""

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                hdr, _body = self.chan.recv_frame()
                with self._lock:
                    self.events.append(hdr)
        except Exception:
            pass

    def send(self, header):
        self.chan.send_frame(header, b"")

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, h in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h
            time.sleep(0.01)
        return None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        hdr = self.wait("welcome")
        if hdr:
            self.uid = hdr["uid"]
        return hdr

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def test_tcp_desktop_game_state_compat(env):
    """桌面端走 GAME_CREATE 一样建房，game_state 附带 nicks（未知键可忽略）。"""
    _h, tcp_port, _web = env
    a = _Cli(tcp_port, "桌友")
    try:
        assert a.hello()
        a.send({"t": MsgType.GAME_CREATE.value, "game": "gomoku"})
        gs = a.wait("game_state", timeout=3.0)
        assert gs is not None, "桌面端建房未收到 game_state"
        assert gs["room"]["game"] == "gomoku"
        assert _onwire(gs)["nicks"].get(str(a.uid)) == "桌友"
    finally:
        a.close()


# ============ rps：字符串出拳兼容 + snapshot 结果可见修复 ============

def test_rps_string_choices_unit():
    """字符串出拳（含大小写/空白）映射为 0/1/2；非法串与旧整数行为不变。"""
    g = RpsGame([1, 2, 3], seed=1)
    g.act(1, {"choice": "rock"})            # 0
    g.act(2, {"choice": " PAPER "})         # 1（空白+大写）
    with pytest.raises(GameRuleError):
        g.act(3, {"choice": "lizard"})      # 非法串
    g.act(3, {"choice": 2})                 # 整数路径不变
    assert g.round == 1 and len(g.matches) == 1 and g.byes == [3]
    m = g.matches[0]
    assert (m["a"], m["b"]) in ((1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2))
    # 布(1) 胜 石头(0)：ca/cb 已是整数
    pair = {m["ca"], m["cb"]}
    assert pair == {0, 1} and m["winner"] != -1


def test_rps_rest_round_strings_and_snapshot_fix():
    """整局字符串出拳：resolve 后 snapshot 仍携带 matches/byes（R49 修复）。"""
    g = RpsGame([1, 2, 3], seed=1)
    g.act(1, {"choice": "rock"})
    g.act(2, {"choice": "scissors"})        # 石头胜剪刀
    g.act(3, {"choice": "paper"})
    snap = json.loads(json.dumps(g.snapshot()))
    assert snap["matches"], "resolve 后 snapshot 丢失对战结果（旧 bug）"
    assert len(snap["matches"]) == 1 and snap["byes"] == [3]
    assert all(m["ca"] in (0, 1, 2) and m["cb"] in (0, 1, 2)
               for m in snap["matches"])


# ============ uno：private 并行 hand_ids ============

def test_uno_private_hand_ids():
    """private 含 hand_ids 与 hand 等长对齐，供网页端点牌；id 唯一且合法。"""
    g = UnoGame([1, 2], seed=7)
    priv = g.private(1)
    assert priv is not None and len(priv["hand"]) == 7
    ids = priv["hand_ids"]
    assert len(ids) == 7 and len(set(ids)) == 7
    assert all(isinstance(i, int) and 0 <= i <= 107 for i in ids)
    # 观战者/非成员无私密
    assert g.private(99) is None


def test_uno_play_by_id_via_manager():
    """网页端动作通路：act 用 {"card": id} 出牌，与 hand_ids 对齐。"""
    g = UnoGame([1, 2], seed=7)
    priv = g.private(1)
    assert priv and len(priv["hand_ids"]) == len(g.hands[1])
    playable = [c for c in g.hands[1] if g._playable(c)]
    if not playable:                        # 起手无可出牌则摸一张再试
        g._give_cards(1, 1)
        playable = [c for c in g.hands[1] if g._playable(c)]
    assert playable
    card = playable[0]
    n_before = len(g.hands[1])
    msgs = g.act(1, {"card": card["id"], "color": card["color"] or "red"})
    assert msgs and len(g.hands[1]) == n_before - 1
    assert g.discard[-1]["id"] == card["id"]


# ============ SSE 连接级 fanout：多连接/刷新不再互偷帧 ============

def test_web_send_fanout(env):
    """R49 丢帧根因回归：预连接缓冲搬运、双连接广播各得一份、detach 回缓冲。

    旧实现全会话单队列由唯一 SSE drain，刷新时旧连接未断/多开会多消费者
    竞争同一队列随机偷帧（game_state 偶发丢失）。"""
    import queue as _q
    h, _tcp, _web = env
    sess, _tok = h.login_web("扇出员", "127.0.0.1")
    assert sess is not None

    def drain_until(q, t):
        """按类型取帧（跳过混入的 roster/system 等广播），2s 超时返回 None。"""
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                p = q.get(timeout=0.2)[0]
            except _q.Empty:
                continue
            if p.get("t") == t:
                return p
        return None

    def drain_all(q):
        while True:
            try:
                q.get_nowait()
            except _q.Empty:
                return

    c1, c2 = _q.Queue(), _q.Queue()

    # 1) 无 SSE 连接：帧进预连接缓冲
    sess.send({"t": "welcome", "uid": sess.uid})

    # 2) attach 搬运存量（welcome 及混入的登录广播都不丢）
    sess.send.attach(c1)
    assert drain_until(c1, "welcome") is not None, "预连接缓冲未搬运"

    # 3) 双连接广播：两连接各得一份（不互偷）
    sess.send.attach(c2)
    sess.send({"t": "game_state", "room_id": "g1"})
    assert drain_until(c1, "game_state") is not None, "c1 未收到广播帧"
    assert drain_until(c2, "game_state") is not None, "c2 未收到广播帧"

    # 4) detach c1（页面关闭/刷新）：之后只有 c2 收到
    drain_all(c1)
    sess.send.detach(c1)
    sess.send({"t": "roster"})
    assert drain_until(c2, "roster") is not None, "c2 未收到帧"
    time.sleep(0.2)
    assert c1.empty(), "已 detach 的连接仍收到帧"

    # 5) 全部 detach：回到预连接缓冲，新连接 attach 时搬运
    sess.send.detach(c2)
    sess.send({"t": "system", "text": "x"})
    sess.send.attach(c1)
    assert drain_until(c1, "system") is not None, "缓冲帧未随新连接搬运"
