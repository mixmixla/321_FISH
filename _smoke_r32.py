# -*- coding: utf-8 -*-
"""R32（Telegram 细节补齐）冒烟：
- A1 拖拽：enable_dropfiles 真实注册 + _on_drop_files 确认后分发（图片前置/首图带 caption/输入框清空）
- A2 输入框：真实 Text 多行 → 自适应 6 行；清空 → 收回 1 行
- B3 caption：MsgList 图下说明渲染与高度
- B4 壁纸：set_wallpaper 应用/恢复/换肤保留
"""
import os
import sys
import tempfile
import time
import tkinter as tk
from types import MethodType, SimpleNamespace

import client as client_mod
from client import ChatWindow
from widgets.msg_list import MsgList
from widgets.dropfiles import enable_dropfiles

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


def _is_image(p):
    return os.path.splitext(p)[1].lower() in IMG_EXT   # 与 client.is_image_path 同参


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="r32_")
    root = tk.Tk()
    root.geometry("640x480")

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    def pump(secs):
        t = time.time() + secs
        while time.time() < t:
            root.update()
            time.sleep(0.02)

    # ---------- A1 拖拽注册 ----------
    dropped = []
    check("dropfiles 注册成功", enable_dropfiles(root, lambda ps: dropped.append(ps)))
    check("proc 引用保持", getattr(root, "_dropfiles_proc", None) is not None)

    # ---------- A2 输入框自适应（真实 Text） ----------
    entry = tk.Text(root, height=1, wrap="word")
    entry.pack(fill="x")
    host_e = SimpleNamespace(entry=entry)
    host_e._adjust_entry_height = MethodType(ChatWindow._adjust_entry_height, host_e)
    entry.insert("1.0", "\n".join(f"第{i}行内容" for i in range(9)))
    host_e._adjust_entry_height()
    check("多行 → 6 行钳制", int(entry.cget("height")) == 6,
          f"h={entry.cget('height')}")
    entry.delete("1.0", "end")
    host_e._adjust_entry_height()
    check("清空 → 收回 1 行", int(entry.cget("height")) == 1,
          f"h={entry.cget('height')}")

    # ---------- A1 分发（stub host 挂 _on_drop_files） ----------
    sent = []
    sys_lines = []
    entry2 = tk.Text(root, height=1)
    img1 = os.path.join(tmp, "a.png")
    img2 = os.path.join(tmp, "b.png")
    doc = os.path.join(tmp, "c.txt")
    try:
        from PIL import Image
        Image.new("RGB", (40, 30), (0, 200, 100)).save(img1)
        Image.new("RGB", (40, 30), (200, 100, 0)).save(img2)
    except Exception as e:
        print(f"[FAIL] 生成测试图失败: {e}")
        return 1
    open(doc, "w", encoding="utf-8").write("x")

    host = SimpleNamespace(
        root=root,
        view=("private", 7),
        entry=entry2,
        _entry_text=lambda: entry2.get("1.0", "end-1c"),
        _append_sys=lambda t: sys_lines.append(t),
        core=SimpleNamespace(roster={7: {"nick": "同事甲"}}, nick="我",
                             uid=1,
                             files=SimpleNamespace(
                                 send_file=lambda p, to, caption="":
                                 sent.append((p, caption)) or "fid")),
        _send_attachment=lambda p, to, nick, caption="":
        sent.append((p, caption, to, nick)),
    )
    host._on_drop_files = MethodType(ChatWindow._on_drop_files, host)

    orig_ask = client_mod.messagebox.askyesno
    client_mod.messagebox.askyesno = lambda *a, **k: True
    try:
        entry2.insert("1.0", "这是图片说明")
        host._on_drop_files([img1, img2, doc])
    finally:
        client_mod.messagebox.askyesno = orig_ask
    check("确认后逐个发送", len(sent) == 3, str(len(sent)))
    check("图片前置", _is_image(sent[0][0]) and _is_image(sent[1][0])
          and not _is_image(sent[2][0]))
    check("首图带 caption", sent[0][1] == "这是图片说明", str(sent[0][1]))
    check("次图/文件不带 caption", sent[1][1] == "" and sent[2][1] == "")
    check("输入框 caption 已清空", entry2.get("1.0", "end-1c") == "")

    client_mod.messagebox.askyesno = lambda *a, **k: False
    try:
        sent.clear()
        host._on_drop_files([img1])
    finally:
        client_mod.messagebox.askyesno = orig_ask
    check("拒绝后不发送", sent == [])

    # 非私聊兜底
    host.view = ("public", None)
    sys_lines.clear()
    host._on_drop_files([img1])
    check("非私聊提示", any("仅限私聊" in t for t in sys_lines))

    # ---------- B3 caption 渲染 ----------
    ml = MsgList(root, font=("Microsoft YaHei", 10), me_uid=1)
    ml.pack_forget()
    ml.configure(width=480, height=400)
    ml.pack(fill="both", expand=True)
    ml.append({"seq": 1, "uid": 2, "nick": "同事甲", "channel": "private",
               "image_path": img1, "text": "截图说明：这是测试图片",
               "ts": time.time()})
    pump(0.5)
    check("caption 行提取", ml._rows[0].caption == "截图说明：这是测试图片")
    check("caption 行高含说明", ml._heights[0] > ml._linespace + 3 * ml.PAD_TOP)
    check("caption 渲染无崩", bool(ml._item_ids))
    ml.clear()

    # ---------- B4 壁纸 ----------
    default_bg = ml.cget("bg")
    ml.set_wallpaper("#e8dcc8")
    check("壁纸应用", ml.cget("bg") == "#e8dcc8")
    ml.set_colors({"bg": "#111111"})     # 模拟换深色皮肤
    check("换肤保留壁纸", ml.cget("bg") == "#e8dcc8")
    ml.set_wallpaper(None)
    check("清壁纸回新主题", ml.cget("bg") == "#111111"
          and default_bg != "#111111")

    pump(0.2)
    root.destroy()

    print("\n".join(results))
    print("R32 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
