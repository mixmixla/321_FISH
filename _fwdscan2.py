# -*- coding: utf-8 -*-
"""一次性扫描：文件消息行构造 / FILE_OFFER 帧 / forward 渲染支持。"""
import re

CLIENT = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\client.py",
              encoding="utf-8").read()
FC = open(r"c:\Users\Administrator\Documents\trae_projects\AI\learn_demos\321_局域网摸鱼助手_聊天文件游戏\file_client.py",
          encoding="utf-8").read()

print("== client.py 中 'file' 消息行构造处 ==")
for m in re.finditer(r".{50}[`\"']t[`\"']\s*:\s*[`\"']file[`\"'].{90}", CLIENT):
    print(m.group(0).replace("\n", " ")[:170])

print("\n== file_client FILE_OFFER 帧构造 ==")
i = FC.find("FILE_OFFER")
for m in re.finditer(r".{40}FILE_OFFER.{80}", FC):
    print(m.group(0).replace("\n", " ")[:160])

print("\n== client.py 渲染 forward 的地方 ==")
for m in re.finditer(r".{60}forward.{60}", CLIENT):
    s = m.group(0).replace("\n", " ")
    if "get(\"forward\")" in s or "['forward']" in s or "\"forward\"" in s:
        print(s[:170])
