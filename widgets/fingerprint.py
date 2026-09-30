# -*- coding: utf-8 -*-
"""R36 E2EE 指纹比对窗：展示本端与对端的会话指纹（emoji 序），供人工比对防 MITM。

- 指纹来自双方各自独立派生的会话密钥前 8 字节（一致 ⇒ 信道无中间人）
- 密聊说明与「本机明文」边界同窗展示
"""
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"


class FingerprintDialog(tk.Toplevel):
    """指纹比对窗（非阻塞 Toplevel；双方屏幕各弹一个，肉眼核对 emoji 序列）。"""

    def __init__(self, master, *, peer_nick: str, fingerprint: str,
                 peer_fingerprint: str | None = None):
        super().__init__(master)
        self.title("密聊指纹核验")
        self.geometry("440x300")
        self.resizable(False, False)
        self.configure(bg="#ffffff")

        tk.Label(self, text=f"与「{peer_nick}」的密聊指纹",
                 font=(FONT_FAMILY, 11, "bold"), bg="#ffffff", fg="#222").pack(
            pady=(16, 4))

        tk.Label(self, text="本端指纹", font=(FONT_FAMILY, 9), bg="#ffffff",
                 fg="#888").pack()
        tk.Label(self, text=fingerprint or "（未建立）", font=(FONT_FAMILY, 13),
                 bg="#f2f6ff", fg="#4c7de8", padx=14, pady=8).pack(pady=(2, 10))

        if peer_fingerprint is not None:
            tk.Label(self, text="对端报告指纹", font=(FONT_FAMILY, 9),
                     bg="#ffffff", fg="#888").pack()
            match = bool(fingerprint) and fingerprint == peer_fingerprint
            tk.Label(self, text=peer_fingerprint or "（未建立）",
                     font=(FONT_FAMILY, 13), bg="#f2f6ff",
                     fg=("#2e9e5b" if match else "#d33"), padx=14, pady=8
                     ).pack(pady=(2, 6))
            tk.Label(self, text="✅ 指纹一致，信道安全" if match else
                     "⚠️ 指纹不一致！可能存在中间人，请勿信任该会话",
                     font=(FONT_FAMILY, 10, "bold"), bg="#ffffff",
                     fg=("#2e9e5b" if match else "#d33")).pack(pady=(0, 6))

        tk.Label(self, text="双方在本窗看到的 emoji 序列一致 ⇒ 通信密钥未被篡改。\n"
                            "请通过其他渠道（当面/语音）与对方核对序列。",
                 font=(FONT_FAMILY, 8), bg="#ffffff", fg="#999",
                 justify="left").pack(pady=(0, 2))
        tk.Label(self, text="边界：密聊正文端到端加密，服务器不可见；"
                            "本机历史为明文 JSONL（保搜索/重开可用）。",
                 font=(FONT_FAMILY, 8), bg="#ffffff", fg="#bbb").pack()

        tk.Button(self, text="我已核对", relief="flat", cursor="hand2",
                  font=(FONT_FAMILY, 9), fg="#ffffff", bg="#4c7de8",
                  command=self.destroy).pack(pady=(12, 14))
