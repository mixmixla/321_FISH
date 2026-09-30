# -*- coding: utf-8 -*-
"""扫描：file_progress 事件处理 / 文件消息行 / 接收文件路径。"""
CLIENT = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\client.py",
              encoding="utf-8").read()
lines = CLIENT.splitlines()

for i, ln in enumerate(lines, 1):
    s = ln.strip()
    if ("file_progress" in s or "filename" in s or "files." in s or "file_id" in s) and len(s) < 200:
        print(i, s[:170])
