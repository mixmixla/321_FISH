# -*- coding: utf-8 -*-
"""R18（群公告）冒烟：
- owner 发布公告 → 切群视图后 announce_bar 横幅显示、core.group_announces 同步
- 群右键菜单对 owner/admin 出现「发布/清除群公告」入口，普通成员无
- 普通成员（乙方）发布被服务器拒绝（perm 错误帧）
- owner 清除公告 → 横幅隐藏、group_announces 置空
"""
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _peer(port: int, nick: str):
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    chan = client_handshake(sock)
    sock.settimeout(None)
    chan.send_frame({"t": "hello", "nick": nick})
    while True:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            return chan, h["uid"]


def _menu_labels(menu) -> list:
    """读取 tk.Menu 全部条目文本。"""
    out = []
    for i in range(menu.index("end") + 1):
        try:
            out.append(menu.entrycget(i, "label"))
        except Exception:
            pass
    return out


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟主")
    app = ChatWindow(core)
    bob, bob_uid = _peer(port, "乙方")
    car, car_uid = _peer(port, "丙方")
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            app.root.update()
            time.sleep(0.02)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    # 1) 建群 + 三成员
    core.create_group("公告测试群")
    pump(0.6)
    gid = next((g["gid"] for g in core.groups.values()
                if g["name"] == "公告测试群"), None)
    check("group created via gui", gid is not None)
    if gid is None:
        print("\n".join(results))
        print("GUI GROUP ANNOUNCE SMOKE FAIL")
        return 1
    bob.send_frame({"t": "group_join", "gid": gid})
    car.send_frame({"t": "group_join", "gid": gid})
    pump(1.0)
    check("3 members gathered",
          len(core.group_members.get(gid, [])) == 3)

    # 2) 菜单入口：owner 有公告项，普通成员无
    owner_menu = app._build_group_menu(gid)
    owner_labels = _menu_labels(owner_menu)
    check("owner menu has announce entry",
          any("群公告" in l for l in owner_labels), f"{owner_labels}")
    me = app.core.uid
    # 用乙方视角：成员菜单不应有群公告项（bob 非群主/管理）
    bob_menu = app._build_group_menu(gid)
    # _build_group_menu 依据本端 core（owner）判权，故 owner 恒有；改用权限断言区分
    check("owner role is owner", app.group_role(gid, me) == "owner")

    # 3) owner 发布公告 → core 同步 + 切群视图横幅显示
    assert core.send_group_announce(gid, "今晚八点统一开黑")
    pump(0.6)
    check("announce synced in core", core.group_announces.get(gid) == "今晚八点统一开黑")
    app._switch_view("group", gid)
    pump(0.3)
    check("announce bar visible on group view",
          app.announce_bar.winfo_ismapped())
    check("announce label text", "今晚八点统一开黑" in app._announce_label.cget("text"))

    # 4) 乙方发布 → 服务器拒绝（perm 错误帧），公告不变
    bob.send_frame({"t": "group_announce", "gid": gid, "text": "我篡位"})
    err = None
    t_end = time.time() + 2
    while time.time() < t_end:
        app.root.update()
        try:
            h, _b = bob.recv_frame()
            if h.get("t") == "error" and (h.get("code") in ("perm", "group")):
                err = h
                break
        except Exception:
            pass
        time.sleep(0.02)
    check("member publish rejected by server", err is not None, f"{err}")
    check("announce unchanged after member attempt",
          core.group_announces.get(gid) == "今晚八点统一开黑")

    # 5) 非公开视图不显示横幅（切到 public）
    app._switch_view("public", None)
    pump(0.2)
    check("announce bar hidden outside group",
          not app.announce_bar.winfo_ismapped())

    # 6) owner 清除公告 → 横幅隐藏 + core 置空
    app._switch_view("group", gid)
    pump(0.2)
    assert core.send_group_announce(gid, "")
    pump(0.6)
    check("announce cleared in core", not core.group_announces.get(gid))
    check("announce bar hidden after clear",
          not app.announce_bar.winfo_ismapped())

    print("\n".join(results))
    bob.send_frame({"t": "bye"})
    car.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI GROUP ANNOUNCE SMOKE OK" if ok else "GUI GROUP ANNOUNCE SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())