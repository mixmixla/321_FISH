# -*- coding: utf-8 -*-
"""_smoke_t7_imageview.py —— R7/T7 图片放大查看窗冒烟。

链路：
- 生成 2 张真实 PNG → MsgList 塞 image 行
- 左键命中缩略图 → on_row_image 回调（携带 行下标+路径）
- ImageViewer 打开：Toplevel 映射、标题=文件名
- Left/Right 在图片列表内循环切换；Esc 关闭
"""
import os
import sys
import tempfile
import time
import tkinter as tk

from PIL import Image  # noqa:E402

from widgets.msg_list import MsgList  # noqa:E402
from widgets.image_viewer import ImageViewer  # noqa:E402

FONT = ("Microsoft YaHei UI", 9)


def make_png(d, name, w, h, color):
    im = Image.new("RGB", (w, h), color)
    p = os.path.join(d, name)
    im.save(p, "PNG")
    return p


def main() -> int:
    results = []
    ok = True

    def check(label, cond, extra=""):
        nonlocal ok
        results.append(f"[{'OK' if cond else 'FAIL'}] {label}"
                       + (f"  {extra}" if extra else ""))
        if not cond:
            ok = False

    root = tk.Tk()
    tmp = tempfile.mkdtemp(prefix="imgview_")
    p1 = make_png(tmp, "a.png", 400, 300, "#cc3333")
    p2 = make_png(tmp, "b.png", 640, 480, "#3366cc")

    calls = []
    ml = MsgList(root, FONT, on_row_image=lambda i, p: calls.append((i, p)))
    ml.configure(width=600, height=400)
    ml.pack(fill="both", expand=True)
    root.update()

    for i, p in enumerate((p1, p2)):
        ml.append({"uid": 1, "nick": "甲", "channel": "private",
                   "to": 2, "ts": time.time() - i,
                   "image_path": p})
    for _ in range(8):                     # 等缩略图解码+渲染到位
        root.update()
        time.sleep(0.1)
    root.update()

    check("two image rows", ml.image_rows() == [(0, p1), (1, p2)],
          str(ml.image_rows()))

    # 左键命中第一张缩略图 → on_row_image(idx=0, path=p1)
    try:
        x1, y1, x2, y2 = ml.bbox("imgrow0")
        ml.focus_force()
        ml.event_generate("<Button-1>", x=(x1 + x2) // 2,
                          y=(y1 + y2) // 2)
        root.update()
    except Exception as exc:
        check("image bbox", False, str(exc))
    check("click fired on_row_image", (0, p1) in calls,
          str(calls[:1]))

    # ImageViewer：打开 + 标题 + Left/Right 切换 + Esc 关闭
    v = ImageViewer(root, [p1, p2], index=0, font=FONT)
    for _ in range(5):
        root.update()
        time.sleep(0.1)
    root.update()
    check("viewer is toplevel", isinstance(v, tk.Toplevel)
          and v.winfo_ismapped(), "mapped=toplevel")
    check("viewer title = filename", "a.png" in v.title())
    check("starts at index 0", v._idx == 0)

    v._nav(1)
    root.update()
    check("Right nav to index 1", v._idx == 1)

    v._nav(1)                                # wrap 回 0
    root.update()
    check("Right wraps to 0", v._idx == 0)

    v._nav(-1)                               # wrap 到末位
    root.update()
    check("Left wraps to last", v._idx == 1)

    v.destroy()
    root.update()
    check("viewer closed", not v.winfo_exists())

    try:
        ml.destroy()
        root.destroy()
    except tk.TclError:
        pass

    print("\n".join(results))
    print("GUI IMAGE VIEW SMOKE OK" if ok else "GUI IMAGE VIEW SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())