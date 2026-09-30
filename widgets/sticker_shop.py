# -*- coding: utf-8 -*-
"""R35 贴纸商店：Toplevel 浏览表情包目录，一键订阅/退订。

- 数据由 ChatWindow 驱动：打开时 core.request_sticker_shop() 拉目录；
  回帧（sticker_shop_list / sticker_sub）→ refresh() 重绘
- 每包一节：包名 + 条目 emoji 预览 + 订阅/退订按钮（on_toggle 回调发帧）
- 订阅状态以 core.sticker_subs 为准（回帧带回全量，客户端只读渲染）
"""
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"


class StickerShop(tk.Toplevel):
    def __init__(self, master, *, core, on_toggle):
        super().__init__(master)
        self.core = core
        self._on_toggle = on_toggle        # on_toggle(pack_id, on) → core.send_sticker_sub
        self.title("贴纸商店")
        self.geometry("420x480")
        self.resizable(False, True)

        tk.Label(self, text="表情包商店（订阅后进入表情面板）",
                 font=(FONT_FAMILY, 9), fg="#666", anchor="w").pack(
            fill="x", padx=12, pady=(10, 4))

        self.body = tk.Frame(self, bg="#ffffff")
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        tk.Button(self, text="刷新目录", relief="flat", cursor="hand2",
                  font=(FONT_FAMILY, 9), fg="#4c7de8",
                  command=self._refetch).pack(pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()

    def _refetch(self) -> None:
        self.core.request_sticker_shop()   # 回帧驱动 refresh()

    def refresh(self) -> None:
        """按 core.sticker_shop + core.sticker_subs 全量重建（回帧后调用）。"""
        for w in self.body.winfo_children():
            w.destroy()
        packs = self.core.sticker_shop or []
        if not packs:
            tk.Label(self.body, text="目录加载中…", font=(FONT_FAMILY, 9),
                     fg="#999", bg="#ffffff").pack(pady=24)
            return
        subs = set(self.core.sticker_subs or [])
        for p in packs:
            self._pack_section(p, p.get("pack_id") in subs)

    def _pack_section(self, pack: dict, subscribed: bool) -> None:
        card = tk.Frame(self.body, bg="#f7f8fa",
                        highlightthickness=1, highlightbackground="#e3e6ea")
        card.pack(fill="x", pady=4)
        head = tk.Frame(card, bg="#f7f8fa")
        head.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(head, text=f"{pack.get('name') or pack.get('pack_id')}"
                 f"  ·  {len(pack.get('items') or [])} 枚",
                 font=(FONT_FAMILY, 10, "bold"), bg="#f7f8fa",
                 fg="#333").pack(side="left")
        tk.Button(head, text=("已订阅 ✓" if subscribed else "＋ 订阅"),
                  relief="flat", cursor="hand2", font=(FONT_FAMILY, 9),
                  fg=("#999" if subscribed else "#ffffff"),
                  bg=("#eef1f5" if subscribed else "#4c7de8"),
                  command=lambda: self._toggle(pack, subscribed)
                  ).pack(side="right")
        row = tk.Frame(card, bg="#f7f8fa")
        row.pack(fill="x", padx=10, pady=(0, 8))
        items = pack.get("items") or []
        shown = items[:12]
        for s in shown:
            tk.Label(row, text=(s or {}).get("emoji", "?"),
                     font=(FONT_FAMILY, 13), bg="#f7f8fa",
                     padx=2).pack(side="left")
        if len(items) > len(shown):
            tk.Label(row, text=f"…共 {len(items)} 枚",
                     font=(FONT_FAMILY, 8), bg="#f7f8fa",
                     fg="#999").pack(side="left", padx=4)

    def _toggle(self, pack: dict, subscribed: bool) -> None:
        pack_id = str(pack.get("pack_id") or "")
        if not pack_id:
            return
        self._on_toggle(pack_id, not subscribed)   # 发帧；回帧驱动 refresh()
