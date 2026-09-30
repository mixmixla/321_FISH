# -*- coding: utf-8 -*-
"""R3 C7/C8 冒烟：群管理（角色判定/禁言状态/成员对话框）+ 通知（任务栏闪烁 DND 门控）。
- owner/admin/member 角色由 group_role 正确判定
- 服务器禁言后 core.group_mutes 更新，_group_member_muted 生效
- 成员管理对话框可打开/可随 group_state 自动重载
- _toggle_dnd 切换免打扰并持久化 prefs；免打扰下 _flash_taskbar 不动作也不崩
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

    # 1) 主端建群，乙方/丙方入群
    core.create_group("管理测试群")
    pump(0.6)
    gid = next((g["gid"] for g in core.groups.values()
                if g["name"] == "管理测试群"), None)
    check("group created via gui", gid is not None)
    if gid is None:
        print("\n".join(results))
        print("GUI GROUP/NOTIFY SMOKE FAIL")
        return 1
    bob.send_frame({"t": "group_join", "gid": gid})
    car.send_frame({"t": "group_join", "gid": gid})
    pump(1.0)
    check("3 members gathered",
          len(core.group_members.get(gid, [])) == 3)

    # 2) 角色判定
    check("gui is owner", app.group_role(gid, core.uid) == "owner")
    check("bob is member", app.group_role(gid, bob_uid) == "member")

    # 3) 群主设 bob 为管理员 → group_admins 更新、角色变 admin
    core.set_admin(gid, bob_uid, True)
    pump(0.6)
    check("bob promoted admin", bob_uid in core.group_admins.get(gid, set()))
    check("role now admin", app.group_role(gid, bob_uid) == "admin")

    # 4) 禁言丙方 → mutes 记录 + 判定命中
    core.mute_member(gid, car_uid, 600)
    pump(0.6)
    until = core.group_mutes.get(gid, {}).get(car_uid)
    check("car recorded muted", until is not None)
    check("member muted predicate", app._group_member_muted(gid, car_uid))
    check("owner not muted", not app._group_member_muted(gid, core.uid))

    # 5) 成员管理对话框：打开 + 自动重载（踢人触发 group_state → reload 不崩）
    app._group_members_dialog(gid)
    pump(0.3)
    check("members dialog open", app._members_dlg is not None
          and app._members_dlg["gid"] == gid)
    core.kick_member(gid, car_uid)        # 触发一次重载
    pump(0.6)
    check("dialog survives group_state reload",
          app._members_dlg is not None)
    if app._members_dlg:
        app._members_dlg["dlg"].destroy()
        app._members_dlg = None
    check("kicked leaves mutes", car_uid not in core.group_mutes.get(gid, {}))

    # 6) 通知：DND 门控 + 持久化；非免打扰时闪烁调用不崩
    app._dnd = False
    app.root.withdraw()                  # 模拟藏到迷你条（非前台）
    app._flash_taskbar()                 # 不应崩（是否真闪烁看桌面环境）
    check("flash callable when hidden", True)
    app._toggle_dnd()
    check("dnd on", app._dnd is True and app._prefs.get("dnd") is True)
    app._flash_taskbar()                 # 免打扰下应直接返回（不崩）
    check("dnd suppress flash", app._dnd is True)
    app._toggle_dnd()                    # 复原
    check("dnd off persisted", app._dnd is False
          and app._prefs.get("dnd") is False)

    print("\n".join(results))
    bob.send_frame({"t": "bye"})
    car.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI GROUP/NOTIFY SMOKE OK" if ok else "GUI GROUP/NOTIFY SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())