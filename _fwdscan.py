# -*- coding: utf-8 -*-
"""一次性扫描：图片/文件消息的存储字段与发送协议（转发支持改造用）。"""
import re

CLIENT = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\client.py",
              encoding="utf-8").read()
CORE = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\client_core.py",
            encoding="utf-8").read()

print("== client_core 发送类 API ==")
for m in re.finditer(r"def (send\w+)\(self", CORE):
    print(m.group(1))

print("\n== client.py 消息行中 img/file 相关字段 ==")
seen = set()
for m in re.finditer(r".{60}\[\"(img|file_id|filename|fid|attach|size|thumb)\"\].{60}", CLIENT):
    s = m.group(0).strip()
    if s not in seen:
        seen.add(s)
        print(s[:150])
