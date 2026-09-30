# -*- coding: utf-8 -*-
"""关键字扫描：文件行构造 / OFFER 帧 / forward 渲染。"""
import re

CLIENT = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\client.py",
              encoding="utf-8").read()
FC = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\file_client.py",
          encoding="utf-8").read()
lines = CLIENT.splitlines()

print("== client.py: 'file' 消息行 / file_id 行构造 ==")
for i, ln in enumerate(lines, 1):
    if ('"file"' in ln or "'file'" in ln or 't=="file"' in ln) and ("append" in ln or "file_id" in ln or "filename" in ln):
        print(i, ln.strip()[:150])

print("\n== client.py: forward 渲染（含 'fwd' 快照消费） ==")
for i, ln in enumerate(lines, 1):
    if "forward" in ln and ("get(" in ln or "渲染" in ln or "label" in ln or "fwd" in ln):
        print(i, ln.strip()[:150])
