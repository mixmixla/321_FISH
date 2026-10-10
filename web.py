# -*- coding: utf-8 -*-
"""网页端聊天：轻量 HTTP + SSE（纯标准库，无外部依赖）。

与 TCP 客户端完全互通（同一 Hub / ChatBus / 名单 / 群组）：
    GET  /            → 聊天页（单文件 HTML：EventSource 收消息 + fetch 发消息）
    POST /api/login   → {nick, password?} → {ok, uid, nick, token, roster, groups, stickers, history}
                        （成功后 Set-Cookie: mt_token=… HttpOnly，登录态走 Cookie）
    POST /api/send    → {token, channel, to, text, sticker, reply?} → {ok}
                        （reply={nick,text,seq} 引用快照，R41G）
    POST /api/sched   → {token, action=set|cancel|list, ...} → {ok}   （R51 定时消息）
    POST /api/del     → {token, seq, scope=self|both} → {ok}          （R51 撤回）
    GET  /api/history → {channel, to}（鉴权取 Cookie；?token= 为旧客户端兼容回退）
    GET  /api/events  → SSE 长连接（Cookie 鉴权；心跳 ": ping" 每 15s）

安全（P0 加固）：serve(https=True) 时走自签证书 HTTPS（tls_cert 零依赖生成）；
登录态用 HttpOnly Cookie 携带，token 不再出现在 URL（防浏览器历史/日志/Referer
泄漏）；登录失败按 IP 指数退避限速（_LoginGuard，内存态）。网页端 = 服务器
（用户自己机器）上的附加入口，口令为空时局域网免密（config.WEB_PASSWORD 可设
口令）；聊天正文依旧不落盘（见 server.ChatBus）。
"""
import json
import hmac
import os
import base64
import queue
import re
import ssl
import select
import sys
import threading
import time
import urllib.parse
from dataclasses import replace
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from protocol import MsgType
import credential_ops as credential_mod
from ui_design import icon_svg, web_chat_css
import bots as _bots                     # R46：登录下发机器人清单（网页端入口）
try:
    import _art as _art_assets            # 原创美术：登录横幅/吉祥物（内嵌 base64）
except Exception:
    _art_assets = None

def _SERVED_PAGE():
    """登录页注入原创美术数据 URI（src 模式；_art 缺失时回退为纯色横幅）。"""
    if _art_assets:
        hero, mas = _art_assets.BANNER, _art_assets.MASCOT
    else:
        hero, mas = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='600' height='180'><rect width='600' height='180' fill='%23f6eee0' rx='18'/></svg>", "")
    page = PAGE.replace("@@HERO@@", hero).replace("@@MASCOT@@", mas)
    page = page.replace('@@UX_CHAT_CSS@@', web_chat_css())
    for name in ('chat', 'game', 'moments', 'image', 'attach', 'send'):
        page = page.replace('@@UX_ICON_'+name+'@@', icon_svg(name))
    return page.encode("utf-8")

COOKIE_NAME = "mt_token"                 # 登录态 Cookie（HttpOnly）
# Web 安全响应头（每响应统一附加）。页面为单文件内联模板（1 个 <script>/<style>、
# 516 个内联事件处理器、无外部资源），故 CSP 用 'unsafe-inline' 保兼容，同时用
# default-src 'self' + object-src/base-uri/frame-ancestors/form-action 收紧：
# 阻止外部脚本/插件注入、<base> 劫持、点击劫持、表单外发；img/media 放行
# data:/blob:（头像 data URI、语音/视频 blob 播放）。
_SEC_HEADERS = (
    ("Content-Security-Policy",
     "default-src 'self' data: blob:; script-src 'unsafe-inline' 'self'; "
     "style-src 'unsafe-inline' 'self'; img-src 'self' data: blob:; "
     "font-src 'self' data:; object-src 'none'; base-uri 'self'; "
     "frame-ancestors 'none'; form-action 'self'"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),      # 登录态 token 走 Cookie，Referer 不外泄
    ("X-XSS-Protection", "0"),               # 现代浏览器建议关闭旧式 XSS 过滤器（易被绕过）
)
_IMG_EXT_RE = re.compile(r"\.(png|jpe?g|gif|bmp|webp)$", re.I)   # 图片扩展名（📎 传图自动按图片内联）
_IMG_CTYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp"}

_SSE_MAX = 256                            # SSE 长连接全局上限（防连接耗尽）
_sse_lock = threading.Lock()
_sse_active = 0

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="mist">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>内部办公助手</title>
<style>
:root{--bg:#fdf6ec;--card:#fffdf8;--line:#f2e2cc;--txt:#4a3b32;--dim:#b39378;--accent:#ff8a5c;--self:#6fcba0;--bub-in:#f6eee0;--side:#fbefe0;--blur:blur(22px) saturate(150%);--shadow-sm:0 2px 10px rgba(172,121,72,.10);--shadow-md:0 6px 22px rgba(172,121,72,.14);--shadow-lg:0 14px 40px rgba(172,121,72,.18);--coral:#ff8a5c;--peri:#8f9bff;--sun:#ffd166;--mint:#6fcba0;--ring-a:#ff8a5c;--ring-b:#c58bff;--r1:10px;--r2:16px;--r3:22px}
/* R60 UI① 一键深色主题 */
:root[data-theme="dark"]{
  --bg:#28221d;--card:#352c26;--line:#4d4136;--txt:#f2e8dc;--dim:#b49c84;
  --bub-in:#3a302a;--side:#2f2721;--mint:#3fb989;--self:#3fb989;
  --shadow-sm:0 3px 10px rgba(0,0,0,.4);--shadow-lg:0 12px 38px rgba(0,0,0,.5)}
:root[data-theme="dark"] body{color:var(--txt);
  background-image:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><g fill='%233d3540' opacity='.45'><circle cx='30' cy='26' r='5'/><circle cx='122' cy='18' r='3'/><circle cx='70' cy='140' r='4'/></g><g fill='%23ff8a5c' opacity='.07'><circle cx='40' cy='110' r='6'/><circle cx='132' cy='92' r='4'/><circle cx='10' cy='70' r='3'/></g></svg>"),
    radial-gradient(1100px 480px at 85% -8%,rgba(255,138,92,.10),transparent 60%),
    radial-gradient(900px 420px at 8% 108%,rgba(143,155,255,.10),transparent 60%),
    linear-gradient(178deg,#2b251f 0%,#211c17 100%)}
:root[data-theme="dark"] #head{background:rgba(40,34,29,.88);color:#f2e8dc;border-color:var(--line)}
:root[data-theme="dark"] #side{background:rgba(47,39,33,.94)}
:root[data-theme="dark"] #input{background:rgba(53,44,38,.92)}
:root[data-theme="dark"] #input textarea{background:#241f1a;color:var(--txt)}
:root[data-theme="dark"] .msg .bub{border-color:var(--line)}
:root[data-theme="dark"] .msg.self .bub{background:linear-gradient(135deg,var(--mint),#2f8a66);box-shadow:0 3px 10px rgba(63,185,137,.28)}
:root[data-theme="dark"] #emoji{background:var(--card)}
:root[data-theme="dark"] #sbar,#selbar{background:var(--card)}
:root[data-theme="dark"] #login,#mpanel .mcard,#apanel input{background:var(--card)}
:root[data-theme="dark"] .pv,.fwd .it,.qb,.daysep span{background:var(--card)}
:root[data-theme="dark"] button.ghost{background:linear-gradient(135deg,#43372f,#514239);color:var(--txt)}
:root[data-theme="dark"] ::-webkit-scrollbar{width:9px}
:root[data-theme="dark"] ::-webkit-scrollbar-thumb{background:var(--line);border-radius:6px}
:root[data-theme="dark"] ::-webkit-scrollbar-track{background:transparent}
/* —— 主题包二：扁平极简冷灰（flat 家族）——
   data-theme="flat"（冷灰浅）/ "flat-dark"（墨蓝黑）。浅灰底/白卡/冷描边/单一
   强调色（钢蓝），扁平小圆角、去除渐变噪点，与暖粉手绘风形成两极。
   只覆写本套需要的 CSS 变量与元素；聊天主题(data-chat)叠层照常叠加。 */
:root[data-theme="flat"]{
  --bg:#f3f4f6;--card:#ffffff;--line:#dfe2e7;--txt:#2b3036;--dim:#8b9199;
  --accent:#2e63e0;--mint:#2e63e0;--self:#2e63e0;--bub-in:#ffffff;--side:#eceef1;
  --chat-bg:var(--bg);--bub-self:var(--self);
  --coral:#2e63e0;--peri:#6f8fe8;--sun:#6f8fe8;--ring-a:#2e63e0;--ring-b:#6f8fe8;
  --shadow-sm:0 1px 2px rgba(20,24,34,.06);--shadow-md:0 4px 12px rgba(20,24,34,.08);--shadow-lg:0 8px 24px rgba(20,24,34,.10);
  --r1:8px;--r2:12px;--r3:16px}
:root[data-theme="flat-dark"]{
  --bg:#171a21;--card:#1f232c;--line:#303744;--txt:#e0e5ec;--dim:#8b95a3;
  --accent:#5b8def;--mint:#3f6fd8;--self:#3f6fd8;--bub-in:#232834;--side:#1c2028;
  --chat-bg:var(--bg);--bub-self:var(--self);
  --coral:#5b8def;--peri:#7d9cf0;--sun:#7d9cf0;--ring-a:#5b8def;--ring-b:#7d9cf0;
  --shadow-sm:0 1px 3px rgba(0,0,0,.35);--shadow-md:0 4px 12px rgba(0,0,0,.40);--shadow-lg:0 10px 28px rgba(0,0,0,.50);
  --r1:8px;--r2:12px;--r3:16px}
/* 冷灰下：去暖色噪点渐变、按钮回归单强调色、气泡改用冷灰细描边、自气泡纯色 */
:root[data-theme="flat"] body,:root[data-theme="flat-dark"] body{background-image:none}
:root[data-theme="flat"] button,:root[data-theme="flat-dark"] button{background:var(--accent);box-shadow:var(--shadow-sm)}
:root[data-theme="flat"] button.ghost,:root[data-theme="flat-dark"] button.ghost{background:var(--card)}
:root[data-theme="flat"] #head{background:rgba(236,238,241,.9);border-color:var(--line)}
:root[data-theme="flat-dark"] #head{background:rgba(28,32,40,.9);border-color:var(--line)}
:root[data-theme="flat"] #side{background:rgba(236,238,241,.85)}
:root[data-theme="flat-dark"] #side{background:rgba(28,32,40,.9)}
:root[data-theme="flat"] #input{background:rgba(255,255,255,.92)}
:root[data-theme="flat-dark"] #input{background:rgba(31,35,44,.94)}
:root[data-theme="flat"] .msg .bub,:root[data-theme="flat-dark"] .msg .bub{border-color:var(--line)}
:root[data-theme="flat"] .msg.self .bub,:root[data-theme="flat-dark"] .msg.self .bub{box-shadow:var(--shadow-sm)}
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.55 "PingFang SC","Microsoft YaHei","Hiragino Sans GB",-apple-system,"Segoe UI",sans-serif;color:var(--txt);height:100vh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased;
  background-color:var(--bg);
  background-image:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><g fill='%23ffd166' opacity='.10'><circle cx='30' cy='26' r='5'/><circle cx='122' cy='18' r='3'/><circle cx='70' cy='140' r='4'/></g><g fill='%23ff8a5c' opacity='.07'><circle cx='40' cy='110' r='6'/><circle cx='132' cy='92' r='4'/><circle cx='10' cy='70' r='3'/></g></svg>"),
    radial-gradient(1200px 500px at 12% -8%,rgba(255,255,255,.55),transparent 60%),
    radial-gradient(1000px 460px at 92% 108%,rgba(255,209,102,.16),transparent 60%),
    linear-gradient(178deg,#fdf7ee 0%,#fbf1e0 100%);
  background-attachment:fixed}
#login{max-width:360px;margin:12vh auto;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:30px 34px 32px;box-shadow:var(--shadow-lg),0 0 0 6px rgba(255,209,102,.10)}
#login .mascot{text-align:center;margin:-58px auto 4px}
#login .mascot img{width:76px;height:76px;border-radius:50% 50% 46% 50%;box-shadow:0 6px 18px rgba(255,138,92,.30),inset 0 -3px 6px rgba(0,0,0,.06);border:4px solid #fff}
#login .hbanner{width:100%;border-radius:18px 18px 18px 8px;display:block;margin:6px 0 14px;box-shadow:var(--shadow-sm)}
#login h1{font-size:20px;margin-bottom:4px;color:#3d3a54;font-weight:900;text-align:center}
#login input{width:100%;padding:11px 14px;border:1.5px solid var(--line);border-radius:14px 14px 14px 6px;margin-bottom:12px;font-size:15px;background:var(--bg);color:var(--txt);transition:border-color .2s,box-shadow .2s}
#login input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px rgba(255,138,92,.14)}
button{cursor:pointer;border:none;border-radius:16px 16px 16px 8px;background:linear-gradient(135deg,var(--coral),#ffb28a);color:#fff;padding:9px 20px;font-size:14px;font-weight:600;box-shadow:0 3px 12px rgba(255,138,92,.28);transition:opacity .15s,transform .12s}
button:hover{opacity:.92;transform:translateY(-1px)}
button:active{transform:scale(.96)}
button.ghost{background:linear-gradient(135deg,var(--side),#fff);color:var(--txt);box-shadow:var(--shadow-sm);border:1px solid var(--line)}
button.sm{padding:4px 12px;font-size:12px;border-radius:12px 12px 12px 6px;box-shadow:none}
#main{flex:1;display:flex;align-items:stretch;min-height:0;display:none}
#chat{display:flex;flex-direction:column;flex:1;min-width:0;min-height:0;overflow:hidden;isolation:isolate}
#chat > :not(#msgs){flex-shrink:0}
#chat #msgs{min-height:0;overflow:auto;overflow-wrap:anywhere}
#chat #head{overflow-x:auto}
#side{width:248px;flex:0 0 248px;background:rgba(251,239,224,.62);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border-right:1px solid var(--line);padding:18px 12px;overflow:auto}
#side h2{font-size:11px;color:var(--dim);margin:20px 4px 8px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;display:flex;align-items:center;gap:6px}
#side h2::after{content:"";height:3px;flex:1;border-radius:2px;background:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='6' viewBox='0 0 60 6'><path d='M1 4c10-4 18 3 28-1 7-3 16-3 22-1 5 2 8 1 9 0' stroke='%23ff8a5c' stroke-width='2' fill='none' stroke-linecap='round' opacity='.5'/></svg>") repeat-x center;background-size:60px 6px;opacity:.5}
#side .item{padding:9px 12px;border-radius:14px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .16s,transform .12s,box-shadow .16s;font-size:13px;margin:2px 0}
#side .item:hover{background:var(--card);transform:translateX(3px);box-shadow:var(--shadow-sm)}
#side .item.on{background:linear-gradient(135deg,var(--coral),#ffb28a);color:#fff;box-shadow:0 4px 14px rgba(255,138,92,.30)}
#side .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#34c759;margin-right:6px}
/* R52：头像（列表行 26px / 消息 30px / 资料 88px；无图回退首字色块） */
#side .rowav{display:inline-block;width:26px;height:26px;border-radius:50%;vertical-align:middle;margin-right:6px;overflow:hidden;background:linear-gradient(135deg,var(--ring-a),var(--ring-b));color:#fff;text-align:center;line-height:26px;font-size:12px;font-weight:600;box-shadow:0 0 0 1.5px rgba(255,255,255,.6),0 2px 6px rgba(172,121,72,.2)}
.avc{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:linear-gradient(135deg,var(--ring-a),var(--ring-b));color:#fff;font-weight:600;flex:0 0 auto;overflow:hidden;box-shadow:0 0 0 1.5px rgba(255,255,255,.6),0 2px 6px rgba(172,121,72,.16)}
.av{border-radius:50%;object-fit:cover;flex:0 0 auto;background:var(--side);vertical-align:middle;display:block}
.msgav{float:left;margin:2px 8px 0 0}
.msg.self .msgav{display:none}
#side .grpdot{background:#ff9500}
#side .botdot{background:#8e8e93}                      /* R46 bot 恒在线灰点 */
#side .svdot{background:#ffd60a}                        /* R63 收藏夹（发给自己）金色点 */
#side .unread{float:right;background:#ff3b30;color:#fff;border-radius:10px;font-size:10px;padding:0 6px;min-width:16px;text-align:center;line-height:16px;font-weight:600}
#side .blk{float:right;color:#e57373;border:1px solid #e57373;border-radius:8px;font-size:10px;padding:0 5px;line-height:15px;font-weight:400}
#side .sign{margin-left:6px;color:var(--dim);font-size:10px;overflow:hidden;text-overflow:ellipsis;max-width:90px;display:inline-block;vertical-align:middle}
#side .add{float:right;cursor:pointer;color:var(--accent);font-weight:700;padding:0 4px}
/* R63（任务6）会话级星标：行尾 ⭐/☆ 切换钮 */
#side .stbtn{float:right;margin-left:8px;cursor:pointer;color:#c9a227;font-size:15px;line-height:1;opacity:.55;transition:opacity .15s,transform .15s}
#side .item:hover .stbtn{opacity:1;transform:scale(1.12)}
#side .stbtn.on{opacity:1}
#side .item:hover .stbtn{color:#f0b90b}
/* R69C11 标为未读：名称前蓝点 + 行尾 ⏳ 切换钮 */
#side .umark{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:5px;vertical-align:middle}
#side .mkbtn{float:right;margin-left:6px;cursor:pointer;color:#9aa0aa;font-size:13px;line-height:1;opacity:.45;transition:opacity .15s,transform .15s}
#side .item:hover .mkbtn{opacity:1;transform:scale(1.12)}
#side .mkbtn.on{opacity:1;color:var(--accent)}
#void{flex:1;display:flex;align-items:center;justify-content:center;color:var(--dim);gap:6px}
#apanel{max-width:300px;background:rgba(255,255,255,.72);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border-left:1px solid var(--line);overflow:auto;padding:12px}
#apanel h3{font-size:14px;margin:4px 0 10px;color:var(--accent);font-weight:600}
#apanel .ann{background:#fff8e6;border:1px solid #f0dfb4;border-radius:10px;padding:8px 10px;font-size:12px;margin-bottom:10px;white-space:pre-wrap}
#apanel .mrow{display:flex;align-items:center;gap:6px;padding:6px 8px;border-bottom:1px solid var(--line);font-size:12px}
#apanel .mrow .nick{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#apanel .tag{font-size:10px;color:#fff;border-radius:4px;padding:1px 6px;font-weight:500}
#apanel .tag.o{background:#ff3b30}#apanel .tag.a{background:#ff9500}
#apanel .row-btn{font-size:11px;padding:2px 8px;cursor:pointer;border:none;border-radius:6px;background:var(--side);color:var(--txt);transition:background .15s}
#apanel .row-btn:hover{background:rgba(0,0,0,.08)}
/* ============ 朋友圈 · 微信风格 ============ */
#mpanel{display:none;position:fixed;inset:0;z-index:40;background:rgba(40,32,24,.46);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)}
#mwrap{position:absolute;top:0;left:50%;transform:translateX(-50%);width:min(660px,100vw);height:100%;display:flex;flex-direction:column;overflow:hidden;background:#f2f2f2;box-shadow:0 0 48px rgba(0,0,0,.35)}
/* 顶部导航 */
#mnav{flex:0 0 auto;background:linear-gradient(90deg,#2a2a2a,#3d3d3d);color:#fff;padding:0 16px;height:44px;display:flex;align-items:center;justify-content:space-between}
#mnav .t{font-weight:600;font-size:15px;letter-spacing:.5px}
#mnav button{border:0;background:none;color:#fff;font-size:16px;cursor:pointer;padding:0 6px;opacity:.85}
#mnav button:hover{opacity:1}
/* 封面 */
#mcover{flex:0 0 auto;height:120px;background:
  radial-gradient(circle at 20% 30%,rgba(255,255,255,.55),transparent 45%),
  radial-gradient(circle at 85% 20%,rgba(181,255,214,.35),transparent 40%),
  linear-gradient(135deg,#a8d8ea 0%,#f4e3c1 55%,#ffd6e0 100%);
  position:relative}
#mcovCap{position:absolute;right:16px;bottom:10px;color:#fff;font-size:14px;font-weight:700;text-shadow:0 1px 4px rgba(0,0,0,.35);letter-spacing:.3px}
#mcovMe{position:absolute;right:16px;bottom:-24px;width:56px;height:56px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,.28);display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;font-weight:700;border:3px solid #fff}
#mcovSig{position:absolute;right:16px;bottom:32px;color:#fff;font-size:11px;text-shadow:0 1px 3px rgba(0,0,0,.4);cursor:pointer;max-width:62%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#mcovBtn{position:absolute;right:8px;top:8px;background:#fff;border:none;border-radius:12px 12px 12px 4px;padding:3px 9px;font-size:11px;color:#8a6a55;cursor:pointer;box-shadow:0 2px 6px rgba(120,80,40,.25)}
#mcovPrevs{position:absolute;right:8px;top:32px;display:none;background:#fff;border:1px solid #efdcc4;border-radius:10px 10px 10px 3px;padding:6px 5px 4px;box-shadow:0 4px 14px rgba(120,80,40,.2);z-index:3}
#mcovPrevs .pv{width:56px;height:34px;border-radius:8px;margin:2px 3px;cursor:pointer;border:2px solid transparent;display:inline-block;vertical-align:top;background-size:cover;background-position:center}
#mcovPrevs .pv.sel{border-color:#ff8a5c}
#mcovPrevs .pvup{display:block;margin:4px 3px 2px;font-size:11px;color:#8a6a55;cursor:pointer}
#mcovPrevs .pvdef{display:block;margin:2px 3px;font-size:11px;color:#b08968;cursor:pointer}
/* 发布区 */
#mwrite{flex:0 0 auto;background:#fff;margin:34px 0 0;padding:10px 14px}
#mwrite textarea{width:100%;height:58px;border:1px solid #e5e5e5;border-radius:8px;padding:8px 10px;resize:none;background:#fff;color:#333;outline:none;font:inherit}
#mwrite textarea:focus{border-color:#07c160}
.mwb{display:flex;align-items:center;gap:8px;margin-top:6px}
.cam{width:34px;height:34px;border-radius:6px;background:#f5f5f5;border:1px dashed #c8c8c8;display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;color:#888}
.cam:hover{background:#f0f0f0}
#mping{font-size:12px;color:#999}
.mwb .sp{flex:1}
#mpub{background:#07c160;color:#fff;border:0;border-radius:6px;padding:8px 20px;font-size:15px;font-weight:600;cursor:pointer;box-shadow:none}
#mpub:hover{opacity:.9;transform:none}
/* 时间轴 */
#mfeed{flex:1;overflow:auto;padding:14px 12px 24px}
/* 卡片：微信式——头像左上，内容居右下 */
.mpc{background:#fff;border-radius:10px;margin-bottom:12px;padding:12px}
.mpc-hd{display:flex;align-items:flex-start;gap:10px}
.mpc-av{width:40px;height:40px;border-radius:6px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px}
.mpc-me{flex:1;min-width:0}
.mpc-nm{color:#576b95;font-weight:600;font-size:14px;margin-bottom:2px}
.mpc-tm{color:#999;font-size:11px}
.mpc-del{flex:0 0 auto;margin-left:6px}
.mpc-del button{border:0;background:none;color:#999;cursor:pointer;font-size:15px;padding:0}
.mpc-tx{margin:8px 0;white-space:pre-wrap;word-break:break-word;color:#2b2b2b;font-size:14px;line-height:1.6}
/* 图片九宫格 */
.mpc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
.mpc-grid.row1{grid-template-columns:repeat(1,1fr)}
.mpc-grid.row1 img{max-width:160px;height:200px;object-fit:cover;border-radius:4px;width:auto}
.mpc-grid.row2{grid-template-columns:repeat(2,1fr)}
.mpc-grid img{width:100%;height:86px;object-fit:cover;border-radius:4px;display:block;background:#f0f0f0}
/* 操作行 */
.mpc-act{display:flex;align-items:center;gap:14px;margin-top:8px;font-size:13px}
.mpc-act a{cursor:pointer;color:#576b95;user-select:none}
.mpc-act a:active{opacity:.6}
.mpc-act .acnt{color:#888;font-size:12px}
/* 点赞 + 评论 合并框 */
.mpc-soc{background:#f7f7f7;border-radius:6px;padding:8px 10px;margin-top:4px}
.mpc-like{color:#2b2b2b;font-size:13px;margin-bottom:4px}
.mpc-like .lk{color:#f18c2b;font-weight:600}
.mpc-cmt-list{font-size:13px;line-height:1.7;border-top:1px solid #ececec;padding-top:4px}
.mpc-cmt{cursor:pointer}
.mpc-cmt .cwho{color:#576b95}
.mpc-cmt .cmine{color:#e53935}
.mpc-write{display:flex;gap:6px;margin-top:8px}
.mpc-write input{flex:1;border:1px solid #e5e5e5;border-radius:6px;padding:6px 10px;font:13px/1.4 inherit;outline:none}
.mpc-write input:focus{border-color:#07c160}
.mpc-write button{border:0;background:#07c160;color:#fff;border-radius:6px;padding:6px 12px;cursor:pointer;box-shadow:none}
.mpc-empty{text-align:center;color:#999;padding:48px 0;font-size:13px}
@media (max-width:520px){#mwrap{width:100%}}
.msg .rd{font-size:10px;color:#8e8e93;margin-top:2px;text-align:right;min-height:0}
.msg .rd .xdel{cursor:pointer;color:var(--dim);margin-left:6px;font-weight:400;font-size:12px}
.msg .rd .xdel:hover{color:#e33}
.ed{color:var(--dim);font-size:12px;text-decoration:line-through}
.react{display:inline-block;font-size:12px;background:var(--side);border:1px solid var(--line);border-radius:14px;padding:2px 10px;margin-right:4px;cursor:pointer;transition:transform .15s;animation:popIn .22s ease}
.react:hover{transform:scale(1.08)}
.react.mine{background:#d8e6ff;border-color:var(--accent);color:var(--accent);font-weight:600}
.rr{margin-top:4px;min-height:18px}
.kbrow{margin-top:4px;display:flex;flex-wrap:wrap;gap:4px}   /* R46 bot 键盘行 */
.kbtn{border:none;border-radius:12px;background:var(--side);border:1px solid var(--line);color:var(--txt);font-size:12px;padding:3px 12px;cursor:pointer;transition:transform .15s,background .15s;animation:popIn .22s ease}
.kbtn:hover{transform:scale(1.06);background:#d8e6ff}
.th{margin-top:3px;font-size:12px;color:var(--accent);cursor:pointer;user-select:none;min-height:16px}
.thr{margin:2px 0;padding:4px 8px;border-left:2px solid var(--line);max-height:180px;overflow:auto}
.tli{font-size:12px;line-height:1.7;color:var(--txt)}
.tin{display:flex;gap:4px;margin-top:3px}
.tin input{flex:1;border:1px solid var(--line);border-radius:6px;padding:3px 8px;font:12px/1.4 inherit;background:var(--card);color:var(--txt);outline:none}
.tin button{border:0;background:var(--accent);color:#fff;border-radius:6px;padding:3px 10px;cursor:pointer}
/* R41G 引用前缀块 + 跳转高亮 + 引用回复条 */
.rq{font-size:12px;color:var(--accent);background:rgba(0,122,255,.08);border-left:2px solid var(--accent);border-radius:6px;padding:3px 8px;margin-bottom:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rq.j{cursor:pointer}
.rq.j:hover{background:rgba(0,122,255,.15)}
.msg.hl .bub{box-shadow:0 0 0 2px var(--accent);transition:box-shadow .25s}
#rbar{display:none;align-items:center;gap:8px;padding:6px 16px;background:var(--card);border-top:1px solid var(--line);font-size:12px;color:var(--dim)}
#rbar span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#rbar b{cursor:pointer;padding:2px 8px;border-radius:6px;font-weight:400}
#rbar b:hover{background:rgba(0,0,0,.08)}
/* R55-2 会话内搜索条 */
#sbar{display:none;align-items:center;gap:8px;padding:6px 16px;background:var(--card);border-bottom:1px solid var(--line);font-size:12px}
#sbar input{flex:1;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);outline:none}
#sbar input:focus{border-color:var(--accent)}
#sbar button{cursor:pointer;border:none;background:none;font-size:14px;color:var(--dim)}
#sbar #scount{color:var(--dim);min-width:48px;text-align:center}
.msg.smatch{background:rgba(255,193,7,.18);border-radius:8px}
.msg.smatch.cur{background:rgba(255,193,7,.42)}
/* R27 快速回应：hover 消息时浮出的表情条 */
.qb{display:inline-flex;gap:2px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:3px 6px;box-shadow:var(--shadow-lg);margin-bottom:4px;vertical-align:top}
.qb b{font-size:18px;cursor:pointer;padding:0 5px;border-radius:14px;line-height:24px;transition:background .12s}
.qb b:hover{background:rgba(0,0,0,.06)}
.qb b.mine{background:#d8e6ff}
@keyframes popIn{0%{transform:scale(.35);opacity:0}70%{transform:scale(1.12)}100%{transform:scale(1);opacity:1}}
#head{height:56px;background:rgba(255,253,248,.72);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border-bottom:1px solid var(--line);border-radius:0 0 20px 20px;display:flex;align-items:center;padding:0 22px;font-weight:700;font-size:15px;color:#3d3a54;gap:6px}
#head .sub{font-weight:400;color:var(--dim);font-size:12px;margin-left:2px}
#msgs{flex:1;overflow:auto;padding:18px 24px;background:var(--chat-bg,#fdf6ec);transition:background .25s}
.msg{margin-bottom:12px;max-width:72%;position:relative;animation:msgIn .28s cubic-bezier(.18,.7,.3,1)}
.msg .who{font-size:12px;color:var(--dim);margin-bottom:4px}
.msg .who .burn{color:#ff5544;font-size:11px}
/* R70A 剧透文字：默认 blur 遮盖，点击揭示（.on） */
.msg .bub .spoiler{background:#c9c3ba;color:transparent;border-radius:6px;padding:0 3px;cursor:pointer;user-select:none;text-shadow:none}
.msg .bub .spoiler:not(.on){filter:blur(4px)}
.msg .bub .spoiler.on{background:transparent;color:inherit;filter:none}
/* R70E 消息伪装：三风格外观（正文默认遮盖，复用 .spoiler 点击揭示） */
.msg .bub .dishdr{font-family:ui-monospace,Consolas,Menlo,monospace;font-size:12px;opacity:.85;margin-bottom:4px;letter-spacing:.3px}
.msg .bub.dis-code{background:#1f2633;color:#c8d3e0;border-color:#2b3444}
.msg .bub.dis-code .dishdr{color:#8fd3a8;border-bottom:1px solid #3a4658;padding-bottom:3px}
.msg .bub.dis-log{background:#f2f3f5;color:#3d4552;border-color:#dfe3e8;font-family:ui-monospace,Consolas,Menlo,monospace}
.msg .bub.dis-log .dishdr{color:#5b6b7c}
.msg .bub.dis-excel{background:#fff;color:#2c333a;border-color:#d8dee4}
.msg .bub.dis-excel .dishdr{color:#3c4a3f;border-bottom:1px solid #d8dee4;padding-bottom:3px}
/* R70B 编辑历史：who 行的「（已编辑）」标签可点 */
.msg .who .edtag{color:var(--dim);font-size:11px;cursor:default}
.msg .who .edtag[onclick]{cursor:pointer;text-decoration:underline dotted}
.msg .bub{background:var(--bub-in,#f6eee0);border:1px solid #f6ead7;border-radius:18px 18px 18px 8px;padding:10px 14px;word-break:break-word;font-size:14px;line-height:1.55;box-shadow:var(--shadow-sm);color:var(--bub-txt,var(--txt))}
.msg.self{margin-left:auto}
.msg.self .bub{background:var(--bub-self,linear-gradient(135deg,var(--mint),#a5e6c8));color:var(--bub-self-txt,#fff);border-radius:18px 18px 8px 18px;box-shadow:0 4px 14px rgba(111,203,160,.30)}
/* R__ 聊天主题叠层（data-chat 选择器切换气泡/聊天区配色，深浅主题可叠加）
   注：data-chat 切换的浅色气泡需自带深色文字(--bub-txt/--bub-self-txt)，
   否则在深色模式下气泡文字会继承 --txt 的近白而几乎不可见(对比度≈1.2)。 */
:root[data-chat="mint"]{--chat-bg:#eef7ef;--bub-in:#ffffff;--bub-self:linear-gradient(135deg,#4fc38d,#a5e6c8);--bub-txt:#2f4a3c;--bub-self-txt:#0a3d2a}
:root[data-chat="coral"]{--chat-bg:#fff3ed;--bub-in:#ffffff;--bub-self:linear-gradient(135deg,#ff8a5c,#ffb28a);--bub-txt:#6a3d2a;--bub-self-txt:#4a2414}
:root[data-chat="peach"]{--chat-bg:#fff0f2;--bub-in:#ffffff;--bub-self:linear-gradient(135deg,#f7a8b8,#ffd6de);--bub-txt:#6b3140;--bub-self-txt:#4a1a28}
:root[data-chat="ink"]{--chat-bg:#eef1f8;--bub-in:#ffffff;--bub-self:linear-gradient(135deg,#4a6fa5,#bdcbe0);--bub-txt:#2e3a52;--bub-self-txt:#16233c}
/* @全体 广播消息醒目样式（区别于普通私聊/群聊气泡） */
.msg.evb .who .evtag{background:#ffd66e;color:#6b4a00;border-radius:8px;padding:0 6px;font-size:11px;font-weight:700;margin-right:6px}
.msg.evb .bub,.msg.self.evb .bub{background:linear-gradient(135deg,#fff3cd,#ffe2a8);border-color:#ffd66e;color:#5a4300;box-shadow:0 0 0 2px rgba(255,190,0,.30)}
@keyframes msgIn{0%{opacity:0;transform:translateY(8px) scale(.97)}100%{opacity:1;transform:none}}
.msg.self .who{display:none}
.msg .bub .st{font-size:32px;line-height:1}
.msg .bub img{max-width:220px;max-height:220px;border-radius:14px;display:block;cursor:zoom-in;background:#fff}
.msg .bub.file a{color:var(--accent);text-decoration:none;word-break:break-all}
.msg.self .bub.file a{color:#9ec5ff}
.msg .bub.file a:hover{text-decoration:underline}
/* R63（任务5）语音气泡：▶ 图标 + 时长，暖粉手绘风格 */
.msg .bub.voice{display:inline-flex;align-items:center;gap:8px;min-width:120px;max-width:220px}
.msg .bub.voice .vmic{font-size:22px;animation:vmicw 1.6s ease-in-out infinite;transform-origin:50% 70%}
@keyframes vmicw{0%,100%{transform:rotate(-8deg) scale(1)}50%{transform:rotate(8deg) scale(1.06)}}
.msg .bub.voice .vtxt{font-size:14px}
.msg.self .bub.voice .vtxt{color:#fff}
.msg .bub.voice .vdur{font-size:12px;opacity:.78;white-space:nowrap}
/* R60 web 消息多选 */
.msg .mulsel{position:absolute;left:6px;top:14px;font-size:16px;cursor:pointer;color:var(--accent);background:var(--card);border-radius:6px;width:20px;height:20px;line-height:18px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.12);opacity:0;transform:scale(.7);transition:opacity .12s,transform .12s}
.msg:hover .mulsel{opacity:1;transform:scale(1)}
.msg.self .mulsel{left:auto;right:6px}
.msg.sel .mulsel{opacity:1;transform:scale(1);content:"☑"}
.msg.sel{outline:2px solid var(--accent);outline-offset:2px;border-radius:12px;background:rgba(255,138,92,.06)}
.msg.sel .mulsel{background:var(--accent);color:#fff;border-radius:6px}
/* R60 批量操作条 */
#selbar{display:none;position:fixed;left:50%;transform:translateX(-50%);top:12px;z-index:60;background:var(--card);border:1px solid var(--line);border-radius:14px 14px 14px 6px;box-shadow:0 6px 22px rgba(91,68,51,.25);padding:8px 12px;align-items:center;gap:8px;font-size:13px}
#selbar #selcnt{color:var(--accent);font-weight:700;white-space:nowrap}
#selbar button{border:1px solid var(--line);background:var(--bg);border-radius:10px 10px 10px 4px;padding:4px 10px;cursor:pointer;white-space:nowrap}
#selbar button:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
#selbar .delbtn:hover{background:#e0413f;border-color:#e0413f}
/* R26A 投票气泡 */
.poll .q{font-weight:600;margin-bottom:6px}
.poll .opt{position:relative;border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:4px 0;cursor:pointer;overflow:hidden;background:var(--bg);transition:border-color .15s}
.poll .opt:hover{border-color:var(--accent)}
.poll .opt .bar{position:absolute;left:0;top:0;bottom:0;background:rgba(0,122,255,.12);z-index:0}
.poll .opt span{position:relative;z-index:1}
.poll .opt .cnt{float:right;color:var(--dim);font-size:11px}
.poll .opt.mine{border-color:var(--accent)}
.poll .st{font-size:11px;color:var(--dim);margin-top:6px}
/* R26D 链接预览卡片 */
.pv{margin-top:6px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;padding:8px 12px;background:var(--card);font-size:12px;word-break:break-all}
.pv .d{color:var(--accent);font-size:11px}
.pv .t{font-weight:600;color:var(--txt)}
.pv .s{color:var(--dim);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* R26C 静默开关 */
#input .sil{margin-left:auto;align-self:center;font-size:12px;color:var(--dim);white-space:nowrap;cursor:pointer;display:flex;align-items:center;gap:3px}
.sys{text-align:center;color:var(--dim);font-size:12px;margin:10px 0}
.nudge{font-style:italic;opacity:.92}
@keyframes moeyu-shake{0%,100%{transform:translate(0,0)}12%{transform:translate(-8px,0)}25%{transform:translate(8px,0)}38%{transform:translate(-6px,3px)}50%{transform:translate(6px,-3px)}62%{transform:translate(-4px,0)}75%{transform:translate(4px,0)}88%{transform:translate(-2px,0)}}
body.shaking{animation:moeyu-shake .6s ease-in-out}
.momdot{display:inline-block;min-width:16px;height:16px;line-height:16px;padding:0 4px;margin-left:6px;border-radius:9px;background:#e5484d;color:#fff;font-size:10px;text-align:center;vertical-align:middle}
/* R55-9 日期分隔线 / 未读分隔线 */
.daysep{text-align:center;color:var(--dim);font-size:11px;margin:14px 0 8px;position:relative}
.daysep::before{content:"";position:absolute;left:0;right:0;top:50%;height:1px;background:var(--line);z-index:0}
.daysep{background:transparent}
.daysep span{background:var(--bg);padding:0 10px;position:relative;z-index:1}
.unsep{text-align:center;color:#1890ff;font-size:11px;margin:10px 0;background:rgba(24,144,255,.06);border-radius:6px;padding:3px 0}
#emoji{padding:8px 14px 10px;border-top:1px solid var(--line);background:var(--card)}
#epacks{white-space:nowrap;overflow-x:auto;padding-bottom:6px;margin-bottom:4px;border-bottom:1px dashed var(--line)}
#epacks .pkt{display:inline-flex;align-items:center;gap:4px;font-size:12px;cursor:pointer;padding:3px 9px;margin-right:6px;border-radius:12px;border:1px solid var(--line);background:var(--side);color:var(--txt);vertical-align:middle;max-width:130px}
#epacks .pkt .lab{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#epacks .pkt:hover{border-color:var(--accent)}
#epacks .pkt.on{background:linear-gradient(135deg,var(--coral),#ffb28a);color:#fff;border-color:transparent}
#epacks .pkt .pkcv{width:16px;height:16px;border-radius:4px;object-fit:cover;flex:0 0 auto}
#epacks .pkt .lk{font-size:11px;opacity:.75}
#epacks .pkadd{font-size:14px;padding:3px 8px}
#egrid{white-space:normal;max-height:150px;overflow-y:auto}
#egrid .trial{font-size:11px;color:var(--dim);margin:4px 0 6px}
#egrid .subbtn{font-size:11px;cursor:pointer;border:1px solid var(--accent);color:var(--accent);background:transparent;border-radius:10px;padding:2px 10px;margin-left:8px}
#eshop .sp{border:1px solid var(--line);border-radius:12px;padding:6px 10px;margin:4px 0;display:flex;align-items:center;gap:8px;font-size:12px}
#eshop .sp .nm{font-weight:700}
#eshop .sp .em{font-size:16px;letter-spacing:1px}
#eshop .sp button{margin-left:auto;cursor:pointer;border:1px solid var(--line);background:var(--side);color:var(--txt);border-radius:10px;padding:2px 10px;font-size:11px}
#eshop .sp button.on{border-color:var(--accent);color:var(--accent)}
#emoji b{font-size:22px;cursor:pointer;padding:0 4px;display:inline-block;transition:transform .1s}
#emoji b:hover{transform:scale(1.2)}
#emoji b.trialoff{opacity:.42;filter:grayscale(1)}
#emoji .favlab{font-size:11px;color:var(--accent);font-weight:700;margin-right:2px;vertical-align:middle}
#emoji .favdiv{display:inline-block;width:2px;height:22px;background:var(--line);vertical-align:middle;margin:0 8px;border-radius:2px}
#emoji hr{display:none}
#emoji b.fav-ged{outline:1px dashed var(--accent);outline-offset:2px;border-radius:6px}
#ctxmenu{position:fixed;z-index:120;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow-lg);padding:4px 0;min-width:132px}
#ctxmenu .mi{padding:6px 14px;font-size:12px;cursor:pointer;color:var(--txt);white-space:nowrap}
#ctxmenu .mi:hover{background:var(--side);color:var(--accent)}
#ctxmenu .hr{height:1px;background:var(--line);margin:4px 6px}
#input{display:flex;gap:10px;padding:14px 20px;background:rgba(255,253,248,.80);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border-top:1px solid var(--line);border-radius:20px 20px 0 0;align-items:flex-end;position:relative}  /* autogrow 时工具栏按钮贴底对齐，不拉伸；R67 相对定位供 @浮层锚点 */
/* R67 网页端 @成员选择器浮层：贴输入框正上方 */
#atpick{position:absolute;left:10px;right:10px;bottom:calc(100% - 4px);display:none;
  background:var(--card);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow-lg);max-height:200px;overflow:auto;z-index:80}
#atpick b{display:block;padding:7px 14px;font-weight:400;font-size:13px;cursor:pointer}
#atpick b.on{background:var(--accent);color:#fff}
#atpick .h{font-size:11px;color:var(--dim);padding:6px 14px 2px}
#input textarea{flex:1;resize:none;border:1.5px solid var(--line);border-radius:16px;padding:10px 14px;height:42px;max-height:160px;overflow-y:auto;font:14px/1.5 inherit;background:var(--bg);transition:border-color .2s,box-shadow .2s}
#input textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px rgba(255,138,92,.12),var(--shadow-sm)}
/* 输入工具栏按钮：hover 上浮、按下回落、只读 disabled 降透明（对等桌面按钮反馈） */
#input button{transition:transform .1s,opacity .15s,box-shadow .15s}
#input button:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 5px 16px rgba(255,138,92,.34)}
#input button:active:not(:disabled){transform:translateY(0) scale(.96);box-shadow:0 1px 4px rgba(255,138,92,.2)}
#input button:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
#status{position:fixed;right:8px;bottom:4px;font-size:11px;color:var(--dim)}
/* R43B1 合并转发折叠卡 / R43B2 图片灯箱 */
.fwd{border:1px solid var(--line);border-radius:10px;background:var(--card);font-size:12px;min-width:180px}
.fwd summary{cursor:pointer;padding:7px 12px;color:var(--accent);font-weight:600;list-style:none}
.fwd summary::-webkit-details-marker{display:none}
.fwd .it{padding:6px 12px;border-top:1px solid var(--line)}
.fwd .it:first-child{border-top:none}
.fwd .n{color:var(--accent);font-size:11px;margin-right:6px}
.fwd .ts{color:var(--dim);font-size:10px}
.fwd .t{white-space:pre-wrap;word-break:break-word;margin-top:2px}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.78);display:none;align-items:center;justify-content:center;z-index:99;cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:92vw;max-height:92vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.5)}
#lb .lbnav{position:fixed;top:50%;transform:translateY(-50%);font-size:34px;color:#fff;opacity:.5;cursor:pointer;padding:8px 14px;user-select:none;font-weight:400}
#lb .lbnav:hover{opacity:1}
#lb .prev{left:12px}
#lb .next{right:12px}
#lb .lbnum{position:fixed;right:20px;bottom:18px;color:#fff;opacity:.8;font-size:13px;font-style:normal}
/* R69B5 会话图片墙（聚合已加载消息图片，九宫格） */
#alb{position:fixed;inset:0;background:rgba(30,28,40,.55);display:none;align-items:center;justify-content:center;z-index:98}
#alb.on{display:flex}
#alb .card{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:22px 22px 22px 10px;padding:12px;width:min(720px,94vw);max-height:88vh;display:flex;flex-direction:column;gap:8px;box-shadow:var(--shadow-lg)}
#alb .hd{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px}
#alb .hd span{flex:1}
#alb .grid{overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px}
#alb .cell{aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:var(--side);cursor:zoom-in;border:1px solid var(--line)}
#alb .cell img{width:100%;height:100%;object-fit:cover;display:block}
/* R69B6/B7 群待办 / 接龙 / 签到面板 */
#tkpanel{position:fixed;inset:0;background:rgba(30,28,40,.55);display:none;align-items:center;justify-content:center;z-index:98}
#tkpanel.on{display:flex}
#tkpanel .card{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:22px 22px 22px 10px;padding:12px;width:min(560px,94vw);max-height:80vh;display:flex;flex-direction:column;gap:6px;box-shadow:var(--shadow-lg)}
#tkpanel #tkList{overflow:auto;display:flex;flex-direction:column;gap:6px}
/* R49 桌游 */
#gpanel{position:fixed;inset:0;background:rgba(90,70,50,.5);display:flex;align-items:center;justify-content:center;z-index:97}
#gpanel .card{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:26px 26px 26px 12px;padding:16px;width:min(740px,94vw);max-height:90vh;display:flex;flex-direction:column;gap:8px;box-shadow:var(--shadow-lg),0 0 0 6px rgba(255,209,102,.10)}
#ghead{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;color:#3d3a54}
#gmain{overflow:auto;max-height:50vh}
#gpriv{background:var(--side);border:1px dashed #f0d3a8;border-radius:14px 14px 14px 6px;padding:8px 12px;font-size:12px;color:var(--txt)}
#glog{background:var(--side);border:1px solid var(--line);border-radius:14px 14px 14px 6px;padding:7px 12px;font-size:11px;max-height:15vh;overflow:auto;color:var(--dim)}
.gbtn{cursor:pointer;border:1px solid var(--line);background:var(--side);color:var(--txt);border-radius:14px 14px 14px 6px;padding:5px 14px;font-size:12px;font-weight:600;box-shadow:var(--shadow-sm);transition:transform .1s,background .15s}
.gbtn:hover{background:linear-gradient(135deg,var(--coral),#ffb28a);color:#fff;border-color:transparent}
.gbtn:disabled{opacity:.4;cursor:default;box-shadow:none}
.gbtn.go{background:linear-gradient(135deg,var(--coral),#ffb28a);color:#fff;border:none;box-shadow:0 3px 10px rgba(255,138,92,.28)}
.gbtn.go:hover{transform:translateY(-1px)}
.gcard{border:1px solid var(--line);border-radius:20px 20px 20px 10px;padding:12px;font-size:12px;display:flex;flex-direction:column;gap:4px;overflow:hidden;background:var(--card);box-shadow:var(--shadow-sm);transition:transform .15s,box-shadow .15s}
.gcard:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg)}
.gcard b{font-size:14px}
.gcard .go{margin-top:auto}
.gcell{width:36px;height:36px;border:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:17px;border-radius:12px 12px 12px 6px;background:var(--card);transition:transform .1s,box-shadow .1s}
.gcell:hover{transform:scale(1.06);box-shadow:var(--shadow-sm)}
.gmap{display:grid;gap:3px;font-size:10px}
.gmap>div{border:1px solid var(--line);border-radius:9px 9px 9px 4px;padding:2px;min-height:26px;text-align:center;background:var(--card)}
.glogl{padding:1px 0;border-bottom:1px dashed var(--line)}
.unocard{display:inline-block;border:1.5px solid #7a5c4a;border-radius:10px 10px 10px 4px;padding:3px 9px;margin:2px;cursor:pointer;background:#fff;color:#111;font-size:12px;font-weight:600;box-shadow:0 2px 4px rgba(0,0,0,.08)}
.unocard.dis{opacity:.4;cursor:default}
.gsec{font-weight:700;margin:8px 0 3px;font-size:12px;color:#8a6a52}
/* Apple 风格滚动条 */
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(0,0,0,.14);border-radius:99px;border:2px solid transparent;background-clip:content-box}
::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.26);background-clip:content-box;border:2px solid transparent}
/* R__ web 「回到最新」浮动按钮（对等桌面 R31A 吸底跳底键） */
#jumpBottom{position:fixed;right:26px;bottom:104px;display:none;align-items:center;justify-content:center;z-index:55;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--accent);font-size:16px;box-shadow:var(--shadow-lg);cursor:pointer;transition:transform .12s,background .15s}
#jumpBottom:hover{transform:translateY(-2px);background:var(--accent);color:#fff;border-color:var(--accent)}
#jumpBottom:active{transform:translateY(0) scale(.92)}
/* R67 手机端适配：窄屏会话列表转抽屉 */
#btnSide{display:none}
#scrim{display:none}
@media (max-width:640px){
  #side{position:fixed;left:0;top:0;bottom:0;width:min(280px,86vw);
        transform:translateX(-105%);transition:transform .22s ease;z-index:90;
        box-shadow:var(--shadow-lg);background:var(--card);border-right:none}
  #side.open{transform:translateX(0)}
  #scrim{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:89}
  #scrim.on{display:block}
  #btnSide{display:block;margin-right:6px;font-size:18px;cursor:pointer;color:var(--dim)}
  #head{padding:0 10px;height:52px;font-size:14px;border-radius:0}
  #head .sub,#selThemeFamily,#selChatTheme{display:none}
  #msgs{padding:10px 12px}
  .msg{max-width:92%}
  #input{padding:10px;gap:6px;border-radius:0}
  #login{margin:6vh auto;width:92vw;padding:20px 16px}
}
#chat #input{flex-wrap:wrap;gap:8px}
#chat #input textarea{flex:1 0 100%;min-width:0;width:100%;font-family:inherit}
#chat #input button{padding:7px 12px}
#chat #input #btnSend{margin-left:auto}
#chat #input .sil{margin-left:0}

/* Keep primary reading/composing space usable; secondary tools remain named and reachable. */
#chat #head{overflow:visible;position:relative;z-index:60}
#chat #input{z-index:50}
#headTitle{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.head-tools,.compose-tools{position:relative;flex-shrink:0;font-size:12px;font-weight:400}
.head-tools summary,.compose-tools summary{cursor:pointer;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--txt);white-space:nowrap}
.head-tools summary:focus-visible,.compose-tools summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.toolmenu{position:absolute;right:0;z-index:80;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;width:300px;max-width:calc(100vw - 20px);padding:12px;background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow-lg)}
.head-tools .toolmenu{top:calc(100% + 8px)}
.compose-tools .toolmenu{bottom:calc(100% + 8px);right:auto;left:-86px}
.toolmenu>.add{cursor:pointer;display:flex;align-items:center;gap:4px;min-width:0;margin:0;padding:5px;font-size:14px;float:none}
.toolmenu>.add::after{content:attr(title);font-size:11px;font-weight:400;line-height:1.4}
.toolmenu select{max-width:100%}
#chat .toolmenu .sil{margin-left:0}
.toolmenu button{min-width:0}
@media(max-width:640px){
  .compose-tools{position:static}
  .compose-tools .toolmenu{left:10px;right:10px;width:auto;max-width:none;bottom:calc(100% + 8px)}
}
@@UX_CHAT_CSS@@
</style>
</head>
<body>
<div id="login">
  <div class="mascot"><img src="@@MASCOT@@" alt=""></div>
  <img class="hbanner" src="@@HERO@@" alt="摸鱼助手">
  <h1>局域网摸鱼助手</h1>
  <input id="nick" placeholder="昵称" maxlength="20" autocomplete="off">
  <input id="pwd" placeholder="密码（选填：昵称已设密码必填；首次填入即绑定）" type="password" autocomplete="off">
  <input id="npwd" placeholder="昵称密码（选填：已设密码必填；首次填入即绑定）" type="password" autocomplete="off" style="display:none">
  <button id="btnLogin" style="width:100%">进入</button>
</div>
<div id="main">
  <nav id="uxRail" aria-label="主要功能">
    <div class="brand">m.</div>
    <button class="on" data-ux-nav="chat" aria-current="page" title="消息" onclick="selectChannel({type:'public'})">@@UX_ICON_chat@@<span>消息</span></button>
    <button data-ux-nav="game" title="游戏大厅" onclick="gameLobby()">@@UX_ICON_game@@<span>桌游</span></button>
    <button data-ux-nav="moments" title="朋友圈动态" onclick="openMoments()">@@UX_ICON_moments@@<span>动态</span></button>
  </nav>
  <div id="side">
    <h2>⭐ 星标<span class="add" title="展开/收起星标会话" onclick="toggleStarPanel()">⌄</span></h2>
    <div id="starsec" style="display:none"></div>
    <h2>⏳ 稍后处理<span class="add" title="展开/收起待处理清单" onclick="toggleMarkPanel()">⌄</span></h2>
    <div id="marksec" style="display:none"></div>
    <h2>频道</h2>
    <div class="item on" data-ch="public" role="button" tabindex="0" onclick="selectChannel({type:'public'})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}"><span class="dot"></span>公共聊天</div>
    <div class="item" data-ch="saved" onclick="openSaved()" title="发给自己：收藏夹 / 我的笔记"><span class="dot svdot"></span>📌 收藏夹（我的笔记）</div>
    <div class="item" onclick="openFavMsgs()" title="⭐消息收藏（本地）：跨会话聚合浏览"><span class="dot svdot"></span>⭐ 我的收藏</div>
    <h2>群聊<span class="add" title="创建群" onclick="createGroup()">＋</span><span class="add" title="凭邀请码加入" onclick="joinByInvite()">✉</span></h2>
    <div id="groups"></div>
    <h2>最近私聊</h2>
    <div id="convos"></div>
    <h2>在线成员（点击私聊）</h2>
    <div id="roster"></div>
    <h2>机器人</h2>
    <div id="bots"></div>
    <h2>桌游<span class="add" title="游戏大厅" onclick="gameLobby()">🎮</span></h2>
    <div id="games"></div>
    <h2>朋友圈<span id="momDot" class="momdot" style="display:none"></span></h2>
    <div class="item" onclick="openMoments()"><span class="dot"></span>看看大家的动态</div>
  </div>
  <div id="chat">
    <div id="head"><span id="btnSide" title="会话列表" onclick="toggleSide()">☰</span><span id="headTitle">公共聊天</span><span class="sub" id="headSub"></span><details class="head-tools"><summary>更多</summary><div class="toolmenu"><span id="btnBlock" class="add" style="display:none" title="屏蔽/解除屏蔽"></span><span id="btnAdmin" class="add" style="display:none" title="管理员面板" onclick="adminPanel()">🧹</span><span id="btnExport" class="add" title="导出本会话记录（txt）" onclick="exportChat()">⬇</span><span class="add" title="图片墙（聚合本会话已加载图片）" onclick="openAlbum()">🖼</span><span class="add" title="我的资料" onclick="profilePanel()">👤</span><span class="add" title="退出登录" onclick="logout()">⏻</span><span class="add" title="昵称密码" onclick="pwdPanel()">🔑</span><span class="add" title="新消息提示音（关闭/轻柔/默认/叮咚）" onclick="soundPanel()">🔊</span><span class="add" title="勿扰时段（抑制通知/提示音）" onclick="dndPanel()">🔕</span><span class="add" title="关键词提醒（命中关键词始终系统通知）" onclick="kwPanel()">🔔</span><span class="add" title="敏感词打码（仅本机显示，点击揭示）" onclick="guardPanel()">🕶️</span><span class="add" title="摸鱼排行榜（只读，按游戏累计积分）" onclick="fishBoardPanel()">🏆</span><span class="add" title="主题风格（暖粉手绘/冷灰极简）"><select id="selThemeFamily" onchange="setThemeFamily(this.value)" style="height:24px;font-size:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--txt)"><option value="mist">雾岸</option><option value="retro">暖粉</option><option value="flat">冷灰</option></select></span><span id="btnTheme" class="add" title="深浅色主题切换" onclick="toggleTheme()">🌙</span><select id="selChatTheme" class="add" title="聊天主题（气泡配色）" onchange="setChatTheme(this.value)" style="height:24px;font-size:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--txt)"><option value="">跟随皮肤</option><option value="mint">薄荷</option><option value="coral">珊瑚</option><option value="peach">暖粉</option><option value="ink">墨蓝</option></select></div></details></div>
    <div id="sbar" style="display:none">
      <input id="sinput" placeholder="搜索本会话消息（Ctrl+F，Enter 下一个）" autocomplete="off">
      <span id="scount"></span>
      <button onclick="searchClose()" title="关闭搜索">✕</button>
    </div>
    <div id="msgs"></div>
    <div id="emoji"></div>
    <div id="rbar">↩ <span id="rprev"></span><b onclick="cancelBar()" title="取消引用/编辑">✕</b></div>
    <div id="input">
      <textarea id="text" placeholder="输入消息，Enter 发送，:smile: 表情"></textarea>
      <button id="btnImg" title="发送图片">@@UX_ICON_image@@图片</button>
      <button id="btnFile" title="发送文件">@@UX_ICON_attach@@附件</button>
      <details class="compose-tools"><summary>更多</summary><div class="toolmenu">
      <button id="btnPoll" title="发起投票">🗳</button>
      <button id="btnEvbody" title="群内@全体（醒目广播）" onclick="insertEvbody()">📣@所有</button>
      <button id="btnSched" title="定时发送（服务器托管）">⏰</button>
      <button id="btnBurn" title="阅后即焚（全体读完自动删除）">🔥</button>
      <label class="sil"><input type="checkbox" id="silent">🔕静默</label>
      <select id="disguise" title="消息伪装外观（正文遮盖，点击揭示）">
        <option value="">🎭关</option>
        <option value="code">🎭代码</option>
        <option value="log">🎭日志</option>
        <option value="excel">🎭表格</option>
      </select>
      </div></details>
      <span class="ux-send-hint">Enter 发送 · Shift+Enter 换行</span>
      <button id="btnSend">@@UX_ICON_send@@发送</button>
    </div>
    <input type="file" id="fimg" accept="image/*" style="display:none">
    <input type="file" id="ffile" style="display:none">
    <input type="file" id="fpackcover" accept="image/*" style="display:none">
    <button id="jumpBottom" title="回到最新"></button>
  </div>
  <div id="mpanel">
    <div id="mwrap">
      <div id="mnav">
        <div class="t">📸 朋友圈</div>
        <button onclick="closeMoments()" title="关闭">✕</button>
      </div>
      <div id="mcover">
        <div id="mcovMe"></div>
        <div id="mcovCap">生活原本沉闷，但跑起来就有风</div>
        <div id="mcovSig" title="点击修改个性签名">点击设置个性签名</div>
        <button id="mcovBtn" onclick="toggleCovMenu()">🖼 换封面</button>
        <div id="mcovPrevs"></div>
        <input type="file" id="mcovFile" accept="image/*" style="display:none">
      </div>
      <div id="mwrite">
        <textarea id="mptext" placeholder="分享新鲜事…"></textarea>
        <div class="mwb">
          <div class="cam" title="添加图片" onclick="document.getElementById('mpfile').click()">➕</div>
          <span id="mping"></span>
          <span class="sp"></span>
          <button id="mpub" onclick="publishMoment()">发布</button>
        </div>
        <input type="file" id="mpfile" accept="image/*" multiple style="display:none">
      </div>
      <div id="mfeed"></div>
    </div>
  </div>
  <div id="apanel" style="display:none"></div>
</div>
<div id="status"></div>
<script>
const $=s=>document.querySelector(s);
const state={token:null,uid:0,nick:"",stickers:{},cur:{type:"public"},es:null,esRetry:null,
  meIn:{},reads:{},panelGid:null,panelRole:"",serverGroups:[],
  convos:[],unread:{},pollData:{},drafts:{},reply:null,blocked:[],scheds:[],
  is_admin:false,editSeq:null,lastDay:null,burnMode:false,groupTotal:0,   // R50：屏蔽名单 / R51：定时消息 / R53：管理员标识 / R55-3：编辑态 / R55-9：日期分隔线 / R14：阅后即焚模式 // C9② 群成员总数
  packMeta:{},subs:null,shopPacks:null,curPack:"",shopOpen:false,coverV:1,
  gmembers:{},atOpen:false,atCands:[],atIdx:0,
  remarkCache:{},
  marks:[],   // R69C11：本地「标为未读」会话键（稍后处理清单）
  memByStatus:true,   // R69C12：群成员面板按在线状态分组（默认开）
  tasks:[],taskGid:null,   // R69B6/B7：群任务清单 / 面板所属群
  momUnread:0,momSig:{}};   // R65 贴纸包封面元数据/订阅/商店目录/当前包/商店视图/封面缓存戳 // R67 群成员缓存 + @选择器状态 // R68 朋友圈红点 // R69C9 好友备注缓存
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
// R69C9 好友备注名：本人视角优先（本地缓存 > 名单 remark），无则回退昵称
function dnid(uid,fb){
  const c=state.remarkCache[uid];
  if(c)return c;
  const u=(state.roster||[]).find(x=>x.uid===uid)||(state.known||[]).find(x=>x.uid===uid);
  const r=u?String(u.remark||"").trim():"";
  return r||((u&&u.nick)||fb||("用户"+uid));
}
// R69C9 备注名设置：右键好友行 → prompt（留空清除）
function remarkDlg(uid){
  const cur=String(state.remarkCache[uid]||"").trim();
  const v=prompt("设置备注名（留空=清除，最多 24 字）",cur);
  if(v===null)return;
  const rem=String(v).trim().slice(0,24);
  fetch("/api/remark",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token: state.token, uid: uid, remark: rem})})
    .then(r=>r.json()).then(r=>{if(!r.ok)showStatus(r.error||"设置失败")});
}
// R60 UI① 深浅色 + 主题家族（retro 暖粉 / flat 冷灰）
// 单 token 保存在 localStorage['web_theme']，取值：
//   light     暖粉浅（默认） / dark     暖粉深
//   flat      冷灰浅         / flat-dark 冷灰深（墨蓝黑）
function webThemeMode(){let m="";try{m=localStorage.getItem("web_theme")||""}catch(e){}
  return ["light","dark","flat","flat-dark","mist","mist-dark"].includes(m)?m:"mist";}
function applyWebTheme(mode){
  const m=(arguments.length===1)?mode:webThemeMode();
  const r=document.documentElement;
  if(m==="light")r.removeAttribute("data-theme");else r.setAttribute("data-theme",m);
  const b=$("#btnTheme");if(b)b.textContent=(m==="dark"||m==="flat-dark"||m==="mist-dark")?"☀️":"🌙";
  const fam=$("#selThemeFamily");if(fam)fam.value=m.startsWith('mist')?'mist':(m==="flat"||m==="flat-dark")?"flat":"retro";
  try{localStorage.setItem("web_theme",m)}catch(e){}
}
function setTheme(dark){          // 兼容旧布尔调用：布尔=当前家族内切深浅；字符串=整 token
  const cur=webThemeMode();let m;
  if(typeof dark==="string")m=dark;
  else{const fam=cur.startsWith('mist')?'mist':(cur==="flat"||cur==="flat-dark")?"flat":"retro";
       m=fam==='mist'?(dark?'mist-dark':'mist'):fam==="flat"?(dark?"flat-dark":"flat"):(dark?"dark":"light");}
  applyWebTheme(m);
}
function toggleTheme(){           // 🌙/☀️：当前家族内切换深浅、保留家族
  const cur=webThemeMode();if(cur.startsWith('mist')){applyWebTheme(cur==='mist'?'mist-dark':'mist');return;}const fam=(cur==="flat"||cur==="flat-dark")?"flat":"retro";
  applyWebTheme(fam==="flat"?(cur==="flat"?"flat-dark":"flat"):(cur==="dark"?"light":"dark"));
}
function setThemeFamily(fam){     // 家族切换（暖粉/冷灰）：保留当前深浅
  const cur=webThemeMode();const dark=(cur==="dark"||cur==="flat-dark"||cur==="mist-dark"); if(fam==='mist'){applyWebTheme(dark?'mist-dark':'mist');return;}
  applyWebTheme(fam==="flat"?(dark?"flat-dark":"flat"):(dark?"dark":"light"));
}
applyWebTheme();                  // 启动恢复：默认 light（暖粉浅）；旧的 "dark" 仍落在暖粉深
// ---- 功能① 被引用聚合徽标 + 功能④ 头像相框 的补充样式（一次性注入） ----
function ensureFeatureCss(){
  if(document.getElementById("featCss"))return;
  const st=document.createElement("style");st.id="featCss";
  st.textContent=
    ".msg .quo{position:absolute;right:6px;top:2px;font-size:11px;color:var(--col,#06c);"
    +"background:var(--qb,#ececec);padding:1px 6px;border-radius:9px;cursor:pointer;z-index:3}"
    +".msg .quo:hover{filter:brightness(.93)}"
    +"@keyframes avpulse{0%,100%{box-shadow:0 0 0 2px #2e9e5b}50%{box-shadow:0 0 0 4px rgba(46,158,91,.55)}}"
    +".avf-ring .avc,.avf-ring img.av{box-shadow:0 0 0 2px #3d7bff}"
    +".avf-gold .avc,.avf-gold img.av{box-shadow:0 0 0 3px #f0b429}"
    +".avf-glow .avc,.avf-glow img.av{box-shadow:0 0 0 2px #2e9e5b;animation:avpulse 2.2s ease-in-out infinite}"
    +".bub.cc{display:flex;align-items:center;gap:8px;cursor:pointer;border:1px solid var(--line,#ddd);"
    +"background:var(--card,#f4f7fb);padding:6px 10px;border-radius:10px;min-width:150px}"
    +".bub.cc:hover{filter:brightness(.96)}"
    +".bub.cc .ccn{font-weight:600}"
    +".bub.cc .ccs{font-size:11px;color:var(--dim,#888)}";
  (document.head||document.documentElement).appendChild(st);
}
// 功能④：头像相框样式（localStorage 持久化，坏数据回落 none）
function avFrame(){let v="";try{v=localStorage.getItem("web_avframe")||""}catch(e){}return ["","none","ring","gold","glow"].includes(v)?v:"none";}
function setAvFrame(v){v=(["","none","ring","gold","glow"].includes(String(v))?String(v):"none");try{localStorage.setItem("web_avframe",v)}catch(e){}}
// R__ 聊天主题（气泡配色叠层）：localStorage 持久化，应用即改 CSS 变量
function setChatTheme(v){
  const r=document.documentElement;
  if(v){r.setAttribute("data-chat",v);}else r.removeAttribute("data-chat");
  try{localStorage.setItem("web_chat_theme",v||"")}catch(e){}
}
function applyChatTheme(){
  let v="";try{v=localStorage.getItem("web_chat_theme")||""}catch(e){}
  const s=$("#selChatTheme");if(s)s.value=v;
  setChatTheme(v);
}
applyChatTheme();
function discardGroupDraft(gid,discardLocal=true){
  const key=convKey("group",gid);
  if(discardLocal)delete state.drafts[key];
  const versions=state.draftVersions||(state.draftVersions={});
  versions[key]=(versions[key]||0)+1;
  const epochs=state.groupDraftEpoch||(state.groupDraftEpoch={});
  epochs[gid]=(epochs[gid]||0)+1;
  if(state.cur.type==="group"&&state.cur.gid===gid)clearTimeout(pushDraft.t);
}
function writeDraft(c,text,token,epoch=(state.groupDraftEpoch||{})[c.gid]||0){
  // One writer per account/channel: a slow older save cannot resurrect a cleared draft.
  const key=token+"|"+convKey(c.type,c.type==="group"?c.gid:c.uid);
  const queues=writeDraft.pending||(writeDraft.pending=new Map());
  const previous=queues.get(key)||Promise.resolve();
  const next=previous.then(()=>{
    if(!token||state.token!==token)return;
    if(c.type==="group"&&(!state.meIn[c.gid]||state.groupAccessPending===c.gid||
      ((state.groupDraftEpoch||{})[c.gid]||0)!==epoch))return;
    const body={token:token,channel:c.type,text:text};
    if(c.type!=="public")body.to=c.uid||c.gid;
    return fetch("/api/draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
      .then(r=>r.json()).then(d=>{if(!d.ok)throw Error("draft rejected");});
  }).catch(()=>{if(state.token===token)showStatus("草稿同步失败，本页内容已保留");});
  queues.set(key,next);
  next.then(()=>{if(queues.get(key)===next)queues.delete(key);});
  return next;
}
function pushDraft(immediate=false){
  // Capture the owner and text at input time, before another channel is selected.
  clearTimeout(pushDraft.t);
  if(state.editSeq!=null)return;
  const c={...state.cur},text=$("#text").value,key=convKey();
  const versions=state.draftVersions||(state.draftVersions={});
  if(immediate!==true||state.drafts[key]!==text)versions[key]=(versions[key]||0)+1;
  state.drafts[key]=text;
  const token = state.token;
  const epoch=(state.groupDraftEpoch||{})[c.gid]||0;
  const save=()=>writeDraft(c,text,token,epoch);
  if(immediate===true)save();else pushDraft.t=setTimeout(save,1000);}
function applyDraft(force=false){
  // R29B：切会话时若输入为空且服务器有草稿 → 回填
  const t=$("#text");if(!force&&t.value.trim())return;
  const d=state.drafts[convKey()]||"";
  if(t.value!==d){t.value=d;t.focus();}growTextArea();}
function expand(t){return (t||"").replace(/:([A-Za-z0-9_]+):/g,(m,c)=>state.stickers[c]?state.stickers[c].emoji:m)}
function fmtTime(ts){const d=new Date(ts*1000);return String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0")}
function fmtText(t){                             // R41G + R70F：贴纸码展开 → 本地打码 → 安全 HTML
  return guardHtml(expand(t));}
// ---- R59 富文本：Markdown 解析 + 安全 HTML 渲染（粗/斜/代码/链接） ----
function richSegs(t){                         // 解析 Markdown → [[text,kind,href],...]（与桌面端同构）
  if(!t)return [];
  const out=[],re=/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\|\|[^|\n]+\|\||\[[^\]\n]+\]\([^()\s]+\))/g;
  let pos=0,m;
  while((m=re.exec(t))){
    if(m.index>pos)out.push([t.slice(pos,m.index),"plain",""]);
    const s=m[0];
    if(s.startsWith("**")&&s.endsWith("**"))out.push([s.slice(2,-2),"bold",""]);
    else if(s.startsWith("*")&&s.endsWith("*"))out.push([s.slice(1,-1),"italic",""]);
    else if(s.startsWith("`"))out.push([s.slice(1,-1),"code",""]);
    else if(s.startsWith("||"))out.push([s.slice(2,-2),"spoiler",""]);
    else{const lm=/^\[([^\[\]()\n]+)\]\s*\(\s*([^()\s]+)\s*\)$/.exec(s);
      if(lm)out.push([lm[1],"link",lm[2]]);else out.push([s,"plain",""]);}
    pos=m.index+s.length;}
  if(pos<t.length)out.push([t.slice(pos),"plain",""]);
  return out;}
function disHdr(s){                           // R70E：伪装风格表头文案（与桌面端同款）
  if(s==="code")return "📄 config.py · UTF-8 · LF";
  if(s==="log")return "["+fmtTime(Date.now()/1000)+"] INFO  connection established";
  if(s==="excel")return "Sheet1     A     B     C";
  return "";}
function disguiseHtml(e){                     // R70E：风格表头 + 正文遮盖（点击揭示）
  const hdr=disHdr(e.disguise);
  return "<div class='bub dis-"+esc(e.disguise)+"'>"
    +(hdr?"<div class='dishdr'>"+esc(hdr)+"</div>":"")
    +"<span class='spoiler' onclick=\"this.classList.toggle('on')\" title='点击揭示/遮盖'>"
    +esc(e.text||"")+"</span></div>";}
function richHtml(rich){                      // Q：rich 段 → 安全 HTML
  let h="";
  (rich||[]).forEach(seg=>{
    const t=esc(String(seg[0]||"")).replace(/\n/g,"<br>"),k=seg[1]||"plain",href=seg[2]||"";
    if(k==="bold")h+="<b>"+t+"</b>";
    else if(k==="italic")h+="<i>"+t+"</i>";
    else if(k==="code")h+="<code style='background:rgba(0,0,0,.07);padding:1px 4px;border-radius:4px;font-family:monospace;font-size:.93em'>"+t+"</code>";
    else if(k==="spoiler")h+="<span class='spoiler' onclick=\"this.classList.toggle('on')\" title='点击揭示/遮盖'>"+t+"</span>";
    else if(k==="link"){const u=/^www\./i.test(href)?("http://"+href):href;
      h+="<a href='"+esc(u)+"' target='_blank' rel='noopener'>"+t+"</a>";}
    else if(k==="hashtag")h+="<span style='color:var(--accent)'>"+t+"</span>";
    else h+=guardHtml(seg[0]===undefined?"":seg[0]);   // R70F：纯文本段走本地打码
  });
  return h||"";}
function showStatus(s){$("#status").textContent=s;setTimeout(()=>{if($("#status").textContent===s)$("#status").textContent=""},3000)}
// ---- R55-1 通知体系：标题未读计数 + 浏览器通知 + 提示音 ----
function updateTitle(){
  const total=Object.values(state.unread).reduce((a,b)=>a+b,0);
  document.title=total?"("+total+") 内部办公助手":"内部办公助手";
}
function requestNotif(){try{if("Notification"in window&&Notification.permission==="default")Notification.requestPermission()}catch(e){}}
function showNotification(e){
  try{
    if(inDnd())return;   // R61 勿扰时段：抑制浏览器通知（未读/已读计数不受影响）
    if(!("Notification"in window)||Notification.permission!=="granted")return;
    if(document.visibilityState!=="hidden")return;
    const prefix=e.everyone?"📣全体通知 · ":"";
    new Notification(prefix+(e.nick||"消息")+" 发来消息",{body:String(e.text||"").slice(0,80)||"新消息",icon:avUrl(e.uid)});
  }catch(err){}
}

// ---- R60 关键词提醒：命中关键词 → 即使当前正在看该会话也弹系统通知（勿扰仍最高优先） ----
function kwList(){
  let s="";try{s=localStorage.getItem("web_kw")||""}catch(e){}
  return String(s).replace(/，/g,",").split(",").map(x=>x.trim().toLowerCase()).filter(Boolean);}
function kwHit(e){
  const kws=kwList();if(!kws.length||!e.text)return false;
  const t=String(e.text).toLowerCase();return kws.some(w=>t.indexOf(w)>=0);}
function kwPanel(){
  let cur="";try{cur=localStorage.getItem("web_kw")||""}catch(e){}
  const v=prompt("关键词提醒（逗号分隔）：收到含关键词的消息时始终弹系统通知（免打扰仍最高优先）\n\n当前：",cur);
  if(v!==null){try{localStorage.setItem("web_kw",v)}catch(e){}showStatus("关键词已保存（"+(kwList().length)+" 个）");}}
// ---- R70F 敏感词本地打码（纯显示层；localStorage 持久化，不影响服务端存储/搜索） ----
function guardWords(){
  let s="";try{s=localStorage.getItem("web_guard_words")||""}catch(e){}
  return String(s).replace(/，/g,",").split(",").map(x=>x.trim()).filter(Boolean).slice(0,200);}
function guardOn(){try{return localStorage.getItem("web_guard_on")==="1"}catch(e){return false}}
function guardHours(){
  let s="";try{s=localStorage.getItem("web_guard_hours")||""}catch(e){}
  return String(s).trim();}
function guardActive(){                         // 开关开 + 时段命中（空=全天；支持跨天如 22-6）
  if(!guardOn())return false;
  const spec=guardHours();if(!spec)return true;
  const cur=new Date(),now=cur.getHours()*60+cur.getMinutes();
  const toM=s=>{const m=String(s||"").trim().split(":").map(x=>parseInt(x,10));
    if(!m.length||isNaN(m[0]))return null;return m[0]*60+(isNaN(m[1])?0:m[1]);};
  return spec.replace(/，/g,",").split(",").some(p=>{
    p=p.trim();if(p.indexOf("-")<0)return false;
    const a=p.split("-"),lo=toM(a[0]),hi=toM(a[1]);
    if(lo==null||hi==null)return false;
    return lo<=hi?(now>=lo&&now<hi):(now>=lo||now<hi);});}
function guardHtml(raw){                        // 纯文本 → 命中词包 .spoiler（点击揭示）
  const s=String(raw==null?"":raw),ws=guardWords();
  let out;
  if(!guardActive()||!ws.length){out=esc(s);}
  else{
    const rx=new RegExp("("+ws.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join("|")+")","gi");
    out="";let pos=0,m;
    while((m=rx.exec(s))){
      if(m.index>pos)out+=esc(s.slice(pos,m.index));
      out+="<span class='spoiler' onclick=\"this.classList.toggle('on')\" title='敏感词已打码，点击揭示'>"+esc(m[0])+"</span>";
      pos=m.index+m[0].length;if(!m[0].length)rx.lastIndex++;}
    if(pos<s.length)out+=esc(s.slice(pos));
  }
  return out.replace(/#[^\s#]{1,32}/g,mm=>"<span style='color:var(--accent)'>"+mm+"</span>").replace(/\n/g,"<br>");}
function refreshGuardView(){                     // 开关/词表变更 → 重载当前会话以套用打码
  try{const box=$("#msgs");if(box)box.innerHTML="";loadHistory(state.cur);}catch(e){}}
function guardPanel(){
  let m=document.getElementById("guarddlg");if(m)m.remove();
  m=document.createElement("div");m.id="guarddlg";
  m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  let cur="";try{cur=localStorage.getItem("web_guard_words")||""}catch(e){}
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(320px,88vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:10px'>🕶️ 敏感词打码（仅本机显示）</div>"
    +"<div style='display:flex;align-items:center;gap:6px;margin-bottom:8px'><input type='checkbox' id='gdOn'"+(guardOn()?" checked":"")+"><label for='gdOn'>启用打码（命中词遮盖，点击揭示）</label></div>"
    +"<div style='font-size:12px;color:var(--dim);margin-bottom:4px'>敏感词（逗号或换行分隔）</div>"
    +"<textarea id='gdWords' rows='5' style='width:100%;box-sizing:border-box;resize:vertical'>"+esc(cur)+"</textarea>"
    +"<div style='font-size:12px;color:var(--dim);margin:8px 0 4px'>生效时段（留空=全天，如 9-18 或 22-6）</div>"
    +"<input id='gdHours' value='"+esc(guardHours())+"' placeholder='全天' style='width:100%;box-sizing:border-box'>"
    +"<div style='font-size:11px;color:var(--dim);margin-top:6px'>仅影响本机显示，不影响消息存储、搜索与复制。</div>"
    +"<div style='display:flex;gap:6px;margin-top:12px'><button id='gdOk' style='flex:1'>保存</button><button class='ghost' id='gdX' style='flex:1'>关闭</button></div>";
  m.appendChild(card);m.onclick=e=>{if(e.target===m)m.remove()};document.body.appendChild(m);
  $("#gdX").onclick=()=>m.remove();
  $("#gdOk").onclick=()=>{
    const on=document.getElementById("gdOn").checked;
    const ws=document.getElementById("gdWords").value.replace(/，/g,",");
    const hh=document.getElementById("gdHours").value.trim();
    try{localStorage.setItem("web_guard_on",on?"1":"0");
      localStorage.setItem("web_guard_words",ws);
      localStorage.setItem("web_guard_hours",hh);}catch(e){}
    m.remove();
    showStatus(on?("🕶️ 打码已开启（"+guardWords().length+" 个词，点击遮盖可揭示）"):"打码已关闭");
    refreshGuardView();};
}
// ---- R70H 摸鱼排行榜（只读展示；服务器 opt-in 关闭时恒为空榜，网页端不上报） ----
function fishGames(){                          // 可选游戏：注册目录 ∪ 已收榜单 ∪ 当前房间
  const s=new Set(Object.keys(state.gmeta||{}));
  Object.keys(state.fish||{}).forEach(k=>s.add(k));
  const rm=state.gst&&state.gst.room;if(rm&&rm.game)s.add(rm.game);
  return Array.from(s).filter(Boolean).sort();}
window.fishRender=function(){
  const box=document.getElementById("fishList");if(!box)return;
  const es=((state.fish||{})[state.fishGame])||[];
  if(!es.length){box.innerHTML="<div style='color:var(--dim);font-size:12px;padding:12px 0'>（暂无数据，点击「刷新」拉取）</div>";return;}
  const md=["🥇","🥈","🥉"];
  box.innerHTML=es.map((e,i)=>"<div style='display:flex;justify-content:space-between;padding:6px 2px;border-bottom:1px solid var(--line)'>"
    +"<span>"+(md[i]||((i+1)+"."))+" "+esc(e.nick||"?")+"</span>"
    +"<b>"+(parseInt(e.score,10)||0)+" 分</b></div>").join("");};
function fishFetch(){
  const g=state.fishGame||"";
  fetch("/api/fish_board"+(g?("?game="+encodeURIComponent(g)):""))
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"拉取失败");return;}
      if(d.game){state.fish=Object.assign({},state.fish||{});state.fish[d.game]=d.entries||[];}
      window.fishRender();}).catch(()=>showStatus("拉取失败"));}
function fishBoardPanel(){
  let m=document.getElementById("fishdlg");if(m)m.remove();
  m=document.createElement("div");m.id="fishdlg";
  m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(340px,90vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:4px'>🏆 摸鱼排行榜</div>"
    +"<div style='font-size:11px;color:var(--dim);margin-bottom:8px'>按游戏累计积分（每结束一局 +1），仅显示昵称与总分</div>"
    +"<div style='display:flex;gap:6px;margin-bottom:8px'><select id='fishSel' style='flex:1'></select><button id='fishGo'>刷新</button></div>"
    +"<div id='fishList' style='min-height:80px;max-height:300px;overflow:auto'></div>"
    +"<button class='ghost' id='fishX' style='width:100%;margin-top:12px'>关闭</button>";
  m.appendChild(card);document.body.appendChild(m);
  const close=()=>{state.fishOpen=false;m.remove();};
  m.onclick=e=>{if(e.target===m)close()};
  $("#fishX").onclick=close;
  state.fishOpen=true;
  const sel=$("#fishSel");
  const fill=()=>{
    const gs=fishGames();sel.innerHTML="";
    if(!gs.length){const o=document.createElement("option");o.value="";o.textContent="（暂无游戏）";sel.appendChild(o);state.fishGame="";return;}
    if(!state.fishGame||gs.indexOf(state.fishGame)<0)state.fishGame=gs[0];
    gs.forEach(g=>{const o=document.createElement("option");o.value=g;o.textContent=g;if(g===state.fishGame)o.selected=true;sel.appendChild(o);});};
  fill();
  sel.onchange=()=>{state.fishGame=sel.value;fishFetch();};
  $("#fishGo").onclick=()=>fishFetch();
  window.fishRender();
  if(Object.keys(state.gmeta||{}).length===0){     // 目录未载入 → 顺带拉一次元数据补齐下拉
    fetch("/api/game_list").then(r=>r.json()).then(d=>{
      if(d.ok){state.gmeta={};(d.games||[]).forEach(g=>state.gmeta[g.name]=g);fill();}
      fishFetch();}).catch(()=>fishFetch());
  }else fishFetch();
}
function notifySound(){                       // R67：网页端提示音档位（与桌面 prefs['notify_sound'] 语义一致）
  let s="";try{s=localStorage.getItem("notify_sound")||""}catch(e){}
  return ["off","soft","default","ding"].indexOf(s)>=0?s:"default";}
function playSound(){                       // WebAudio 合成提示音，无需静态文件
  try{
    if(inDnd())return;   // R61 勿扰时段：抑制提示音
    const s=notifySound();if(s==="off")return;
    const ctx=window.__ac||(window.__ac=new (window.AudioContext||window.webkitAudioContext)());
    if(ctx.state==="suspended")ctx.resume();
    const o=ctx.createOscillator(),g=ctx.createGain();
    if(s==="soft"){o.type="sine";o.frequency.value=660;g.gain.value=0.035;}     // 轻柔：低音轻短
    else if(s==="ding"){o.type="triangle";o.frequency.value=1568;g.gain.value=0.05;}  // 叮咚：清脆
    else{o.type="sine";o.frequency.value=880;g.gain.value=0.05;}                // 默认：原 880Hz
    o.connect(g);g.connect(ctx.destination);
    const dur=s==="soft"?160:(s==="ding"?260:220);
    o.start();
    setTimeout(()=>{o.stop();g.disconnect()},dur);
  }catch(err){}
}
function soundPanel(){                                    // R67：新消息提示音设置弹层（localStorage 存取，点选即试听+保存）
  let m=document.getElementById("sounddlg");if(m)m.remove();
  m=document.createElement("div");m.id="sounddlg";
  m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const cur=notifySound(),labels={"off":"🔇 关闭","soft":"🔈 轻柔","default":"🔔 默认","ding":"🔔 叮咚"};
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(280px,84vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:12px'>🔔 新消息提示音</div>"
    +Object.keys(labels).map(k=>{const on=k===cur;
      return "<div class='sndopt' data-k='"+k+"' style='display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:8px;cursor:pointer;margin-bottom:4px;background:"+(on?"var(--bub2,#fff)":"transparent")+"'>"
        +"<span style='flex:1'>"+labels[k]+"</span>"+(on?"<span style='font-size:11px;color:var(--dim)'>✓</span>":"")+"</div>";}).join("")
    +"<div style='display:flex;gap:6px;margin-top:12px'><button id='soundX' class='ghost' style='flex:1'>关闭</button></div>";
  m.appendChild(card);m.onclick=e=>{if(e.target===m)m.remove()};document.body.appendChild(m);
  $("#soundX").onclick=()=>m.remove();
  card.querySelectorAll(".sndopt").forEach(d=>{d.onclick=()=>{
    try{localStorage.setItem("notify_sound",d.dataset.k)}catch(e){}
    playSound();                                  // 立即试听
    card.querySelectorAll(".sndopt").forEach(x=>{x.style.background="transparent";
      const ck=x.querySelector("span:last-child");if(ck&&ck.textContent==="✓")ck.textContent="";});
    d.style.background="var(--bub2,#fff)";
    const dd=d.querySelector("span:last-child");if(dd)dd.textContent="✓";
    showStatus("提示音已保存："+labels[d.dataset.k]);};});
}
// ---- R61 勿扰时段（网页端本地设置，与桌面统一：只抑制打扰，不影响未读/已读） ----
function dndRange(){try{const r=JSON.parse(localStorage.getItem("dnd_range")||"null");return r&&typeof r==="object"?r:{};}catch(e){return{}}}
function inDnd(){const r=dndRange();if(!r.on)return false;   // 支持跨天（如 23:00~08:00）
  const toM=s=>{const m=String(s||"").split(":").map(x=>parseInt(x,10));if(m.length!==2||isNaN(m[0])||isNaN(m[1]))return null;return m[0]*60+m[1];};
  const a=toM(r.start),b=toM(r.end);if(a==null||b==null)return false;
  const d=new Date(),cur=d.getHours()*60+d.getMinutes();
  if(a===b)return true;if(a<b)return a<=cur&&cur<b;return cur>=a||cur<b;}
function insertEvbody(){const t=$("#text");const s=t.selectionStart,en=t.selectionEnd;
  t.value=t.value.slice(0,s)+"@全体 "+t.value.slice(en);t.focus();try{t.setSelectionRange(s+4,s+4)}catch(e){}}
function dndPanel(){                                    // 勿扰时段设置弹层（localStorage 存取）
  let m=document.getElementById("dnddlg");if(m)m.remove();
  m=document.createElement("div");m.id="dnddlg";
  m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const r=dndRange(),st=r.start||"23:00",en=r.end||"08:00";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(280px,84vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:12px'>🔕 勿扰时段</div>"
    +"<div style='display:flex;align-items:center;gap:6px;margin-bottom:10px'><input type='checkbox' id='dndOn'"+(r.on?" checked":"")+"><label for='dndOn'>启用勿扰（时段内不弹通知/提示音）</label></div>"
    +"<div style='display:flex;gap:8px;align-items:center;margin-bottom:6px'><span style='font-size:12px;color:var(--dim)'>开始</span><input id='dndStart' type='time' value='"+st+"' style='flex:1'></div>"
    +"<div style='display:flex;gap:8px;align-items:center;margin-bottom:12px'><span style='font-size:12px;color:var(--dim)'>结束</span><input id='dndEnd' type='time' value='"+en+"' style='flex:1'></div>"
    +"<div style='display:flex;gap:6px'><button id='dndOk' style='flex:1'>保存</button><button class='ghost' id='dndX' style='flex:1'>关闭</button></div>";
  m.appendChild(card);m.onclick=e=>{if(e.target===m)m.remove()};document.body.appendChild(m);
  $("#dndX").onclick=()=>m.remove();
  $("#dndOk").onclick=()=>{const on=document.getElementById("dndOn").checked;
    let s=document.getElementById("dndStart").value||"23:00",e=document.getElementById("dndEnd").value||"08:00";
    if(!/^\d{2}:\d{2}$/.test(s)||!/^\d{2}:\d{2}$/.test(e)){showStatus("时间格式需为 HH:MM");return;}
    try{localStorage.setItem("dnd_range",JSON.stringify({on:on,start:s,end:e}))}catch(err){}
    m.remove();showStatus(on?"🔕 勿扰已开启（"+s+"~"+e+"，时段内不弹通知/提示音）":"勿扰已关闭");};
}
const LB={list:[],i:0};                          // R69B5：灯箱多图态（←/→ 循环翻页）
function lightbox(src){                          // R43B2 页内灯箱：替代 window.open（不弹新标签，Esc/点击关闭）
  lbOpen(src,null,null);
}
function lightboxList(list,idx){                 // R69B5：多图灯箱（图片墙点格进入，←/→ 循环翻页）
  const ls=(list||[]).slice();
  lbOpen(ls[Math.max(0,Math.min(idx||0,ls.length-1))],ls,idx||0);
}
function lbOpen(src,list,idx){
  let lb=document.getElementById("lb");
  if(!lb){
    lb=document.createElement("div");lb.id="lb";
    lb.innerHTML="<img alt='查看大图'><b class='lbnav prev' title='上一张（←）'>‹</b>"
      +"<b class='lbnav next' title='下一张（→）'>›</b><i class='lbnum'></i>";
    lb.onclick=ev=>{if(!ev.target.classList||!ev.target.classList.contains("lbnav"))lb.classList.remove("on");};
    document.body.appendChild(lb);
    lb.querySelector(".prev").onclick=ev=>{ev.stopPropagation();lbStep(-1);};
    lb.querySelector(".next").onclick=ev=>{ev.stopPropagation();lbStep(1);};
    document.addEventListener("keydown",e=>{
      const x=document.getElementById("lb");
      if(!x||!x.classList.contains("on"))return;
      if(e.key==="Escape")x.classList.remove("on");
      else if(e.key==="ArrowLeft")lbStep(-1);
      else if(e.key==="ArrowRight")lbStep(1);});
  }
  LB.list=(list&&list.length)?list.slice():[src];
  let i=(idx==null)?LB.list.indexOf(src):idx;
  LB.i=Math.max(0,Math.min(i<0?0:i,LB.list.length-1));
  lbShow();
  lb.classList.add("on");
}
function lbShow(){
  const lb=document.getElementById("lb");if(!lb)return;
  lb.querySelector("img").src=LB.list[LB.i]||"";
  const many=LB.list.length>1;
  lb.querySelector(".prev").style.display=many?"":"none";
  lb.querySelector(".next").style.display=many?"":"none";
  lb.querySelector(".lbnum").textContent=many?((LB.i+1)+" / "+LB.list.length):"";
}
function lbStep(d){
  if(LB.list.length<2)return;
  LB.i=(LB.i+d+LB.list.length)%LB.list.length;   // 循环翻页（与桌面灯箱一致）
  lbShow();
}
// R69B5 会话图片墙：聚合当前会话已加载消息里的图片（不含头像/贴纸/表情包）
function albumSrcs(){
  return [...document.querySelectorAll("#msgs .bub img.mimg")]
    .map(im=>im.getAttribute("src")).filter(Boolean);}
function closeAlbum(){const x=document.getElementById("alb");if(x)x.classList.remove("on");}
function openAlbum(){
  const srcs=albumSrcs();
  if(!srcs.length){showStatus("本会话暂无图片（图片墙聚合已加载消息的图片）");return;}
  let box=document.getElementById("alb");
  if(!box){
    box=document.createElement("div");box.id="alb";
    box.innerHTML="<div class='card'><div class='hd'><span id='albTitle'></span>"
      +"<button class='ghost' id='albX' title='关闭（Esc）'>✕</button></div>"
      +"<div class='grid' id='albGrid'></div></div>";
    box.onclick=ev=>{if(ev.target===box)closeAlbum();};
    document.body.appendChild(box);
    document.getElementById("albX").onclick=closeAlbum;
    document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAlbum();});
  }
  const g=document.getElementById("albGrid");
  g.innerHTML="";
  srcs.forEach((s,i)=>{
    const d=document.createElement("div");d.className="cell";
    const im=document.createElement("img");im.src=s;im.loading="lazy";im.alt="";
    d.appendChild(im);
    d.onclick=()=>lightboxList(srcs,i);
    g.appendChild(d);});
  document.getElementById("albTitle").textContent=
    "🖼 图片墙 · "+channelName()+" · 共 "+srcs.length+" 张";
  box.classList.add("on");
}
// ---- R69B6/B7 群待办 / 接龙 / 签到（服务端权威：TASK_* + task_state 广播） ----
const TK_MODE={todo:"待办",relay:"接龙",checkin:"签到"};
const TK_DO={todo:"✓ 完成",relay:"＋ 接龙",checkin:"📍 打卡"};
function tkMode(){
  const r=document.querySelector("input[name='tkmode']:checked");
  return r?r.value:"todo";}
function openTasksPanel(){
  const c=state.cur;
  if(c.type!=="group"||!state.panelGid){showStatus("请先打开群聊");return;}
  state.taskGid=state.panelGid;
  let box=document.getElementById("tkpanel");
  if(!box){
    box=document.createElement("div");box.id="tkpanel";
    box.innerHTML="<div class='card'><div style='display:flex;align-items:center;gap:6px'>"
      +"<b style='flex:1'>🧾 群待办 / 接龙 / 签到</b>"
      +"<button class='ghost' id='tkX' title='关闭'>✕</button></div>"
      +"<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap'>"
      +"<label><input type='radio' name='tkmode' value='todo' checked> 待办</label>"
      +"<label><input type='radio' name='tkmode' value='relay'> 接龙</label>"
      +"<label><input type='radio' name='tkmode' value='checkin'> 签到</label>"
      +"<input id='tkText' placeholder='内容，Enter 发起' maxlength='200' style='flex:1;min-width:120px'>"
      +"<button id='tkAdd'>发起</button></div>"
      +"<div id='tkList'></div></div>";
    box.onclick=ev=>{if(ev.target===box)box.classList.remove("on");};
    document.body.appendChild(box);
    document.getElementById("tkX").onclick=()=>box.classList.remove("on");
    document.getElementById("tkAdd").onclick=tkAdd;
    document.getElementById("tkText").addEventListener("keydown",
      e=>{if(e.key==="Enter"){e.preventDefault();tkAdd();}});
  }
  box.classList.add("on");
  groupApi("task_list",{gid:state.taskGid});      // 拉最新清单（回帧走 SSE）
  renderTasks();
}
function tkAdd(){
  const el=document.getElementById("tkText");
  const t=(el.value||"").trim();
  if(!t){showStatus("内容不能为空");return;}
  el.value="";
  groupApi("task_add",{gid:state.taskGid,text:t,mode:tkMode()});
}
function tkDo(tid,on){groupApi("task_do",{gid:state.taskGid,tid:tid,on:on?1:0});}
function tkDel(tid){groupApi("task_del",{gid:state.taskGid,tid:tid});}
function renderTasks(){
  const box=document.getElementById("tkList");if(!box)return;
  const ts=state.tasks||[];
  if(!ts.length){box.innerHTML="<div style='color:#999;font-size:12px'>暂无任务，输入内容后点「发起」</div>";return;}
  box.innerHTML=ts.map(t=>{
    const done=t.done||{},n=Object.keys(done).length;
    const mine=done[String(state.uid)]!=null;
    const mark=t.closed?"✅":(mine?"☑":"☐");
    const tail="<span style='color:#999;font-size:11px'> · "+n+" 人 · "+esc(dnid(t.uid))+"</span>";
    if(t.closed)return "<div class='mrow'>"+mark+" <span class='tag'>"+esc(TK_MODE[t.mode]||"待办")
      +"</span> "+esc(t.text)+tail+"</div>";
    return "<div class='mrow'>"+mark+" <span class='tag'>"+esc(TK_MODE[t.mode]||"待办")
      +"</span> "+esc(t.text)+tail
      +" <button class='row-btn' onclick='tkDo("+t.tid+","+(mine?0:1)+")'>"
      +(mine?"↩ 撤销":(TK_DO[t.mode]||"＋ 参与"))+"</button>"
      +" <button class='row-btn' onclick='tkDel("+t.tid+")'>关闭</button></div>";}).join("");
}
function channelName(){const c=state.cur;
  if(c.type==="public")return "公共聊天";
  if(c.type==="group"){const g=[...document.querySelectorAll("#groups .item")].find(e=>e.dataset.gid==c.gid);return g?g.textContent.trim():"群聊"}
  if(c.type==="private"){                      // R46：私聊标题解析 bot/会话昵称
    const b=(state.bots||[]).find(x=>x.uid===c.uid);
    const cv=(state.convos||[]).find(x=>x.uid===c.uid);
    const u=(state.roster||[]).find(x=>x.uid===c.uid);
    return "私聊："+dnid(c.uid,(b&&b.nick)||(cv&&cv.nick)||(u&&u.nick))}   // R69C9 备注名优先
  return "私聊："+c.uid}
// ---- R20：会话键 / 已读 / 群管理 ----
function convKey(type,to){const c=type||state.cur.type;
  if(type==null)to=c==="group"?state.cur.gid:state.cur.uid;
  if(c==="public")return "public";
  if(c==="group")return "group:"+to;
  const lo=Math.min(state.uid,to),hi=Math.max(state.uid,to);return "private:"+lo+":"+hi;}
function groupApi(action,data){
  const token = state.token,navigation=state.navigationRequest;
  const body=Object.assign({token:state.token,action:action},data||{});
  fetch("/api/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(state.token!==token)return;
      if(d.ok&&d.groups){
        if(action==="join"&&data.gid!=null)state.meIn[data.gid]=true;
        if(action==="leave"&&data.gid!=null){
          const sameNavigation=state.navigationRequest===navigation;
          const inSameGroup=state.cur.type==="group"&&state.cur.gid===data.gid;
          // Always invalidate writes captured before this leave. A newer visit
          // keeps its local text until fresh detail confirms current membership.
          discardGroupDraft(data.gid,sameNavigation||!inSameGroup);
          if(sameNavigation){
            delete state.meIn[data.gid];
            if(inSameGroup)selectChannel({type:"public"},false);
          }
        }
        if(action==="join_invite")showStatus("已凭邀请码加入群");   // R28
        syncGroups(d.groups);
        if(action==="join"&&data.gid!=null&&state.navigationRequest===navigation){openGroup({gid:data.gid});}
        if(action==="ann_mode"||action==="announce"||action==="slow")refreshPanel();   // C9①/R70D：模式/公告/慢速变化刷新面板
      }else if(!d.ok&&d.error){showStatus(d.error);}});}
function createGroup(){
  const name=prompt("输入新群名");
  if(!name)return;
  const isPub=confirm("设为公开群？\n\n公开群：所有人都能看到并直接加入。\n私有群（默认）：仅群成员可见，需凭邀请码加入。");
  groupApi("create",{name:name.slice(0,20),public:isPub?1:0});}
function openGroup(g){
  const token = state.token,navigation=state.navigationRequest=(state.navigationRequest||0)+1;
  // 成员关系一律由 detail 判定；已加入则进会话+面板，否则提示加入
  fetch("/api/group_detail?gid="+g.gid).then(r=>r.json()).then(d=>{
    if(state.token!==token||state.navigationRequest!==navigation)return;
    if((!d.ok||!d.member)&&state.cur.type==="group"&&state.cur.gid===g.gid){
      state.meIn[g.gid]=false;state.groupAccessPending=null;
      discardGroupDraft(g.gid);closePanel();selectChannel({type:"public"},false);
      showStatus("群不可用或已不在该群，返回公共聊天");return;
    }
    if(!d.ok){showStatus("群不存在或无权访问");return;}
    state.meIn[g.gid]=!!d.member;
    if(!d.member){ if(confirm("加入群「"+g.name+"」？"))groupApi("join",{gid:g.gid});return; }
    state.gmembers[g.gid]=d.members||[];   // R67：缓存群成员供 @ 候选
    state.groupAccessPending=null;
    selectChannel({type:"group",gid:g.gid});
    renderGroupPanel(d);
    // R9H：进群时把 detail 的 avatar 同步到列表项，群头像即刻可见
    const lg=(state.serverGroups.length?state.serverGroups:state.groups||[]).find(x=>x.gid===g.gid);
    if(lg&&d.avatar){(lg.avatar=d.avatar);renderGroups();}
    });}
function renderGroupPanel(d){
  state.panelGid=d.gid;state.panelRole=d.my_role||"member";
  state.panelDetail=d;state.hideInvis=state.hideInvis||false;   // R57 可选隐藏隐身成员
  state.groupTotal=(d.members||[]).length;   // C9②：群成员总数（供 N/M 已读）
  const p=$("#apanel");p.style.display="block";
  const isAdmin=(d.my_role==="owner"||d.my_role==="admin");
  let h="<h3>"+esc(d.name)+"（成员管理）</h3>";
  if(d.announce)h+="<div class='ann'>📢 "+esc(d.announce)+"</div>";
  if(d.announce_mode)h+="<div style='font-size:11px;color:#c0392b;margin-bottom:6px'>🔒 已开启「仅公告说话」模式，普通成员只能回复引用公告</div>";
  if(d.slow)h+="<div style='font-size:11px;color:#2e7d32;margin-bottom:6px'>🐢 已开启群慢速模式（"+d.slow+" 秒）</div>";   // R70D
  // R9H：群资料——头像 + 群简介（有图贴图，无图回退首字）
  h+="<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>"
     +"<span id='gAv' style='width:36px;height:36px'></span>"
     +"<div style='flex:1;line-height:1.4'>"
     +"<div style='font-size:12px;color:#1890ff;font-weight:600'>群简介</div>"
     +"<div style='font-size:12px;color:#555'>"+(d.about?"📝 "+esc(d.about):"<span style='color:#aaa'>（暂无群简介）</span>")+"</div>"
     +"</div></div>";
  h+="<div style='margin-bottom:6px'>"
     +"<button class='row-btn' onclick='setAnnounce()'>"+((isAdmin)?"修改公告":"查看公告")+"</button>"
     +"<button class='row-btn' onclick='leaveGroup()'>退出该群</button>";
  if(isAdmin){  // R28：群主/管理员专属邀请码 + 改名 + R9H 群资料编辑
    h+="<button class='row-btn' onclick='getInvite()'>复制邀请码</button>"
       +"<button class='row-btn' onclick='renameGroup()'>重命名群</button>"
       +"<button class='row-btn' onclick='setGroupAbout()'>编辑群简介</button>"
       +"<button class='row-btn' onclick='setAnnMode()'>"
       +(d.announce_mode?"🔓 关闭仅公告":"🔒 开启仅公告")+"说话</button>"
       // R70D：群慢速档位下拉（0/5/10/30/60/300 秒，服务端白名单校验）
       +"<select class='row-btn' onchange='setGroupSlow(this.value)'>"
       +[0,5,10,30,60,300].map(s=>"<option value='"+s+"'"+(Number(d.slow||0)===s?" selected":"")+">"
         +(s?("🐢 慢速 "+s+" 秒"):"🐢 关闭慢速")+"</option>").join("")
       +"</select>"
       +"<button class='row-btn' onclick='uploadGroupAvatar()'>上传群头像</button>"
       +"<button class='row-btn' onclick='delGroupAvatar()'>清除群头像</button>";
  }
  // R57：普通成员可选开关——把「隐身上线」的成员从这份成员列表里临时隐藏
  h+="<button class='row-btn' onclick='toggleHideInvis()'>"
     +(state.hideInvis?"🙈 显示隐身成员":"👻 隐藏隐身成员")+"</button>"
     // R69C12：按在线状态分组开关（默认开）
     +"<button class='row-btn' onclick='toggleMemGroup()'>"
     +(state.memByStatus===false?"按状态分组 ●":"关闭分组 ○")+"</button>"
     // R69B6/B7：群待办/接龙/签到面板
     +"<button class='row-btn' onclick='openTasksPanel()'>🧾 群任务</button>"
     +"</div>";
  const memStatus=m=>{const u=(state.roster||[]).find(x=>x.uid===m.uid);
    return u?((u.status)||"online"):"offline";};
  const memRank=m=>(m.role==="owner"||m.role==="admin")?0:1;
  const memRow=m=>{
    const tag=m.role==="owner"?"<span class='tag o'>群主</span>":(m.role==="admin"?"<span class='tag a'>管理</span>":"");
    const muted=m.muted?"（禁言中）":"";
    const invLbl=m.invisible?"<span style='color:#8e24aa;font-size:11px'>👻隐身</span>":"";
    let btns="";
    if(m.uid!==state.uid&&isAdmin&&m.role!=="owner"){
      btns+="<button class='row-btn' onclick='groupApi(\"kick\",{gid:"+d.gid+",target:"+m.uid+"})'>踢</button>"
         +"<button class='row-btn' onclick='toggleMute("+d.gid+","+m.uid+","+m.muted+")'>"+(m.muted?"解禁":"禁言")+"</button>";
      if(d.my_role==="owner"){
        btns+="<button class='row-btn' onclick='groupApi(\"admin\",{gid:"+d.gid+",target:"+m.uid+",enable:"+(m.role!=="admin")+"})'>"
           +(m.role==="admin"?"撤管":"设管")+"</button>";}}
    const s=memStatus(m),stLbl=ST_TEXT[s]||ST_TEXT.offline;
    return "<div class='mrow'>"+(ST_COLOR[s]?"<span style='color:"+ST_COLOR[s]+"'>●</span> ":"")
       +"<span class='nick'>"+esc(dnid(m.uid,m.nick))+" "+esc(muted)+" "+invLbl+"</span>"   // R69C9 备注名优先
       +"<span style='color:#999;font-size:11px;margin-left:4px'>"+stLbl+"</span>"+tag+btns+"</div>";};
  const visible=d.members.filter(m=>!(state.hideInvis&&m.invisible));   // R57：按开关过滤
  if(state.memByStatus!==false){                 // R69C12：在线/离开/忙碌/离线 分组
    const cnt={};
    visible.forEach(m=>{const s=memStatus(m);cnt[s]=(cnt[s]||0)+1;});
    ["online","away","busy","offline"].forEach(s=>{
      const grp=visible.filter(m=>memStatus(m)===s);
      if(!grp.length)return;
      grp.sort((a,b)=>memRank(a)-memRank(b)||a.uid-b.uid);
      h+="<div style='margin:6px 0 2px;font-size:11px;font-weight:600;color:"
        +(ST_COLOR[s]||ST_COLOR.offline)+"'>● "+ST_TEXT[s]+"（"+cnt[s]+"）</div>";
      grp.forEach(m=>{h+=memRow(m);});});
  }else{
    visible.sort((a,b)=>memRank(a)-memRank(b)||a.uid-b.uid);
    visible.forEach(m=>{h+=memRow(m);});
  }
  p.innerHTML=h;
  setGroupAv(p.querySelector("#gAv"),d,36);}   // R9H：面板头像（拖过 DOM 挂载后填充）
// R9H：群资料编辑（仅群主/管理员按钮可见；服务器仍强制校验权限）
function setGroupAbout(){                       // 编辑群简介（支持清空）
  const cur=(state.panelDetail&&state.panelDetail.about)||"";
  const t=prompt("输入群简介（≤80 字；留空=清除）",cur);
  if(t!==null)groupApi("about",{gid:state.panelGid,text:t.slice(0,80)});}
function uploadGroupAvatar(){                   // 上传/更换群头像（≤1MB）
  const inp=document.createElement("input");inp.type="file";inp.accept="image/*";
  inp.onchange=()=>{
    const f=inp.files[0];if(!f)return;
    if(f.size>1048576){showStatus("群头像不能超过 1MB");return}
    const rd=new FileReader();
    rd.onload=()=>{
      const b64=String(rd.result).split(",")[1]||"";
      const ext=(f.name.split(".").pop()||"png").toLowerCase().replace(/[^a-z0-9]/g,"");
      const body=Object.assign({token:state.token,action:"avatar_set"},
        {gid:state.panelGid,ext:ext,data:b64});
      fetch("/api/group",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
        .then(r=>r.json()).then(d=>{if(!d.ok){showStatus(d.error||"上传失败");return}
          showStatus("✅ 群头像已更新，已同步全员");});};
    rd.readAsDataURL(f);};
  inp.click();}
function delGroupAvatar(){                      // 清除群头像
  if(!confirm("确认清除该群头像？"))return;
  groupApi("avatar_del",{gid:state.panelGid});}
function toggleHideInvis(){
  state.hideInvis=!state.hideInvis;
  if(state.panelDetail)renderGroupPanel(state.panelDetail);
}
function toggleMemGroup(){   // R69C12：群成员面板「按在线状态分组」开关
  state.memByStatus=(state.memByStatus===false);
  if(state.panelDetail)renderGroupPanel(state.panelDetail);}
function toggleMute(gid,target,on){groupApi("mute",{gid:gid,target:target,duration:on?0:600});}
function setAnnounce(){const t=prompt("输入群公告（清空=清除）");if(t!==null)groupApi("announce",{gid:state.panelGid,text:t});}
function setAnnMode(){   // C9①：仅公告说话模式开关（owner/admin）
  const on=state.panelDetail&&state.panelDetail.announce_mode;
  if(!confirm("确定"+(on?"关闭":"开启")+"「仅公告说话」模式？"))return;
  groupApi("ann_mode",{gid:state.panelGid,on:!on});}
function setGroupSlow(v){   // R70D：群慢速档位（秒，0=关闭；owner/admin，服务端校验）
  groupApi("slow",{gid:state.panelGid,seconds:Number(v)||0});}
function getInvite(){groupApi("invite",{gid:state.panelGid});}                    // R28：取邀请码（SSE 回 group_invite）
function renameGroup(){const n=prompt("输入新群名");if(n)groupApi("rename",{gid:state.panelGid,name:n.slice(0,20)});}  // R28：群改名
function joinByInvite(){const code=prompt("输入 8 位群邀请码");if(code)groupApi("join_invite",{code:code.trim()});}       // R28：凭邀请码入群
function showInviteCode(code){   // R28：弹窗显示邀请码，并尝试复制到剪贴板
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(code||"").catch(()=>{});
  prompt("群邀请码（已尝试复制到剪贴板）",code||"");}
function leaveGroup(){if(state.panelGid&&confirm("确认退出该群？")){groupApi("leave",{gid:state.panelGid});closePanel();}}
function syncGroups(list){
  state.groups=list;state.serverGroups=list;
  renderGroups();
  refreshPanel();
}
// R9H：群状态/群头像回帧 → 把 about/avatar 同步进群对象并重绘列表与面板
function syncGroupProfile(d){
  const gid=d.gid,src=(state.serverGroups.length?state.serverGroups:state.groups)||[];
  const g=src.find(x=>x.gid===gid);
  const avatar=("ext" in d)?(d.ext||""):("avatar" in d?(d.avatar||""):null);
  const about=("about" in d)?(d.about||""):null;
  if(g){
    if(avatar!==null)g.avatar=avatar;
    if(about!==null)g.about=about;
  }
  if(state.panelDetail&&state.panelDetail.gid===gid){
    if(avatar!==null)state.panelDetail.avatar=avatar;
    if(about!==null)state.panelDetail.about=about;
    renderGroupPanel(state.panelDetail);
  }
  renderGroups();}
function closePanel(){state.panelGid=null;$("#apanel").style.display="none";}
function renderRead(){
  const key=convKey();const recs=state.reads[key]||{};
  document.querySelectorAll("#msgs .msg").forEach(node=>{
    const rd=node.querySelector(".rd");
    if(!rd)return;
    if(node.dataset.own==="1"){
      const seq=+node.dataset.seq||0;
      // C9②：群@(所有人)消息显示「✓ N/M 已读」逐人统计
      const isGroupAt=state.cur&&state.cur.type==="group"&&node.classList.contains("evb")&&state.groupTotal>1;
      const readN=isGroupAt?Object.keys(recs).filter(u=>u!=state.uid&&recs[u]>=seq).length:0;
      if(isGroupAt&&readN>0){
        rd.textContent="✓ "+readN+"/"+state.groupTotal+" 已读";
        rd.style.cursor="pointer";
        rd.title="点击查看谁已读（N/M）";
        rd.onclick=()=>showReadDetail(seq);
      }else{
        const anyRead=Object.keys(recs).some(u=>u!=state.uid&&recs[u]>=seq);
        if(anyRead){
          rd.textContent="✓ 已读";
          rd.style.cursor="pointer";
          rd.title="点击查看谁已读";
          rd.onclick=()=>showReadDetail(seq);   // R33③：点击弹已读成员
        }else{rd.textContent="";rd.onclick=null;}
      }
    }else{rd.textContent="";}
  });
}
function showReadDetail(seq){   // R33③：已读详情 → 列出读到本条的成员；群会话用 /api/readers 逐人统计（C9②）
  const isGroup=state.cur&&state.cur.type==="group";
  const body={token:state.token,key:convKey()};
  if(isGroup)body.seq=seq;
  fetch(isGroup?"/api/readers":"/api/read_detail",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"获取失败");return}
      if(isGroup){
        const read=(d.members||[]).map(x=>x.uid===state.uid?"我":x.nick);
        const unread=(d.unread||[]).map(x=>x.uid===state.uid?"我":x.nick);
        if(!read.length){showStatus("还没有人已读");return}
        let s="👀 已读 "+d.count+"/"+d.total+"："+read.slice(0,8).join("、")+(read.length>8?"…":"");
        if(unread.length)s+="　⚠未读:"+unread.slice(0,6).join("、")+(unread.length>6?"…":"");
        showStatus(s);
      }else{
        const names=(d.readers||[]).filter(x=>+x.seq>=seq)
          .map(x=>x.uid===state.uid?"我":x.nick);
        if(!names.length){showStatus("还没有人已读");return}
        showStatus("👀 已读："+names.slice(0,8).join("、")+(names.length>8?"…":""));
      }});}
function markRead(){
  const c=state.cur,elt=$("#msgs");
  if(c.type==="group"&&!state.meIn[c.gid])return;
  const nodes=elt.querySelectorAll(".msg");let last=0;
  // 只看非自己消息的 seq 作为已读线
  nodes.forEach(n=>{if(n.dataset.own!=="1"&&+n.dataset.seq>last)last=+n.dataset.seq;});
  if(!last)return;
  const body={token:state.token,channel:c.type,seq:last};
  if(c.type!=="public")body.to=c.gid||c.uid;
  fetch("/api/read",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).catch(()=>{});}
function syncMeInFromGroups(list){state.meIn={};Object.keys(list||state.serverGroups||{}).forEach(()=>{});}
// 由 detail 决定成员关系；进入群时拉 detail 即可。这里 meIn 由 detail 设置
function matchActive(e){
  if(e.channel==="public")return state.cur.type==="public";
  if(e.channel==="group")return state.cur.type==="group"&&e.to===state.cur.gid;
  if(e.channel==="private")return state.cur.type==="private"&&
    ((e.to===state.uid&&e.uid===state.cur.uid)||(e.to===state.cur.uid&&e.uid===state.uid));
  return false}
function dayStr(ts){const d=new Date(ts*1000);return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
function dayLabel(ts){                            // R68：今天/昨天/N天前/日期（对齐桌面端）
  const d=new Date(ts*1000),n=new Date();
  const d0=new Date(d.getFullYear(),d.getMonth(),d.getDate());
  const n0=new Date(n.getFullYear(),n.getMonth(),n.getDate());
  const diff=Math.round((n0-d0)/86400000);
  if(diff<=0)return "今天";
  if(diff===1)return "昨天";
  if(diff<7)return diff+"天前";
  return dayStr(ts)+" 星期"+"日一二三四五六".charAt(d.getDay());}
function addDateSep(ts){                          // R55-9：跨天插入日期分隔线
  const ds=dayStr(ts);
  if(state.lastDay===ds)return;
  state.lastDay=ds;
  const sep=document.createElement("div");sep.className="daysep";
  sep.innerHTML="<span>"+dayLabel(ts)+"</span>";
  $("#msgs").appendChild(sep);
}
function addMsg(e,self){
  if(kwHit(e)&&!inDnd()){requestNotif();showNotification(e);}   // R60：关键词命中 → 强制系统通知（勿扰仍最高优先）
  if(e.thread_root!=null){threadReply(e);return}   // R34：话题回复 → 内联进根消息折叠块
  const box=document.createElement("div");box.className="msg"+(self?" self":"")+(e.everyone?" evb":"");
  const enk=dnid(e.uid,e.nick);              // R69C9 备注名优先
  const who=enk+(self?"（我）":"");
  box.dataset.seq=e.seq||"";box.dataset.own=self?1:0;
  let key=e.key||"public";
  if(e.channel==="private"){const pr=(e.uid===state.uid?e.to:e.uid);key=convKey("private",pr);}
  else if(e.channel==="group"){key="group:"+(e.to!=null?e.to:"");}
  box.dataset.key=key;
  let body="";
  if(e.poll){body=pollHtml(e);}     // R26A 投票气泡
  else if(e.file){            // R23 图片/文件消息
    const f=e.file,dl="/api/file?fid="+f.fid;
    if(f.kind==="image"){
      body="<div class='bub'><img class='mimg' src='"+dl+"' title='点击查看大图' onclick='lightbox(\""+dl+"\")'></div>";
    }else{
      body="<div class='bub file'><a href='"+dl+"' download='"+esc(f.name)+"'>📎 "+esc(f.name)+"（"+fmtSize(f.size)+"）</a></div>";
    }
  }
  else if(e.voice){              // R63（任务5）：语音气泡——Web 端无原生 P2P 语音通道，仅展示时长
    const d=Math.round((+e.duration||0)*10)/10;
    let suf=""+d;if(Number.isInteger(d))suf=""+d;
    body="<div class='bub voice' title='网页端暂无法播放本地录制的 P2P 语音（仅显示时长）'>"
      +"<span class='vmic'>🎙</span> <span class='vtxt'>语音消息</span>"
      +"<span class='vdur'>"+suf+" 秒</span></div>";
  }
  else if(e.fp){                  // R43B1 合并转发卡：details 折叠块（fp={n,items[]} 服务器白名单透传）
    let rows="";
    (e.fp.items||[]).forEach(it=>{
      rows+="<div class='it'><span class='n'>"+esc(it.nick||"?")+"</span>"
        +"<span class='ts'>"+(it.ts?fmtTime(it.ts):"")+"</span>"
        +"<div class='t'>"+fmtText(it.text||"")+"</div></div>";
    });
    body="<div class='bub'><details class='fwd'><summary>📚 合并转发 · "
      +(+e.fp.n||(e.fp.items||[]).length)+" 条消息（点击展开）</summary>"+rows+"</details></div>";
  }
  else if(e.card){                // R71 联系人名片：可点小卡（服务器白名单透传 uid+nick）
    const cu=+e.card.uid||0,cn=e.card.nick||("用户"+cu);
    body="<div class='bub cc' data-card-uid='"+cu+"' data-card-nick=\""+esc(cn)
      +"\" title='点击查看资料'><span class='ccav'></span>"
      +"<span class='ccn'>👤 "+esc(cn)+"</span><span class='ccs'>联系人名片</span></div>";
  }
  else if(e.text!==undefined||e.sticker){   // 纯表情消息服务器只带 sticker 无 text → 同样进气泡
    // R30C：整条消息就是单个自定义贴纸 → 大图渲染；普通文本走 fmtText（贴纸内联 + hashtag）
    const solo=(e.text||"").trim().match(/^\[:([A-Za-z0-9_]{1,24}):\]$/);
    if(solo&&state.customStickers[solo[1]]){
      body="<div class='bub'><img class='cst big' src='/api/sticker/"+encodeURIComponent(solo[1])+"' title=':"+solo[1]+":'></div>";
    }else if(e.disguise){                    // R70E 消息伪装：风格外观 + 正文遮盖
      body=disguiseHtml(e);
    }else{
      body="<div class='bub'>"+(e.sticker?"<div class='st'>"+esc(state.stickers[e.sticker]?state.stickers[e.sticker].emoji:":"+e.sticker+":")+"</div>":"")+(e.rich&&e.rich.length?richHtml(e.rich):fmtText(e.text||""))+"</div>";
    }
  }
  if(e.preview)body+="<div class='pv'>"+pvHtml(e.preview)+"</div>";  // R26D 链接预览卡片
  box.innerHTML="<span class='msgav' data-uid='"+e.uid+"' data-nick='"+esc(enk||"")+"'></span><div class='who'>"+(e.everyone?"<span class='evtag' title='群内@全体通知'>📣全体</span>":"")+esc(who)+" "+fmtTime(e.ts)+(e.burn?" <span class='burn' title='阅后即焚：全体读完自动删除'>🔥</span>":"")+(e.edited?" <span class='edtag'"+(e.edits&&e.edits.length?" title='点击查看编辑历史' onclick='showEdits("+(e.seq||0)+")'":"")+">（已编辑）</span>":"")+"</div>"+body+"<div class='rd'></div>";
  if(e.uid!=null)setAv(box.querySelector(".msgav"),e.uid,enk||"?",30);   // R52：消息头像
  box.__raw={nick:enk||"?",text:e.voice?("🎙 语音消息 · "+(+e.duration||0)+" 秒"):(e.text!==undefined?String(e.text):""),seq:e.seq||0,sticker:e.sticker||null,uid:e.uid,edits:e.edits||null,disguise:e.disguise||null,card:e.card||null};   // R41G：引用快照源 + R60 多选快照 + R70B 编辑历史 + R70E 伪装 + R71 名片
  if(e.card)box.__raw.text="👤 名片："+(e.card.nick||e.card.uid);
  const cc=box.querySelector(".bub.cc");       // R71 名片：头像是占位符，点击开资料卡
  if(cc){
    ensureFeatureCss();
    const cu=+cc.dataset.cardUid||0;
    setAv(cc.querySelector(".ccav"),cu,cc.dataset.cardNick||"?",30);
    cc.onclick=ev=>{ev.stopPropagation();userCard(cu);};
  }
  if(curIsChannel()&&!e.deleted)ensureTh(box);   // R71 频道：贴下始终留「💬 评论」入口
  // R60 多选：悬停勾选钮 + 提示文字；ctrl/cmd+点击整行切换选中
  if(e.seq&&!e.deleted){
    const mk=document.createElement("b");mk.className="mulsel";mk.title="多选（Ctrl+点击行另可勾选）";mk.textContent="◻";
    mk.onclick=ev=>{ev.stopPropagation();ev.preventDefault();toggleSel(box);};
    box.appendChild(mk);
    box.onclick=ev=>{if((ev.ctrlKey||ev.metaKey)){toggleSel(box);}};
    box.ondblclick=ev=>{                          // R68 双击消息快速引用（对齐微信 PC）
      if(state.selSet&&state.selSet.size)return;
      ev.preventDefault();startReply(Number(box.dataset.seq),box);};
  }
  if(e.reply){                                     // R41G：引用前缀块（可点跳原消息）
    box.__reply=e.reply;
    const bub=box.querySelector(".bub");
    const qh=replyHtml(e.reply);
    if(bub)bub.insertAdjacentHTML("afterbegin",qh);
  }
  box.__reacts=e.reactions||{};                    // R27：回应快照（悬浮条标"我已回"）
  box.insertAdjacentHTML("beforeend",reactHtml(e.seq,box.__reacts));
  if(e.kb){                                       // R46：bot inline 键盘按钮
    box.insertAdjacentHTML("beforeend",kbHtml(e.uid,e.kb));}
  if(e.seq){                                       // R27：hover 浮出快速回应条
    box.onmouseenter=()=>showQuick(e.seq,box);
    box.onmouseleave=()=>{const q=box.querySelector(".qb");if(q)q.remove();};
    // R51：撤回——自己消息任何频道可删；私聊中对方消息也可删（scope=both）
    // R53：管理员可撤回任何频道/任何人的消息
    const me=e.uid===state.uid;
    if(!e.deleted&&(me||state.cur.type==="private"||state.is_admin)){
      const x=document.createElement("b");x.className="xdel";x.title=me?"撤回":(state.is_admin?"管理员撤回":"撤回对方消息");
      x.textContent="✕";
      x.onclick=()=>delMsg(e.seq,me?"self":"both");
      box.querySelector(".rd").appendChild(x);
    }
    if(!e.deleted&&me&&!e.poll&&!e.file&&!e.fp&&!e.sticker){   // R55-3：编辑——仅自己的纯文本消息
      const x=document.createElement("b");x.className="xdel";x.title="编辑";
      x.textContent="✎";
      x.onclick=()=>startEdit(e);
      box.querySelector(".rd").appendChild(x);
    }}
  // 功能②：消息收藏/取消（localStorage 本地，跨会话聚合，点击徽标可看列表）
  if(e.seq&&!e.deleted){
    const sk=favMsgKey(e.seq);
    const sb=document.createElement("b");sb.className="xdel";sb.title="⭐收藏/取消收藏消息";
    sb.textContent=favMsgHas(e.seq)?"★":"☆";
    sb.onclick=()=>{favMsgToggle(e.seq,e);sb.textContent=favMsgHas(e.seq)?"★":"☆";};
    box.querySelector(".rd").appendChild(sb);
  }
  if(e.ts)addDateSep(e.ts);                          // R55-9：跨天日期分隔线
  $("#msgs").appendChild(box);scrollToBottom(false); // 吸底：仅当用户已在底部时才自动滚（上翻阅读时不动）
  refreshQuoteBadges();                              // 功能①：重算「被引用 N」徽标
  if(state.cur.type!==null)markReadDelay();}
let _markTimer=null;
function markReadDelay(){clearTimeout(_markTimer);_markTimer=setTimeout(markRead,250);}
function findMsg(seq){
  let nd=null;document.querySelectorAll("#msgs .msg").forEach(n=>{if(n.dataset.seq==String(seq))nd=n;});return nd;}
// 功能①：扫描已渲染消息统计「被引用 N」，为目标消息挂/撤徽标；点徽标高亮所有引用行
function refreshQuoteBadges(){
  ensureFeatureCss();
  const cnt={},refs={};
  document.querySelectorAll("#msgs .msg").forEach(n=>{
    const r=n.__raw,rp=n.__reply;
    if(r&&rp&&rp.seq&&rp.seq!==(r.seq||0)&&n.dataset.seq){cnt[rp.seq]=(cnt[rp.seq]||0)+1;refs[rp.seq]=refs[rp.seq]||[];refs[rp.seq].push(n);}});
  document.querySelectorAll("#msgs .quo").forEach(x=>x.remove());
  document.querySelectorAll("#msgs .msg").forEach(n=>{
    const r=n.__raw;if(!r||!r.seq)return;
    const c=cnt[r.seq]||0;
    if(c>0){
      const s=document.createElement("span");s.className="quo";s.textContent="↩"+c;
      s.title="被引用 "+c+" 次（已加载范围内），点击查看引用它的消息";   // C9③：标注统计范围为「已加载」
      s.onclick=ev=>{ev.stopPropagation();const hit=refs[r.seq]||[];hit.forEach(x=>{x.classList.add("hl");setTimeout(()=>x.classList.remove("hl"),1400);});if(hit.length)hit[0].scrollIntoView({behavior:"smooth",block:"center"});};
      n.querySelector(".rd")?n.querySelector(".rd").appendChild(s):n.appendChild(s);
    }});
}
// 功能②：消息收藏（localStorage 本地，无服务端通道，跨会话按时间聚合）
function favMsgArr(){try{return JSON.parse(localStorage.getItem("web_msg_stars_"+(state.uid||0))||"[]")}catch(_e){return[]}}
function favMsgSave(a){if(a.length>200)a=a.slice(a.length-200);try{localStorage.setItem("web_msg_stars_"+(state.uid||0),JSON.stringify(a))}catch(_e){}}
function favMsgHas(seq){return favMsgArr().some(x=>x.seq===seq)}
function favMsgKey(seq){
  const c=state.cur||{};return (c.type==="group"?("group:"+(c.gid||"")):(c.type==="private"?("private:"+(c.uid||"")):("public:"+seq)));}
function favMsgToggle(seq,e){
  let a=favMsgArr();const t=Date.now();
  if(favMsgHas(seq)){a=a.filter(x=>x.seq!==seq);}
  else{
    const c=state.cur||{};const convo=c.type==="group"?"group:"+(c.gid||""):(c.type==="private"?"private:"+(c.uid||""):"public");
    a.push({seq:seq,convo:convo,nick:e.nick||"?",text:(e.voice?("🎙 语音消息 · "+(+e.duration||0)+" 秒"):(String(e.text==null?"":e.text))),ts:t});
  }
  favMsgSave(a);}
function openFavMsgs(){
  ensureFeatureCss();
  const a=favMsgArr();if(!a.length){showStatus("暂无收藏的消息");return}
  const t=document.createElement("div");t.style.cssText="position:fixed;right:12px;bottom:42px;width:300px;max-height:60vh;overflow:auto;background:var(--panel,#fff);color:var(--fg,#222);border:1px solid #ccc;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.25);z-index:99;padding:8px";
  t.innerHTML="<b style='display:block;margin-bottom:6px'>⭐ 我的收藏（"+a.length+"，本地）</b>";
  a.slice().sort((x,y)=>x.ts-y.ts).forEach(x=>{
    const row=document.createElement("div");row.style.cssText="padding:5px 8px;border-radius:6px;cursor:pointer;font-size:13px";row.textContent=("["+x.convo+"] "+x.nick+": "+(x.text||"").replace(/\s+/g," ").slice(0,26));
    row.onclick=()=>{t.remove();jumpFavMsg(x);};
    row.onmouseenter=()=>row.style.background="var(--qb,#eee)";row.onmouseleave=()=>row.style.background="";
    t.appendChild(row);});
  const close=()=>t.remove();
  t.addEventListener("click",ev=>{ev.stopPropagation();});
  document.body.appendChild(t);
  setTimeout(()=>{document.body.onclick=close;},0);document.body.onclick=close;
}
// 功能②：跳转到收藏消息——若当前会话不符提示（跨会话需重新加载历史，此处做尽力跳序）
function jumpFavMsg(x){
  const c=state.cur||{};
  const curKey=c.type==="group"?"group:"+(c.gid||""):(c.type==="private"?"private:"+(c.uid||""):"public");
  if(curKey!==x.convo){showStatus("收藏消息在其它会话「"+x.convo+"」，请切换后查看（网页端暂不自动切会话）");return}
  const nd=findMsg(x.seq);if(!nd){showStatus("原消息不在当前视图（可能已撤回或未加载）");return}
  nd.scrollIntoView({behavior:"smooth",block:"center"});nd.classList.add("hl");setTimeout(()=>nd.classList.remove("hl"),1400);}
function updateMsg(d){
  const nd=findMsg(d.seq);if(!nd)return;
  const bub=nd.querySelector(".bub");if(!bub)return;
  nd.__raw.text=d.text==null?"":d.text;nd.__raw.rich=d.rich;nd.__raw.edited=true;   // R55-3：回写原始数据，二次编辑载入最新文本
  if(d.edits&&d.edits.length)nd.__raw.edits=d.edits;   // R70B：编辑历史版本
  const edc=d.edits&&d.edits.length?" title='点击查看编辑历史' onclick='showEdits("+(d.seq||0)+")'":"";
  const _dg=nd.__raw.disguise;
  bub.innerHTML=replyHtml(nd.__reply)+(d.rich&&d.rich.length?richHtml(d.rich):fmtText(d.text==null?"":d.text))+"<span class='edtag' style='color:var(--dim);font-size:11px'"+edc+"> （已编辑）</span>";
  if(_dg)bub.insertAdjacentHTML("afterbegin",(disHdr(_dg)?"<div class='dishdr'>"+esc(disHdr(_dg))+"</div>":""));   // R70E：编辑后保留伪装表头
}
function showEdits(seq){                          // R70B：编辑历史弹层（逐版本列出）
  const nd=findMsg(seq);if(!nd)return;
  const eds=(nd.__raw&&nd.__raw.edits)||[];
  let h="<div style='min-width:280px;max-width:520px;max-height:70vh;overflow:auto;background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:14px;padding:12px 14px'>"
    +"<div style='font-size:13px;color:var(--dim);margin-bottom:8px'>编辑历史 · "+eds.length+" 个更早版本 <b style='float:right;cursor:pointer' class='edx'>✕</b></div>";
  eds.forEach((s,i)=>{h+="<div style='border-top:1px solid var(--line);padding:8px 0'><div style='font-size:11px;color:var(--dim)'>版本 "+(i+1)+" · "+esc(s.ts?fmtTime(s.ts):"?")+"</div><div style='font-size:14px;white-space:pre-wrap;word-break:break-word'>"+esc(String(s.text||"（空）"))+"</div></div>";});
  h+="<div style='border-top:1px solid var(--line);padding:8px 0;background:rgba(0,0,0,.03)'><div style='font-size:11px;color:var(--dim)'>当前版本</div><div style='font-size:14px;white-space:pre-wrap;word-break:break-word'>"+esc(String((nd.__raw&&nd.__raw.text)||"（空）"))+"</div></div></div>";
  const m=document.createElement("div");m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  m.innerHTML=h;document.body.appendChild(m);
  m.onclick=ev=>{if(ev.target===m||ev.target.classList.contains("edx"))m.remove();};}
function replyHtml(q){                           // R41G：引用前缀块（seq 可点 → 跳原消息）
  if(!q)return "";
  const qt=String(q.text||"").replace(/\s+/g," ").slice(0,80);
  return "<div class='rq"+(q.seq?" j":"")+"'"+(q.seq?" onclick='jumpSeq("+Number(q.seq)+")'":"")
    +">↩ "+esc(q.nick||"?")+": "+esc(qt)+"</div>";}
function jumpSeq(seq){                           // R41G：引用点击 → 滚动定位 + 短暂高亮
  const nd=findMsg(seq);
  if(!nd){showStatus("原消息不在当前视图（可能已撤回或未加载）");return}
  nd.scrollIntoView({behavior:"smooth",block:"center"});
  nd.classList.add("hl");
  setTimeout(()=>nd.classList.remove("hl"),1400);}
// ---- R71 消息永久链接：位置形如 #<会话键>/<seq>（桌面端「🔗 复制消息链接」生成）----
function parseDeepLink(){
  const h=String(location.hash||"").replace(/^#/,"");
  const i=h.lastIndexOf("/");
  if(i<=0)return null;
  const seq=parseInt(h.slice(i+1),10);
  if(!seq)return null;
  const key=h.slice(0,i);
  let c=null;
  if(key==="public")c={type:"public"};
  else if(key.indexOf("group:")===0)c={type:"group",gid:+key.slice(6)};
  else if(key.indexOf("private:")===0){
    const p=key.split(":"),a=+p[1],b=+p[2];
    c={type:"private",uid:(state.uid===a?b:a)};}
  if(!c||!c.uid&&c.type==="private")return null;
  return {convo:c,seq:seq};}
function gotoDeepLink(){
  const t=parseDeepLink();
  if(!t)return false;
  history.replaceState(null,"",location.pathname+location.search);   // 消费后抹掉 hash，免得刷新反复定位
  selectChannel(t.convo);
  let tries=0;                                    // 历史为异步拉取 → 轮询等目标行出现
  const timer=setInterval(()=>{
    if(findMsg(t.seq)){clearInterval(timer);jumpSeq(t.seq);return}
    if(++tries>25){clearInterval(timer);showStatus("消息不存在或已超出保留期");}
  },150);
  return true;}
window.addEventListener("hashchange",()=>gotoDeepLink());
function eraseMsg(d){
  const nd=findMsg(d.seq);if(!nd)return;
  nd.querySelectorAll(".bub,.react,.pv,.rr,.qb,.th").forEach(x=>x.remove());
  nd.querySelector(".rd")&&nd.querySelector(".rd").remove();
  const b=document.createElement("div");b.className="bub ed";b.textContent="（已撤回）";
  nd.appendChild(b);refreshQuoteBadges();}
// ---- R34 群内话题：根消息下的「N 条回复」内联折叠块 ----
function ensureTh(root){
  let th=root.querySelector(".th");
  if(!th){
    root.__thr=root.__thr||[];
    th=document.createElement("div");th.className="th";th.dataset.root=root.dataset.seq||"";
    th.onclick=ev=>{if(ev.target===th)toggleTh(th,root);};   // R71：仅点徽标本体才折叠（避免点回复框/发送按钮误收起）
    root.insertBefore(th,root.querySelector(".rd"));
  }
  if(!root.__thr)root.__thr=[];
  return th;}
function threadReply(e){
  const root=findMsg(e.thread_root);if(!root)return;   // 根不在视图（历史未载）→ 忽略
  ensureTh(root);
  root.__thr.push(e);
  const th=root.querySelector(".th");
  th.innerHTML=thHtml(root);
  if(th.classList.contains("open"))renderThOpen(th,root);}  // 展开态实时追加
function thHtml(root){
  const n=(root.__thr||[]).length;
  return n?("💬 "+n+" 条回复"):"💬 评论";}   // R71：频道贴 0 条评论时也作入口（文案「💬 评论」）
function toggleTh(th,root){
  const open=th.classList.toggle("open");
  if(!open){th.innerHTML=thHtml(root);return}
  renderThOpen(th,root);
  const b={token:state.token,channel:state.cur.type,root_seq:th.dataset.root};
  if(state.cur.type!=="public")b.to=state.cur.uid||state.cur.gid;
  fetch("/api/thread",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok)return;
      root.__thr=d.msgs||[];                       // 服务器环形为准（覆盖换端/丢帧）
      th.innerHTML=thHtml(root);
      renderThOpen(th,root);});}
function renderThOpen(th,root){
  let h="<div class='thr'>";
  (root.__thr||[]).slice().sort((a,b)=>(a.seq||0)-(b.seq||0)).forEach(m=>{
    h+="<div class='tli'>"+esc(m.uid!=null?dnid(m.uid,m.nick):(m.nick||"?"))+": "+fmtText(m.text||"")+"</div>";});
  h+="</div><div class='tin'><input placeholder='回复话题…'><button>发送</button></div>";
  th.innerHTML=h;
  const inp=th.querySelector("input");
  const doSend=()=>{
    const t=inp.value.trim();if(!t)return;
    const b={token:state.token,channel:state.cur.type,text:t,thread_root:+th.dataset.root,rich:richSegs(t)};
    if(state.cur.type!=="public")b.to=state.cur.uid||state.cur.gid;
    fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
    inp.value="";};
  th.querySelector("button").onclick=doSend;
  inp.addEventListener("keydown",ev=>{if(ev.key==="Enter")doSend()});}
// ---- R27 表情回应扩展：渲染药丸 / 点击切换 / hover 快速条 / SSE 更新 ----
const QUICK_EMOJIS=["👍","❤️","😂","😮","🔥"];
function reactHtml(seq,reactions){
  const rs=Object.entries(reactions||{}).sort((a,b)=>Object.keys(b[1]).length-Object.keys(a[1]).length);
  if(!rs.length)return "";
  let h="<div class='rr'>";
  rs.forEach(([emoji,users])=>{
    const cnt=Object.keys(users||{}).length;if(!cnt)return;
    const mine=users[state.uid]!==undefined;
    h+="<span class='react"+(mine?" mine":"")+"' data-e='"+esc(emoji)+"' onclick='reactToggle("+seq+",this)'>"+esc(emoji)+" "+cnt+"</span>";
  });
  return h+"</div>";
}
function reactToggle(seq,el){
  const emoji=el.getAttribute("data-e");
  const on=!el.classList.contains("mine");
  postReaction(seq,emoji,on);
}
// ---- R46：bot inline 键盘（kb=[[{t,c}],...]，点按钮=向 bot 发送指令文本） ----
function kbHtml(uid,kb){
  let h="";
  (kb||[]).forEach(row=>{
    h+="<div class='kbrow'>";
    (row||[]).forEach(b=>{
      const cmd=String(b.c||"")
        .replace(/\\/g,"\\\\")     // JS 字符串：先转义反斜杠
        .replace(/'/g,"\\x27")     // 再用 \x27 表达单引号，防 onclick 注入
        .replace(/"/g,"\\x22")
        .replace(/&/g,"&amp;").replace(/</g,"&lt;");   // HTML 属性安全
      h+="<button class='kbtn' onclick='kbClick("+Number(uid)+",\""+cmd+"\")'>"+esc(b.t||"")+"</button>";});
    h+="</div>";});
  return h;}
function kbClick(uid,cmd){
  if(state.cur.type!=="private"||state.cur.uid!==uid)
    selectChannel({type:"private",uid:uid});          // 不在 bot 会话 → 先切过去
  fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,channel:"private",to:uid,text:cmd})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"发送失败")}).catch(()=>{});}
function showQuick(seq,box){
  if(!seq||box.querySelector(".qb")||box.querySelector(".ed"))return;
  const rs=box.__reacts||{};
  let h="<div class='qb'>";
  QUICK_EMOJIS.forEach(e=>{
    const mine=rs[e]&&rs[e][state.uid]!==undefined;
    h+="<b class='"+(mine?"mine":"")+"' data-e='"+e+"' onclick='quickToggle(this)'>"+e+"</b>";
  });
  h+="<b class='rp' title='引用回复' onclick='startReply("+seq+",this)'>↩</b>";   // R41G：引用入口
  if((state.cur.type==="private"||state.cur.type==="group")&&box.__raw&&box.__raw.uid!=null){
    h+="<b class='rp' title='拍一拍' onclick='nudgeMsg(this)'>👋</b>";}          // R67 拍一拍入口
  if(state.cur.type==="private"||state.cur.type==="group"){
    h+="<b class='rp' title='窗口抖动' onclick='shakeMsg(this)'>📳</b>";}         // R68 窗口抖动入口
  h+="<b class='rp' title='提醒我' onclick='remindMsg(this)'>⏰</b>";            // R68 消息提醒入口
  box.insertAdjacentHTML("afterbegin",h+="</div>");
}
function startReply(seq,el){                     // R41G：设置引用态 + 输入区上方预览条
  const box=el.closest(".msg"),raw=box.__raw||{};
  state.reply={seq:+seq,nick:raw.nick,text:raw.text};
  $("#rprev").textContent=(raw.nick||"?")+": "+String(raw.text||"").replace(/\s+/g," ").slice(0,60);
  $("#rbar").style.display="flex";$("#text").focus();}
function cancelReply(){state.reply=null;$("#rbar").style.display="none";}
function cancelBar(){if(state.editSeq!=null)cancelEdit();else cancelReply();}   // R55-3：✕ 同时退出编辑态（防下一条误发成编辑）
// ---- R55-3 消息编辑：✎ 载入输入框 → send 走 /api/edit ----
function startEdit(e){
  cancelReply();                                    // 编辑态退出引用态，防状态串扰
  state.editSeq=+e.seq;
  const t=$("#text");t.value=e.text!=null?String(e.text):"";t.focus();
  $("#rbar").style.display="flex";$("#rprev").textContent="✎ 正在编辑消息 #"+e.seq+"（Enter 保存）";}
function cancelEdit(){
  if(state.editSeq==null)return;
  state.editSeq=null;$("#text").value="";$("#rbar").style.display="none";growTextArea();}
function quickToggle(el){
  const box=el.closest(".msg");
  postReaction(Number(box.dataset.seq),el.getAttribute("data-e"),!el.classList.contains("mine"));
}
function postReaction(seq,emoji,on){
  fetch("/api/reaction",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,seq:seq,emoji:emoji,on:on})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"回应失败")});
}
function nudgeMsg(el){                        // R67 拍一拍：向 /api/nudge 发帧，成功本地乐观渲染
  const box=el.closest(".msg"),target=box.__raw.uid;if(target==null)return;
  const c=state.cur,body={token:state.token,channel:c.type,target:target};
  if(c.type!=="public")body.to=c.uid||c.gid;
  fetch("/api/nudge",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"拍一拍失败");return;}
      addNudge(state.nick+" 拍了拍 "+(target===state.uid?"自己":(box.__raw.nick||"ta")));});
}
function shakeMsg(el){                        // R68 窗口抖动：向 /api/shake 发帧，成功本地提示
  const box=el.closest(".msg"),c=state.cur;
  const body={token: state.token, channel: c.type};
  if(c.type!=="public")body.to=c.uid||c.gid;
  fetch("/api/shake",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"窗口抖动失败");return;}
      shakeWindow();addShake("你发送了窗口抖动");});
}
function shakeWindow(){                       // R68 本窗口抖动动画（CSS keyframes，~0.6s）
  const el=document.body;if(!el)return;
  el.classList.remove("shaking");void el.offsetWidth;el.classList.add("shaking");
  setTimeout(()=>el.classList.remove("shaking"),700);}
// ---- R68 消息「提醒我」：localStorage 持久化 + 定时检查 → 系统通知 ----
function loadReminders(){try{return JSON.parse(localStorage.getItem("web_reminders")||"[]")||[]}catch(e){return[]}}
function saveReminders(l){try{localStorage.setItem("web_reminders",JSON.stringify(l))}catch(e){}}
function remindMsg(el){                        // 给某条消息设提醒（分钟数，1-1440）
  const box=el.closest(".msg"),raw=box.__raw||{};
  const s=prompt("几分钟后提醒你？（1-1440）","5");if(s===null)return;
  const m=parseInt(s,10);if(!(m>=1&&m<=1440)){showStatus("请输入 1-1440 分钟");return;}
  const l=loadReminders();
  l.push({at:Date.now()+m*60000,nick:raw.nick||"有人",text:String(raw.text||"")});
  saveReminders(l);
  addSys("⏰ 已设置提醒（"+m+" 分钟后）");
}
function reminderTick(){                       // 到点：系统通知 + 提示音 + 会话内提示
  const now=Date.now(),l=loadReminders(),keep=[];
  l.forEach(r=>{
    if((r.at||0)<=now){
      const msg="⏰ 提醒："+(r.nick||"有人")+":"+String(r.text||"").replace(/\s+/g," ").slice(0,40);
      try{if("Notification"in window&&Notification.permission==="granted"){new Notification("⏰ 摸鱼助手提醒",{body:msg});}}catch(e){}
      playSound();addSys(msg);showStatus(msg);
    }else{keep.push(r);}
  });
  if(keep.length!==l.length)saveReminders(keep);
}
setInterval(reminderTick,20000);
function updateReactions(d){
  const nd=findMsg(d.seq);if(!nd)return;
  if(d.reactions)nd.__reacts=d.reactions;
  // R33②：增量加/摘单药丸（只动 .rr，不重建整块，quick bar 与选中态不闪）
  if(d.emoji&&d.actor!==undefined){
    const rs=nd.__reacts||(nd.__reacts={});
    const b=rs[d.emoji]||(rs[d.emoji]={});
    if(d.on)b[d.actor]=Date.now()/1000;else delete b[d.actor];
    if(!Object.keys(b).length)delete rs[d.emoji];
  }
  const old=nd.querySelector(".rr");if(old)old.remove();
  const html=reactHtml(d.seq,nd.__reacts);
  if(html)nd.insertAdjacentHTML("beforeend",html);}
// ---- R26A 投票 / R26D 链接预览 ----
function pollHtml(e){
  const p=e.poll||{},opts=p.options||[],votes=p.votes||{};
  const st=p.state||null;
  const anon=!!p.anonymous,multi=!!p.multi,quiz=!!p.quiz;   // R70C
  let mine=[],counts=null,total=0,correct=null,end=p.end||0;
  if(st){
    counts=(st.counts||[]).slice();while(counts.length<opts.length)counts.push(0);
    total=(st.total!=null)?st.total:counts.reduce((a,b)=>a+b,0);
    mine=st.mine||[];correct=(st.correct!=null)?st.correct:null;end=st.end||end;
  }else{
    counts=opts.map(()=>0);const by={};
    Object.keys(votes).forEach(u=>{const v=votes[u];const arr=Array.isArray(v)?v:[v];
      const idx=arr.map(Number);by[+u]=idx;
      idx.forEach(x=>{if(x>=0&&x<opts.length)counts[x]++;});});
    total=counts.reduce((a,b)=>a+b,0);
    mine=by[state.uid]||(Array.isArray(p.mine)?p.mine.map(Number):[]);   // 匿名历史只回本人 mine
    correct=(p.correct!=null)?p.correct:null;
  }
  if(!mine.length&&votes&&Object.keys(votes).length&&state.uid!=null){
    Object.keys(votes).forEach(u=>{if(+u===+state.uid){const v=votes[u];
      mine=(Array.isArray(v)?v:[v]).map(Number);}});}
  const ended=Date.now()/1000>=end;
  state.pollData[e.seq]={question:p.question,options:opts,end:end,votes:votes,
    anonymous:anon,multi:multi,quiz:quiz,state:st};
  let tags="";if(anon)tags+="🕶 匿名 ";if(multi)tags+="☑ 多选 ";if(quiz)tags+="🎯 测验 ";
  let h="<div class='bub poll'><div class='q'>🗳 "+esc(p.question||"投票")
    +(tags?("<span class='cnt'>"+tags+"</span>"):"")+"</div>";
  opts.forEach((o,i)=>{
    const cnt=counts[i]||0;
    const pct=total?Math.round(cnt*100/total):0;
    const sel=mine.indexOf(i)>=0;
    let res="";
    if(quiz&&correct!=null){if(i===+correct)res=" <b>✅正确答案</b>";else if(sel)res=" <b>❌选错</b>";}
    h+="<div class='opt"+(sel?" mine":"")+"'"+(ended?"":" onclick='pollVote("+e.seq+","+i+")'")+">"
      +"<div class='bar' style='width:"+pct+"%'></div>"
      +"<span>"+esc(o)+(sel?" <b>✓</b>":"")+"</span>"+res
      +(total?("<span class='cnt'>"+cnt+"票 "+pct+"%</span>"):"")+"</div>";
  });
  h+="<div class='st'>"+(ended?"已结束 · 共 "+total+" 票":"剩余"+fmtLeft(end)+" · 共 "+total+" 票")+"</div></div>";
  return h;
}
function fmtLeft(end){
  const s=Math.max(0,Math.floor(end-Date.now()/1000));
  if(s>=3600)return Math.floor(s/3600)+" 小时";
  if(s>=60)return Math.floor(s/60)+" 分钟";
  return Math.max(1,s)+" 秒";
}
function pvHtml(p){
  let h="";
  if(p.domain)h+="<div class='d'>🔗 "+esc(p.domain)+"</div>";
  if(p.title)h+="<div class='t'>"+esc(p.title)+"</div>";
  if(p.desc)h+="<div class='s'>"+esc(p.desc)+"</div>";
  return h;
}
function pollVote(seq,option){
  fetch("/api/poll",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,action:"vote",seq:seq,option:option})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"投票失败")});
}
function updatePoll(d){
  const p=state.pollData[d.seq];if(!p)return;
  const nd=findMsg(d.seq);if(!nd)return;
  const old=nd.querySelector(".bub.poll");if(!old)return;
  if(d.counts!==undefined||d.mine!==undefined||d.correct!==undefined){   // R70C 新形状
    p.state=Object.assign({},p.state||{});
    ["counts","total","mine","correct","end"].forEach(k=>{if(k in d)p.state[k]=d[k];});
  }else{p.votes=d.votes||{};}
  const nb=document.createElement("div");nb.innerHTML=pollHtml({seq:d.seq,poll:p});
  old.replaceWith(nb.firstChild);}
function updatePreview(d){
  const nd=findMsg(d.seq);if(!nd)return;
  if(nd.querySelector(".pv"))return;
  const dv=document.createElement("div");dv.className="pv";dv.innerHTML=pvHtml(d.preview||{});
  nd.appendChild(dv);}
function sendPoll(){
  const q=prompt("投票问题：");
  if(!q)return;
  const o1=prompt("选项 1（至少 2 个选项）：");
  if(!o1)return;
  const o2=prompt("选项 2：");
  const o3=prompt("选项 3（可留空）：");
  const options=[o1,o2,o3].filter(x=>x&&x.trim());
  if(options.length<2){showStatus("至少需要两个选项");return}
  // R70C：匿名 / 多选 / 测验
  const anon=confirm("匿名投票？\n\n确定 = 匿名（只显示票数，不显示投票人）");
  const multi=confirm("多选？\n\n确定 = 可投多项（再点一次取消）");
  let quiz=false,correct=0;
  if(confirm("测验？\n\n确定 = 结束前不公布答案，需指定正确项")){
    quiz=true;
    const c=parseInt(prompt("正确选项序号（1 起）：","1"),10);
    if(!(c>=1&&c<=options.length)){showStatus("正确选项序号无效");return}
    correct=c-1;
  }
  const body={token:state.token,action:"create",channel:state.cur.type,
    question:q,options:options,anonymous:anon?1:0,multi:multi?1:0,quiz:quiz?1:0};
  if(quiz)body.correct=correct;
  if(state.cur.type!=="public")body.to=state.cur.uid||state.cur.gid;
  fetch("/api/poll",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)}).then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"投票失败")});
}
function refreshPanel(){
  if(state.cur.type!=="group")return;
  const gid=state.cur.gid,token = state.token,navigation=state.navigationRequest;
  const request=state.groupAccessRequest=(state.groupAccessRequest||0)+1;
  state.groupAccessPending=gid;applyRO();
  const current=()=>state.token===token&&state.navigationRequest===navigation&&state.groupAccessRequest===request&&state.cur.type==="group"&&state.cur.gid===gid;
  fetch("/api/group_detail?gid="+gid).then(r=>r.json()).then(d=>{
    if(!current())return;
    state.groupAccessPending=null;
    state.meIn[gid]=!!d.ok&&!!d.member;
    if(!state.meIn[gid]){discardGroupDraft(gid);closePanel();selectChannel({type:"public"},false);showStatus("已不在该群，返回公共聊天");return;}
    const key=convKey("group",gid);
    if(Object.prototype.hasOwnProperty.call(state.drafts,key))writeDraft({type:"group",gid:gid},state.drafts[key],token);
    if(state.panelGid===gid)renderGroupPanel(d);
    applyRO();renderGroups();
  }).catch(()=>{if(current())showStatus("群权限暂无法确认，请重新打开该群");});}
function addSys(t){const d=document.createElement("div");d.className="sys";d.textContent=t;$("#msgs").appendChild(d);scrollToBottom(false)}
function addNudge(t){const d=document.createElement("div");d.className="sys nudge";d.textContent=t;$("#msgs").appendChild(d);scrollToBottom(false)}   // R67 拍一拍轻量行
function addShake(t){const d=document.createElement("div");d.className="sys nudge";d.textContent=t;$("#msgs").appendChild(d);scrollToBottom(false)}   // R68 窗口抖动轻量行
function clearMsgs(){$("#msgs").innerHTML="";state.lastDay=null;searchReset()}
// ---- R__ web 消息吸底 + 「回到最新」浮动按钮（对等桌面 R31A）----
// 顶在底部：scrollHeight 与 viewport 底差 ≤40px 视为在底部；上翻阅读则解除。
function scrollToBottom(hard){                        // hard=切会话强制钉底；否则仅底部用户吸底
  if(!state.atBottom&&!hard)return;
  const m=$("#msgs");m.scrollTop=m.scrollHeight;}
function applyMsgScroll(){                            // 滚动后：刷新吸底态 + 浮动按键显隐
  const m=$("#msgs");
  state.atBottom=(m.scrollHeight-m.scrollTop-m.clientHeight)<=40;
  const b=$("#jumpBottom");
  const show=!state.atBottom&&(m.scrollHeight>m.clientHeight+10);
  b.style.display=show?"flex":"none";
  b.textContent="⬇";}
function jumpToLatest(){                              // 点击「回到最新」→ 立即钉底
  const m=$("#msgs");m.scrollTop=m.scrollHeight;state.atBottom=true;applyMsgScroll();m.focus();}
// ---- R55-2 会话内搜索：Ctrl+F 打开搜索条，Enter 下一个，高亮定位 ----
function searchReset(){if(window.__sidx!==undefined){document.querySelectorAll(".msg.smatch").forEach(n=>n.classList.remove("smatch","cur"));window.__sidx=undefined;$("#scount").textContent="";}}
function searchClose(){$("#sbar").style.display="none";searchReset()}
function searchOpen(){
  $("#sbar").style.display="flex";
  const inp=$("#sinput");inp.value="";inp.focus();
  inp.oninput=searchRun;inp.onkeydown=e=>{
    if(e.key==="Enter"){e.preventDefault();searchJump(e.shiftKey?-1:1);}
    else if(e.key==="Escape"){searchClose();}};
  searchRun();
}
function searchRun(){
  const q=$("#sinput").value.toLowerCase().trim();
  document.querySelectorAll(".msg.smatch").forEach(n=>n.classList.remove("smatch","cur"));
  if(!q){window.__sidx=undefined;$("#scount").textContent="";return}
  const nodes=[...document.querySelectorAll("#msgs .msg")].filter(n=>{
    const txt=n.__raw?String(n.__raw.nick+" "+(n.__raw.text||"")).toLowerCase():n.textContent.toLowerCase();
    return txt.includes(q);});
  nodes.forEach(n=>n.classList.add("smatch"));
  window.__smList=nodes;window.__sidx=nodes.length?-1:0;
  $("#scount").textContent=nodes.length?("0/"+nodes.length):"无结果";
  if(nodes.length)searchJump(1);
}
function searchJump(dir){
  const list=window.__smList||[];
  if(!list.length)return;
  window.__sidx=(window.__sidx+dir+list.length)%list.length;
  const n=list[window.__sidx];
  list.forEach(x=>x.classList.remove("cur"));
  n.classList.add("cur");
  n.scrollIntoView({behavior:"smooth",block:"center"});
  $("#scount").textContent=(window.__sidx+1)+"/"+list.length;
}
document.addEventListener("keydown",e=>{           // R55-2：Ctrl+F 打开会话内搜索（主界面内）
  if(e.key==="f"&&(e.ctrlKey||e.metaKey)&&!e.shiftKey){
    if($("#main").style.display!=="none"){e.preventDefault();searchOpen();}}});
function uxSelectNavigation(key){
  document.querySelectorAll('[data-ux-nav]').forEach(button=>{
    const selected=button.dataset.uxNav===key;
    button.classList.toggle('on',selected);
    if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  });
}
function selectChannel(c,saveDraft=true){
  uxSelectNavigation('chat');
  state.navigationRequest=(state.navigationRequest||0)+1;
  const unreadBefore=state.unread[convKey(c.type,c.type==="group"?c.gid:c.uid)]||0;
  if(state.editSeq==null&&saveDraft)pushDraft(true);else clearTimeout(pushDraft.t);
  cancelEdit();                                    // R55-3：切会话退出编辑态
  closeSide();                                      // R67：窄屏点会话自动收起抽屉
  state.cur=c;$("#headTitle").textContent=channelName()+"  ";
  unmarkConvo(convKey(c.type,c.type==="group"?c.gid:c.uid));   // R69C11：打开会话即清未读标记
  state.atBottom=true;    // R__：切会话默认钉底，加载历史落到底部
  document.querySelectorAll("#side .item").forEach(e=>e.classList.remove("on"));
  if(c.type==="public")document.querySelector('[data-ch="public"]').classList.add("on");
  if(c.type==="private"&&c.uid===state.uid)document.querySelector('[data-ch="saved"]').classList.add("on");
  if(c.type==="private"){state.unread[convoKey(c.uid)]=0;renderConvos();updateTitle();}
  if(c.type!=="group")$("#apanel").style.display="none";
  renderHeadActions();
  clearMsgs();loadHistory(c,unreadBefore);renderRoster();renderGroups();applyRO();
  applyDraft(true);cancelReply();}          // Replace the composer with this channel's draft.
function renderHeadActions(){               // R50：私聊标题右侧屏蔽/解除按钮
  const c=state.cur,b=$("#btnBlock");
  if(c.type==="private"&&c.uid!==state.uid){
    const on=(state.blocked||[]).includes(c.uid);
    b.style.display="";
    b.textContent=on?"🚫 解除":"🚫 屏蔽";
    b.onclick=()=>toggleBlock();
  }else{b.style.display="none";b.onclick=null;}
}
function toggleBlock(){                     // R50：屏蔽/解除当前私聊对象
  const c=state.cur;
  if(c.type!=="private"||c.uid===state.uid)return;
  const on=!(state.blocked||[]).includes(c.uid);
  fetch("/api/block",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,op:on?"block":"unblock",uid:c.uid})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"操作失败")});
}
function loadHistory(c,unreadBefore=null){
  const key=convKey(c.type,c.type==="group"?c.gid:c.uid),token = state.token;
  const request=state.historyRequest=(state.historyRequest||0)+1;
  const q={channel:c.type};
  if(c.type==="private")q.to=c.uid;
  if(c.type==="group")q.to=c.gid;
  const un=unreadBefore==null?(state.unread[key]||0):unreadBefore;
  fetch("/api/history?"+new URLSearchParams(q)).then(r=>r.json()).then(d=>{
    if(!d.ok||state.token!==token||state.historyRequest!==request||convKey()!==key)return;
    const msgs=d.msgs||[];
    msgs.forEach(e=>addMsg(e,e.uid===state.uid));
    if(un>0&&msgs.length){                        // R55-9：在末尾 un 条前插「未读分隔线」
      const nodes=[...document.querySelectorAll("#msgs .msg")];
      const n=Math.min(un,nodes.length);
      const sep=document.createElement("div");sep.className="unsep";
      sep.textContent="── "+n+" 条未读消息 ──";
      if(nodes.length>n)nodes[nodes.length-n].insertAdjacentElement("beforebegin",sep);
      else $("#msgs").appendChild(sep);
      state.unread[convKey()]=0;renderConvos();updateTitle();
    }
    renderRead();refreshQuoteBadges();markReadDelay();});}   // C9③：历史加载完成后重算引用徽标
// ---- R63：收藏夹（发给自己）/ 会话导出 / 最后在线相对文案 ----
function openSaved(){
  // 打开「收藏夹（我的笔记）」：即发给自己（private:self）的会话，可发文字/表情/文件
  selectChannel({type:"private",uid:state.uid});
  $("#headTitle").textContent="📌 收藏夹（我的笔记）  ";
}
function exportChat(){
  const c=state.cur,q={channel:c.type};
  if(c.type==="private")q.to=c.uid;
  if(c.type==="group")q.to=c.gid;
  fetch("/api/export?"+new URLSearchParams(q),{credentials:"include"})
    .then(r=>{if(!r.ok)throw 0;return r.blob()})
    .then(b=>{const a=document.createElement("a");
      a.href=URL.createObjectURL(b);a.download="chat-"+Date.now()+".txt";
      a.click();URL.revokeObjectURL(a.href)})
    .catch(()=>showStatus("导出失败"));
}
function lastOnlineText(ts){
  if(!ts)return "";
  const age=(Date.now()/1000)-Number(ts);
  if(age<60)return "最后在线 刚刚";
  if(age<3600)return "最后在线 "+Math.floor(age/60)+" 分钟前";
  if(age<86400)return "最后在线 "+Math.floor(age/3600)+" 小时前";
  if(age<7*86400)return "最后在线 "+Math.floor(age/86400)+" 天前";
  const d=new Date(Number(ts)*1000);
  return "最后在线 "+d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
}
// ---- R68：在线状态点（在线绿/离开黄/忙碌红/离线灰） ----
const ST_COLOR={online:"#2e9e5b",away:"#e0a33e",busy:"#e05252",offline:"#b9bec4"};
const ST_TEXT={online:"在线",away:"离开",busy:"忙碌",offline:"离线"};
function stDot(u,isOnline){
  const st=isOnline?((u&&u.status)||"online"):"offline";
  return "<span style='color:"+(ST_COLOR[st]||ST_COLOR.offline)+"'>●</span>";
}
// ---- R52：头像（有图贴 <img>，无图回退首字色块） ----
function avUrl(uid){return "/api/avatar?uid="+(uid||0)}
function setAv(el,uid,nick,size){
  const s=size||28,init=esc(String(nick||"?")).slice(0,1).toUpperCase()||"?";
  const u=(state.roster||[]).find(x=>x.uid===uid);
  el.classList.add("avf-"+avFrame());        // 功能④：头像相框样式类（none→avf-none 无效果）
  if(u&&u.avatar){
    el.innerHTML="<img class='av' style='width:"+s+"px;height:"+s+"px'>";
    const im=el.firstChild;
    im.src=avUrl(uid);
    im.onerror=()=>{el.innerHTML="<span class='avc' style='width:"+s+"px;height:"+s+"px'>"+init+"</span>"};
  }else{
    el.innerHTML="<span class='avc' style='width:"+s+"px;height:"+s+"px'>"+init+"</span>";
  }
}
function renderRoster(){
  const box=$("#roster");box.innerHTML="";
  const online={};(state.roster||[]).forEach(u=>online[u.uid]=1);
  // 在线 ∪ 已知离线（R63：离线联系人补「最后在线 X 前」）
  const merged=(state.roster||[]).concat(
    (state.known||[]).filter(u=>!online[u.uid]&&u.uid!==state.uid));
  merged.forEach(u=>{
    if(u.uid===state.uid)return;
    const key=convKey(u.uid);
    const blk=(state.blocked||[]).includes(u.uid);   // R50：屏蔽标记
    const st=isStarred(key);
    const dn=dnid(u.uid,u.nick);   // R69C9 备注名优先
    state.starMeta[key]=state.starMeta[key]||{type:"private",id:u.uid,nick:dn};
    const d=document.createElement("div");d.className="item"+(state.cur.type==="private"&&state.cur.uid===u.uid?" on":"");
    d.innerHTML=markDot(key)+stDot(u,online[u.uid])+" <span class='rowav'></span><span>"+esc(dn)+(u.type==="web"?"（网）":"")
      +"</span>"+(online[u.uid]?"":"<span class='sign'>"+lastOnlineText(u.last_online)+"</span>")
      +(u.sign?"<span class='sign' title='"+esc(u.sign)+"'>"+esc(u.sign)+"</span>":"")
      +(blk?"<span class='blk'>已屏蔽</span>":"")
      +markBtn(key)
      +"<span class='stbtn"+(st?" on":"")+"' onclick='toggleStar(\""+key+"\",event)' title='星标会话'>"+(st?"★":"☆")+"</span>";
    setAv(d.querySelector(".rowav"),u.uid,dn,26);
    const rav=d.querySelector(".rowav");      // R69C10：点头像看资料
    rav.style.cursor="pointer";rav.title="查看资料";
    rav.onclick=ev=>{ev.stopPropagation();userCard(u.uid);};
    d.onclick=()=>selectChannel({type:"private",uid:u.uid});
    d.oncontextmenu=ev=>{ev.preventDefault();remarkDlg(u.uid);};   // R69C9 右键设备注名
    box.appendChild(d);});
}
// ---- R46：机器人区（登录下发 bots 清单，点击开 bot 私聊） ----
function renderBots(){
  const box=$("#bots");if(!box)return;box.innerHTML="";
  (state.bots||[]).forEach(b=>{
    const d=document.createElement("div");
    d.className="item"+(state.cur.type==="private"&&state.cur.uid===b.uid?" on":"");
    d.innerHTML="<span class='dot botdot'></span>🤖 "+esc(b.nick);
    d.title=b.desc||"";
    d.onclick=()=>selectChannel({type:"private",uid:b.uid});box.appendChild(d);});
}
// ---- R22：最近私聊会话列表（含未读角标） ----
function convoKey(uid){return convKey("private",uid);}
function renderConvos(){
  const box=$("#convos");box.innerHTML="";
  state.convos.forEach(c=>{
    const n=state.unread[convoKey(c.uid)]||0;
    const blk=(state.blocked||[]).includes(c.uid);     // R50：屏蔽标记
    const key=convoKey(c.uid),st=isStarred(key);
    const cn=dnid(c.uid,c.nick);   // R69C9 备注名优先
    state.starMeta[key]=state.starMeta[key]||{type:"private",id:c.uid,nick:cn};
    const d=document.createElement("div");
    d.className="item"+(state.cur.type==="private"&&state.cur.uid===c.uid?" on":"");
    d.innerHTML=(n?"":markDot(key))+"<span class='rowav'></span><span>"+esc(cn)
      +"</span>"+(blk?"<span class='blk'>已屏蔽</span>":"")
      +(n?("<span class='unread'>"+n+"</span>"):"")
      +markBtn(key)
      +"<span class='stbtn"+(st?" on":"")+"' onclick='toggleStar(\""+key+"\",event)' title='星标会话'>"+(st?"★":"☆")+"</span>";
    setAv(d.querySelector(".rowav"),c.uid,cn,26);
    const cav=d.querySelector(".rowav");     // R69C10：点头像看资料
    cav.style.cursor="pointer";cav.title="查看资料";
    cav.onclick=ev=>{ev.stopPropagation();userCard(c.uid);};
    d.onclick=()=>selectChannel({type:"private",uid:c.uid});
    box.appendChild(d);});
}
function bumpConvo(e){
  // SSE 收到私聊消息：更新最近列表，非当前会话才累计未读
  const other=e.uid===state.uid?e.to:e.uid;
  const c=state.convos.find(x=>x.uid===other);
  if(c){c.nick=e.nick;c.last_ts=e.ts;}
  else state.convos.push({uid:other,nick:e.nick,last_ts:e.ts});
  state.convos.sort((x,y)=>(y.last_ts||0)-(x.last_ts||0));
  if(!matchActive(e)){
    const k=convoKey(other);state.unread[k]=(state.unread[k]||0)+1;}
  renderConvos();
}
function renderGroups(){
  const box=$("#groups");box.innerHTML="";
  (state.serverGroups.length?state.serverGroups:state.groups||[]).forEach(g=>{
    const d=document.createElement("div");d.className="item"+(state.cur.type==="group"&&state.cur.gid===g.gid?" on":"");
    d.dataset.gid=g.gid;
    const inGroup=state.meIn[g.gid];
    const key=starKey("group",g.gid),st=isStarred(key);
    state.starMeta[key]=state.starMeta[key]||{type:"group",id:g.gid,gid:g.gid,name:g.name};
    d.innerHTML=markDot(key)+"<span class='rowav'></span><span class='dot "+(inGroup?"":"grpdot")+"'></span>"
      +"<span style='font-size:10px;color:#1890ff;border:1px solid #1890ff;border-radius:3px;padding:0 3px;margin-right:4px;vertical-align:1px'>公</span>".repeat(g.public?1:0)
      +esc(g.name)+"（"+g.member_count+"/"+(g.member_max||64)+"）"
      +markBtn(key)
      +"<span class='stbtn"+(st?" on":"")+"' onclick='toggleStar(\""+key+"\",event)' title='星标会话'>"+(st?"★":"☆")+"</span>";
    setGroupAv(d.querySelector(".rowav"),g,26);
    d.onclick=()=>openGroup(g);box.appendChild(d);});
}
// ---- R63（任务6）会话级星标：本地 localStorage 持久化（对标桌面 prefs['stars']），无服务端通道 ----
function loadStars(){try{return JSON.parse(localStorage.getItem("wstars_"+(state.uid||0))||"[]")}catch(_e){return []}}
function saveStars(){try{localStorage.setItem("wstars_"+(state.uid||0),JSON.stringify(state.stars))}catch(_e){}}
function isStarred(key){return state.stars.indexOf(key)>=0;}
function toggleStar(key,ev){
  if(ev){ev.stopPropagation();ev.preventDefault();}
  const i=state.stars.indexOf(key);
  if(i>=0)state.stars.splice(i,1);else state.stars.push(key);
  saveStars();renderStars();renderRoster();renderConvos();renderGroups();
}
function starKey(type,id){return type+":"+id;}
function renderStars(){
  const box=$("#starsec");if(!box)return;
  box.innerHTML="";
  state.stars.forEach(key=>{
    const m=state.starMeta[key];if(!m){return;}
    const d=document.createElement("div");d.className="item"+
      ((m.type==="private"&&state.cur.type==="private"&&state.cur.uid===m.id)||
       (m.type==="group"&&state.cur.type==="group"&&state.cur.gid===m.id)?" on":"");
    d.innerHTML="<span class='rowav'></span><span>⭐ "+(m.nick||m.name||"?")+"</span>";
    if(m.type==="private")setAv(d.querySelector(".rowav"),m.id,m.nick,26);
    else setGroupAv(d.querySelector(".rowav"),{avatar:0,name:m.name},26);
    d.onclick=()=>{if(m.type==="private")selectChannel({type:"private",uid:m.id});else openGroup(m.gid);};
    box.appendChild(d);
  });
}
function toggleStarPanel(){
  const box=$("#starsec");
  box.style.display=(box.style.display==="none")?"":"none";
  if(box.style.display!=="none"&&!state.starInit){state.starInit=1;renderStars();}
}
// ---- R69C11 标为未读（本地 localStorage，对标桌面 prefs['unread_marks']）+ 稍后处理清单 ----
function loadMarks(){try{return JSON.parse(localStorage.getItem("wmarks_"+(state.uid||0))||"[]")}catch(_e){return []}}
function saveMarks(){try{localStorage.setItem("wmarks_"+(state.uid||0),JSON.stringify(state.marks))}catch(_e){}}
function isMarked(key){return (state.marks||[]).indexOf(key)>=0;}
function markDot(key){return isMarked(key)?"<span class='umark' title='标为未读'></span>":"";}
function markBtn(key){const on=isMarked(key);
  return "<span class='mkbtn"+(on?" on":"")+"' onclick='toggleMark(\""+key+"\",event)' title='"+(on?"取消未读标记":"标为未读")+"'>⏳</span>";}
function toggleMark(key,ev){
  if(ev){ev.stopPropagation();ev.preventDefault();}
  const i=state.marks.indexOf(key);
  if(i>=0)state.marks.splice(i,1);else state.marks.push(key);
  saveMarks();renderRoster();renderConvos();renderGroups();renderMarkPanel();
  showStatus(i>=0?"已取消未读标记":"已标为未读");}
function unmarkConvo(key){          // 打开会话即清标记（对齐桌面）
  if(!key||!isMarked(key))return;
  state.marks.splice(state.marks.indexOf(key),1);saveMarks();
  renderRoster();renderConvos();renderGroups();renderMarkPanel();}
function markLabel(key){
  if(key==="public")return "公共频道";
  if(key.indexOf("group:")===0){const gid=+key.slice(6);
    const g=(state.serverGroups.length?state.serverGroups:state.groups||[]).find(x=>x.gid===gid);
    return g?g.name:("群"+gid);}
  if(key.indexOf("private:")===0){const p=key.split(":");
    const other=(+p[1]===state.uid)?+p[2]:+p[1];
    const u=(state.roster||[]).find(x=>x.uid===other)||(state.known||[]).find(x=>x.uid===other);
    return dnid(other,u&&u.nick);}
  return key;}
function gotoConvKey(key){
  if(key==="public"){selectChannel({type:"public"});return;}
  if(key.indexOf("group:")===0){const gid=+key.slice(6);
    const g=(state.serverGroups.length?state.serverGroups:state.groups||[]).find(x=>x.gid===gid);
    if(g)openGroup(g);return;}
  if(key.indexOf("private:")===0){const p=key.split(":");
    const other=(+p[1]===state.uid)?+p[2]:+p[1];
    selectChannel({type:"private",uid:other});}}
function renderMarkPanel(){
  const box=$("#marksec");if(!box)return;
  box.innerHTML="";
  if(!state.marks.length){
    box.innerHTML="<div class='item' style='color:var(--dim);font-size:12px;padding:6px 8px'>暂无待处理会话</div>";
    return;}
  state.marks.forEach(key=>{
    const d=document.createElement("div");d.className="item";
    d.innerHTML=markDot(key)+"<span>"+esc(markLabel(key))+"</span>"
      +"<span class='mkbtn on' title='标为已处理'>✓</span>";
    d.onclick=ev=>{if(String(ev.target.className).indexOf("mkbtn")>=0){
      ev.stopPropagation();unmarkConvo(key);return;}gotoConvKey(key);};
    box.appendChild(d);});
}
function toggleMarkPanel(){
  const box=$("#marksec");
  box.style.display=(box.style.display==="none")?"":"none";
  if(box.style.display!=="none")renderMarkPanel();}
// ---- R9H：群头像（有图贴 <img>，无图回退首字色块；带时间戳换缓存即时刷新） ----
function gavUrl(gid){return "/api/group_avatar?gid="+(gid||0)+"&v="+Math.random().toString(36).slice(2,8)}
function setGroupAv(el,g,size){
  const s=size||26,init=esc(String((g&&g.name)||"?").slice(0,1).toUpperCase()||"?");
  if(g&&g.avatar){
    el.innerHTML="<img class='av' style='width:"+s+"px;height:"+s+"px'>";
    const im=el.firstChild;
    im.src=gavUrl(g.gid);
    im.onerror=()=>{el.innerHTML="<span class='avc' style='width:"+s+"px;height:"+s+"px'>"+init+"</span>"};
  }else{
    el.innerHTML="<span class='avc' style='width:"+s+"px;height:"+s+"px'>"+init+"</span>";
  }
}
function enterMain(d){
  // R47-A2：登录成功 / whoami 会话恢复共用初始化
  Object.assign(state,{token:d.token,uid:d.uid,nick:d.nick,roster:d.roster,groups:d.groups,serverGroups:d.groups||[],
    bots:d.bots||[],                                   // R46：机器人清单（登录下发）
    convos:d.convos||[],known:d.known||[],unread:{},drafts:{},blocked:d.blocked||[],scheds:d.scheds||[],
    is_admin:!!d.is_admin});   // R29B/R50/R51/R53：管理员标识（仅管理员见面板入口）
  state.stars=loadStars();state.starMeta={};   // R63（任务6）：会话级星标 localStorage
  state.marks=loadMarks();                     // R69C11：标为未读（稍后处理清单）
  (d.convos||[]).forEach(c=>{if(c.unread>0)state.unread[convoKey(c.uid)]=c.unread;});
  updateTitle();                                   // R55-1：登录恢复未读计数
  (d.drafts||[]).forEach(x=>state.drafts[x.key]=x.text);   // R29B：草稿同步带回
  d.stickers.forEach(s=>state.stickers[s.code]=s);
  state.customStickers={};(d.custom_stickers||[]).forEach(s=>state.customStickers[s.code]=s);  // R30C
  state.packMeta=d.sticker_pack_meta||{};state.subs=d.sticker_subs||[];   // R65：包封面元数据 + 订阅
  state.curPack="";state.shopOpen=false;
  $("#login").style.display="none";$("#main").style.display="flex";
  $("#headSub").textContent=state.nick;
  $("#btnAdmin").style.display=state.is_admin?"":"none";   // R53：管理员面板入口仅管理员可见
  buildEmoji();renderRoster();renderConvos();renderGroups();renderBots();
  shopPost({op:"list"});                           // R65：拉内置包目录（导航条列包 + 🔒 判定）
  (d.history||[]).forEach(e=>addMsg(e,e.uid===state.uid));
  openStream();
  gotoDeepLink();                                  // R71：带 #会话键/seq 打开 → 切会话并定位高亮
}
function leaveLogin(){
  if(state.esRetry){clearTimeout(state.esRetry);state.esRetry=null;}
  const es=state.es;state.es=null;if(es)es.close();
  state.token=null;state.uid=0;state.nick="";state.is_admin=false;
  state.roster=[];state.groups=[];state.convos=[];state.unread={};
  state.drafts={};state.blocked=[];state.scheds=[];state.cur={type:"public"};
  state.groom=null;state.gst=null;state.gpriv=null;state.glog=[];state.grooms=[];state.gleft={};
  const msgs=document.getElementById("msgs");if(msgs)msgs.innerHTML="";
  const gpanel=document.getElementById("gpanel");if(gpanel)gpanel.remove();
  if(typeof renderGames==="function")renderGames();
  if(typeof closeLobby==="function")closeLobby();
  const loginBox=document.getElementById("login");
  const main=document.getElementById("main");
  if(main)main.style.display="none";
  if(loginBox)loginBox.style.display="";
  $("#pwd").value="";$("#npwd").value="";
}
function installSessionFetch(){
  const nativeFetch=window.fetch.bind(window);
  window.fetch=(input,options)=>{
    const currentToken=state.token;
    let protectedApi=false;
    try{
      const raw=typeof input==="string"?input:(input.url||input.href);
      const url=new URL(raw,window.location.href);
      protectedApi=url.origin===window.location.origin&&url.pathname.startsWith("/api/")
        &&!["/api/login","/api/meta"].includes(url.pathname)
        &&!url.pathname.startsWith("/api/sticker/");
    }catch(_e){}
    return nativeFetch(input,options).then(response=>{
      if(response.status===401&&protectedApi&&currentToken&&state.token===currentToken){
        leaveLogin();showStatus("登录已失效，请重新登录");
      }
      return response;
    });
  };
}
installSessionFetch();
function logout(){
  const tok=state.token;
  if(!tok){leaveLogin();return}
  fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:tok})})
    .then(async r=>{let d={};try{d=await r.json()}catch(_e){};
      return {status:r.status,data:d};})
    .then(({status,data})=>{
      if(state.token!==tok)return;
      if((status===200&&data.ok)||status===401){leaveLogin();return}
      showStatus(data.error||"退出失败");
    })
    .catch(()=>showStatus("退出失败，请检查网络后重试"));
}
function login(){
  const nick=$("#nick").value.trim();
  if(!nick){showStatus("请输入昵称");return}
  // R48：站点口令启用时 password=站点口令、昵称密码走独立 nick_pwd 字段（与服务器语义对齐）
  const body={nick:nick,password:$("#pwd").value};
  if(state.sitePwd)body.nick_pwd=$("#npwd").value;
  fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"登录失败");return}
      $("#pwd").value="";$("#npwd").value="";
      requestNotif();                               // R55-1：登录后请求通知权限（用户手势内）
      enterMain(d);
    });
}
// R48：登录页探测站点口令——启用则拆出第二个密码框（站点口令/昵称密码分列）
fetch("/api/meta").then(r=>r.json()).then(d=>{
  if(d.ok&&d.site_pwd){state.sitePwd=true;
    $("#npwd").style.display="";
    $("#pwd").placeholder="站点口令";}
}).catch(()=>{});
// R47-A2：页面加载先探活 Cookie 会话——命中则免登录直达主界面（刷新无感）；
// 未命中静默留在登录页（首次访问/会话过期属正常路径，不报错）。
fetch("/api/whoami").then(r=>r.json()).then(d=>{if(d.ok)enterMain(d)}).catch(()=>{});
// R47-B：昵称密码面板（设置/修改/清除；新密码留空=清除）
function pwdPanel(){
  let d=document.getElementById("pwdlg");
  if(d)d.remove();
  d=document.createElement("div");d.id="pwdlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(280px,84vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:8px'>🔑 昵称密码</div>"
    +"<input id='pwdOld' type='password' placeholder='旧密码（未设过可留空）' style='width:100%;box-sizing:border-box;margin-bottom:6px'>"
    +"<input id='pwdNew' type='password' placeholder='新密码（留空=清除密码）' style='width:100%;box-sizing:border-box'>"
    +"<div style='margin-top:10px;text-align:right'><button id='pwdOk'>保存</button> <button id='pwdCancel'>取消</button></div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d)d.remove()};
  document.body.appendChild(d);
  $("#pwdCancel").onclick=()=>d.remove();
  $("#pwdOk").onclick=()=>{
    fetch("/api/passwd",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:state.token,old:$("#pwdOld").value,new:$("#pwdNew").value})})
      .then(r=>r.json()).then(r=>{
        if(!r.ok){showStatus(r.error||"操作失败");return}
        d.remove();
        showStatus($("#pwdNew").value?"✅ 昵称密码已保存，下次登录需输入":"✅ 昵称密码已清除");
      });
  };
}
// ---- R69C10 用户资料卡（点消息/好友头像打开；只读）----
function commonGroups(uid){
  // 共同群：已缓存成员表的群里包含该 uid（键为 gid，成员含 uid 字段）
  const out=[];
  Object.keys(state.gmembers).forEach(gid=>{
    const ms=state.gmembers[gid]||[];
    if(ms.some(m=>+m.uid===uid)){
      const g=(state.serverGroups||[]).find(x=>String(x.gid)===String(gid))
        ||(state.groups||[]).find(x=>String(x.gid)===String(gid))||{};
      out.push({gid:+gid,name:g.name||("群"+gid)});
    }
  });
  out.sort((a,b)=>String(a.name).localeCompare(String(b.name),"zh"));
  return out;
}
function userCard(uid){
  uid=+uid||0;if(!uid)return;
  if(uid===state.uid){profilePanel();return}   // 自己 → 个人资料（可编辑）
  const u=(state.roster||[]).find(x=>x.uid===uid)
    ||(state.known||[]).find(x=>x.uid===uid);
  if(!u){showStatus("该用户资料不可用");return}
  let d=document.getElementById("ucdlg");
  if(d)d.remove();
  const online=(state.roster||[]).some(x=>x.uid===uid);
  const st=online?(u.status||"online"):"offline";
  const dn=dnid(uid,u.nick);
  const cgs=commonGroups(uid);
  const isBot=u.type==="bot";
  d=document.createElement("div");d.id="ucdlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(300px,84vw);text-align:center";
  card.innerHTML=
    "<div id='ucAv' style='width:88px;height:88px;margin:0 auto 6px'></div>"
    +"<div style='font-weight:600'>"+esc((isBot?"🤖 ":"")+dn)+"</div>"
    +((u.nick&&u.nick!==dn)?"<div style='font-size:11px;color:var(--dim)'>昵称："+esc(u.nick)+"</div>":"")
    +"<div style='font-size:12px;margin:6px 0 2px'><span style='color:"+(ST_COLOR[st]||ST_COLOR.offline)+"'>●</span> "+esc(ST_TEXT[st]||st)
      +((!online&&u.last_online)?"（"+esc(lastOnlineText(u.last_online))+"）":"")+"</div>"
    +"<div style='font-size:11px;color:var(--dim);text-align:left;margin-top:8px'>个性签名</div>"
    +"<div style='font-size:12px;text-align:left;word-break:break-all'>"+esc(String(u.sign||"").trim()||"（未设置）")+"</div>"
    +"<div style='font-size:11px;color:var(--dim);text-align:left;margin-top:8px'>共同群（"+cgs.length+"）</div>"
    +"<div style='font-size:12px;text-align:left;word-break:break-all'>"
      +(cgs.length?cgs.slice(0,8).map(g=>"· "+esc(g.name)).join("<br>")
        +(cgs.length>8?"<br>…等 "+cgs.length+" 个群":""):"（暂无共同群）")+"</div>"
    +"<div style='display:flex;gap:6px;margin-top:12px'>"
    +(isBot?"":"<button id='ucDm' style='flex:1'>发消息</button>")
    +"<button class='ghost' id='ucRem' style='flex:1'>备注名</button>"
    +"<button class='ghost' id='ucClose' style='flex:1'>关闭</button></div>";
  d.appendChild(card);
  d.onclick=ev=>{if(ev.target===d)d.remove()};
  document.body.appendChild(d);
  setAv(d.querySelector("#ucAv"),uid,dn,88);
  const dm=d.querySelector("#ucDm");
  if(dm)dm.onclick=()=>{d.remove();selectChannel({type:"private",uid:uid})};
  d.querySelector("#ucRem").onclick=()=>remarkDlg(uid);
  d.querySelector("#ucClose").onclick=()=>d.remove();
}
// ---- R52：个人资料（头像上传/删除 + 个性签名 + 改密码；昵称=登录标识不可改）----
function profilePanel(){
  let d=document.getElementById("pfdlg");
  if(d)d.remove();
  d=document.createElement("div");d.id="pfdlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const me=(state.roster||[]).find(u=>u.uid===state.uid)||{};
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:16px;width:min(300px,84vw);text-align:center";
  card.innerHTML="<div style='font-weight:600;margin-bottom:10px'>我的资料</div>"
    +"<div id='pfAv' style='width:88px;height:88px;margin:0 auto 6px;position:relative'></div>"
    +"<div style='color:var(--dim);font-size:11px;margin-bottom:10px'>点击头像更换 · 右键删除</div>"
    +"<div style='margin-bottom:2px;font-size:12px;color:var(--dim)'>昵称（登录标识，不可修改）</div>"
    +"<div style='font-weight:600;margin-bottom:10px'>"+esc(state.nick)+"</div>"
    +"<div style='font-size:12px;color:var(--dim);text-align:left'>个性签名</div>"
    +"<input id='pfSign' maxlength='60' value='"+esc(me.sign||"")+"' style='width:100%;box-sizing:border-box;margin:2px 0 8px'>"
    +"<div id='pfInvis' style='text-align:left;padding:6px 2px;font-size:12px;display:flex;align-items:center;gap:6px'>"
    +"  <input type='checkbox' id='pfInvisCk'>"
    +"  <label for='pfInvisCk'>隐身上线（不出现在他人可见名单）</label>"
    +"</div>"
    +"<div style='text-align:left;padding:2px 2px;font-size:12px;display:flex;align-items:center;gap:6px'>"
    +"  <label for='pfStatus'>在线状态</label>"
    +"  <select id='pfStatus' style='flex:1'>"
    +"    <option value='online'>● 在线</option><option value='away'>● 离开</option><option value='busy'>● 忙碌</option>"
    +"  </select>"
    +"</div>"
    +"<div style='display:flex;gap:6px'><button id='pfOk' style='flex:1'>保存</button>"
    +"<button class='ghost' id='pfPwd' style='flex:1'>改密码</button>"
    +"<button class='ghost' id='pfCancel' style='flex:1'>关闭</button></div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d)d.remove()};
  document.body.appendChild(d);
  // R56：拉取当前隐身状态
  fetch("/api/invis",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token})})
    .then(r=>r.json()).then(d=>{$("#pfInvisCk").checked=!!(d.ok&&d.on);});
  // R68：拉取当前在线状态
  fetch("/api/status",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token})})
    .then(r=>r.json()).then(r=>{if(r.ok)$("#pfStatus").value=r.status||"online";});
  const av=d.querySelector("#pfAv");
  av.style.cursor="pointer";
  av.onclick=()=>{
    const inp=document.createElement("input");inp.type="file";inp.accept="image/*";
    inp.onchange=()=>{
      const f=inp.files[0];if(!f)return;
      if(f.size>1048576){showStatus("头像不能超过 1MB");return}
      const rd=new FileReader();
      rd.onload=()=>{
        const b64=String(rd.result).split(",")[1]||"";
        const ext=(f.name.split(".").pop()||"png").toLowerCase().replace(/[^a-z0-9]/g,"");
        fetch("/api/avatar",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({token:state.token,op:"set",ext:ext,data:b64})})
          .then(r=>r.json()).then(r=>{
            if(!r.ok){showStatus(r.error||"头像上传失败");return}
            showStatus("✅ 头像已上传，已同步全员");updateRosterAll();setAv(av,state.uid,state.nick,88);
          });
      };
      rd.readAsDataURL(f);
    };
    inp.click();
  };
  av.oncontextmenu=e=>{e.preventDefault();
    if(confirm("删除头像？")){
      fetch("/api/avatar",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:state.token,op:"del"})})
        .then(r=>r.json()).then(r=>{
          if(!r.ok){showStatus(r.error||"删除失败");return}
          showStatus("头像已删除");updateRosterAll();setAv(av,state.uid,state.nick,88);
        });
    }};
  setAv(av,state.uid,state.nick,88);
  $("#pfCancel").onclick=()=>d.remove();
  $("#pfPwd").onclick=()=>{d.remove();pwdPanel();};
  $("#pfOk").onclick=()=>{
    const sign=$("#pfSign").value.trim().slice(0,60);
    const invis=!!$("#pfInvisCk").checked;
    const status=$("#pfStatus").value||"online";
    Promise.resolve(fetch("/api/profile",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:state.token,sign:sign})})
      .then(r=>r.json()).then(r=>{
        if(!r.ok){showStatus(r.error||"保存失败");return false}
        return true;
      })).then(ok=>{
      if(!ok){return}
      fetch("/api/invis",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:state.token,on:invis})})
        .then(r=>r.json()).then(r=>{
          if(!r.ok){showStatus(r.error||"隐身状态保存失败");return}
          // R68：状态一并提交（服务器权威，SSE 回 status_ack）
          fetch("/api/status",{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({token:state.token,status:status})});
          d.remove();
          showStatus("✅ 已保存"+(invis?"，已开启隐身上线（仅自己和管理员可见）":"")
            +"（状态："+(ST_TEXT[status]||status)+"）");
        });
    });
  };
}
function updateRosterAll(){   // R52：头像/签名变更 → 重绘依赖区
  renderRoster();renderConvos();
  document.querySelectorAll("#msgs .msgav").forEach(el=>{
    setAv(el,+el.dataset.uid||0,el.dataset.nick||"?",30);});
}
function favEmojiKey(){return "web_fav_emoji_"+state.uid;}
function loadFavEmoji(){try{const a=JSON.parse(localStorage.getItem(favEmojiKey()));return Array.isArray(a)?a:[]}catch(e){return []}}
function saveFavEmoji(a){try{localStorage.setItem(favEmojiKey(),JSON.stringify(a))}catch(e){}}
function toggleFavEmoji(code){
  let a=loadFavEmoji();
  const has=a.includes(code);
  if(has)a=a.filter(x=>x!==code);else{a.unshift(code);a=a.slice(0,24);}
  saveFavEmoji(a);buildEmoji();
  showStatus(has?"⭐ 已取消收藏":"⭐ 已收藏 "+code);
}
// ---- R65 贴纸包：自定义包分组 / 封面 / 导航条 / 商店订阅 / 包内排序 ----
const STICKER_TRIAL_MAX=8;      // 未订阅内置包试看条数（与桌面端一致）
function customPackGroups(){          // {包名: [meta...]}，包内按 (order, code) 升序
  const g={};
  Object.values(state.customStickers).forEach(s=>{
    const p=(s.pack||"").trim()||"未分组";
    (g[p]=g[p]||[]).push(s);});
  Object.keys(g).forEach(p=>g[p].sort((a,b)=>((+a.order||0)-(+b.order||0))||(a.code<b.code?-1:1)));
  return g;
}
function packIsSub(pid){return (state.subs||[]).includes(pid)}
function coverUrl(pack){return "/api/packcover?pack="+encodeURIComponent(pack)+"&v="+state.coverV}
function emojiTitle(s){return (s.label||s.code)+":"+s.code+"（右键收藏）"}
function clickBuiltin(code){          // 内置 emoji：空输入直接发，否则插入短代码
  const t=$("#text");if(!t.value.trim())sendSticker(code);else{t.value+=":"+code+":";t.focus()}}
function clickCustom(code){const t=$("#text");t.value+="[: "+code+":]".replace(" ","");t.focus()}
function addBuiltin(b,s,fav){        // 渲染一个内置 emoji 按钮
  b.innerHTML="<span>"+esc(s.emoji)+"</span>";
  b.title=(fav?"⭐ ":"")+emojiTitle(s);
  if(fav)b.className="fav-ged";
  b.onclick=()=>clickBuiltin(s.code);
  b.oncontextmenu=ev=>{ev.preventDefault();stickerMenu(ev,s.code)};}
function buildEmoji(){
  const box=$("#emoji");box.innerHTML="";
  const nav=document.createElement("div");nav.id="epacks";box.appendChild(nav);
  const grid=document.createElement("div");grid.id="egrid";box.appendChild(grid);
  const shop=document.createElement("div");shop.id="eshop";shop.style.display=state.shopOpen?"":"none";
  box.appendChild(shop);
  const groups=customPackGroups();
  if(!state.curPack||(state.curPack.indexOf("p:")===0&&!groups[state.curPack.slice(2)]))state.curPack="";
  if(state.curPack.indexOf("s:")===0&&!state.shopPacks)state.curPack="";
  // ---- 导航条 ----
  const tab=(key,html,extra)=>{
    const t=document.createElement("span");t.className="pkt"+(state.curPack===key?" on":"");
    t.innerHTML=html;t.onclick=()=>{state.curPack=key;state.shopOpen=false;buildEmoji()};
    if(extra)extra(t);nav.appendChild(t);return t;};
  tab("","<span class='lab'>🕘 最近</span>");
  Object.keys(groups).sort().forEach(p=>{
    const hasCover=state.packMeta[p]&&state.packMeta[p].cover;
    tab("p:"+p,(hasCover?"<img class='pkcv' src='"+coverUrl(p)+"'>":"")+
        "<span class='lab'>"+esc(p)+"</span>",
      t=>{t.oncontextmenu=ev=>{ev.preventDefault();packMenu(ev,p)}});});
  (state.shopPacks||[]).forEach(pk=>{
    const sub=packIsSub(pk.pack_id);
    tab("s:"+pk.pack_id,"<span class='lab'>"+esc(pk.name)+"</span>"+
        (sub?"":"<span class='lk'>🔒</span>"),
      t=>{t.oncontextmenu=ev=>{ev.preventDefault();shopPackMenu(ev,pk)}});});
  const add=document.createElement("span");add.className="pkt pkadd";add.title="贴纸商店（订阅/退订内置包）";
  add.textContent="🛍";add.onclick=()=>{state.shopOpen=!state.shopOpen;openShop()};
  nav.appendChild(add);
  // ---- 视图：商店 / 包内容 ----
  if(state.shopOpen){renderShop(shop);return}
  if(state.curPack.indexOf("s:")===0){
    const pk=(state.shopPacks||[]).find(x=>x.pack_id===state.curPack.slice(2));
    if(pk){const sub=packIsSub(pk.pack_id);
      if(!sub){const tip=document.createElement("div");tip.className="trial";
        tip.innerHTML="试看中 · 未订阅，仅展示前 "+STICKER_TRIAL_MAX+" 条"+
          "<button class='subbtn'>＋ 订阅</button>";
        tip.querySelector(".subbtn").onclick=()=>shopSub(pk.pack_id,true);
        grid.appendChild(tip);}
      (pk.items||[]).slice(0,sub?99:STICKER_TRIAL_MAX).forEach(s=>{
        const b=document.createElement("b");b.title=emojiTitle(s);
        b.textContent=s.emoji;
        if(sub){b.onclick=()=>clickBuiltin(s.code);}
        else{b.className="trialoff";b.onclick=()=>{showStatus("订阅「"+pk.name+"」后可发送");shopSub(pk.pack_id,true)};}
        grid.appendChild(b);});}
    return;
  }
  if(state.curPack.indexOf("p:")===0){
    const p=state.curPack.slice(2);
    (groups[p]||[]).forEach(s=>{
      const b=document.createElement("b");b.title=emojiTitle(s);
      b.innerHTML="<img class='cst' src='/api/sticker/"+encodeURIComponent(s.code)+"'>";
      b.onclick=()=>clickCustom(s.code);
      b.oncontextmenu=ev=>{ev.preventDefault();stickerMenu(ev,s.code)};
      grid.appendChild(b);});
    return;
  }
  // 「最近」：⭐收藏 + 全部自定义贴纸 + 已订阅内置包
  const favs=loadFavEmoji();
  if(favs.length){
    const fw=document.createElement("span");
    fw.innerHTML="<span class='favlab'>⭐收藏</span><span class='favdiv'></span>";
    favs.forEach(code=>{
      const b=document.createElement("b");
      const info=state.stickers[code]||state.customStickers[code];
      if(info){
        if(info.emoji)addBuiltin(b,info,true);
        else{b.className="fav-ged";b.title="⭐ "+emojiTitle(info);
          b.innerHTML="<img class='cst' src='/api/sticker/"+encodeURIComponent(code)+"'>";
          b.onclick=()=>clickCustom(code);}
      }else{b.className="fav-ged";b.textContent=code;b.onclick=()=>clickBuiltin(code);}
      b.oncontextmenu=ev=>{ev.preventDefault();stickerMenu(ev,code)};
      fw.appendChild(b);});
    fw.appendChild(document.createElement("hr"));
    grid.appendChild(fw);
  }
  Object.values(state.stickers).forEach(s=>{       // 内置（仅已订阅包）
    const pid=builtinPackOf(s.code);
    if(pid&&!packIsSub(pid))return;
    const b=document.createElement("b");grid.appendChild(b);addBuiltin(b,s,false);});
  Object.values(state.customStickers).forEach(s=>{
    const b=document.createElement("b");b.title=emojiTitle(s);
    b.innerHTML="<img class='cst' src='/api/sticker/"+encodeURIComponent(s.code)+"'>";
    b.onclick=()=>clickCustom(s.code);
    b.oncontextmenu=ev=>{ev.preventDefault();stickerMenu(ev,s.code)};
    grid.appendChild(b);});
}
function builtinPackOf(code){                          // code → 所属内置包 pack_id
  for(const pk of (state.shopPacks||[]))
    if((pk.items||[]).some(x=>x.code===code))return pk.pack_id;
  return "";
}
function renderShop(box){
  box.innerHTML="";
  if(!state.shopPacks){box.innerHTML="<div class='trial'>正在加载商店…</div>";return}
  state.shopPacks.forEach(pk=>{
    const sub=packIsSub(pk.pack_id);
    const row=document.createElement("div");row.className="sp";
    row.innerHTML="<span class='nm'>"+esc(pk.name)+"</span>"+
      "<span class='em'>"+(pk.items||[]).map(x=>esc(x.emoji)).join("")+"</span>"+
      "<button class='"+(sub?"on":"")+"'>"+(sub?"已订阅 · 退订":"＋ 订阅")+"</button>";
    row.querySelector("button").onclick=()=>shopSub(pk.pack_id,!sub);
    box.appendChild(row);});
}
function openShop(){                       // 打开商店视图时按需拉目录（首次）
  if(!state.shopPacks)shopPost({op:"list"});
}
function shopPost(body){
  body.token = state.token;                 // 只进 POST 体，不进 URL（P0 验收）
  return fetch("/api/shop",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)}).then(r=>r.json())
    .then(d=>{if(!d.ok)showStatus(d.error||"操作失败");return d}).catch(()=>null);
}
function shopSub(pack_id,on){
  shopPost({op:"sub",pack_id:pack_id,on:on})
    .then(d=>{if(d&&d.ok)showStatus(on?"已订阅表情包":"已退订表情包")});
}
function packPost(body,okMsg){
  body.token = state.token;                 // 只进 POST 体，不进 URL（P0 验收）
  return fetch("/api/pack",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)}).then(r=>r.json())
    .then(d=>{showStatus(d.ok?(okMsg||"已更新"):(d.error||"操作失败"));return d}).catch(()=>null);
}
function reorderSticker(code,dir){
  packPost({op:"reorder",code:code,dir:dir},"顺序已更新");
}
function renamePack(pack){
  const n=window.prompt("重命名贴纸包（1~16 位中英文/数字/空格/_-）",pack);
  if(n==null)return;const v=n.trim();
  if(!v||v===pack)return;
  if(!/^[\w\u4e00-\u9fa5 \-]{1,16}$/.test(v)){showStatus("包名仅支持中英文/数字/空格/_-（≤16字）");return}
  packPost({op:"rename",pack:pack,new:v},"包已重命名");
}
function delPack(pack){
  if(!window.confirm("删除贴纸包「"+pack+"」？包内贴纸将一并删除。"))return;
  packPost({op:"del",pack:pack},"包已删除");
}
function clearPackCover(pack){packPost({op:"cover_del",pack:pack},"已恢复默认封面")}
function pickPackCover(pack){
  const f=$("#fpackcover");f.value="";
  f.onchange=()=>{const file=f.files&&f.files[0];if(!file)return;
    const rd=new FileReader();
    rd.onload=()=>{
      const b64=String(rd.result).split(",")[1]||"";
      const ext=(file.name.split(".").pop()||"png").toLowerCase();
      packPost({op:"cover_set",pack:pack,img:{ext:ext,data:b64}},"封面已更新");};
    rd.onerror=()=>showStatus("读取图片失败");
    rd.readAsDataURL(file);};
  f.click();
}
// ---- 右键上下文菜单（自定义包 / 内置包 / 单条贴纸）----
function ctxMenu(x,y,items){
  closeCtx();
  const m=document.createElement("div");m.id="ctxmenu";
  items.forEach(it=>{
    if(it==="-"){const hr=document.createElement("div");hr.className="hr";m.appendChild(hr);return}
    const d=document.createElement("div");d.className="mi";d.textContent=it[0];
    d.onclick=ev=>{ev.stopPropagation();closeCtx();it[1]()};
    m.appendChild(d);});
  document.body.appendChild(m);
  m.style.left=Math.min(x,window.innerWidth-m.offsetWidth-8)+"px";
  m.style.top=Math.min(y,window.innerHeight-m.offsetHeight-8)+"px";
}
function closeCtx(){const m=document.getElementById("ctxmenu");if(m)m.remove()}
document.addEventListener("click",closeCtx);
function packMenu(ev,pack){
  const hasCover=state.packMeta[pack]&&state.packMeta[pack].cover;
  ctxMenu(ev.clientX,ev.clientY,[
    ["✏️ 重命名",()=>renamePack(pack)],
    ["🖼 设置/更换封面",()=>pickPackCover(pack)],
    ...(hasCover?[["♻️ 清除封面",()=>clearPackCover(pack)]]:[]),
    "-",
    ["🗑 删除贴纸包",()=>delPack(pack)]]);
}
function shopPackMenu(ev,pk){
  const sub=packIsSub(pk.pack_id);
  ctxMenu(ev.clientX,ev.clientY,[
    [sub?"退订该包":"订阅该包",()=>shopSub(pk.pack_id,!sub)],
    ["🛍 打开商店",()=>{state.shopOpen=true;openShop();buildEmoji()}]]);
}
function stickerMenu(ev,code){
  const info=state.customStickers[code];
  const fav=loadFavEmoji().includes(code);
  const items=[[fav?"⭐ 取消收藏":"⭐ 收藏",()=>toggleFavEmoji(code)]];
  if(info){                        // 自定义贴纸：包内排序
    items.push("-",
      ["⇧ 上移",()=>reorderSticker(code,"up")],
      ["⇩ 下移",()=>reorderSticker(code,"down")],
      ["⤒ 置顶",()=>reorderSticker(code,"top")],
      ["⤓ 置底",()=>reorderSticker(code,"bottom")]);
  }
  ctxMenu(ev.clientX,ev.clientY,items);
}
function sendSticker(code){
  if(channelRO()){showStatus("当前频道只读");return;}
  fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,channel:state.cur.type,to:state.cur.type==="public"?undefined:(state.cur.uid||state.cur.gid),sticker:code})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"发送失败")});
}
function send(){
  if(channelRO()){showStatus("当前频道只读");return;}
  const owner={...state.cur},key=convKey(),token = state.token,original=$("#text").value;
  const version=(state.draftVersions||{})[key]||0;
  const t=$("#text").value.trim();
  if(!t)return;
  if(state.editSeq!=null){                         // R55-3：编辑态 → 走 /api/edit
    const seq=state.editSeq;
    fetch("/api/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:state.token,seq:seq,text:t,rich:richSegs(t)})})
      .then(r=>r.json()).then(d=>{
        if(d.ok){if(state.token===token&&convKey()===key&&state.editSeq===seq&&$("#text").value===original){$("#text").value="";growTextArea();cancelEdit();pushDraft();}}
        else showStatus(d.error||"编辑失败")});
    return;
  }
  const body={token:state.token,channel:state.cur.type,text:t,rich:richSegs(t)};
  if($("#silent").checked)body.silent=true;      // R26C 静默发送
  const dsel=$("#disguise");if(dsel&&dsel.value)body.disguise=dsel.value;   // R70E 消息伪装
  if(state.burnMode)body.burn=true;              // R14 阅后即焚发送
  if(state.reply)body.reply=state.reply;         // R41G：附带引用快照
  if(state.cur.type!=="public")body.to=state.cur.uid||state.cur.gid;
  fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{if(d.ok){
      if(state.token!==token)return;
      if(((state.draftVersions||{})[key]||0)!==version)return;
      state.drafts[key]="";
      writeDraft(owner,"",token);
      if(convKey()===key&&state.editSeq==null&&$("#text").value===original){
        clearTimeout(pushDraft.t);
        $("#text").value="";growTextArea();cancelReply();
      }
    }else{showStatus(d.error||"发送失败，文本已保留可重发")}})
    .catch(()=>{showStatus("⚠ 发送失败，文本已保留，点击发送即可重发");});   // R60：网络断连 → 保留草稿供重发
}
// ---- R23 网页端图片/文件 ----
function fmtSize(n){n=+n||0;if(n<1024)return n+"B";if(n<1048576)return (n/1024).toFixed(1)+"KB";return (n/1048576).toFixed(1)+"MB";}
function uploadSend(file,kind){
  if(channelRO()){showStatus("当前频道只读");return;}
  const owner={...state.cur},token = state.token;
  const rd=new FileReader();
  rd.onload=()=>{
    if(state.token!==token)return;
    const b64=String(rd.result).split(",")[1]||"";
    fetch("/api/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:state.token,name:file.name,kind:kind,data:b64})})
      .then(r=>r.json()).then(d=>{
        if(!d.ok){showStatus(d.error||"上传失败");return}
        if(state.token===token)sendFile(d.file,owner,token);})
      .catch(()=>showStatus("上传失败，请重新选择文件"));
  };
  rd.onerror=()=>showStatus("读取文件失败");
  rd.readAsDataURL(file);
}
function sendFile(f,owner={...state.cur},token = state.token){
  if(state.token!==token)return;
  const body={token:token,channel:owner.type,file:f};
  if(owner.type!=="public")body.to=owner.uid||owner.gid;
  fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"发送失败")})
    .catch(()=>showStatus("文件消息发送失败，请重试"));
}
// ---- R51 网页端：定时发送（服务器托管）+ 撤回（scope） ----
function delMsg(seq,scope){
  fetch("/api/del",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,seq:seq,scope:scope||"self"})})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"撤回失败")});
}
// ---- R60 web 消息多选：批量删除 / 合并转发 ----
function selSet(){if(!state.selSet)state.selSet=new Set();return state.selSet;}
function selBoxes(){
  const s=selSet(),out=[];
  document.querySelectorAll("#msgs .msg").forEach(n=>{if(n.dataset.seq&&s.has(+n.dataset.seq))out.push(n);});
  return out;
}
function toggleSel(box){
  const s=selSet(),seq=+box.dataset.seq||0;if(!seq)return;
  if(s.has(seq)){s.delete(seq);box.classList.remove("sel");}
  else{s.add(seq);box.classList.add("sel");}
  renderSelBar();
}
function clearSel(){const s=selSet();s.clear();document.querySelectorAll("#msgs .msg.sel").forEach(n=>n.classList.remove("sel"));renderSelBar();}
function selAll(){
  const s=selSet();
  document.querySelectorAll("#msgs .msg").forEach(n=>{const q=+n.dataset.seq||0;if(q){s.add(q);n.classList.add("sel");}});
  renderSelBar();
}
function renderSelBar(){
  let bar=document.getElementById("selbar");
  if(!state.selSet||state.selSet.size===0){
    if(bar){bar.style.display="none";}
    return;
  }
  if(!bar){
    bar=document.createElement("div");bar.id="selbar";
    bar.innerHTML="<span id='selcnt'></span><button id='selAllBtn'>全选</button><button id='selFwd'>↪ 转发</button><button id='selDel' class='delbtn'>🗑 删除</button><button id='selCancel'>取消</button>";
    document.body.appendChild(bar);
    $("#selAllBtn").onclick=()=>selAll();
    $("#selFwd").onclick=()=>selForward();
    $("#selDel").onclick=()=>selDelete();
    $("#selCancel").onclick=()=>clearSel();
  }
  bar.style.display="flex";
  $("#selcnt").textContent="已选 "+state.selSet.size+" 条　";
}
function selDelete(){
  const boxes=selBoxes();if(!boxes.length)return;
  const mine=boxes.filter(n=>+n.dataset.own===1);
  const others=boxes.filter(n=>+n.dataset.own!==1);
  if(!confirm("确认删除选中的 "+boxes.length+" 条消息？"+((state.is_admin||state.cur.type==="private")&&others.length?"\n（含 "+others.length+" 条他人消息，将按权限撤回）":"")))return;
  const seqs=[...selSet()];
  seqs.forEach(seq=>{
    const row=boxes.find(n=>+n.dataset.seq===seq);
    const me=row?(row.dataset.own==="1"):true;
    const scope=(me?"self":(state.is_admin?((state.cur.type==="group")?"both":"both"):(state.cur.type==="private"?"both":"self")));
    delMsg(seq,scope);
  });
  clearSel();
}
function selForward(){
  const boxes=selBoxes();
  const items=[];
  boxes.forEach(b=>{
    const ra=b.__raw||{};
    const t=(ra.text||"").trim();
    if(t){items.push({nick:ra.nick||"?",text:t,seq:ra.seq||0,ts:Date.now()/1000|0});}
  });
  if(items.length===0){showStatus("选中的都是图片/文件，暂不支持转发");return;}
  fwdPickDialog(items);
}
function fwdPickDialog(items){
  let d=document.getElementById("fwddlg");if(d)d.remove();
  d=document.createElement("div");d.id="fwddlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(320px,90vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:4px'>↪ 合并转发 "+items.length+" 条消息</div>"
    +"<div style='font-size:11px;color:var(--dim);margin-bottom:8px'>选择目标会话（公共频道 / 好友 / 群）</div>"
    +"<div id='fwdtargets' style='max-height:240px;overflow:auto'></div>"
    +"<div style='margin-top:10px;text-align:right'><button id='fwdClose'>取消</button></div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d)d.remove()};
  document.body.appendChild(d);
  $("#fwdClose").onclick=()=>d.remove();
  const box=$("#fwdtargets");
  function row(label,fn){
    const r=document.createElement("div");
    r.style.cssText="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:8px;cursor:pointer";
    r.onmouseenter=()=>{r.style.background="rgba(255,138,92,.08)"};
    r.onmouseleave=()=>{r.style.background="transparent"};
    r.innerHTML="<span style='flex:1'>"+label+"</span>";
    r.onclick=()=>{d.remove();sendMerged(items,fn);};
    box.appendChild(r);
  }
  row("💬 公共频道",{type:"public"});
  (state.convos||[]).forEach(c=>{
    const u=(state.roster||[]).find(x=>x.uid===c.uid);
    row("👤 "+esc(u?u.nick:c.nick||("用户"+c.uid)),{type:"private",uid:c.uid});
  });
  (state.serverGroups.length?state.serverGroups:state.groups||[]).forEach(g=>row("👥 "+esc(g.name||("群"+g.gid)),{type:"group",gid:g.gid}));
}
function sendMerged(items,target){
  const seqs=items.map(it=>+it.seq||0).filter(s=>s>0);
  if(seqs.length===0){showStatus("无法合并转发：缺少源消息序号");return;}
  const body={token:state.token,channel:target.type,text:"",fwd_seqs:seqs};
  const cur=state.cur||{};
  body.fwd_from={type:cur.type||"public"};
  if(cur.type==="private"&&cur.uid!=null)body.fwd_from.uid=cur.uid;
  if(cur.type==="group"&&cur.gid!=null)body.fwd_from.gid=cur.gid;
  if(target.type==="private")body.to=target.uid;
  if(target.type==="group")body.to=target.gid;
  fetch("/api/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"转发失败");else{showStatus("✅ 已转发 "+seqs.length+" 条消息");clearSel();}});
}
function adminOp(op,uid,on){
  const body={token:state.token,op:op};
  if(uid!=null)body.uid=uid;
  if(on!=null)body.on=!!on;
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{if(!d.ok)showStatus(d.error||"操作失败")});
}
function onCleared(d){
  if(d.all){                                     // 清空全部：重载当前会话历史
    $("#msgs").innerHTML="";
    if(state.cur.type==="public"||state.cur.uid||state.cur.gid)loadHistory(state.cur);
    addSys("🧹 管理员已清空全部聊天记录");
  }else if(d.uid!=null){
    const u=(state.roster||[]).find(x=>x.uid===d.uid)||{};
    if(state.cur.uid===d.uid||state.cur.type==="public"){ // 命中当前会话 → 重载
      $("#msgs").innerHTML="";
      loadHistory(state.cur);
    }
    addSys("🧹 管理员已清空用户 "+(u.nick||d.uid)+" 的全部消息");
  }
}
function adminPanel(){
  let d=document.getElementById("admldg");
  if(d){d.remove();return}
  d=document.createElement("div");d.id="admldg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(340px,90vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:4px;color:#b71c1c'>🧹 管理员面板</div>"
    +"<div style='font-size:11px;color:var(--dim);margin-bottom:10px'>以下操作对全员生效，不可恢复，请谨慎使用</div>"
    +"<button id='admClear' style='width:100%;background:#fdecea;color:#b71c1c;border:1px solid #f5c6c2;margin-bottom:8px'>清空全部聊天记录（全员）</button>"
    +"<div style='display:flex;gap:6px;margin-bottom:8px'>"
    +"  <button id='admGroups' style='flex:1'>👥 群管理</button>"
    +"  <button id='admAudit' style='flex:1'>📋 审计日志</button>"
    +"</div>"
    +"<div style='font-size:12px;color:var(--dim);margin-bottom:4px'>在线用户</div>"
    +"<div style='display:flex;gap:4px;margin-bottom:4px'>"
    +"  <input id='admNick' placeholder='昵称/uid' value='' style='flex:1;padding:2px 4px'>"
    +"  <button id='admKickNick'>踢下线</button>"
    +"</div>"
    +"<div id='admList' style='max-height:200px;overflow:auto'></div>"
    +"<div style='margin-top:10px;text-align:right'><button id='admClose'>关闭</button></div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d)d.remove()};
  document.body.appendChild(d);
  $("#admClear").onclick=()=>{if(confirm("确认清空全部聊天记录？全员本地历史将同步删除，不可恢复。")){adminOp("clear_all");showStatus("✅ 已提交：清空全部聊天记录")}};
  $("#admGroups").onclick=()=>{d.remove();adminGroupsPanel()};
  $("#admAudit").onclick=()=>{d.remove();auditPanel()};
  $("#admKickNick").onclick=()=>{const t=$("#admNick").value.trim();if(!t){showStatus("请输入昵称/uid");return}adminOp("kick",t);showStatus("✅ 已提交：踢 @"+t);$("#admNick").value=""};
  $("#admNick").onkeydown=e=>{if(e.key==="Enter")$("#admKickNick").onclick()};
  $("#admClose").onclick=()=>d.remove();
  function loadAdminUsers(){
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,op:"users"})})
    .then(r=>r.json()).then(d=>{
      if(d.ok&&Array.isArray(d.users))state.admin_users=d.users;
      if(document.getElementById("admldg"))renderAdm();
    });
}
const renderAdm=()=>{
    const box=$("#admList");box.innerHTML="";
    const list=(state.admin_users||state.roster||[]).slice()
      .sort((a,b)=>(a.nick||"").localeCompare(b.nick||""));
    list.forEach(u=>{
      const inv=!!u.invisible;
      // roster 条目天生在线；admin_users 用 online 字段区分在线/离线
      const online=u.hasOwnProperty("online")?!!u.online:true;
      const row=document.createElement("div");
      row.style.cssText="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px dashed var(--line,#eee)";
      row.innerHTML="<span style='flex:1'>"
        +(inv?"👻 ":"")
        +"<span style='color:"+(online?"#2e7d32":"#999")+"'>"+(online?"●":"○")+"</span> "
        +esc(u.nick||"用户"+u.uid)
        +(inv?" <span style='color:#8e24aa;font-size:11px'>隐身</span>":"")
        +(online?"":" <span style='color:#bbb;font-size:11px'>离线</span>")
        +"</span>"
        +"<button class='ghost' style='font-size:11px' onclick='grpUserInfo("+u.uid+")'>资料</button>"
        +(inv?"<button class='ghost' style='font-size:11px' onclick='adminOp(\"force_invis\","+u.uid+",false)'>显身</button>"
             :"<button class='ghost' style='font-size:11px' onclick='adminOp(\"force_invis\","+u.uid+",true)'>隐身</button>")
        +(online?"<button class='ghost' style='font-size:11px' onclick='adminOp(\"kick\","+u.uid+")'>踢下线</button>":"")
        +"<button class='ghost' style='font-size:11px' onclick='adminOp(\"clear_uid\","+u.uid+")'>清空其消息</button>";
      box.appendChild(row);
    });
};
  renderAdm();loadAdminUsers();
  const timer=setInterval(()=>{if(document.getElementById("admldg")){renderAdm();loadAdminUsers()}else clearInterval(timer)},5000);
}
// ---- R56 网页端：系统管理员群管理：目录+增删成员+解散 ----
let _grpData=[],_grpSelG=-1,_grpSelM=-1;
function grpReq(op,gid,uid,cb){
  const body={token:state.token,op:op,gid:gid};
  if(uid!=null)body.uid=uid;
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"操作失败");return}
      if(cb)cb();
    });
}
function loadGrpData(cb){
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,op:"groups"})})
    .then(r=>r.json()).then(d=>{_grpData=d.groups||[];if(cb)cb();});
}
function adminGroupsPanel(){
  let d=document.getElementById("grpdlg");
  if(d){d.remove();return}
  d=document.createElement("div");d.id="grpdlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:100";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(760px,94vw);height:min(560px,88vh);display:flex;flex-direction:column";
  card.innerHTML=
    "<div style='font-weight:600;color:#b71c1c'>👥 群管理 · 系统管理员</div>"
    +"<div style='font-size:11px;color:var(--dim);margin-bottom:8px'>选中群查看成员；可增删成员或直接解散群</div>"
    +"<div style='display:flex;flex:1;gap:10px;min-height:0'>"
    +"  <div style='flex:1;display:flex;flex-direction:column;min-width:0'>"
    +"    <div style='font-size:12px;color:var(--dim);margin-bottom:4px'>群聊</div>"
    +"    <div id='gpList' style='flex:1;overflow:auto;border:1px solid var(--line,#eee);border-radius:8px'></div>"
    +"  </div>"
    +"  <div style='flex:1;display:flex;flex-direction:column;min-width:0'>"
    +"    <div style='font-size:12px;color:var(--dim);margin-bottom:4px'>成员（选中成员可移除）</div>"
    +"    <div id='gpMem' style='flex:1;overflow:auto;border:1px solid var(--line,#eee);border-radius:8px'></div>"
    +"  </div>"
    +"</div>"
    +"<div style='margin-top:10px;display:flex;gap:6px;align-items:center;flex-wrap:wrap'>"
    +"  <div style='font-size:11px;color:var(--dim)'>在线</div>"
    +"  <select id='gpAddSel' style='flex:1;min-width:120px;max-width:190px'></select>"
    +"  <button id='gpAdd'>➕ 加</button>"
    +"  <input id='gpNick' placeholder='昵称/uid（可加离线）' value='' style='flex:1;min-width:120px;padding:2px 4px'>"
    +"  <button id='gpAddNick'>⌨ 昵称加</button>"
    +"  <button id='gpRemove'>➖ 移除</button>"
    +"  <button id='gpDissolve' style='background:#fdecea;color:#b71c1c;border:1px solid #f5c6c2'>💣 解散</button>"
    +"  <button id='gpClose'>关闭</button>"
    +"</div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d){d.remove();_grpData=[]}};
  document.body.appendChild(d);
  $("#gpClose").onclick=()=>d.remove();
  $("#gpAdd").onclick=()=>{
    const g=_grpData[_grpSelG];const v=parseInt($("#gpAddSel").value);
    if(!g||isNaN(v)){showStatus("请先选择群与候选成员");return}
    grpReq("group_add",g.gid,v,()=>{showStatus("✅ 已加入成员");reloadGrp()});
  };
  $("#gpAddNick").onclick=()=>{
    const g=_grpData[_grpSelG];const t=$("#gpNick").value.trim();
    if(!g){showStatus("请先选择一个群");return}
    if(!t){showStatus("请输入昵称或uid");return}
    grpReq("group_add_nick",g.gid,t,()=>{showStatus("✅ 已加入（含离线用户）");$("#gpNick").value="";reloadGrp()});
  };
  $("#gpNick").onkeydown=e=>{if(e.key==="Enter")$("#gpAddNick").onclick()};
  $("#gpRemove").onclick=()=>{
    const g=_grpData[_grpSelG];
    if(!g||_grpSelM==null){showStatus("请先选择群和要移除的成员");return}
    const m=g.members[_grpSelM];if(!m)return;
    if(m.uid===g.owner){showStatus("⚠ 不能移除群主，请先解散群");return}
    grpReq("group_remove",g.gid,m.uid,()=>{showStatus("✅ 已移除成员");reloadGrp()});
  };
  $("#gpDissolve").onclick=()=>{
    const g=_grpData[_grpSelG];if(!g){showStatus("请先选择一个群");return}
    if(g.public){showStatus("⚠ 公共频道为系统频道，不能解散");return}
    if(confirm("确认解散群「"+g.name+"」？将移除全部成员且不可恢复。"))
      grpReq("group_dissolve",g.gid,null,()=>{showStatus("✅ 已解散该群");reloadGrp()});
  };
  const reloadGrp=()=>loadGrpData(()=>{_grpSelG=-1;_grpSelM=-1;renderGrp();renderMem();renderAddSel()});
  loadGrpData(()=>{_grpSelG=-1;_grpSelM=-1;renderGrp();renderMem();renderAddSel()});
}
function renderGrp(){
  const box=$("#gpList");box.innerHTML="";
  _grpData.forEach((g,i)=>{
    const r=document.createElement("div");
    r.style.cssText="padding:7px 9px;border-bottom:1px dashed var(--line,#eee);cursor:pointer;display:flex;justify-content:space-between;"+(i===_grpSelG?"background:#e8f1fd":"");
    r.innerHTML="<span>"+esc(g.name)+"</span><span style='color:#888'>"+g.member_count+"/"+(g.member_max!==undefined?g.member_max:"?")+"</span>";
    r.onclick=()=>{_grpSelG=i;_grpSelM=-1;renderGrp();renderMem();renderAddSel()};
    box.appendChild(r);
  });
}
function renderMem(){
  const box=$("#gpMem");box.innerHTML="";
  const g=_grpData[_grpSelG];
  if(!g){box.innerHTML="<div style='padding:10px;color:#999;font-size:12px'>← 选择左侧群查看成员</div>";return}
  const mems=(g.members||[]).slice().sort((a,b)=>(a.nick||"").localeCompare(b.nick||""));
  mems.forEach((m,i)=>{
    const r=document.createElement("div");
    const tag=(m.uid===g.owner?"👑":(((g.admins||[]).indexOf(m.uid)>=0)?"🛡":""));
    r.style.cssText="padding:6px 9px;border-bottom:1px dashed var(--line,#eee);cursor:pointer;display:flex;align-items:center;gap:6px;"+(i===_grpSelM?"background:#e8f1fd":"");
    const span=document.createElement("span");span.style.cssText="flex:1";
    span.innerHTML=tag+(m.invisible?"👻 ":"")+esc(m.nick||("用户"+m.uid))+" <span style='color:#888'>#"+m.uid+"</span>"
      +(m.invisible?" <span style='color:#8e24aa;font-size:11px'>隐身</span>":"");
    const bt=document.createElement("button");
    bt.className="ghost";bt.style.cssText="font-size:11px";
    bt.textContent="🔍 所属群";
    bt.onclick=ev=>{ev.stopPropagation();grpUserInfo(m.uid)};
    r.appendChild(span);r.appendChild(bt);
    r.onclick=()=>{_grpSelM=i;renderMem()};
    box.appendChild(r);
  });
}
function grpUserInfo(uid){
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,op:"user_groups",uid:uid})})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){showStatus(d.error||"查询失败");return}
      const g=d.groups||[];
      const lines=["昵称: "+(d.nick||d.uid)+"  #"+d.uid,
             "状态: "+(d.online?"● 在线":"○ 离线")+(d.invisible?"  👻 隐身":"")];
      lines.push("","所属群("+g.length+"):");
      if(g.length)lines.push(...g.map(x=>"["+x.gid+"] "+x.name+" · "+(x.role==="owner"?"👑群主":x.role==="admin"?"🛡管理":"成员")));
      else lines.push("（未加入任何群）");
      alert(lines.join("\r\n"));
    });
}
function renderAddSel(){
  const sel=$("#gpAddSel");if(!sel)return;
  sel.innerHTML="";
  const g=_grpData[_grpSelG];
  if(!g){sel.innerHTML="<option>先选择群</option>";return}
  const inIds={};(g.members||[]).forEach(m=>inIds[m.uid]=1);
  const cands=(state.roster||[]).filter(u=>!inIds[u.uid]).sort((a,b)=>(a.nick||"").localeCompare(b.nick||""));
  if(cands.length===0){sel.innerHTML="<option>无候选用户</option>";return}
  cands.forEach(u=>{const o=document.createElement("option");o.value=u.uid;o.textContent=esc(u.nick||("用户"+u.uid))+"  #"+u.uid;sel.appendChild(o);});
}
// ---- 网页端：管理员操作审计日志展示 ----
const _ADM_ACT={"admin_kick":"踢下线","admin_clear_all":"清空全部记录",
  "admin_clear_uid":"清空用户消息","admin_group_add":"群加成员",
  "admin_group_remove":"群撤成员","admin_group_dissolve":"解散群",
  "admin_user_get":"查看用户资料","admin_force_invis":"管理员强制显身/隐身"};
function auditPanel(){
  fetch("/api/admin",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,op:"audit"})})
    .then(r=>r.json()).then(d=>{
      const rows=d.rows||[];
      let dl=document.getElementById("audldg");
      if(dl)dl.remove();
      dl=document.createElement("div");dl.id="audldg";
      dl.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:100";
      const card=document.createElement("div");
      card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(480px,92vw);max-height:78vh;display:flex;flex-direction:column";
      card.innerHTML="<div style='font-weight:600;color:#b71c1c'>📋 审计日志 · 管理员操作</div>"
        +"<div style='font-size:11px;color:var(--dim);margin-bottom:6px'>今日共 "+rows.length+" 条（管理员在校操作）</div>"
        +"<div id='audBody' style='flex:1;overflow:auto'></div>"
        +"<div style='margin-top:8px;text-align:right'><button id='audClose'>关闭</button></div>";
      dl.appendChild(card);dl.onclick=e=>{if(e.target===dl)dl.remove()};
      document.body.appendChild(dl);
      $("#audClose").onclick=()=>dl.remove();
      const body=$("#audBody");
      if(!rows.length){body.innerHTML="<div style='color:#999;font-size:12px;padding:8px'>暂无管理员操作记录</div>";return}
      rows.reverse().forEach(r=>{
        const action=_ADM_ACT[r.type]||r.type;
        const who=(r.uid==null?"?":("@"+r.uid));
        const what=r.target!=null?(r.target_nick!=null?("@ "+(r.target_nick||r.target)+" #"+r.target):("#"+r.target)):"";
        const gid=r.gid!=null?("群#"+r.gid):"";
        const line=document.createElement("div");
        line.style.cssText="padding:6px 2px;border-bottom:1px dashed var(--line,#eee);font-size:12px";
        line.innerHTML="<b>"+esc(action)+"</b> "+esc(who+" "+what+" "+gid)
          +"<div style='color:var(--dim);font-size:11px'>"+esc(r.time||"")+"</div>";
        body.appendChild(line);
      });
    });
}
function schedPanel(){
  let d=document.getElementById("scheddlg");
  if(d){d.remove();return}
  d=document.createElement("div");d.id="scheddlg";
  d.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:99";
  const card=document.createElement("div");
  card.style.cssText="background:var(--side,#fff);border:1px solid var(--line,#ddd);border-radius:12px;padding:14px;width:min(340px,90vw)";
  card.innerHTML="<div style='font-weight:600;margin-bottom:8px'>⏰ 定时发送（服务器托管）</div>"
    +"<div id='schedList'></div>"
    +"<div style='margin-top:10px;display:flex;align-items:center;gap:6px'>"
    +"<input id='schedMin' type='number' min='1' max='120' value='1' style='width:58px'>"
    +"<span>分钟后发送输入框内容</span><button id='schedAdd'>定时</button></div>"
    +"<div style='margin-top:10px;text-align:right'><button id='schedClose'>关闭</button></div>";
  d.appendChild(card);
  d.onclick=e=>{if(e.target===d)d.remove()};
  document.body.appendChild(d);
  renderSchedList();
  $("#schedClose").onclick=()=>d.remove();
  $("#schedAdd").onclick=()=>{
    const mins=Math.max(1,parseInt($("#schedMin").value)||1);
    const t=$("#text").value.trim();
    if(!t){showStatus("先把要定时发送的内容打好");return}
    const body={token:state.token,action:"set",channel:state.cur.type,text:t,minutes:mins};
    if(state.cur.type!=="public")body.to=state.cur.uid||state.cur.gid;
    fetch("/api/sched",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
      .then(r=>r.json()).then(r=>{
        if(!r.ok){showStatus(r.error||"定时失败");return}
        $("#text").value="";
        showStatus("✅ 已定时（服务器托管，离线也会到点发出）");
        refreshSched();});
  };
}
function renderSchedList(){
  const box=$("#schedList");if(!box)return;
  box.innerHTML="";
  const list=(state.scheds||[]).slice().sort((a,b)=>a.fire_at-b.fire_at);
  if(!list.length){box.innerHTML="<div style='color:var(--dim)'>暂无待发定时消息</div>";return}
  list.forEach(r=>{
    const remain=Math.max(0,Math.floor(r.fire_at-Date.now()/1000));
    const mm=String(Math.floor(remain/60));const ss=String(remain%60).padStart(2,"0");
    const row=document.createElement("div");
    row.style.cssText="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:3px 0";
    row.innerHTML="<span>["+new Date(r.fire_at*1000).toTimeString().slice(0,5)+"] 剩"+mm+"分"+ss+"秒 "
      +esc(String(r.text||"").slice(0,18))+"</span>";
    const c=document.createElement("button");c.textContent="取消";
    c.onclick=()=>{
      fetch("/api/sched",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:state.token,action:"cancel",rid:r.rid})})
        .then(r=>r.json()).then(r=>{if(!r.ok)showStatus(r.error||"取消失败")});
    };
    row.appendChild(c);
    box.appendChild(row);
  });
}
function refreshSched(){
  fetch("/api/sched",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token:state.token,action:"list"})})
    .then(r=>r.json()).then(r=>{if(r.ok){state.scheds=r.scheds||[];renderSchedList();}});
}
$("#btnImg").onclick=()=>$("#fimg").click();
$("#btnFile").onclick=()=>$("#ffile").click();
$("#fimg").onchange=e=>{const f=e.target.files[0];if(f)uploadSend(f,"image");e.target.value="";};
$("#ffile").onchange=e=>{const f=e.target.files[0];if(f)uploadSend(f,"file");e.target.value="";};
document.getElementById("mpfile").onchange=e=>{const n=e.target.files.length;document.getElementById("mping").textContent=n?("📷 已选 "+n+" 张图"):"";};
// ---- R67 手机端：会话列表抽屉（窄屏 #side 转 fixed + 遮罩） ----
function sideScrim(){let s=$("#scrim");if(!s){s=document.createElement("div");s.id="scrim";
  s.onclick=closeSide;document.body.appendChild(s);}return s;}
function toggleSide(){const open=$("#side").classList.toggle("open");
  sideScrim().classList.toggle("on",open);}
function closeSide(){$("#side").classList.remove("open");const s=$("#scrim");if(s)s.classList.remove("on");}
function openStream(){
  if(!state.token)return;
  if(state.esRetry){clearTimeout(state.esRetry);state.esRetry=null;}
  if(state.es)state.es.close();
  function mpMTime(ts){const d=new Date(ts*1000);const n=Date.now();const s=(n-ts*1000)/1000;if(s<60)return"刚刚";if(s<3600)return Math.floor(s/60)+"分钟前";if(s<86400)return Math.floor(s/3600)+"小时前";if(s<86400*3)return Math.floor(s/86400)+"天前";const p=x=>String(x).padStart(2,"0");return(d.getMonth()+1)+"月"+p(d.getDate()+"")+"日"}
  const mfx=(a,b)=>{const s=(b.toString().charCodeAt(0)||0)%a.length;return a[s]};     // 头像色板
  const mpAL="#07c160,#ff8a5c,#5aa9e6,#c77bec,#f5a623,#e8635a,#3ba676,#9b6bd8".split(",");
  const mavColor=u=>{try{return mpAL[Math.abs(Number(u))%mpAL.length]}catch(e){return mpAL[0]}};
  function mpgrid(fns){
    const n=fns.length;if(!n)return"";
    const cls=n===1?"mpc-grid row1":(n===2||n===4?"mpc-grid row2":"mpc-grid");
    return "<div class='"+cls+"'>"+fns.map(f=>"<img src='/api/moment_img/"+encodeURIComponent(f)+"' loading='lazy' onclick='window.open(this.src)'></img>").join("")+"</div>";
  }
  window.closeMoments=function(){state.mpanelOpen=false;document.getElementById("mpanel").style.display="none";uxSelectNavigation('chat')};
  function updateMomDot(){                         // R68 朋友圈互动红点
    const e=document.getElementById("momDot");if(!e)return;
    if(state.momUnread>0){e.textContent=state.momUnread>99?"99+":state.momUnread;e.style.display="inline-block";}
    else{e.style.display="none";}}
  window.momBump=function(d){                      // R68：窗口未开时他人新动态/新赞/新评 → 未读+1
    const p=d.post;if(!p)return;
    const pid=p.pid||d.pid,likes=new Set(p.likes||[]),n=(p.comments||[]).length;
    const prev=state.momSig[pid];let other=false;
    if(d.t==="moment_new")other=(p.uid!==state.uid);
    else if(prev){
      const al=[...likes].filter(u=>!prev.likes.has(u));
      const ac=(p.comments||[]).slice(prev.n);
      other=al.some(u=>u!==state.uid)||ac.some(c=>c&&c.uid!==state.uid);}
    state.momSig[pid]={likes,n};
    if(other&&!state.mpanelOpen){state.momUnread+=1;updateMomDot();}};
  window.momentLike=function(pid,on){fetch("/api/moment_like",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:state.token,pid,on})}).then(()=>window.fetchMoments())}
  window.momentComment=function(pid){
    const inp=document.getElementById("mc-"+pid);if(!inp)return;
    const t=(inp.value||"").trim();if(!t)return;
    fetch("/api/moment_comment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:state.token,pid,text:t})}).then(()=>window.fetchMoments())}
  window.momentDel=function(pid){if(confirm("确定删除这条动态？"))fetch("/api/moment_del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:state.token,pid})}).then(()=>window.fetchMoments())}
  window.openMoments=function(){
    uxSelectNavigation('moments');
    state.mpanelOpen=true;document.getElementById("mpanel").style.display="block";
    const me=document.getElementById("mcovMe");
    if(me){me.style.background=mavColor(state.uid);me.textContent=(state.nick||"我").charAt(0).toUpperCase();}
    document.getElementById("mcovCap").textContent="生活原本沉闷，但跑起来就有风";
    window.applyCover(null);
    const my=(state.roster||[]).find(u=>u.uid===state.uid)||{};
    document.getElementById("mcovSig").textContent=(my.sign||"点击设置个性签名");
    fetch("/api/mcover?token="+encodeURIComponent(state.token)).then(r=>r.json())
      .then(d=>{if(d.ok)window.applyCover(d.cover)}).catch(()=>{});
    window.fetchMoments()}
  // ---- 封面：预设渐变 / 上传图片 / 恢复默认；右下昵称下方签名可点击编辑 ----
  const COVP=[["#ffd0b0","#ffb98f"],["#cdeedd","#9fdcb8"],["#d7e2ff","#aec6ff"],
              ["#ffd3de","#ffadc4"],["#e7dcff","#cbb6ff"],["#ffe0a8","#ffc47a"]];
  window.applyCover=function(cover){
    const m=document.getElementById("mcover");if(!m)return;
    m.style.backgroundImage="";m.style.backgroundSize="";m.style.backgroundPosition="";
    if(cover&&cover.mode==="img"){
      m.style.backgroundImage="url('/api/mcovimg?token="+encodeURIComponent(state.token)+"&t="+Date.now()+"')";
      m.style.backgroundSize="cover";m.style.backgroundPosition="center";
    }else if(cover&&cover.mode==="preset"){
      const p=COVP[(Number(cover.preset)||0)%COVP.length];
      m.style.background="linear-gradient(135deg,"+p[0]+","+p[1]+")";
    }else{
      m.style.background="radial-gradient(circle at 20% 30%,rgba(255,255,255,.55),transparent 45%),"
        +"radial-gradient(circle at 85% 20%,rgba(181,255,214,.35),transparent 40%),"
        +"linear-gradient(135deg,#a8d8ea 0%,#f4e3c1 55%,#ffd6e0 100%)";
    }
    const cur=cover?cover.mode+(cover.mode==="preset"?("-"+(cover.preset||0)):""):"def";
    const sel=document.getElementById("mcovPrevs");if(sel)sel.dataset.cur=cur;
  };
  window.toggleCovMenu=function(){
    const p=document.getElementById("mcovPrevs");if(!p)return;
    if(p.style.display==="block"){p.style.display="none";return}
    if(!p.dataset.built){
      p.dataset.built="1";
      const row=document.createElement("div");
      COVP.forEach((c,i)=>{
        const d=document.createElement("div");
        d.className="pv";d.style.background="linear-gradient(135deg,"+c[0]+","+c[1]+")";
        d.title="预设封面 "+(i+1);
        d.onclick=()=>{fetch("/api/mcover",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({token:state.token,preset:i})}).then(()=>{window.applyCover({mode:"preset",preset:i});p.style.display="none"})};
        row.appendChild(d);});
      p.appendChild(row);
      const up=document.createElement("div");up.className="pvup";up.textContent="📁 上传图片…";
      up.onclick=()=>{document.getElementById("mcovFile").click()};
      p.appendChild(up);
      const def=document.createElement("div");def.className="pvdef";def.textContent="♻️ 恢复默认";
      def.onclick=()=>{fetch("/api/mcover_del",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:state.token})}).then(()=>{window.applyCover(null);p.style.display="none"})};
      p.appendChild(def);
      document.getElementById("mcovFile").onchange=e=>{
        const f=e.target.files[0];e.target.value="";
        if(!f)return;
        const rd=new FileReader();
        rd.onload=()=>{const ds=String(rd.result||"").split(",")[1]||"";
          fetch("/api/mcover",{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({token:state.token,img:{ext:(f.name.split(".").pop()||"jpg").toLowerCase(),data:ds}})})
            .then(()=>{window.applyCover({mode:"img"});p.style.display="none"})};
        rd.readAsDataURL(f);};
    }
    p.style.display="block";
    const cur=p.dataset.cur||"def";
    [...p.querySelectorAll(".pv")].forEach((d,i)=>d.classList.toggle("sel",cur==="preset-"+i));
  };
  document.getElementById("mcovSig").onclick=function(){
    const s=document.getElementById("mcovSig");
    const inp=document.createElement("input");
    const mine=(state.roster||[]).find(u=>u.uid===state.uid)||{};
    inp.value=mine.sign||"";
    inp.maxLength=60;
    inp.style.cssText="position:absolute;right:16px;bottom:32px;width:60%;font-size:11px;border:1px solid #fff;border-radius:8px;padding:2px 6px;background:rgba(255,255,255,.92)";
    s.style.display="none";s.parentNode.appendChild(inp);inp.focus();
    const done=()=>{const v=inp.value.trim();
      s.parentNode.removeChild(inp);s.style.display="";
      if(v)fetch("/api/profile",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:state.token,sign:v})}).then(()=>{s.textContent=v});
      else s.textContent="点击设置个性签名";};
    inp.onblur=done;
    inp.onkeydown=e=>{if(e.key==="Enter"){e.preventDefault();done()}if(e.key==="Escape"){inp.blur()}};
  };
  window.fetchMoments=function(){
    fetch("/api/moments").then(r=>r.json()).then(d=>{if(!d.ok)return;state.moments=d.posts||[];
      state.momSig={};(d.posts||[]).forEach(p=>{state.momSig[p.pid]={likes:new Set(p.likes||[]),n:(p.comments||[]).length};});
      state.momUnread=0;updateMomDot();window.renderMoments()});}
  window.renderMoments=function(){
    const box=document.getElementById("mfeed");if(!box)return;
    const own=u=>u===state.uid;
    if(!(state.moments||[]).length){box.innerHTML="<div class='mpc-empty'>还没有动态，来发第一条吧 📸</div>";return;}
    box.innerHTML=(state.moments).map(p=>{
      const liked=(p.likes||[]).includes(state.uid);
      const lk=(p.likes||[]).length;
      const lks=lk?("<div class='mpc-like'>👍 "+lk+"<span class='lk'> 人觉得很赞</span></div>"):"";
      const cmts=(p.comments||[]).map(c=>{
        const mine=(c.uid===state.uid);
        const r="<span class='"+(mine?"cmine":"cwho")+"'>"+esc(c.nick||"用户")+"</span>："+esc(c.text);
        return "<div class='mpc-cmt' onclick='mcb("+p.pid+")'>"+r+"</div>";
      }).join("");
      const hasSoc=(lks||cmts);
      return "<div class='mpc'>"+
        "<div class='mpc-hd'>"+
          "<div class='mpc-av' style='background:"+mavColor(p.uid)+"'>"+(p.nick||"?").charAt(0).toUpperCase()+"</div>"+
          "<div class='mpc-me'>"+
            "<div class='mpc-nm'>"+esc(p.nick||"用户")+"</div>"+
            "<div class='mpc-tm'>"+mpMTime(p.ts)+"</div>"+
          "</div>"+
          (own(p.uid)?"<div class='mpc-del'><button onclick='momentDel("+p.pid+")' title='删除'>🗑</button></div>":"")+
        "</div>"+
        (p.text?"<div class='mpc-tx'>"+fmtText(p.text)+"</div>":"")+
        mpgrid(p.images||[])+
        "<div class='mpc-act'>"+
          "<a onclick='event.stopPropagation();momentLike("+p.pid+","+(!liked)+")'>"+(liked?"👍 已赞":"👍 赞")+"</a>"+
          "<a onclick='event.stopPropagation();mcb("+p.pid+")'>💬 评论</a>"+
          "<span class='sp'></span><span class='acnt'>"+mpMTime(p.ts)+"</span>"+
        "</div>"+
        (hasSoc?"<div class='mpc-soc'>"+(lks?"<div class='mpc-like'>"+lks+"</div>":"")+(cmts?"<div class='mpc-cmt-list'>"+cmts+"</div>":"")+"</div>":"")+
        "<div class='mpc-write'><input id='mc-"+p.pid+"' placeholder='评论…' onkeydown='if(event.key===\"Enter\")momentComment("+p.pid+")'/><button onclick='momentComment("+p.pid+")'>发表</button></div>"+
      "</div>";
    }).join("");
  }
  window.mcb=function(pid){const el=document.getElementById("mc-"+pid);if(el){el.focus();el.scrollIntoView({behavior:"smooth",block:"center"})}}
  window.publishMoment=function(){
    const text=document.getElementById("mptext").value.trim();
    const files=document.getElementById("mpfile").files||[];
    const done=imgs=>{
      const body={token:state.token,text,images:imgs};
      const mt="本次共 "+imgs.length+" 张图";
      document.getElementById("mping").textContent=mt+"，发布中…";
      fetch("/api/moment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
        .then(r=>r.json()).then(d=>{
          if(d&&d.ok){document.getElementById("mptext").value="";document.getElementById("mpfile").value="";document.getElementById("mping").textContent="✅ 发布成功";window.fetchMoments();}
          else{document.getElementById("mping").textContent="❌ 发布失败："+((d&&d.err)||"未知错误");}
        }).catch(()=>{document.getElementById("mping").textContent="❌ 网络错误，发布失败"});
    };
    if(!text&&files.length===0)return;
    document.getElementById("mping").textContent="上传中…";
    const imgs=[];let left=files.length;
    const read=idx=>{
      if(idx>=files.length){done(imgs);return}
      const fr=new FileReader();
      fr.onload=e=>{const ext=(files[idx].name.split(".").pop()||"jpg").toLowerCase();imgs.push({ext,base64:e.target.result.split(",")[1]});read(idx+1)};
      fr.readAsDataURL(files[idx]);
    };
    if(files.length===0)done(imgs);else read(0);
  }
  const es=new EventSource("/api/events");
  state.es=es;
  let checkingAuth=false;
  es.onmessage=e=>{
    if(state.es!==es||!state.token)return;
    let d;try{d=JSON.parse(e.data)}catch(err){return}
    if(d.t==="chat"||d.t==="poll"){
      if(d.channel==="private")bumpConvo(d);      // R22：维护最近私聊 + 未读
      if(matchActive(d))addMsg(d,d.uid===state.uid);
      else if(d.uid!==state.uid){showNotification(d);playSound();}   // R55-1：非当前会话 → 浏览器通知+提示音
      updateTitle();                               // R55-1：标题未读计数
      renderRead();
    }
    else if(d.t==="poll_state"){updatePoll(d)}    // R26A：票数权威更新
    else if(d.t==="reaction"){updateReactions(d)}  // R27：表情回应实时更新
    else if(d.t==="nudge"){                        // R67 拍一拍：当前会话插轻量行，否则提醒
      const tn=(d.target===state.uid)?"你":(String(d.target_nick||"ta"));
      const txt=(d.nick||"有人")+" 拍了拍 "+tn;
      if(matchActive(d))addNudge(txt);
      else if(d.uid!==state.uid){showNotification({nick:d.nick,text:(d.target===state.uid?"拍了拍你":"拍了拍 "+tn),uid:d.uid});playSound();}
    }
    else if(d.t==="shake"){                        // R68 窗口抖动：当前会话插轻量行+抖窗，否则提醒
      const txt=(d.nick||"有人")+" 向你发送了窗口抖动";
      if(matchActive(d)){addShake(txt);shakeWindow();}
      else if(d.uid!==state.uid){showNotification({nick:d.nick,text:"向你发送了窗口抖动",uid:d.uid});playSound();shakeWindow();}
    }
    else if(d.t==="preview"){updatePreview(d)}    // R26D：链接预览补发
    else if(d.t==="read"){
      const k=d.key||convKey();(state.reads[k]=state.reads[k]||{})[d.uid]=d.seq;
      renderRead();}
    else if(d.t==="edit"){updateMsg(d)}
    else if(d.t==="del"){eraseMsg(d)}
    else if(d.t==="roster"){state.roster=d.online;updateRosterAll();}
    else if(d.t==="status_ack"){                       // R68：在线状态回帧 → 本人名单点色即时校准
      const me=(state.roster||[]).find(u=>u.uid===state.uid);
      if(me)me.status=d.status;
      state.myStatus=d.status;renderRoster();}
    else if(d.t==="remark_ack"){                       // R69C9：备注名回帧 → 本地缓存 + 列表/标题刷新
      const ruid=+d.uid,rem=String(d.remark||"").trim();
      if(rem)state.remarkCache[ruid]=rem;else delete state.remarkCache[ruid];
      [state.roster,state.known].forEach(arr=>{const u=(arr||[]).find(x=>x.uid===ruid);if(u)u.remark=rem;});
      updateRosterAll();renderConvos();
      if(state.cur.type==="private"&&state.cur.uid===ruid)$("#headTitle").textContent=channelName();
      showStatus(rem?("备注名已更新为「"+rem+"」"):"备注名已清除");}
    else if(d.t==="block_list"){                       // R50：屏蔽名单同步 → 标记刷新
      state.blocked=d.blocked||[];
      renderConvos();renderRoster();renderHeadActions();}
    else if(d.t==="sched_list"){                       // R51：定时消息权威列表同步
      state.scheds=d.items||[];
      renderSchedList();}
    else if(d.t==="group_list"){syncGroups(d.groups||[]);renderRoster();applyRO();}
    else if(d.t==="group_state"){addSys(d.text||"群信息已更新");syncGroupProfile(d);refreshPanel();}   // R9H：同步 about/avatar
    else if(d.t==="group_avatar_data"){syncGroupProfile(d);}   // R9H：群头像回帧 → 上传者立即刷新
    else if(d.t==="group_invite"){showInviteCode(d.code);}   // R28：邀请码回帧（单播）
    else if(d.t==="sticker_list"){                            // R30C：贴纸清单实时刷新
      state.stickers={};(d.stickers||[]).forEach(s=>state.stickers[s.code]=s);
      state.customStickers={};(d.custom_stickers||[]).forEach(s=>state.customStickers[s.code]=s);
      state.packMeta=d.sticker_pack_meta||{};state.coverV++;   // R65：包封面元数据 + 换缓存戳
      buildEmoji();}
    else if(d.t==="sticker_shop_list"){                       // R65：商店目录回帧
      state.shopPacks=d.packs||[];state.subs=d.subs||[];buildEmoji();}
    else if(d.t==="sticker_sub"){                             // R65：订阅变更回帧
      state.subs=d.subs||[];buildEmoji();}
    else if(d.t==="game_list"){                            // R49：大厅实时刷新
      state.gmeta={};(d.games||[]).forEach(g=>state.gmeta[g.name]=g);
      state.grooms=d.rooms||[];renderGames();
      if(state.globbyOpen)renderLobby();}
    else if(d.t==="game_state"){                           // R49：房间状态推送
      if(d.nicks)state.gnicks=Object.assign({},state.gnicks,d.nicks);
      const inR=d.room&&((d.room.players||[]).includes(state.uid)
        ||(d.room.spectators||[]).includes(state.uid));
      if(state.groom===d.room_id&&!inR){
        state.gleft[d.room_id]=true;hideGamePanel();return;}
      if(inR&&state.gleft[d.room_id])return;
      if(!state.groom&&inR)openGamePanel(d.room_id);       // 建房/加入自动开面板
      if(state.groom===d.room_id){
        const previous=state.gst&&state.gst.room;
        if(!previous||previous.round!==d.room.round||d.room.status==="created"){
          state.gpriv=null;state.glog=[];}
        if(d.room.status!=="playing")state.gpriv=null;
        state.gst=d;(d.events||[]).forEach(e=>state.glog.push(e));
        if(state.glog.length>200)state.glog=state.glog.slice(-200);
        renderGamePanel();}}
    else if(d.t==="game_private"){                         // R49：私密投递（手牌/词面）
      if(state.groom===d.room_id&&state.gst&&state.gst.room
          &&state.gst.room.status==="playing"){
        state.gpriv=d.state;renderGamePanel();}}
    else if(d.t==="fish_board"){                           // R70H：排行榜实时刷新（广播/单播同形）
      if(d.game){state.fish=Object.assign({},state.fish||{});state.fish[d.game]=d.entries||[];}
      if(state.fishOpen)window.fishRender();}
    else if(d.t==="error"){
      if(d.code==="kicked")leaveLogin();
      showStatus(d.text||d.code||"操作失败");
    }
    else if(d.t==="cleared"){onCleared(d)}        // R53：管理员清理广播 → 清空本地界面
    else if(d.t==="system"){addSys(d.text)}
    else if(d.t==="task_state"){                                  // R69B6/B7 群任务清单
      state.tasks=d.tasks||[];
      if(d.text)addSys("🧾 "+d.text);
      if(state.taskGid===d.gid)renderTasks();}
    else if(d.t==="welcome"){/* 登录响应已含初始状态 */}
    else if(d.t==="moment_new"||d.t==="moment_update"){          // 朋友圈：新动态/点赞评论
      window.momBump(d);                                         // R68：未读数红点
      if(state.mpanelOpen)window.fetchMoments()}
    else if(d.t==="moment_cover"){                                // 朋友圈：我的封面变更 → 立即重绘
      if(state.mpanelOpen&&d.uid===state.uid)window.applyCover(d.cover||null)}
  };
  es.onerror=()=>{
    if(state.es!==es||!state.token)return;
    if(checkingAuth||state.esRetry)return;
    checkingAuth=true;
    const currentToken=state.token;
    const retry=()=>{
      checkingAuth=false;
      if(state.es!==es||state.token!==currentToken||!currentToken)return;
      if(state.esRetry)return;
      state.esRetry=setTimeout(()=>{
        state.esRetry=null;
        if(state.es===es&&state.token===currentToken)openStream();
      },2000);
    };
    fetch("/api/whoami").then(response=>{
      if(state.es!==es||state.token!==currentToken||!currentToken)return;
      if(response.status===401){leaveLogin();showStatus("登录已失效，请重新登录");return;}
      retry();
    }).catch(retry);
  };
}
$("#btnLogin").onclick=login;
$("#nick").addEventListener("keydown",e=>{if(e.key==="Enter")login()});
// ---- R__ web 吸底/跳底接线 + textarea 自动增高（autogrow，对等 TG/微信）----
state.atBottom=true;
$("#msgs").addEventListener("scroll",()=>applyMsgScroll());
// R69C10 用户资料卡：点消息头像打开（自己 → 个人资料）
$("#msgs").addEventListener("click",ev=>{
  const a=ev.target.closest(".msgav");
  if(!a)return;
  const u=+a.dataset.uid||0;
  if(!u)return;
  ev.stopPropagation();userCard(u);
});
$("#jumpBottom").addEventListener("click",jumpToLatest);
function growTextArea(){
  const t=$("#text");
  if(state.editSeq==null&&!t.value){t.style.height="";return;}   // 空内容→回默认高
  t.style.height="42px";
  t.style.height=Math.min(160,t.scrollHeight)+"px";}
$("#text").addEventListener("input",growTextArea);
$("#text").addEventListener("keydown",e=>{if(e.key==="Escape")growTextArea();});   // 取消编辑态后回缩
$("#text").addEventListener("keydown",e=>{
  if(state.atOpen){                                  // R67 @选择器：接管方向键/Enter/Tab/Esc
    e.preventDefault();e.stopImmediatePropagation();
    if(e.key==="ArrowDown")state.atIdx=(state.atIdx+1)%state.atCands.length;
    else if(e.key==="ArrowUp")state.atIdx=(state.atIdx-1+state.atCands.length)%state.atCands.length;
    else if(e.key==="Enter"||e.key==="Tab"){atPickPick(state.atCands[state.atIdx]);}
    else if(e.key==="Escape")atPickHide();
    atPickMark();return;}
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}else if(e.key==="Escape"&&state.editSeq!=null){cancelEdit()}});
$("#text").addEventListener("input",pushDraft);   // R29B：输入防抖推草稿
// ---- R67 网页端 @成员选择器：@ 前缀 → 群成员/在线好友候选浮层（与桌面 _ac_candidates 语义对齐） ----
function atPrefix(){const t=$("#text"),s=t.selectionStart;const at=t.value.lastIndexOf("@",s-1);
  if(at<0)return null;const after=t.value.slice(at+1,s);
  if(!after||/\s/.test(after))return null;return {at,prefix:after};}
function atCandidates(prefix){
  const seen=new Set(),out=[],low=prefix.toLowerCase();
  if(state.cur.type==="group"){(state.gmembers[state.cur.gid]||[]).forEach(m=>{
    const n=String(m.nick||"").trim();if(n&&n!==state.nick&&n.toLowerCase().startsWith(low)&&!seen.has(n)){seen.add(n);out.push(n);}});}
  (state.roster||[]).forEach(u=>{const n=String(u.nick||"").trim();
    if(u.uid!==state.uid&&n&&n.toLowerCase().startsWith(low)&&!seen.has(n)){seen.add(n);out.push(n);}});
  return out;}
function atPickShow(){const p=atPrefix();if(!p)return atPickHide();
  const c=atCandidates(p.prefix);if(!c.length)return atPickHide();
  state.atCands=c;state.atIdx=0;
  let box=$("#atpick");if(!box){box=document.createElement("div");box.id="atpick";$("#input").appendChild(box);}
  box.innerHTML="<div class='h'>@ 成员（群成员优先，含离线）</div>"+c.map((n,i)=>"<b data-i='"+i+"' onclick='atPickChoose(this)'>"+esc(n)+"</b>").join("");
  box.style.display="block";state.atOpen=true;atPickMark();}
function atPickHide(){state.atOpen=false;const b=$("#atpick");if(b)b.style.display="none";}
function atPickMark(){const bs=document.querySelectorAll("#atpick b");bs.forEach((b,i)=>b.className=(i===state.atIdx?"on":""));}
function atPickPick(n){if(!n)return;const t=$("#text"),p=atPrefix();if(!p)return;
  const s=t.selectionStart;t.value=t.value.slice(0,p.at)+"@"+n+" "+t.value.slice(s);
  t.focus();const pos=p.at+1+n.length+1;try{t.setSelectionRange(pos,pos)}catch(e){}
  atPickHide();growTextArea();}
function atPickChoose(el){atPickPick(state.atCands[+el.dataset.i]);}
$("#text").addEventListener("input",()=>{if(atPrefix())atPickShow();else atPickHide();});
$("#btnSend").onclick=send;
$("#btnPoll").onclick=sendPoll;
$("#btnSched").onclick=schedPanel;                  // R51：定时发送面板
$("#btnBurn").onclick=toggleBurn;                   // R14：阅后即焚开关
function toggleBurn(){                              // 🔥 开/关阅后即焚发送（active 高亮提示）
  state.burnMode=!state.burnMode;
  const b=$("#btnBurn");b.title=(state.burnMode?"阅后即焚已开启（再次点击关闭）":"阅后即焚（全体读完自动删除）");
  b.style.boxShadow=state.burnMode?"0 0 8px 2px rgba(255,138,92,.7)":"none";
  b.style.color=state.burnMode?"#ff5544":"";
  showStatus(state.burnMode?"🔥 阅后即焚已开启：下一条消息全体读完即自动删除":"阅后即焚已关闭");
}
// ---- R26B 频道只读：频道（广播群）内非创建者禁言输入/操作 ----
function curChannelGroup(){                        // R71：当前会话若为频道，返回群对象（非群/非频道 → null）
  const c=state.cur;
  if(c.type!=="group")return null;
  return (state.serverGroups.length?state.serverGroups:state.groups||[]).find(x=>x.gid===c.gid)||null;}
function curIsChannel(){const g=curChannelGroup();return !!g&&g.kind==="channel";}
function channelRO(){
  if(state.cur.type!=="group")return false;
  if(state.groupAccessPending===state.cur.gid||!state.meIn[state.cur.gid])return true;
  const g=curChannelGroup();
  return !!g&&g.kind==="channel"&&g.owner!==state.uid;}
function applyRO(){
  const ro=channelRO();
  const text=$("#text"),inp=$("#input");
  const dis=[text,$("#btnSend"),$("#btnImg"),$("#btnFile"),$("#btnPoll"),$("#btnSched"),$("#btnBurn")];
  dis.forEach(el=>{if(el)el.disabled=ro});
  text.placeholder=state.cur.type==="group"&&state.groupAccessPending===state.cur.gid?"正在确认群成员身份…":
    ro?"当前群聊只读或不可用":"输入消息，Enter 发送，:smile: 表情";
  inp.dataset.ro=ro?"1":"";}

// ==================== R49 网页端桌游 ====================
// 数据通路：REST /api/game → hub.dispatch GAME 帧 → 服务器经 SSE 推回
// game_list（房间清单）/ game_state（房间快照+events+nicks）/ game_private（手牌/词面）。
state.gmeta={};state.grooms=[];state.groom=null;state.gst=null;state.gpriv=null;state.gleft={};
state.gnicks={};state.glog=[];state.globbyOpen=false;
state.fish={};state.fishOpen=false;state.fishGame="";   // R70H 摸鱼排行榜缓存
const GICON={guess_number:"🔢",gomoku:"⚫",rps:"✊",spy:"🕵️",uno:"🃏",blackjack:"🂠",
  drawguess:"🎨",connect4:"🔴",othello:"⚪",calc24:"🧮",matchpairs:"🂡",betrayal:"🏚️",
  kaituo:"🏜️",lingdi:"🏰",tielu:"🚆",gongfang:"⚒️",
  chengzhu:"👑",gemcity:"💎",siji:"🌸",bolan:"🗳️",
  azul:"🧱",rummikub:"🀄",yahtzee:"🎲",nimmt:"🐂",
  davinci:"🔐",kalah:"🥜",lovelove:"💌",halloween:"🔔",
  xiangqi:"♟️",chess:"♛",go:"⚫",shogi:"🎎",junqi:"🪖",dou:"🐘",onewolf:"🐺",werewolf:"🐺",avalon:"⚔️",liar:"🎲",ninja:"🥷",coc:"🔮"};
// ---- R59 SVG 游戏美术系统：每款一个渐变底色 + 专属图形，内联 data-URI（不依赖静态路由）----
// GART[name] = [起色, 止色, 48×48 内图形 SVG]
const GART={
  guess_number:["#5b8def","#3b6fd4",'<circle cx="24" cy="19" r="12" fill="rgba(255,255,255,.22)"/><text x="24" y="34" font-size="26" fill="#fff" font-weight="800" text-anchor="middle" font-family="Segoe UI,Arial">?</text>'],
  gomoku:["#b07c45","#8a5a2b",'<g stroke="rgba(255,255,255,.35)" stroke-width="1"><path d="M6 24h36M24 6v36M14 14h20M14 34h20"/></g><circle cx="18" cy="20" r="6" fill="#fff"/><circle cx="18" cy="20" r="6" fill="none" stroke="#000" stroke-width="2"/><circle cx="30" cy="28" r="6" fill="#111"/>'],
  rps:["#e2634b","#c24a33",'<text x="13" y="27" font-size="22">✊</text><text x="31" y="27" font-size="22">✋</text>'],
  spy:["#7b5fb0","#5d4592",'<circle cx="20" cy="20" r="11" fill="none" stroke="#fff" stroke-width="4"/><path d="M28 28 L37 37" stroke="#fff" stroke-width="6" stroke-linecap="round"/>'],
  uno:["#e4483c","#c2362c",'<rect x="8" y="14" width="24" height="16" rx="3" fill="#fff" transform="rotate(-12 20 22)"/><rect x="16" y="18" width="24" height="16" rx="3" fill="#fff" transform="rotate(8 28 26)"/><circle cx="28" cy="26" r="6" fill="#e8b93c"/>'],
  blackjack:["#2f6f4f","#1f5236",'<rect x="12" y="10" width="24" height="30" rx="3" fill="#fff"/><g fill="#222"><path d="M24 16c-4 4-5 8 0 11 5-3 4-7 0-11z"/><circle cx="24" cy="27" r="3.4"/></g>'],
  drawguess:["#e08ac0","#c265a4",'<circle cx="24" cy="24" r="15" fill="#fff"/><circle cx="16" cy="18" r="4" fill="#e4483c"/><circle cx="26" cy="14" r="4" fill="#f0c14b"/><circle cx="33" cy="22" r="4" fill="#3ba55d"/><circle cx="31" cy="31" r="4" fill="#4a7de0"/>'],
  connect4:["#3f6fe0","#2955b8",'<g><circle cx="16" cy="14" r="6.5" fill="#fff"/><circle cx="30" cy="14" r="6.5" fill="#fff"/><circle cx="16" cy="28" r="6.5" fill="#e05555"/><circle cx="30" cy="28" r="6.5" fill="#e05555"/><circle cx="23" cy="34" r="5" fill="#ffd54f"/></g>'],
  othello:["#3a3d42","#23262b",'<circle cx="24" cy="24" r="17" fill="#fff"/><circle cx="24" cy="24" r="12" fill="#000"/><circle cx="24" cy="24" r="6" fill="#fff"/>'],
  calc24:["#e0a13c","#c38427",'<rect x="10" y="10" width="28" height="28" rx="5" fill="rgba(255,255,255,.22)"/><text x="24" y="33" font-size="24" fill="#fff" font-weight="800" text-anchor="middle" font-family="monospace">24</text>'],
  matchpairs:["#37a25f","#21804a",'<g><rect x="10" y="16" width="18" height="24" rx="3" fill="#fff"/><rect x="20" y="12" width="18" height="24" rx="3" fill="#eaf6ef" stroke="#37a25f"/><circle cx="19" cy="22" r="4" fill="#e4483c"/><circle cx="29" cy="22" r="4" fill="#3f6fe0"/></g>'],
  betrayal:["#5a3f78","#3e2a56",'<path d="M10 26 L24 12 L38 26 V36 H10 Z" fill="#fff" opacity=".9"/><path d="M14 36 V28 h6 v8z M28 24 v12 h8 V24 l-4-5z" fill="#3e2a56"/><rect x="20" y="30" width="8" height="6" fill="#f0c14b"/>'],
  kaituo:["#c98a3d","#a96a28",'<polygon points="24,7 39,15 39,33 24,41 9,33 9,15" fill="#fff" opacity=".9"/><polygon points="24,11 36,17 36,31 24,37 12,31 12,17" fill="#e8b93c"/><text x="24" y="27" font-size="13" fill="#6b4a1b" font-weight="700" text-anchor="middle">5</text>'],
  lingdi:["#4f7a54","#37603c",'<rect x="10" y="20" width="28" height="16" rx="2" fill="#fff" opacity=".92"/><path d="M14 20 v-4 a10 10 0 0 1 20 0 v4" fill="none" stroke="#e05555" stroke-width="3"/><circle cx="24" cy="20" r="3.4" fill="#3f6fe0"/><rect x="16" y="26" width="5" height="10" fill="#8a5a2b"/><rect x="27" y="26" width="5" height="10" fill="#8a5a2b"/>'],
  tielu:["#3d5a86","#2c4366",'<g stroke="#fff" stroke-width="4" stroke-linecap="round"><path d="M8 16h32M8 30h32"/></g><rect x="18" y="20" width="12" height="8" rx="2" fill="#efca63"/><g stroke="#fff" stroke-width="1.4" opacity=".7"><path d="M10 14V18M16 14V18M22 14V18M26 30v4M32 30v4M38 30v4"/></g>'],
  gongfang:["#8a6f4a","#6a5336",'<circle cx="16" cy="19" r="7" fill="#fff"/><path d="M24 34 H42 V28 C36 28 26 26 24 20 Z" fill="#fff" opacity=".9"/><rect x="20" y="34" width="24" height="5" rx="2" fill="#d7c9a8"/><path d="M10 34v4h28v-4z" fill="#fff"/>'],
  chengzhu:["#7f5b3f","#5f422c",'<g><rect x="8" y="16" width="20" height="13" rx="2" fill="#e8b93c"/><rect x="20" y="16" width="20" height="13" rx="2" fill="#3ba55d"/><rect x="13" y="21" width="4" height="4" fill="#fff" opacity=".85"/><rect x="25" y="21" width="4" height="4" fill="#fff" opacity=".85"/><rect x="32" y="21" width="4" height="4" fill="#3f6fe0"/></g><g fill="#fff"><circle cx="11" cy="37" r="3"/><circle cx="25" cy="37" r="3"/><circle cx="37" cy="36" r="3"/></g>'],
  gemcity:["#8a5fbf","#6a45a0",'<g stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M24 6 L29 9 L27 15 L21 15 L19 9 Z" fill="#fff" opacity=".9" stroke="none"/><path d="M10 26 L18 22 L24 28" fill="none"/><circle cx="30" cy="30" r="5" fill="#fff" opacity=".85"/><circle cx="24" cy="36" r="3.4" fill="#efca63"/></g>'],
  siji:["#3f8f6a","#2a6b4d",'<path d="M24 8 L28 12 L26 15 L24 13 L22 15 L20 12 Z" fill="#efca63"/><circle cx="17" cy="17" r="4" fill="#fff" opacity=".9"/><circle cx="31" cy="19" r="3" fill="#fff" opacity=".8"/><path d="M14 30 Q24 20 34 30 Q24 34 14 30 Z" fill="#fff" opacity=".85"/><g fill="#e05555"><circle cx="19" cy="28" r="1.6"/><circle cx="24" cy="29" r="1.6"/><circle cx="29" cy="28" r="1.6"/></g>'],
  bolan:["#5b6ca8","#42528a",'<path d="M24 6 L42 18 V42 H6 V18 Z" fill="#fff" opacity=".9"/><path d="M24 14 L36 22 V38 H12 V22 Z" fill="#e8b93c"/><circle cx="24" cy="28" r="3" fill="#1f2a52"/><text x="24" y="25" font-size="4" fill="#333" text-anchor="middle">🗳</text>'],
  azul:["#e05555","#c2362c",'<g fill="rgba(255,255,255,.92)"><rect x="7" y="12" width="12" height="12" rx="2"/><rect x="22" y="12" width="12" height="12" rx="2"/><rect x="13" y="26" width="12" height="12" rx="2"/><rect x="28" y="28" width="9" height="9" rx="2" fill="#e8b93c"/><rect x="12" y="12" width="12" height="12" rx="2" fill="none" stroke="#7a1f18" stroke-width="1.4" transform="rotate(6 18 18)"/><rect x="22" y="12" width="12" height="12" rx="2" fill="none" stroke="#7a1f18" stroke-width="1.4"/></g><circle cx="24" cy="24" r="3" fill="#fff" stroke="#7a1f18" stroke-width="1.2"/>'],
  rummikub:["#3f8f6a","#2a6b4d",'<g stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="M10 18h20"/><path d="M16 24h22"/><path d="M10 30h16"/></g><rect x="14" y="12" width="20" height="24" rx="3" fill="rgba(255,255,255,.22)" stroke="#fff" stroke-width="2"/>'],
  yahtzee:["#e0a13c","#c38427",'<g fill="#fff"><rect x="8" y="14" width="13" height="13" rx="3" transform="rotate(-18 14 20)"/><rect x="19" y="8" width="13" height="13" rx="3"/><rect x="30" y="22" width="13" height="13" rx="3" transform="rotate(20 36 28)"/><rect x="14" y="20" width="11" height="11" rx="3"/><circle cx="38" cy="36" r="4.4" fill="#e05555" opacity=".9"/></g>'],
  nimmt:["#8a5a2b","#6a4121",'<g fill="#fff"><path d="M14 11 L34 11 L30 15 L18 15 Z"/><rect x="12" y="15" width="24" height="4" rx="2"/><rect x="17" y="19" width="14" height="16" rx="2"/><circle cx="17" cy="27" r="1.3" fill="#8a6f4a"/><circle cx="27" cy="27" r="1.3" fill="#8a6f4a"/><path d="M16 12 V6 a2 2 0 0 1 4 0 M22 12 V6 a2 2 0 0 1 4 0 M28 12 V6 a2 2 0 0 1 4 0" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></g>'],
  davinci:["#5b6ca8","#42528a",'<g fill="#fff"><rect x="10" y="10" width="10" height="30" rx="2"/><rect x="22" y="10" width="10" height="30" rx="2"/><rect x="34" y="10" width="8" height="30" rx="2" fill="rgba(255,255,255,.55)"/></g><g fill="#42528a"><rect x="13" y="17" width="4" height="5" rx="1"/><rect x="25" y="17" width="4" height="5" rx="1"/><circle cx="38" cy="15" r="2"/></g>'],
  kalah:["#8a5fbf","#6a45a0",'<g fill="#fff"><circle cx="12" cy="14" r="6.5"/><circle cx="24" cy="14" r="6.5"/><circle cx="36" cy="14" r="6.5"/><circle cx="9" cy="30" r="6.5" opacity=".85"/><circle cx="21" cy="30" r="6.5"/><circle cx="33" cy="30" r="6.5"/><circle cx="42" cy="22" r="9" fill="#e8b93c"/><circle cx="42" cy="22" r="3.4" fill="#6a45a0"/></g>'],
  lovelove:["#e08ac0","#c265a4",'<path d="M24 36 L12 22 a8.5 9 0 0 1 12-6.6 a8.5 9 0 0 1 12 6.6 Z" fill="#fff"/><path d="M24 36 L12 22 a8.5 9 0 0 1 12-6.6 a8.5 9 0 0 1 12 6.6 Z" fill="none" stroke="#fff" stroke-width="2"/><text x="24" y="29" font-size="13" fill="#b04d9b" font-weight="800" text-anchor="middle">8</text>'],
  halloween:["#e05555","#c2362c",'<g fill="#fff"><circle cx="12" cy="20" r="4"/><circle cx="22" cy="20" r="4"/><circle cx="14" cy="30" r="4" opacity=".85"/><circle cx="24" cy="33" r="4"/><circle cx="34" cy="24" r="4" opacity=".9"/></g><rect x="7" y="8" width="22" height="7" rx="3" fill="#e8b93c"/><path d="M40 34 a9 9 0 0 1 -9 6 h2 a7 7 0 0 0 7 -6z" fill="#e8b93c"/>'],
  tictactoe:["#3f6fe0","#2955b8",'<g stroke="rgba(255,255,255,.4)" stroke-width="2"><path d="M16 8h16M16 40h16M8 16v16M40 16v16"/></g><circle cx="19" cy="19" r="6" fill="none" stroke="#fff" stroke-width="3"/><path d="M29 29 l12 12M41 29 L29 41" stroke="#efca63" stroke-width="3.4" stroke-linecap="round"/>'],
  halma:["#4f7a54","#37603c",'<path d="M24 8 L40 18 V38 L24 44 L8 38 V18 Z" fill="none" stroke="#fff" stroke-width="2.6"/><circle cx="24" cy="16" r="4.2" fill="#efca63" stroke="#fff" stroke-width="1.2"/><circle cx="35" cy="26" r="4.2" fill="#e05555" stroke="#fff" stroke-width="1.2"/><circle cx="24" cy="36" r="4.2" fill="#3ba55d" stroke="#fff" stroke-width="1.2"/><circle cx="13" cy="32" r="4.2" fill="#fff" stroke="#fff" stroke-width="1.2"/>'],
  checkers:["#8a5a2b","#6a4121",'<rect x="8" y="8" width="32" height="32" rx="4" fill="rgba(255,255,255,.16)"/><g stroke="#fff" stroke-width="1.4" opacity=".55"><path d="M8 24h32M24 8v32"/></g><circle cx="20" cy="20" r="6.5" fill="#111" stroke="#fff" stroke-width="1.6"/><circle cx="28" cy="28" r="6.5" fill="#e05555" stroke="#fff" stroke-width="1.6"/>'],
  blokus:["#37a25f","#21804a",'<g fill="rgba(255,255,255,.25)" stroke="#fff" stroke-width="1.6"><rect x="7" y="9" width="13" height="13" rx="2"/><rect x="13" y="22" width="13" height="13" rx="2"/><rect x="26" y="13" width="13" height="13" rx="2"/><rect x="26" y="27" width="13" height="13" rx="2" fill="#efca63"/></g>'],
  ludo:["#e0a13c","#c38427",'<g stroke="#fff" stroke-width="1.8"><circle cx="24" cy="13" r="6.4" fill="#e05555"/><circle cx="34" cy="27" r="6.4" fill="#3f6fe0"/><circle cx="15" cy="27" r="6.4" fill="#3ba55d"/><path d="M19 40 a6.4 6.4 0 0 1 10 0z" fill="#e8b93c" stroke="none"/></g>'],
  onewolf:["#4a3b6b","#32264d",'<path d="M8 16 L15 30 L9 38 L20 32 L24 41 L28 32 L39 38 L33 30 L40 16 Z" fill="#fff" opacity=".9"/><circle cx="17" cy="25" r="2.6" fill="#32264d"/><circle cx="31" cy="25" r="2.6" fill="#32264d"/><path d="M13 33 q11 7 22 0" fill="none" stroke="#32264d" stroke-width="2" stroke-linecap="round"/><circle cx="24" cy="12" r="6" fill="#e8b93c"/>'],
  werewolf:["#5a2d3a","#3c1826",'<path d="M6 12 L12 30 L6 40 L20 33 L24 44 L28 33 L42 40 L36 30 L42 12 Z" fill="none" stroke="#fff" stroke-width="3"/><path d="M6 12 L12 30 L20 33 L24 44 L28 33 L36 30 L42 12 L42 12 Z" fill="#fff" opacity=".15"/><circle cx="17" cy="24" r="3" fill="#e05555"/><circle cx="31" cy="24" r="3" fill="#e05555"/><path d="M19 32 q5 4 10 0" fill="none" stroke="#3c1826" stroke-width="2.2" stroke-linecap="round"/>'],
  avalon:["#4f7a9e","#355c7d",'<path d="M24 8 L42 18 V34 L24 44 L6 34 V18 Z" fill="none" stroke="#fff" stroke-width="3"/><path d="M24 8 L42 18 V34 L24 44 L6 34 V18 Z" fill="#fff" opacity=".18"/><circle cx="24" cy="25" r="7" fill="#e8b93c" stroke="#fff" stroke-width="2"/><path d="M24 19 l4 11 h-8 z" fill="#355c7d"/>'],
  liar:["#c9853e","#8a5a2b",'<circle cx="24" cy="24" r="15" fill="rgba(255,255,255,.2)"/><text x="24" y="31" font-size="22" fill="#fff" font-weight="800" text-anchor="middle" font-family="Segoe UI,Arial">?</text><path d="M12 34 h24" stroke="#5a3a1a" stroke-width="3" stroke-linecap="round"/>'],
  ninja:["#33415a","#1d2736",'<g stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round"><path d="M24 42 V20 M24 28 L12 18 M24 28 L36 18 M24 20 l6 8 M24 20 l-6 8"/></g><circle cx="24" cy="20" r="4.5" fill="none" stroke="#efca63" stroke-width="2.4"/><path d="M18 14 a6 6 0 0 1 12 0" fill="#efca63" stroke="none" opacity=".7"/>'],
  coc:["#1f5236","#123022",'<g fill="none" stroke="#fff" stroke-linecap="round"><path d="M12 18 L20 26 L32 14 M16 34 h20 M14 30 q6 5 12 0 M26 10 a4 4 0 0 1 0 8 a4 4 0 0 1 0 -8" stroke-width="2.4"/></g><circle cx="24" cy="24" r="12" fill="none" stroke="#efca63" stroke-width="1.6" stroke-dasharray="2 3"/><circle cx="38" cy="35" r="2.6" fill="#efca63"/>'],
};
function gArt(name,size){
  const a=GART[name]||GART.guess_number,s=size||48;
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+s+'" height="'+s+'" viewBox="0 0 48 48">'
    +'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    +'<stop offset="0" stop-color="'+a[0]+'"/><stop offset="1" stop-color="'+a[1]+'"/>'
    +'</linearGradient></defs>'
    +'<rect width="48" height="48" rx="10" fill="url(#g)"/>'+a[2]+'</svg>';
  return "data:image/svg+xml;utf8,"+encodeURIComponent(svg);
}
function gImg(name,size){
  const i=document.createElement("img");i.src=gArt(name,size);
  i.width=size;i.height=size;i.alt="";
  i.style.cssText="border-radius:10px;display:inline-block;vertical-align:middle;flex:0 0 auto;box-shadow:var(--shadow-sm)";
  return i;
}
function gTitle(gname,txt){                 // 对局内标题条：渐变底 + 游戏图标 + 文案
  const a=GART[gname];
  const d=document.createElement("div");
  d.style.cssText="display:flex;align-items:center;gap:8px;border-radius:10px;padding:8px 12px;margin-bottom:8px;color:#fff;background:linear-gradient(135deg,"+(a?a[0]:"#888")+","+(a?a[1]:"#666")+")";
  d.appendChild(gImg(gname,24));
  const t=document.createElement("span");t.style.cssText="font-weight:700;font-size:14px";t.textContent=txt;
  d.appendChild(t);return d;
}
const UNO_COLOR_CN={red:"红",yellow:"黄",green:"绿",blue:"蓝"};
function gnick(u){if(state.gnicks[u])return state.gnicks[u];
  const r=(state.roster||[]).find(x=>x.uid===u);return r?(r.nick||("玩家"+u)):("玩家"+u)}
function scoreHTML(sc){return "🏆 "+Object.entries(sc||{}).map(([u,v])=>esc(gnick(+u))+" "+v).join("　")}
function gameAPI(op,extra,quiet){
  const b=Object.assign({token:state.token,op:op},extra||{});
  const rid=extra&&extra.room_id,reentry=(op==="join"||op==="spectate")&&rid;
  const wasLeft=reentry&&state.gleft[rid];
  if(reentry)delete state.gleft[rid];       // SSE 状态可能先于 HTTP 回应到达。
  const restore=()=>{if(wasLeft&&state.token===b.token
      &&!(state.gst&&state.gst.room&&state.gst.room.room_id===rid
        &&((state.gst.room.players||[]).includes(state.uid)
          ||(state.gst.room.spectators||[]).includes(state.uid))))state.gleft[rid]=true;};
  return fetch("/api/game",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b)}).then(r=>r.json())
    .then(d=>{if(!d.ok){restore();if(!quiet)showStatus(d.error||"操作失败");}return d})
    .catch(e=>{restore();throw e});}
function renderGames(){                        // 侧栏房间速览
  const box=$("#games");if(!box)return;box.innerHTML="";
  if(!(state.grooms||[]).length){
    box.innerHTML="<div class='item' style='color:var(--dim)'>暂无房间，点 🎮 开局</div>";return}
  state.grooms.forEach(r=>{
    const m=state.gmeta[r.game]||{};
    const st={created:"等待",playing:"对局中",ended:"已结束"}[r.status]||r.status;
    const d=document.createElement("div");d.className="item";
    d.innerHTML="🎮 "+esc(m.label||r.game)+"（"+esc(r.room_id)+"）"
      +"<span style='color:var(--dim);font-size:10px'> "+st+" "+(r.players||[]).length+"人</span>";
    const inR=(r.players||[]).includes(state.uid)||(r.spectators||[]).includes(state.uid);
    d.onclick=()=>{if(!inR&&r.status==="created")gameAPI("join",{room_id:r.room_id});
      openGamePanel(r.room_id)};
    box.appendChild(d);});
}
// ---- 大厅 ----
function gameLobby(){
  uxSelectNavigation('game');
  state.globbyOpen=true;
  let m=$("#globby");if(m)m.remove();
  m=document.createElement("div");m.id="globby";
  m.style.cssText="position:fixed;inset:0;background:rgba(90,70,50,.5);display:flex;align-items:center;justify-content:center;z-index:98";
  const c=document.createElement("div");
  c.style.cssText="background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:28px 28px 28px 14px;padding:18px;width:min(740px,94vw);max-height:88vh;overflow:auto;box-shadow:var(--shadow-lg),0 0 0 6px rgba(255,209,102,.12)";
  c.innerHTML="<div style='font-weight:900;font-size:17px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;color:#3d3a54'>"
    +"<span>🃏 桌游小屋 <span style='font-size:11px;color:var(--dim);font-weight:500'>—— 摸鱼开一局</span></span>"
    +"<span style='cursor:pointer;font-size:15px' onclick='closeLobby()' title='关闭'>✕</span></div>"
    +"<div class='gsec'>🎲 游戏列表（点击卡片创建房间）</div><div id='glGames'></div>"
    +"<div style='height:12px'></div><div class='gsec'>🕹 进行中的房间</div><div id='glRooms'></div>";
  m.appendChild(c);document.body.appendChild(m);
  m.onclick=e=>{if(e.target===m)closeLobby()};
  fetch("/api/game_list").then(r=>r.json()).then(d=>{
    if(d.ok){state.gmeta={};(d.games||[]).forEach(g=>state.gmeta[g.name]=g);
      state.grooms=d.rooms||[];renderLobby();renderGames();}}).catch(()=>{});
  renderLobby();
}
function closeLobby(){state.globbyOpen=false;const m=$("#globby");if(m)m.remove();uxSelectNavigation('chat')}
function renderLobby(){
  const gb=$("#glGames");if(!gb)return;
  gb.innerHTML="";
  const grid=document.createElement("div");
  grid.style.cssText="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px";
  Object.entries(state.gmeta).forEach(([name,g])=>{
    const pastels=[["#ffe3b8","#ffd0a3"],["#ffd6e0","#ffc1cf"],["#d8e0ff","#c3cfff"],["#cceee0","#b0e6cf"],["#fff0b8","#ffe29a"],["#e8dcff","#d8c7ff"],["#ffdfc2","#ffc9a6"],["#cfeeff","#bbe0ff"]];
    const art=GART[name]||[];
    const pi=(name.length||0)%pastels.length;
    const cover=art.length?art:pastels[pi];
    const grad="linear-gradient(135deg,"+cover[0]+","+cover[1]+")";
    const c=document.createElement("div");c.className="gcard";
    c.innerHTML="<div style='height:52px;border-radius:16px 16px 16px 7px;margin:-12px -12px 8px;display:flex;align-items:center;justify-content:center;background:"+grad+"'>"
      +"<img src='"+gArt(name,30)+"' width='30' height='30' style='border-radius:10px;box-shadow:0 2px 6px rgba(120,80,40,.35);background:#fff' alt=''></div>"
      +"<b style='font-size:14px;color:#3d3a54'>"+esc(g.label||name)+"</b>"
      +"<span style='color:var(--dim);font-size:11px'>"+esc(g.desc||"")+"</span>"
      +"<span style='color:var(--dim);font-size:10px'>👥 "+g.min+"~"+(g.max||"∞")+" 人</span>";
    const b=document.createElement("button");b.className="gbtn go";b.textContent="创建房间";
    b.onclick=()=>{gameAPI("create",{game:name});closeLobby()};
    c.appendChild(b);grid.appendChild(c);});
  gb.appendChild(grid);
  const rb=$("#glRooms");rb.innerHTML="";
  if(!(state.grooms||[]).length){rb.innerHTML="<div style='color:var(--dim);font-size:12px'>暂无房间</div>";return}
  state.grooms.forEach(r=>{
    const m=state.gmeta[r.game]||{};
    const inR=(r.players||[]).includes(state.uid)||(r.spectators||[]).includes(state.uid);
    const st=inR?"你已在内":({created:"等待开局面 "+(r.players||[]).length+" 人",
      playing:"对局中 · 观战 "+(r.spectators||[]).length+" 人",ended:"已结束"}[r.status]||r.status);
    const row=document.createElement("div");
    row.style.cssText="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line,#eee);font-size:12px";
    row.innerHTML="<span>"+(GICON[r.game]||"🎮")+" <b>"+esc(m.label||r.game)+"</b>（"+esc(r.room_id)+"）</span>"
      +"<span style='color:var(--dim)'>"+st+"</span>";
    const b=document.createElement("button");b.className="gbtn";
    b.textContent=inR?"进入":(r.status==="created"?"加入":"观战");
    b.onclick=()=>{if(!inR)gameAPI(r.status==="created"?"join":"spectate",{room_id:r.room_id});
      closeLobby();openGamePanel(r.room_id)};
    row.appendChild(b);rb.appendChild(row);});
}
// ---- 房间面板 ----
function openGamePanel(rid){uxSelectNavigation('game');
  const isNew=state.groom!==rid;
  state.groom=rid;if(isNew){state.glog=[]}
  if(isNew)gameAPI("sync",{room_id:rid},true);   // R49：重进/刷新后补拉一次状态
  let p=$("#gpanel");if(p)p.remove();
  p=document.createElement("div");p.id="gpanel";
  const c=document.createElement("div");c.className="card";
  c.innerHTML="<div id='ghead'></div><div id='gmain'></div>"
    +"<div id='gpriv' style='display:none'></div><div id='glog'></div>";
  p.appendChild(c);document.body.appendChild(p);
  p.onclick=e=>{if(e.target===p)hideGamePanel()};
  renderGamePanel();
}
function hideGamePanel(){uxSelectNavigation('chat');state.groom=null;state.gst=null;state.gpriv=null;state.glog=[];
  const p=$("#gpanel");if(p)p.remove()}
function gHeadBtn(txt,fn){const b=document.createElement("button");b.className="gbtn";b.textContent=txt;b.onclick=fn;return b}
function gBtn(txt,act,dis){const b=document.createElement("button");b.className="gbtn";b.textContent=txt;
  if(dis||!state.gst||!state.gst.room||state.gst.room.status!=="playing")b.disabled=true;
  else b.onclick=()=>gameAPI("action",{room_id:state.groom,action:act});return b}
function gLog(line){const box=$("#glog");if(!box)return;
  const d=document.createElement("div");d.className="glogl";d.textContent=line;
  box.appendChild(d);box.scrollTop=box.scrollHeight}
function renderGamePanel(){
  const p=$("#gpanel");if(!p||!state.groom)return;
  const head=$("#ghead");head.innerHTML="";
  const st=state.gst,room=st?st.room:null;
  const gname=room?room.game:"";
  const meta=state.gmeta[gname]||{};
  const title=document.createElement("span");title.style.cssText="display:flex;align-items:center;gap:6px";
  if(room){title.appendChild(gImg(gname,20));}
  title.appendChild(document.createTextNode(room?((meta.label||gname)+" · "+room.room_id+" · "
    +({created:"等待中",playing:"对局中",ended:"已结束"}[room.status]||room.status)):"已离开房间…"));
  head.appendChild(title);
  const sp=document.createElement("span");sp.style.flex="1";head.appendChild(sp);
  if(room){
    if(room.status==="created"&&room.owner_uid===state.uid)
      head.appendChild(gHeadBtn("▶ 开始对局",()=>gameAPI("start",{room_id:room.room_id})));
    head.appendChild(gHeadBtn("🚪 离开",()=>gameAPI("leave",{room_id:room.room_id},true)));
  }
  head.appendChild(gHeadBtn("✕",hideGamePanel));
  const lb=$("#glog");lb.innerHTML="";(state.glog||[]).forEach(gLog);
  const main=$("#gmain"),priv=$("#gpriv");
  main.innerHTML="";priv.style.display="none";priv.innerHTML="";
  if(!room)return;
  main.inert=room.status==="ended";
  if(room.status!=="playing"&&room.status!=="ended"){
    main.innerHTML="<div style='padding:24px;text-align:center'>"
      +(room.status==="created"
        ?"👥 "+(room.players||[]).map(u=>esc(gnick(u))).join("、")+"<br><br>⏳ 等待房主开始…（至少 "
          +(meta.min||2)+" 人，其余可观战）"
        :"🏁 本局结束，3 秒后自动回到房间")+"</div>";
    return;}
  const s=st.state;
  if(!s){main.textContent="等待状态…";return}
  const fn=GRENDER[gname];
  if(fn)fn(main,s);else main.textContent="暂不支持的游戏渲染";
  if(room.status==="ended"){
    main.querySelectorAll("button,input,select").forEach(e=>e.disabled=true);
    const note=document.createElement("div");note.className="gsec";
    note.textContent="🏁 本局结束，3 秒后自动回到房间";main.prepend(note);return;}
  const pv=state.gpriv;if(pv){
    const bits=[];
    if(pv.hand)bits.push("🂠 你的手牌："+pv.hand.join(" "));
    if(gname==="spy")bits.push("🎭 身份："+(pv.role==="spy"?"卧底":"平民")+" · 词："+esc(pv.word));
    if(pv.hint)bits.push(esc(pv.hint));
    if(pv.stats&&gname==="betrayal"){
      bits.push("💪 力量"+pv.stats.might+"　🏃 速度"+pv.stats.speed
        +"　🧠 理智"+pv.stats.sanity+"　📚 知识"+pv.stats.knowledge);
      bits.push("🎒 道具："+(((pv.items||[]).join("、"))||"无")+"　📍 "+esc(pv.room||"")
        +"("+pv.pos+")　阵营："+(pv.side==="traitor"?"叛徒":"幸存者"));}
    if(pv.card&&gname==="coc"){      // COC：自己的调查员卡（属性+技能）
      const c=pv.card,a=c.attrs||{},sg=c.sig||{};
      bits.push("🔰 你："+c.emoji+c.name);
      bits.push("属性："+Object.keys(a).map(k=>k+a[k]).join(" "));
      bits.push("技能："+Object.keys(sg).map(k=>k+sg[k]).join(" "));}
    if(bits.length){priv.innerHTML=bits.join("<br>");priv.style.display=""}}
}
// ---- 各游戏渲染器（s = game_state.state）----
const GRENDER={
  guess_number(box,s){
    const d=document.createElement("div");d.style.cssText="text-align:center;padding:6px";
    d.innerHTML="<div class='gsec'>第 "+s.round+" 轮 · 出题 "+esc(gnick(s.owner_uid))+"</div>"
      +(s.secret!=null?"<div>答案揭晓：<b>"+s.secret+"</b></div>"
        :"<div style='font-size:22px;font-weight:700;margin:8px'>"+s.low+" ~ "+s.high+"</div>")
      +(s.last_guess?"<div style='color:var(--dim)'>"+esc(gnick(s.last_guess.uid))+" 猜 "
        +s.last_guess.val+"："+({low:"低了",high:"高了",hit:"🎉 猜中！"}[s.last_guess.dir]||"")+"</div>":"")
      +"<div style='margin-top:8px'>"+scoreHTML(s.scores)+"</div>";
    box.appendChild(d);
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;justify-content:center;margin:8px";
    const inp=document.createElement("input");inp.type="number";
    inp.style.cssText="width:110px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 8px";
    if(s.status==="await_secret"&&s.owner_uid===state.uid){
      const b=document.createElement("button");b.className="gbtn";b.textContent="🎲 出题";
      b.onclick=()=>{const v=parseInt(inp.value);
        if(v>=1&&v<=100)gameAPI("action",{room_id:state.groom,action:{secret:v}});
        else showStatus("请输入 1~100")};
      bar.append(inp,b);}
    else if(s.status==="playing"){
      const b=document.createElement("button");b.className="gbtn";b.textContent="猜！";
      b.onclick=()=>{const v=parseInt(inp.value);
        if(v>=s.low&&v<=s.high)gameAPI("action",{room_id:state.groom,action:{guess:v}});
        else showStatus("数字须在 "+s.low+"~"+s.high)};
      bar.append(inp,b);}
    else bar.innerHTML="<span style='color:var(--dim);font-size:12px'>下一轮即将开始…</span>";
    box.appendChild(bar);
  },
  gomoku(box,s){
    const n=s.board.length,cell=24,pad=12,W=n*cell+pad*2;
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:4px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :(s.draw?"平局":"轮到 "+esc(gnick(s.turn_uid))+(s.turn_uid===state.uid?"（你执子）":"")));
    box.appendChild(info);
    const cv=document.createElement("canvas");cv.width=W;cv.height=W;
    cv.style.cssText="display:block;margin:0 auto;background:#d9a45b;border-radius:6px;cursor:pointer";
    box.appendChild(cv);
    const ctx=cv.getContext("2d");
    ctx.strokeStyle="#6b4a1b";
    for(let i=0;i<n;i++){
      ctx.beginPath();ctx.moveTo(pad+i*cell,pad);ctx.lineTo(pad+i*cell,W-pad);ctx.stroke();
      ctx.beginPath();ctx.moveTo(pad,pad+i*cell);ctx.lineTo(W-pad,pad+i*cell);ctx.stroke();}
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){const v=s.board[y][x];if(!v)continue;
      ctx.beginPath();ctx.arc(pad+x*cell,pad+y*cell,cell*0.42,0,7);
      ctx.fillStyle=v===1?"#111":"#fff";ctx.fill();ctx.stroke();}
    if(s.last_move){ctx.beginPath();
      ctx.arc(pad+s.last_move[0]*cell,pad+s.last_move[1]*cell,3,0,7);
      ctx.fillStyle="#e33";ctx.fill();}
    if(s.winner_uid==null&&!s.draw)
      cv.onclick=e=>{const r=cv.getBoundingClientRect();
        const x=Math.round((e.clientX-r.left-pad)/cell),y=Math.round((e.clientY-r.top-pad)/cell);
        if(x<0||y<0||x>=n||y>=n)return;
        gameAPI("action",{room_id:state.groom,action:{x:x,y:y}});};
  },
  connect4(box,s){
    const rows=s.board.length,cols=s.board[0].length;
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :(s.draw?"平局":"轮到 "+esc(gnick(s.turn_uid))))+"　"+scoreHTML(s.scores||{});
    box.appendChild(info);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+cols+",1fr);gap:4px;max-width:420px;margin:0 auto";
    for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
      const c=document.createElement("div");c.className="gcell";
      c.style.borderRadius="50%";c.style.justifyContent="center";
      const v=s.board[y][x];
      c.style.background=v===1?"#e05555":(v===2?"#4a7de0":"");
      if(!v)c.textContent="·";
      c.onclick=()=>{if(s.winner_uid!=null||s.draw)return;
        gameAPI("action",{room_id:state.groom,action:{col:x}})};
      grid.appendChild(c);}
    box.appendChild(grid);
  },
  othello(box,s){
    const n=s.board.length;
    const vals=s.scores?Object.values(s.scores):null;
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :(s.passing?"对手无处可落，让过":"轮到 "+esc(gnick(s.turn_uid))))
      +(vals?"　⚫ "+vals[0]+"　⚪ "+vals[1]:"");
    box.appendChild(info);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+n+",36px);gap:2px;max-width:340px;margin:0 auto";
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const c=document.createElement("div");c.className="gcell";c.style.borderRadius="4px";
      const v=s.board[y][x];c.textContent=v===1?"⚫":(v===2?"⚪":"·");
      if(s.winner_uid==null)
        c.onclick=()=>gameAPI("action",{room_id:state.groom,action:{x:x,y:y}});
      grid.appendChild(c);}
    box.appendChild(grid);
  },
  rps(box,s){
    const d=document.createElement("div");d.style.cssText="text-align:center;padding:6px";
    const total=(s.players||[]).length,did=(s.submitted||[]).length;
    d.innerHTML="<div class='gsec'>第 "+s.round+" 轮 · 已出拳 "+did+"/"+total+"</div>"
      +"<div style='margin-top:6px'>"+scoreHTML(s.scores)+"</div>";
    box.appendChild(d);
    if((s.submitted||[]).includes(state.uid)){
      const w=document.createElement("div");w.style.cssText="text-align:center;color:var(--dim);font-size:12px";
      w.textContent="✅ 已出拳，等待揭晓…";box.appendChild(w);}
    else if(s.status==="collecting"&&(s.players||[]).includes(state.uid)){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:8px;justify-content:center;margin:10px";
      [["✊ 石头",0],["✋ 布",1],["✌️ 剪刀",2]].forEach(([t,c])=>bar.appendChild(gBtn(t,{choice:c})));
      box.appendChild(bar);}
    if((s.matches||[]).length){
      const t=document.createElement("div");t.style.marginTop="8px";t.style.fontSize="12px";
      t.innerHTML="<div class='gsec'>本轮对战</div>"+s.matches.map(m=>{
        const nm=v=>v===-1?"未出拳":["✊","✋","✌️"][v];
        return "<div class='glogl'>"+esc(gnick(m.a))+" "+nm(m.ca)+" vs "+esc(gnick(m.b))+" "+nm(m.cb)
          +(m.winner===-1||m.winner==null?" → 平局":" → "+esc(gnick(m.winner))+" 胜")+"</div>";}).join("")
        +((s.byes||[]).length?"<div class='glogl'>"+s.byes.map(u=>esc(gnick(u))).join("、")+" 轮空</div>":"");
      box.appendChild(t);}
  },
  spy(box,s){
    const d=document.createElement("div");d.style.cssText="padding:4px";
    const alive=s.alive||[];
    d.innerHTML="<div class='gsec'>存活 "+alive.length+" 人 · 阶段："+({describing:"轮流描述",voting:"投票中",
      checking:"唱票",reveal:"揭晓",dealing:"发牌"}[s.status]||s.status)+"</div>"
      +(s.speaker_uid?"<div>🎤 发言："+esc(gnick(s.speaker_uid))+"</div>":"")
      +(s.spy_uid!=null?"<div>🕵️ 卧底是 "+esc(gnick(s.spy_uid))+"</div>":"")
      +(s.winner_uid!=null?"<div>🏆 "+esc(gnick(s.winner_uid))+" 阵营胜</div>":"");
    box.appendChild(d);
    (s.describes||[]).forEach(x=>gLog("💬 "+gnick(x.uid)+"："+x.text));
    if(s.status==="describing"&&s.speaker_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;margin:8px 0";
      const inp=document.createElement("input");inp.placeholder="描述你的词（别说破）";
      inp.style.cssText="flex:1;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 8px";
      const b=document.createElement("button");b.className="gbtn";b.textContent="发言";
      b.onclick=()=>{const t=inp.value.trim();if(t)gameAPI("action",{room_id:state.groom,action:{describe:t}})};
      bar.append(inp,b);box.appendChild(bar);}
    if(s.status==="voting"){
      const voted=s.voted||[];
      const w=document.createElement("div");w.className="gsec";
      w.textContent="投票（已投 "+voted.length+" 人）"+(voted.includes(state.uid)?"　✅ 你已投票":"");box.appendChild(w);
      if(!voted.includes(state.uid)&&alive.includes(state.uid)){
        const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap";
        alive.forEach(u=>{if(u!==state.uid)bar.appendChild(gBtn("投 "+gnick(u),{vote:u}))});
        box.appendChild(bar);}}
    if(s.vote_counts&&Object.keys(s.vote_counts).length){
      const t=document.createElement("div");t.style.fontSize="12px";t.style.marginTop="6px";
      t.innerHTML="<div class='gsec'>票数</div>"+Object.entries(s.vote_counts)
        .map(([u,v])=>esc(gnick(+u))+"："+v+" 票").join("　");box.appendChild(t);}
    box.appendChild(Object.assign(document.createElement("div"),
      {innerHTML:"<div class='gsec'>积分</div>"+scoreHTML(s.scores)}));
  },
  onewolf(box,s){
    const me=state.uid, pv=state.gpriv;
    const ph={night:"🌙 夜晚行动",vote:"🗳️ 投票处决",result:"🏁 揭晓"}[s.phase]||s.phase;
    const d=document.createElement("div");d.style.cssText="padding:4px";
    const bits=[];
    if(pv&&pv.name){
      bits.push("🎭 你的身份："+pv.name+(pv.origin&&pv.origin!==pv.name?"（初始："+pv.origin+"）":""));
      if(pv.role===1)bits.push("🐺 狼队友："+((pv.teammates||[]).map(gnick).join("、")||"仅你一人"));
      if(pv.seer_view)bits.push("🔮 看到 "+gnick(pv.seer_view.uid)+" 是 "+pv.seer_view.name);
      if(pv.seer_center)bits.push("🔮 中心两张："+pv.seer_center.role_a+" / "+pv.seer_center.role_b);
      if(pv.robbed_role)bits.push("🗡️ 换牌后你的身份："+pv.robbed_role);
    }
    d.innerHTML="<div class='gsec'>阶段："+ph+" · "+s.players.length+" 人</div>"
      +(bits.length?"<div style='margin:6px 0'>"+bits.join("<br>")+"</div>":"")
      +(s.acted&&s.acted.length?"<div style='color:var(--dim);font-size:11px'>已行动："+s.acted.map(gnick).join("、")+"</div>":"");
    box.appendChild(d);
    const acting=()=>pv&&!s.acted.includes(me);
    if(s.phase==="night"&&acting()&&pv.role===2){          // 预言家
      const w=document.createElement("div");w.className="gsec";w.textContent="🔮 预言家：偷看一人或中心两张";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      s.players.forEach(u=>{if(u!==me)bar.appendChild(gBtn("看 "+gnick(u),{op:"peek",look_one:u}))});
      bar.appendChild(gBtn("看中心两张",{op:"peek",look_center:[0,1]}));
      box.appendChild(bar);}
    if(s.phase==="night"&&acting()&&pv.role===3){          // 强盗
      const w=document.createElement("div");w.className="gsec";w.textContent="🗡️ 强盗：与一位玩家交换身份";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      s.players.forEach(u=>{if(u!==me)bar.appendChild(gBtn("换 "+gnick(u),{op:"swap",rob:u}))});
      box.appendChild(bar);}
    if(s.phase==="vote"&&(s.players||[]).includes(me)&&!(s.voted||[]).includes(me)){
      const w=document.createElement("div");w.className="gsec";
      w.textContent="⚖️ 投票处决（已投 "+(s.voted||[]).length+" 人）";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      s.players.forEach(u=>{if(u!==me)bar.appendChild(gBtn("处决 "+gnick(u),{op:"vote",target:u}))});
      box.appendChild(bar);}
    if(s.dead&&s.dead.length){
      const t=document.createElement("div");t.style.cssText="margin-top:6px;font-weight:700";
      t.textContent="⚖️ 被处决："+s.dead.map(gnick).join("、");box.appendChild(t);}
    if(s.phase==="result"){
      const r=document.createElement("div");r.style.cssText="margin-top:6px";
      r.innerHTML="<div class='gsec'>身份揭晓</div>"+s.players.map(u=>
        esc(gnick(u))+"："+(s.reveal?s.reveal[u]:"?")).join("<br>");box.appendChild(r);
      const w=document.createElement("div");w.style.cssText="margin-top:8px;font-weight:800;font-size:15px";
      w.textContent=s.winner?"🎉 好人获胜！":"🐺 狼人获胜！";box.appendChild(w);}
  },
  werewolf(box,s){
    const me=state.uid, pv=state.gpriv;
    const phm={night_seer:"🔮 预言家验人",night_wolf:"🐺 狼人刀人",night_witch:"🧪 女巫用药",
      shoot:"🏹 猎人开枪",day:"☀️ 白天投票",done:"🏁 已结束"};
    const ph=phm[s.phase]||s.phase;
    const d=document.createElement("div");d.style.cssText="padding:4px";
    const alive=s.alive||[], voted=s.voted||[];
    const bits=[];
    if(pv&&pv.name){
      bits.push("🎭 你的身份："+pv.name+(pv.role===1&&pv.teammates&&pv.teammates.length
        ?"　🐺队友："+pv.teammates.map(gnick).join("、"):""));
      if(pv.seer_view)bits.push("🔮 查验 "+gnick(pv.seer_view.target)+" 是 "+pv.seer_view.name);
      if(pv.witch_kill)bits.push("🩸 本晚将被刀："+gnick(pv.witch_kill));
      if(pv.saved_by_witch)bits.push("🧪 你被女巫用解药救活了");
    }
    d.innerHTML="<div class='gsec'>第 "+s.night+" 夜 · "+ph+" · 存活 "+alive.length+" 人</div>"
      +(bits.length?"<div style='margin:6px 0'>"+bits.join("<br>")+"</div>":"");
    box.appendChild(d);
    const actneed=()=>pv&&(s.need||[]).includes(me)&&!(s.acted||[]).includes(me);
    const av=alive.filter(u=>u!==me);
    if(actneed()&&s.phase==="night_seer"){            // 预言家
      const w=document.createElement("div");w.className="gsec";w.textContent="🔮 查验一位玩家";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      av.forEach(u=>bar.appendChild(gBtn("验 "+gnick(u),{target:u})));
      box.appendChild(bar);}
    if(actneed()&&s.phase==="night_wolf"){            // 狼人
      const w=document.createElement("div");w.className="gsec";w.textContent="🐺 选择今晚刀杀的玩家";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      av.forEach(u=>bar.appendChild(gBtn("刀 "+gnick(u),{target:u})));
      box.appendChild(bar);}
    if(actneed()&&s.phase==="night_witch"){           // 女巫
      const w=document.createElement("div");w.className="gsec";w.textContent="🧪 是否用解药/毒药";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      bar.appendChild(gBtn("💊 用解药",{op:"save"}));
      av.forEach(u=>bar.appendChild(gBtn("☠️ 毒 "+gnick(u),{op:"poison",target:u})));
      box.appendChild(bar);}
    if(actneed()&&s.phase==="shoot"){                 // 猎人开枪
      const w=document.createElement("div");w.className="gsec";w.textContent="🏹 开枪带走一人";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      av.forEach(u=>bar.appendChild(gBtn("带走 "+gnick(u),{target:u})));
      box.appendChild(bar);}
    if(s.phase==="day"&&alive.includes(me)&&!voted.includes(me)){
      const w=document.createElement("div");w.className="gsec";
      w.textContent="⚖️ 投票放逐（已投 "+voted.length+" 人）";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      av.forEach(u=>bar.appendChild(gBtn("放逐 "+gnick(u),{target:u})));
      bar.appendChild(gBtn("弃票",{op:"pass"}));
      box.appendChild(bar);}
    if(s.lynched){const t=document.createElement("div");t.style.cssText="margin-top:6px;font-weight:700";
      t.textContent="⚖️ 被放逐："+gnick(s.lynched);box.appendChild(t);}
    if(s.done){const t=document.createElement("div");t.style.cssText="margin-top:8px;font-weight:800;font-size:15px";
      t.textContent=s.winner?"🎉 好人获胜！":"🐺 狼人获胜！";box.appendChild(t);}
  },
  avalon(box,s){
    const me=state.uid, pv=state.gpriv;
    const phm={nominate:"👑 领袖组队",teamvote:"🗳️ 团队投票",quest:"🃏 执行任务",final:"🎯 刺客指认",done:"🏁 已结束"};
    const ph=phm[s.phase]||s.phase;
    const d=document.createElement("div");d.style.cssText="padding:4px";
    const results=(s.results||[]).map(r=>r?"✅":"💥").join("");
    const team=s.team||[], av=(s.players||[]).filter(u=>!team.includes(u));
    const bits=[];
    if(pv&&pv.name){
      bits.push("🎭 你的身份："+pv.name+(pv.role===1?"（知晓叛军，务必隐藏！）":""));
      if((pv.role===2||pv.role===3)&&pv.evil)bits.push("🌑 叛军："+pv.evil.map(u=>esc(gnick(u))).join("、"));
      if(pv.role===3)bits.push("🗡️ 你是刺客：终局指认梅林");
    }
    d.innerHTML="<div class='gsec'>任务 "+s.quest+"/5 · "+ph+" · 需 "+s.need_size+" 人</div>"
      +"<div>结果："+(results||"—")+"</div>"
      +(bits.length?"<div style='margin:6px 0'>"+bits.join("<br>")+"</div>":"")
      +(team.length?"<div>📋 当前团队："+team.map(gnick).join("、")+"</div>":"");
    box.appendChild(d);
    const acting=()=>pv&&(s.need||[]).includes(me)&&!(s.acted||[]).includes(me);
    if(acting()&&s.phase==="nominate"){              // 领袖提团队
      const w=document.createElement("div");w.className="gsec";
      w.textContent="选择 "+s.need_size+" 名成员组成任务团队";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      (s.players||[]).forEach(u=>{
        const b=gBtn("选 "+gnick(u),{});b.dataset.u=u;
        b.onclick=()=>{ sel[b.dataset.u]=!sel[b.dataset.u]; b.textContent=(sel[b.dataset.u]?"✅ ":"选 ")+gnick(u); };
        bar.appendChild(b);});
      const sel={};
      const ok=document.createElement("button");ok.className="gbtn";ok.textContent="确定组队";
      ok.style.cssText="margin:4px 6px 0 auto;display:block";
      ok.onclick=()=>{const t=Object.keys(sel).filter(u=>sel[u]).map(Number);
        if(t.length===s.need_size)gameAPI("action",{room_id:state.groom,action:{team:t}});
        else showStatus("需选 "+s.need_size+" 人");};
      bar.appendChild(ok);box.appendChild(bar);}
    if(acting()&&s.phase==="teamvote"){               // 赞同/反对
      const w=document.createElement("div");w.className="gsec";
      w.textContent="该团队是否通过？（已投 "+(s.voted||[]).length+" 人）";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;margin:4px 0";
      bar.appendChild(gBtn("✅ 通过",{approve:true}));
      bar.appendChild(gBtn("❌ 否决",{approve:false}));
      box.appendChild(bar);}
    if(acting()&&s.phase==="quest"){                  // 任务成功/失败
      const w=document.createElement("div");w.className="gsec";w.textContent="秘密执行任务（秘密）";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;margin:4px 0";
      bar.appendChild(gBtn("✅ 成功",{success:true}));
      if(pv&&(pv.role===2||pv.role===3))bar.appendChild(gBtn("💥 失败",{success:false}));
      box.appendChild(bar);}
    if(acting()&&s.phase==="final"){                  // 刺客指认梅林
      const w=document.createElement("div");w.className="gsec";w.textContent="🎯 谁是梅林？指认一人";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      (s.players||[]).forEach(u=>{if(u!==me)bar.appendChild(gBtn("指认 "+gnick(u),{op:"guess",target:u},false))});
      box.appendChild(bar);}
    if(s.leader&&s.phase!=="final"){const t=document.createElement("div");t.style.cssText="margin-top:6px;color:var(--dim);font-size:12px";
      t.textContent="👑 当前领袖："+gnick(s.leader);box.appendChild(t);}
    if(s.done){const t2=document.createElement("div");t2.style.cssText="margin-top:8px;font-weight:800;font-size:15px";
      t2.textContent=s.winner?"🎉 好人（梅林阵营）获胜！":"🗡️ 坏人阵营获胜！";box.appendChild(t2);}
  },
  liar(box,s){
    const me=state.uid, pv=state.gpriv;
    const isMe=s.turn===me;
    const d=document.createElement("div");d.style.cssText="padding:4px";
    const pend=s.pending;
    const drink=Object.entries(s.drink||{}).map(([u,c])=>esc(gnick(+u))+" 喝了 "+c+"杯").join("　");
    d.innerHTML="<div class='gsec'>🎲 骗子酒馆 · "+(isMe?"轮到你了":"轮到 "+esc(gnick(s.turn)))+"</div>"
      +(pend?"<div>🃏 最新：<b>"+esc(gnick(pend.uid))+"</b> 报数 <b>"+pend.claim+"</b>（真值保密）</div>"
            :"<div>🃏 桌面空，先出牌</div>")
      +"<div style='margin:6px 0'>"+drink+"</div>"
      +"<div style='color:var(--dim);font-size:12px'>手牌量："+
      Object.entries(s.hand_size||{}).map(([u,c])=>esc(gnick(+u))+"×"+c).join("　")+"</div>";
    box.appendChild(d);
    if(pv&&pv.hand){
      const w=document.createElement("div");w.className="gsec";w.textContent="你的手牌（选一张并报数，可虚报）";
      box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      // 每个手牌值一个按钮，点击后进入报数选择
      const sel=document.createElement("div");sel.className="gsec";
      pv.hand.forEach(v=>{
        const b=document.createElement("button");b.className="gbtn";b.textContent=String(v);
        b.onclick=()=>{ // 选牌后展示报数选项
          const pre=prompt("报多少？（0~9，可虚报，真实牌面隐藏）",""+v);
          if(pre==null)return;
          const claim=parseInt(pre,10);
          if(isNaN(claim)||claim<0||claim>9){showStatus("报数需 0~9");return;}
          gameAPI("action",{room_id:state.groom,action:{op:"play",card:v,claim}});};
        bar.appendChild(b);});
      box.appendChild(bar);
      if(isMe&&pend&&pend.uid!==me)box.appendChild(gBtn("💥 挑战上一位",{op:"challenge"}));
    }
    if(s.done){const t=document.createElement("div");t.style.cssText="margin-top:8px;font-weight:800;font-size:15px";
      t.textContent="🏆 "+esc(gnick(s.winner))+" 最后留在桌上获胜！";box.appendChild(t);}
  },
  ninja(box,s){
    const me=state.uid, pv=state.gpriv;
    const alive=s.alive||[], hp=s.hp||{};
    const hpv=u=>hp[u]!==undefined?hp[u]:(hp[""+u]!==undefined?hp[""+u]:0);
    const d=document.createElement("div");d.style.cssText="padding:4px";
    d.innerHTML="<div class='gsec'>🥷 忍者之夜 · 第 "+s.round+" 回合 · "+
      (s.phase==="pick"?"暗选行动中":"结算中")+"</div>"
      +"<div>存活："+alive.map(u=>esc(gnick(u))+"("+hpv(u)+"血)").join("　")+"</div>";
    box.appendChild(d);
    if(pv&&pv.hp!==undefined){const t=document.createElement("div");t.className="gsec";
      t.textContent="你的生命："+pv.hp+" / "+((pv.hp>1)?"🟢 状态良好":"🔴 濒危");box.appendChild(t);}
    const meAlive=alive.includes(me), submitted=(s.picked||[]).includes(me);
    if(s.phase==="pick"&&meAlive&&!submitted){
      const w=document.createElement("div");w.className="gsec";w.textContent="选择你的行动（保密）：";box.appendChild(w);
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
      // 攻击：选目标
      const a=document.createElement("button");a.className="gbtn";a.textContent="🗡️ 攻击";
      a.onclick=()=>{ // 展示目标选择
        const tb=document.createElement("div");tb.className="gsec";tb.textContent="选择攻击目标";
        alive.forEach(u=>{if(u!==me){const b=gBtn("攻 "+gnick(u),{op:"move",move:"attack",target:u});
          tb.appendChild(b);}});
        box.appendChild(tb);};
      bar.appendChild(a);
      bar.appendChild(gBtn("🛡️ 防御",{op:"move",move:"guard"}));
      box.appendChild(bar);}
    if(s.phase==="resolve"&&(s.last||[]).length){
      const r=document.createElement("div");r.className="gsec";
      r.innerHTML="<div style='font-weight:700'>⚡ 结算</div>"+(s.last||[]).map(l=>"<div>"+esc(l)+"</div>").join("");
      box.appendChild(r);
      if(!s.done)box.appendChild(gBtn("👉 进入下一回合",{op:"next"}));}
    if(s.done){const t=document.createElement("div");t.style.cssText="margin-top:8px;font-weight:800;font-size:15px";
      t.textContent="🏆 "+esc(gnick(s.winner))+" 是最后存活的忍者！";box.appendChild(t);}
  },
  uno(box,s){
    const my=state.uid,isMe=s.current_uid===my;
    const d=document.createElement("div");d.style.cssText="text-align:center;padding:4px";
    d.innerHTML="<div style='font-size:20px;font-weight:700;margin:6px'>"+esc(s.top||"")
      +(s.top_color?"<span style='font-size:12px;color:var(--dim)'>（当前色 "
        +(UNO_COLOR_CN[s.top_color]||s.top_color)+"）</span>":"")+"</div>"
      +"<div>方向 "+s.direction+" · 轮到 "+esc(gnick(s.current_uid))+(isMe?"（你）":"")+"</div>"
      +"<div style='color:var(--dim);font-size:11px;margin-top:2px'>"
      +Object.entries(s.hand_counts||{}).map(([u,c])=>esc(gnick(+u))+"×"+c).join("　")+"</div>"
      +"<div style='margin-top:4px'>"+scoreHTML(s.scores)+"</div>";
    box.appendChild(d);
    const p=state.gpriv;
    if(p&&p.hand&&isMe){
      const bar=document.createElement("div");bar.style.cssText="text-align:center;margin:8px";
      p.hand.forEach((cs,i)=>{
        const c=document.createElement("span");c.className="unocard";c.textContent=cs;
        const isWild=cs.indexOf("万能")===0;
        c.onclick=()=>{
          if(!isWild)gameAPI("action",{room_id:state.groom,action:{card:p.hand_ids[i]}});
          else{
            const cbar=box.querySelector(".wbar");
            if(cbar)cbar.remove();
            const sel=document.createElement("div");sel.className="wbar";
            sel.style.cssText="text-align:center;margin:4px";
            sel.innerHTML="<span style='font-size:11px;color:var(--dim)'>选颜色：</span>";
            ["red","yellow","green","blue"].forEach(cl=>{
              const b=document.createElement("button");b.className="gbtn";
              b.textContent=UNO_COLOR_CN[cl];
              b.onclick=()=>{sel.remove();
                gameAPI("action",{room_id:state.groom,action:{card:p.hand_ids[i],color:cl}})};
              sel.appendChild(b);});
            box.appendChild(sel);}};
        bar.appendChild(c);});
      box.appendChild(bar);
      const draw=document.createElement("div");draw.style.cssText="text-align:center;margin:6px";
      draw.appendChild(gBtn("🂠 摸牌",{draw:true}));
      box.appendChild(draw);}
    else if(p&&p.hand){
      const w=document.createElement("div");w.style.cssText="text-align:center;color:var(--dim);font-size:12px";
      w.textContent="你的手牌："+p.hand.join(" ");box.appendChild(w);}
    if(s.winner_uid!=null)
      box.appendChild(Object.assign(document.createElement("div"),
        {style:"text-align:center;margin-top:6px",innerHTML:"🏆 "+esc(gnick(s.winner_uid))+" 出完！"
          +(s.match_winner!=null?"　比赛冠军 "+esc(gnick(s.match_winner)):"")}));
  },
  blackjack(box,s){
    const handLine=u=>"牌值 "+(s.hand_values[u]||0);
    const d=document.createElement("div");d.style.cssText="padding:4px";
    d.innerHTML="<div class='gsec'>庄家："+(s.dealer||[]).join(" ")+"（"+s.dealer_value+"）</div>"
      +"<div style='font-size:12px'>"+Object.entries(s.hands||{}).map(([u,h])=>{
        const uid=+u;
        return "<div class='glogl'>"+(uid===state.uid?"<b>你</b>":esc(gnick(uid)))
          +"："+h.join(" ")+"（"+(s.hand_values[u]||0)+"）"
          +(s.current_uid===uid?" ⏳":(s.stand||[]).includes(uid)?" 🛑 已停":"")
          +(s.results[u]!=null?(" → "+({win:"✅ 胜",draw:"➖ 平",lose:"❌ 负"}[s.results[u]]||s.results[u])):"")+"</div>";}).join("")+"</div>";
    box.appendChild(d);
    if(s.status==="playing"&&s.current_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:8px;justify-content:center;margin:8px";
      bar.appendChild(gBtn("🃏 要牌",{action:"hit"}));bar.appendChild(gBtn("🛑 停牌",{action:"stand"}));
      box.appendChild(bar);}
    else box.appendChild(Object.assign(document.createElement("div"),
      {style:"text-align:center;color:var(--dim);font-size:12px",
       textContent:s.status==="playing"?"等待 "+gnick(s.current_uid)+" 操作…":"本局结束"}));
  },
  calc24(box,s){
    const d=document.createElement("div");d.style.cssText="text-align:center;padding:6px";
    d.innerHTML="<div style='font-size:22px;font-weight:700;margin:8px'>"+(s.cards||[]).join("　")+"</div>"
      +(s.status==="answering"?"<div style='color:var(--dim)'>剩余 "+s.wait+"s</div>"
        :(s.solved_uid?"<div>🎉 "+esc(gnick(s.solved_uid))+" 答对："+esc(s.win_expr||"")+"</div>":"下一轮即将开始…"))
      +"<div style='margin-top:6px'>"+scoreHTML(s.scores)+"</div>";
    box.appendChild(d);
    if(s.status==="answering"&&(s.players||[]).includes(state.uid)&&s.solved_uid==null){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;justify-content:center;margin:8px";
      const inp=document.createElement("input");inp.placeholder="如 (5-1/5)*5";
      inp.style.cssText="width:180px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 8px";
      const b=document.createElement("button");b.className="gbtn";b.textContent="作答";
      b.onclick=()=>{const t=inp.value.trim();if(t)gameAPI("action",{room_id:state.groom,action:{expr:t}})};
      inp.addEventListener("keydown",e=>{if(e.key==="Enter")b.click()});
      bar.append(inp,b);box.appendChild(bar);}
  },
  matchpairs(box,s){
    const d=document.createElement("div");d.style.cssText="padding:4px";
    d.innerHTML="<div class='gsec'>轮到 "+esc(gnick(s.turn_uid))+"</div>"
      +"<div style='font-size:12px'>"+Object.entries(s.hand_size||{}).map(([u,c])=>{
        const uid=+u;
        return "<div class='glogl'>"+(uid===state.uid?"<b>你</b>":esc(gnick(uid)))+"：剩 "+c+" 张"
          +((s.safe||[]).includes(uid)?"　✅ 安全":"")+"</div>";}).join("")+"</div>";
    box.appendChild(d);
    if(s.loser_uid!=null)
      box.appendChild(Object.assign(document.createElement("div"),
        {style:"text-align:center;margin:8px",innerHTML:"🐢 王八是 "+esc(gnick(s.loser_uid))}));
    else if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="text-align:center;margin:8px";
      bar.appendChild(gBtn("🂠 摸牌",{draw:true}));box.appendChild(bar);}
    const p=state.gpriv;
    if(p&&p.hand){const w=document.createElement("div");
      w.style.cssText="text-align:center;color:var(--dim);font-size:12px";
      w.textContent="你的手牌："+p.hand.join(" ");box.appendChild(w);}
  },
  betrayal(box,s){
    const my=state.uid;
    const d=document.createElement("div");d.style.cssText="padding:2px";
    d.innerHTML="<div class='gsec'>阶段："+({explore:"探索",haunt:"惊魂"}[s.phase]||s.phase)
      +" · 🔮 预兆 "+s.omens+" · 轮到 "+esc(gnick(s.turn_uid))+"（剩 "+s.steps_left+" 步）</div>"
      +"<div style='font-size:11px;color:var(--dim)'>💀 已死："
      +((s.dead||[]).map(u=>esc(gnick(u))).join("、")||"无")+"</div>";
    box.appendChild(d);
    // 地图：把 "x,y" 房间网格化；玩家落位显示座位号
    const keys=Object.keys(s.rooms||{}).map(k=>k.split(",").map(Number));
    if(keys.length){
      const xs=keys.map(k=>k[0]),ys=keys.map(k=>k[1]);
      const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
      const at={};Object.entries(s.pos||{}).forEach(([u,p])=>{(at[p]=at[p]||[]).push(+u)});
      const map=document.createElement("div");map.className="gmap";
      map.style.gridTemplateColumns="repeat("+(x1-x0+1)+",minmax(52px,1fr))";
      for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
        const c=document.createElement("div");
        const key=x+","+y;
        c.innerHTML=(s.rooms[key]?esc(s.rooms[key]):"")
          +((at[key]||[]).map(u=>"<b>"+(s.seats[u]||u)+"</b>").join(""));
        if((at[key]||[]).includes(my))c.style.outline="2px solid #e33";
        map.appendChild(c);}
      box.appendChild(map);}
    // 属性表
    const stats=document.createElement("div");stats.style.cssText="font-size:11px;margin-top:6px";
    stats.innerHTML=Object.entries(s.stats||{}).map(([u,st])=>{
      const uid=+u;
      return "<div class='glogl'>"+(uid===my?"<b>你</b>":esc(gnick(uid)))+"：💪"+st.might+" 🏃"+st.speed
        +" 🧠"+st.sanity+" 📚"+st.knowledge
        +((s.items[u]||[]).length?"　🎒"+s.items[u].join("、"):"")
        +((s.dead||[]).includes(uid)?"　💀":"")+"</div>";}).join("");
    box.appendChild(stats);
    // 动作
    if(s.turn_uid===my){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:8px";
      [["⬆ 上","up"],["⬇ 下","down"],["⬅ 左","left"],["➡ 右","right"]].forEach(([t,dn])=>
        bar.appendChild(gBtn(t,{move:dn},s.steps_left<=0)));
      bar.appendChild(gBtn("结束回合",{end:true}));
      box.appendChild(bar);
      const pv=state.gpriv;
      if(pv&&(pv.items||[]).length){
        const ub=document.createElement("div");
        ub.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px";
        pv.items.forEach(it=>ub.appendChild(gBtn("使用 "+it,{use:it})));
        box.appendChild(ub);}
      const here=Object.entries(s.pos||{}).filter(([u,p])=>+u!==my&&p===s.pos[my]).map(([u])=>+u);
      if(here.length&&s.phase==="haunt"){
        const ab=document.createElement("div");
        ab.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin:4px";
        here.forEach(u=>ab.appendChild(gBtn("⚔ 攻击 "+gnick(u),{attack:u})));
        box.appendChild(ab);}
    }
  },
  drawguess(box,s){
    const my=state.uid,amDrawer=s.drawer_uid===my;
    const d=document.createElement("div");d.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    d.innerHTML="🎨 画手 "+esc(gnick(s.drawer_uid))+(amDrawer?"（你）":"")
      +(s.phase==="round_end"?"　答案："+esc(s.word||""):"　猜词中…")
      +"　第 "+s.round+" 轮　"+scoreHTML(s.scores);
    box.appendChild(d);
    const cv=document.createElement("canvas");cv.width=400;cv.height=300;
    cv.style.cssText="display:block;margin:0 auto;border:1px solid var(--line,#ddd);border-radius:8px;background:#fff;cursor:crosshair";
    box.appendChild(cv);
    const ctx=cv.getContext("2d");ctx.lineCap="round";
    const repaint=()=>{ctx.clearRect(0,0,400,300);
      (s.strokes||[]).forEach(k=>{if(k.type!=="line")return;
        ctx.beginPath();ctx.moveTo(k.x1,k.y1);ctx.lineTo(k.x2,k.y2);
        ctx.strokeStyle=k.color||"black";ctx.lineWidth=k.width||3;ctx.stroke();});};
    repaint();
    if(amDrawer&&s.phase==="drawing"){
      let drawing=false,lx=0,ly=0,pend=[];
      const pos=e=>{const r=cv.getBoundingClientRect();
        return [Math.round((e.clientX-r.left)*400/r.width),
                Math.round((e.clientY-r.top)*300/r.height)];};
      cv.onmousedown=e=>{[lx,ly]=pos(e);drawing=true};
      cv.onmousemove=e=>{if(!drawing)return;const [x,y]=pos(e);
        if(x===lx&&y===ly)return;
        pend.push({type:"line",x1:lx,y1:ly,x2:x,y2:y,color:"black",width:3});
        ctx.beginPath();ctx.moveTo(lx,ly);ctx.lineTo(x,y);ctx.lineWidth=3;ctx.stroke();
        lx=x;ly=y;};
      const flush=()=>{if(!drawing)return;drawing=false;
        pend.forEach(k=>gameAPI("action",{room_id:state.groom,action:{stroke:k}},true));
        pend=[];};
      cv.onmouseup=flush;cv.onmouseleave=flush;
      const bar=document.createElement("div");bar.style.cssText="text-align:center;margin:6px";
      bar.appendChild(gBtn("🗑 清空",{clear:true}));box.appendChild(bar);
      if(state.gpriv&&state.gpriv.word){
        const w=document.createElement("div");w.style.cssText="text-align:center;margin:4px;font-weight:700";
        w.textContent="你的词："+state.gpriv.word;box.appendChild(w);}}
    else if(s.phase==="drawing"&&(s.players||[]).includes(my)){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;justify-content:center;margin:8px";
      const inp=document.createElement("input");inp.placeholder="输入你猜的词";
      inp.style.cssText="width:180px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 8px";
      const b=document.createElement("button");b.className="gbtn";b.textContent="猜！";
      b.onclick=()=>{const t=inp.value.trim();if(t)gameAPI("action",{room_id:state.groom,action:{guess:t}})};
      inp.addEventListener("keydown",e=>{if(e.key==="Enter")b.click()});
      bar.append(inp,b);box.appendChild(bar);}
    (s.guess_log||[]).slice(-10).forEach(x=>gLog("💬 "+gnick(x.uid)+"："+x.text+(x.ok?" ✅":"")));
  },
  kaituo(box,s){
    box.appendChild(gTitle("kaituo","开拓 · 资源建设"));
    const R_CN={wood:"木头",brick:"砖",lamb:"羊",wheat:"麦",ore:"矿"};
    const R_COL={wood:"#8a5b2c",brick:"#c24a33",lamb:"#7fbf4f",wheat:"#e8b93c",ore:"#7a8499",desert:"#e2c9a0"};
    const d=document.createElement("div");
    let html="<div style='font-size:11px;color:var(--dim);margin-bottom:4px'>"
      +"回合 → "+esc(gnick(s.turn_uid))+"　"+scoreHTML(s.score)+"</div>";
    if(s.phase==="setup")html+="<div class='gsec'>布置阶段：轮流放 1 村 + 1 路（逆向再补）</div>";
    else if(s.last_roll!=null)html+="<div>🎲 上次掷骰 "+s.last_roll+"</div>";
    html+="<div style='display:grid;grid-template-columns:repeat("+s.size+",minmax(30px,1fr));"
      +"gap:2px;margin:6px 0'>";
    for(let r=0;r<s.size;r++)for(let c=0;c<s.size;c++){
      const t=s.tiles[r+","+c];if(!t)continue;
      const col=R_COL[t.res]||"#999";
      html+="<div style='height:34px;border-radius:4px;background:"+col+";color:#fff;"
        +"display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700'>"
        +(t.res==="desert"?"🟤":t.num)+"</div>";}
    html+="</div>";
    html+="<div class='gsec'>你的资源（"+esc(gnick(state.uid))+"）</div>";
    const res=s.res[state.uid]||{};
    for(const k of ["wood","brick","lamb","wheat","ore"])
      html+="<span style='margin:0 6px'>"+R_CN[k]+"×"+(res[k]||0)+"</span>";
    html+="<div class='gsec'>定居点/城市/道路</div>";
    html+="<div style='font-size:11px;color:var(--dim)'>村 ×"+(Object.values(s.board).filter(v=>!v.city).length)
      +"　城 ×"+(Object.values(s.board).filter(v=>v.city).length)
      +"　路 ×"+(Object.keys(s.roads||{}).length)+"</div>";
    d.innerHTML=html;box.appendChild(d);
    const my=state.uid,myTurn=s.turn_uid===my;
    if(!myTurn){box.appendChild(gBtn("⏭ 跳过",{op:"skip"},true));return}
    if(s.phase==="setup"){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px";
      const I=(ph)=>Object.assign(document.createElement("input"),{type:"number",placeholder:ph,
        style:"width:52px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"}),
        i=I("纵(0~5)"),j=I("横(0~5)"),bi=I("末纵"),bj=I("末横"),
        b=document.createElement("button");b.className="gbtn";b.textContent="🏠 布置村+路";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"setup",i:i.value,j:j.value,b_i:bi.value,b_j:bj.value}});
      [i,j,bi,bj,b].forEach(x=>bar.appendChild(x));box.appendChild(bar);return}
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
    bar.appendChild(gBtn("🎲 掷骰",{op:"roll"}));
    box.appendChild(bar);
    const b2=document.createElement("div");b2.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
    const sel=Object.assign(document.createElement("select"),{});sel.style.cssText="border-radius:8px;padding:4px;border:1px solid var(--line,#ddd)";
    [["road","路"],["settle","村"],["city","城"]].forEach(k=>{const o=document.createElement("option");o.value=k[0];o.textContent=k[1];sel.appendChild(o)});
    const I=(ph)=>Object.assign(document.createElement("input"),{type:"number",placeholder:ph,
      style:"width:52px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"}),
      ia=I("纵"),jb=I("横"),ib=I("末纵"),jj=I("末横"),
      bb=document.createElement("button");bb.className="gbtn go";bb.textContent="⛏ 建造";
    bb.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"build",kind:sel.value,i:ia.value,j:jb.value,b_i:ib.value,b_j:jj.value}});
    b2.append(document.createTextNode("建造："),sel,ia,jb);
    if(sel.value==="road"){b2.append(ib,jj)}
    sel.onchange=()=>{if(sel.value==="road"){b2.append(ib,jj)}};
    b2.appendChild(bb);box.appendChild(b2);
    box.appendChild(gBtn("⏭ 跳过",{op:"skip"}));
  },
  lingdi(box,s){
    box.appendChild(gTitle("lingdi","领地 · 拼贴得分"));
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>回合 → "+esc(gnick(s.turn_uid))
      +"　剩余牌 "+s.deck_left+"　"+scoreHTML(s.score)+"</div>"
      +"<div class='gsec'>你的米宝："+(s.meeples[state.uid]||0)+"</div>";
    box.appendChild(d);
    if(s.current){
      const ed=s.current.edges||{};
      const edt="<span style='font-size:11px'>本张："+[{k:"N",n:"北"},{k:"E",n:"东"},{k:"S",n:"南"},{k:"W",n:"西"}]
        .map(x=>x.n+"="+({c:"城",r:"路",f:"场"}[ed[x.k]]||"?")).join("　")+"</span>";
      box.appendChild(d);d.innerHTML+=edt;}
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      const I=(ph)=>Object.assign(document.createElement("input"),{type:"number",placeholder:ph,
        style:"width:52px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"}),
        r=I("行"),c=I("列"),m=I("米宝,0-9"),
        b=document.createElement("button");b.className="gbtn go";b.textContent="🏗 放置";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"place",r:r.value,c:c.value,meeple:(m.value?("self"):null)}});
      [r,c,m,b].forEach(x=>bar.appendChild(x));bar.appendChild(gBtn("⏭ 跳过",{op:"pass"}));
      box.appendChild(bar);}
  },
  tielu(box,s){
    box.appendChild(gTitle("tielu","铁路 · 连线得分"));
    const P_COL={red:"#e05555",yellow:"#e8b93c",green:"#3ba55d",blue:"#4a7de0",purple:"#9b5fbf"};
    const routes=(s.routes||[]).map(rt=>{
      const col=rt.claimed?("#666"):(P_COL[rt.color]||"#999");
      return "<div style='font-size:11px;padding:2px 0;border-bottom:1px dashed var(--line,#eee)'>"
        +(rt.claimed?"("+esc(gnick(rt.claimed))+")":"")
        +esc(s.cities[rt.a])+" ↔ "+esc(s.cities[rt.b])
        +" <b style='color:"+col+"'>"+({red:"红",yellow:"黄",green:"绿",blue:"蓝",purple:"紫"}[rt.color]||"")+"×"+rt.length+"</b></div>";}).join("");
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>回合 → "+esc(gnick(s.turn_uid))
      +"　剩线路 "+s.route_left+"　手牌×"+(s.hand_count[state.uid]||0)+"　"+scoreHTML(s.score)+"</div>"
      +"<div class='gsec'>线路</div>"+routes;
    box.appendChild(d);
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      const S=(ph)=>Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px;border:1px solid var(--line,#ddd)"});
      const S_a=S("城市A");
      for(let i=0;i<(s.cities||[]).length;i++){const o=document.createElement("option");o.value=i;
        o.textContent=(s.cities[i]||("城市"+i));S_a.appendChild(o)}
      bar.appendChild(document.createTextNode("认领 "));bar.appendChild(S_a);
      bar.appendChild(document.createTextNode("→"));
      const S_b=S("城市B");S_b.innerHTML=S_a.innerHTML;
      const bb=document.createElement("button");bb.className="gbtn go";bb.textContent="🚂 认领";
      bb.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"claim",a:S_a.value,b:S_b.value}});
      bar.append(S_b,bb);box.appendChild(bar);
      const bar2=document.createElement("div");bar2.style.cssText="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap";
      bar2.appendChild(gBtn("🎫 摸2张",{op:"draw"}));
      bar2.appendChild(gBtn("📜 抽票证",{op:"ticket"}));
      bar2.appendChild(gBtn("⏭ 跳过",{op:"skip"}));box.appendChild(bar2);}
  },
  gongfang(box,s){
    box.appendChild(gTitle("gongfang","工坊 · 工人放置"));
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>第 "+s.round+"/"+s.rounds+" 轮 · 回合 → "
      +esc(gnick(s.turn_uid))+"　"+scoreHTML(s.score)+"</div>"
      +"<div class='gsec'>你的空闲工人："+(s.workers-(s.placed[state.uid]||0))+"</div>"
      +"<div style='display:grid;grid-template-columns:repeat(4,minmax(60px,1fr));gap:4px'>"
      +(s.spots||[]).map(sp=>{const free=sp.owner==null;
        return "<div style='border:1px solid "+(sp.exclusive?"#e8b93c":"var(--line,#ddd)")
          +(free?"":";background:var(--line,#eee)")+";border-radius:6px;padding:5px;text-align:center'>"
          +(sp.exclusive?"✨":"")+"工位"+sp.id+"<br><b>"+sp.pts+"</b> 分<br>"
          +(free?"<span style='color:var(--dim)'>空闲</span>":esc(gnick(sp.owner)))+"</div>";}).join("")+"</div>";
    box.appendChild(d);
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      const free=(s.spots||[]).filter(sp=>sp.owner==null);
      bar.appendChild(document.createTextNode("选工位："));
      const S=Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px;border:1px solid var(--line,#ddd)"});
      free.forEach(sp=>{const o=document.createElement("option");o.value=sp.id;
        o.textContent="工位"+sp.id+"(+"+sp.pts+")";S.appendChild(o)});
      const b=document.createElement("button");b.className="gbtn go";b.textContent="👷 工作";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"work",id:S.value}});
      bar.append(S,b);bar.appendChild(gBtn("⏭ 过牌",{op:"pass"}));box.appendChild(bar);}
  },
  chengzhu(box,s){
    box.appendChild(gTitle("chengzhu","我是城主 · 领地扩"));
    const T_CN={fd:"田",fo:"林",mo:"山",wa:"水",gr:"牧"};
    const T_COL={fd:"#e8d48f",fo:"#3ba55d",mo:"#9aa0a6",wa:"#4a7de0",gr:"#a8d695"};
    const grd=s.grid[state.uid]||{};
    let grid="<div style='display:grid;grid-template-columns:repeat("+s.size+",minmax(26px,1fr));gap:1px;margin:6px 0'>";
    for(let r=0;r<s.size;r++)for(let c=0;c<s.size;c++){
      const cell=grd[r+","+c];
      grid+="<div style='height:26px;border-radius:2px;background:"+(cell?(T_COL[cell.terr]||"#ccc"):"rgba(0,0,0,.04)")
        +";color:#333;font-size:10px;display:flex;align-items:center;justify-content:center'>"
        +(cell?(cell.crown?"👑"+cell.crown:""):"")+"</div>";}
    grid+="</div>";
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>本轮挑选 → "+esc(gnick(s.picker_uid))
      +"　剩余 "+s.piles+"　"+scoreHTML(s.score)+"</div>"
      +"<div class='gsec'>我的领地</div>"+grid
      +"<div class='gsec'>市场</div>"
      +(s.market||[]).map((m,i)=>{const a=T_CN[m.A.terr],b=T_CN[m.B.terr];
        return "<span style='margin-right:8px'>["+i+"] "+a+(m.A.crown?"👑"+m.A.crown:"")+" + "+b+(m.B.crown?"👑"+m.B.crown:"")+"</span>";}).join("");
    box.appendChild(d);
    if(s.picker_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      const I=(ph)=>Object.assign(document.createElement("input"),{type:"number",placeholder:ph,
        style:"width:50px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"});
      const di=I("板号"),x=I("x 0~4"),y=I("y 0~4");
      const S=Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px;border:1px solid var(--line,#ddd)"});
      [["0","向右"],["1","向下"]].forEach(k=>{const o=document.createElement("option");o.value=k[0];o.textContent=k[1];S.appendChild(o)});
      const b=document.createElement("button");b.className="gbtn go";b.textContent="🏰 放置";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"pick",dom:di.value,x:x.value,y:y.value,rot:S.value}});
      bar.append(di,x,y,S,b);box.appendChild(bar);}
  },
  gemcity(box,s){
    box.appendChild(gTitle("gemcity","璀璨宝石 · 收集换分"));
    const C_CN=s.colors||{};
    const tok=(t)=>Object.entries(t||{}).map(([c,n])=>(c+"×"+n)).join("　");
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>回合 → "+esc(gnick(s.turn_uid))
      +"　金库(O/D/R/E/S/G)："+Object.entries(s.bank).map(([c,n])=>c+"×"+n).join(" ")+"　"+scoreHTML(s.score)+"</div>";
    let mkt="<div class='gsec'>市场</div>";
    for(let t=1;t<=3;t++){mkt+="<div style='font-size:11px'><b>"+t+"级</b>　"
      +((s.market[t]||[]).map((c,i)=>{const cost=Object.entries(c.cost).filter(e=>e[1]>0).map(e=>C_CN[e[0]]+"×"+e[1]).join(" ");
        return "<span style='margin:0 6px'>["+i+"] 🎴+"+c.pts+" "+C_CN[c.disc]+"　需"+cost+"</span>";}).join("")||"（空）")+"</div>";}
    mkt+="<div class='gsec'>你的宝石</div>"+tok(s.tokens[state.uid])
      +"<div style='font-size:11px;color:var(--dim)'>永久折扣："+tok(s.discount[state.uid])
      +"　贵宾待邀："+(s.nobles||[]).length+"｜你的贵宾×"+(state.gpriv?(state.gpriv.nobles||[]).length:0)+"</div>";
    d.innerHTML+=mkt;box.appendChild(d);
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      bar.appendChild(document.createTextNode("取3异色(空格分隔)"));
      const I=Object.assign(document.createElement("input"),{placeholder:"o d r",style:"width:80px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"});
      const b=document.createElement("button");b.className="gbtn go";b.textContent="💎 取";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"take",colors:(I.value.trim().split(/\s+/))}});
      bar.append(I,b);box.appendChild(bar);
      const b2=document.createElement("div");b2.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
      b2.appendChild(document.createTextNode("买卡："));
      const S1=document.createElement("select"),S2=document.createElement("select");
      [1,2,3].forEach(t=>{const o=document.createElement("option");o.value=t;o.textContent=t+"级";S1.appendChild(o)});
      for(let i=0;i<4;i++){const o=document.createElement("option");o.value=i;o.textContent="[卡"+i+"]";S2.appendChild(o)}
      const bb=document.createElement("button");bb.className="gbtn";bb.textContent="🛒 购买";
      bb.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"buy",tier:S1.value,idx:S2.value}});
      b2.append(S1,S2,bb);box.appendChild(b2);
      const s3=document.createElement("div");s3.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";
      s3.appendChild(gBtn("➡ 取2同色🔴",{op:"take2",color:"r"}));
      s3.appendChild(gBtn("➡ 取2同色🟢",{op:"take2",color:"e"}));
      const resBox=document.createElement("div");resBox.style.cssText="display:flex;gap:6px;margin-top:6px";
      resBox.appendChild(document.createTextNode("保留："));
      const st=document.createElement("select");[1,2,3].forEach(t=>{const o=document.createElement("option");o.value=t;o.textContent=t+"级";st.appendChild(o)});
      const si=document.createElement("select");for(let i=0;i<4;i++){const o=document.createElement("option");o.value=i;o.textContent="[卡"+i+"]";si.appendChild(o)}
      const rb=document.createElement("button");rb.className="gbtn";rb.textContent="📥 保留";
      rb.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"reserve",tier:parseInt(st.value,10),idx:parseInt(si.value,10)}});
      resBox.append(st,si,rb);box.appendChild(resBox);}
  },
  siji(box,s){
    box.appendChild(gTitle("siji","四季物语 · 引擎构筑"));
    const d=document.createElement("div");
    const hand=(s.hand[state.uid]||[]).map((c,i)=>"["+i+"] "+c.name+"(需"+c.cost+"💧产"+c.out+")").join("　")||"（空）";
    const eng=(s.engine[state.uid]||[]).map((c,i)=>"["+i+"] "+c.name+(c.played?"(已激活)":"")).join("　")||"（空）";
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>第 "+s.season+"/"+s.seasons+" 季 · 剩"+s.turns_left+" 动 · 回合 → "
      +esc(gnick(s.turn_uid))+"　"+scoreHTML(s.vp)+"</div>"
      +"<div style='font-size:12px'>💧 水晶 "+s.crystal[state.uid]+"　🪙 金币 "+s.gold[state.uid]
      +"　👑 胜利点 "+s.vp[state.uid]+"</div>"
      +"<div class='gsec'>手牌</div><div style='font-size:12px'>"+hand+"</div>"
      +"<div class='gsec'>我的引擎</div><div style='font-size:12px'>"+eng+"</div>";
    box.appendChild(d);
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      bar.appendChild(document.createTextNode("出牌 "));
      const S=Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px"});
      for(let i=0;i<(s.hand[state.uid]||[]).length;i++){const o=document.createElement("option");o.value=i;o.textContent=(s.hand[state.uid])[i].name;S.appendChild(o)}
      const b=document.createElement("button");b.className="gbtn go";b.textContent="🎴 打出";
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"play",idx:S.value}});
      bar.append(S,b);box.appendChild(bar);
      const bar2=document.createElement("div");bar2.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
      bar2.appendChild(document.createTextNode("激活 "));
      const S2=Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px"});
      for(let i=0;i<(s.engine[state.uid]||[]).length;i++){const o=document.createElement("option");o.value=i;o.textContent=(s.engine[state.uid])[i].name;S2.appendChild(o)}
      const b2=document.createElement("button");b2.className="gbtn";b2.textContent="⚙️ 激活";
      b2.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"activate",idx:S2.value}});
      bar2.append(S2,b2);box.appendChild(bar2);
      const s3=document.createElement("div");s3.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";
      s3.appendChild(gBtn("👑 3金换1分",{op:"convert"}));s3.appendChild(gBtn("⏭ 跳过",{op:"convert"},true));box.appendChild(s3);}
  },
  bolan(box,s){
    box.appendChild(gTitle("bolan","波兰大选 · 区域控制"));
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>回合 → "+esc(gnick(s.turn_uid))
      +"　影响力："+Object.entries(s.influence).map(([u,v])=>esc(gnick(+u))+"×"+v).join(" ")+"　"+scoreHTML(s.score)+"</div>"
      +"<div class='gsec'>第 "+s.election_round+" 轮选举</div>"
      +Object.entries(s.board).map(([r,counts])=>{
        const rows=Object.entries(counts).filter(e=>e[1]>0).map(([u,v])=>esc(gnick(+u))+"×"+v).join("　");
        return "<div style='font-size:12px;padding:2px 0'>"+(s.regions[r]||("区"+r))+"："
          +(rows||"<span style='color:var(--dim)'>无人</span>")+"</div>";}).join("");
    box.appendChild(d);
    if(s.turn_uid===state.uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
      bar.appendChild(document.createTextNode("投放选区 "));
      const S=Object.assign(document.createElement("select"),{style:"border-radius:8px;padding:4px"});
      for(let i=0;i<5;i++){const o=document.createElement("option");o.value=i;o.textContent=s.regions[i];S.appendChild(o)}
      const place=document.createElement("button");place.className="gbtn go";place.textContent="🗳 投放";
      place.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"place",r:parseInt(S.value,10)}});
      const dev=document.createElement("button");dev.className="gbtn";dev.textContent="🔥 弃2枚翻倍";
      dev.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"devote",r:parseInt(S.value,10)}});
      bar.append(S,place,dev);box.appendChild(bar);}
  },
  azul(box,s){
    box.appendChild(gTitle("azul","花砖物语 · 拼花"));
    const CC=s.colors||{};
    const CTS={r:"#e05555",w:"#f5f2e8",b:"#4a7de0",y:"#e8b93c",k:"#3a3d42"};
    const chunk=a=>a.map(x=>({c:x.c,n:x.n}));   // offers/center 已是 {c,n} 小对象
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>第 "+s.round+" 轮 · 回合 → "
      +esc(gnick(s.turn_uid))+"　🧱 袋剩 "+s.bag+"　"+scoreHTML(s.score)+"</div>";
    d.innerHTML+="<div class='gsec'>工厂碗</div><div style='display:flex;flex-wrap:wrap;gap:4px'>"
      +(s.offers||[]).map((b,i)=>b.length?("<span title='碗"+(i+1)+"' style='border:1px solid var(--line,#ddd);border-radius:6px;padding:3px 5px'>"
        +b.map(t=>"<b style='color:"+CTS[t.c]+"'>"+CC[t.c]+"</b>").join(",")+"</span>"):"<span style='color:var(--dim)'>[碗"+(i+1)+"空]</span>").join("　")
      +"</div><div style='font-size:11px'>中央："+(s.center||[]).map(t=>"<b style='color:"+CTS[t.c]+"'>"+CC[t.c]+"</b>").join(",")||"（空）"+"</div>";
    d.innerHTML+="<div class='gsec'>我的墙</div><div style='display:grid;grid-template-columns:repeat(5,24px);gap:2px'>"
      +[0,1,2,3,4].map(r=>[0,1,2,3,4].map(c=>{
        const v=(s.wall[state.uid]||{})[r+","+c];
        return "<div style='height:24px;width:24px;border-radius:3px;background:"+(v?CTS[v]:"rgba(0,0,0,.04)")
          +";border:1px solid "+(v?CTS[v]:"var(--line,#eee)")+"'>"+(v?CC[v]:"")+"</div>";
      }).join("")).join("")
      +"<div class='gsec' style='grid-column:1/-1'>我的花纹行</div>"
      +Object.entries(s.rows[state.uid]||{}).map(([r,row])=>"<div style='grid-column:1/-1;font-size:11px'>第"+(+r+1)+"行："
        +row.map(t=>"<b style='color:"+CTS[t]+"'>"+CC[t]+"</b>").join("")+"（"+(+r+1-row.length)+"空）</div>").join("")
      +"<div style='grid-column:1/-1;font-size:11px'>地板："+((s.floor[state.uid]||0))+"　分："+s.score[state.uid]+"</div>"
      +"</div>";
    box.appendChild(d);
    if(s.turn_uid!==state.uid){box.appendChild(gBtn("⏸ 等待他行动",null,true));return}
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
    const S=document.createElement("select");const opt=document.createElement("option");opt.value="center";opt.textContent="中央";S.appendChild(opt);
    (s.offers||[]).forEach((b,i)=>{const o=document.createElement("option");o.value=i;o.textContent="碗"+(i+1);S.appendChild(o)});
    const C=document.createElement("select");
    Object.entries(CC).forEach(([k,v])=>{const o=document.createElement("option");o.value=k;o.textContent=v;C.appendChild(o)});
    const bt=document.createElement("button");bt.className="gbtn go";bt.textContent="🧱 取砖";
    bt.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"take",src:S.value,col:C.value}});
    bar.append(document.createTextNode("取："),S,C,bt);box.appendChild(bar);
    const bar2=document.createElement("div");bar2.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
    const R=document.createElement("select");[0,1,2,3,4].forEach(r=>{const o=document.createElement("option");o.value=r;o.textContent="第"+(r+1)+"行";R.appendChild(o)});
    const bp=document.createElement("button");bp.className="gbtn";bp.textContent="🪟 落砖";
    bp.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"place",row:R.value}});
    bar2.append(document.createTextNode("落："),R,bp,gBtn("🌀 溢出地板",{op:"floor"}));box.appendChild(bar2);
  },
  rummikub(box,s){
    box.appendChild(gTitle("rummikub","拉密 · 出牌"));
    const CC={红:"#e05555",黄:"#e8b93c",蓝:"#4a7de0",黑:"#3a3d42"};
    const tile=t=>"<b style='color:"+(CC[t.c]||"#333")+";font-size:12px'>"+t.c+t.n+"</b>";
    function rClass(row){
      if(row.length<3)return null;
      const uniqN=new Set(row.map(t=>t.n)),uniqC=new Set(row.map(t=>t.c));
      if(uniqN.size===1){if(row.length>4||uniqC.size!==row.length)return null;return ["group",row[0].n]}
      if(uniqC.size===1){const v=row.map(t=>t.n).sort((a,b)=>a-b);
        for(let i=1;i<v.length;i++)if(v[i]!==v[i-1]+1)return null;
        return ["run",row[0].c,v[0],v.length]}
      return null;
    }
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>回合 → "+esc(gnick(s.turn_uid))
      +"　🂡袋剩 "+s.bag+"</div>"
      +"<div class='gsec'>桌面</div>"
      +((s.table||[]).map(function(row,i){
        const k=rClass(row);let hot="";
        if(k&&k[0]==="run")hot=k[1]+k[2]+"-"+(k[2]+k[3]-1);
        if(k&&k[0]==="group")hot="同"+k[1]+"异色";
        return "<div style='font-size:11px;padding:2px 0'>["+(i+1)+"] <span title='"
          +esc(hot)+"'>"+row.map(tile).join(" ")+"</span></div>";}).join("")||"<span style='color:var(--dim)'>（空）</span>");
    box.appendChild(d);
    const p=state.gpriv;
    if(p&&p.hand){
      const w=document.createElement("div");w.style.cssText="margin-top:4px;font-size:12px";
      w.innerHTML="<div class='gsec'>我的手牌</div>"+p.hand.map(tile).join("　")
        +"　<small style='color:var(--dim)'>（id："+p.hand.map(t=>t.id).join(",")+"）</small>";
      box.appendChild(w);}
    if(s.turn_uid!==state.uid)return;
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
    const I=(ph,w)=>Object.assign(document.createElement("input"),{placeholder:ph,style:"width:"+(w||"160px")+"px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"});
    const ids=I("牌id，用空格分隔"),row=I("接续行号(0起)",70);
    const bm=document.createElement("button");bm.className="gbtn go";bm.textContent="🎴 组新组";
    bm.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"meld",tiles:ids.value.trim().split(/\\s+/).map(Number)}});
    const be=document.createElement("button");be.className="gbtn";be.textContent="🔧 接续";
    be.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"extend",row:row.value,tiles:ids.value.trim().split(/\\s+/).map(Number)}});
    bar.append(ids,bm,row,be,gBtn("✅ 结束回合",{op:"done"}));box.appendChild(bar);
  },
  yahtzee(box,s){
    box.appendChild(gTitle("yahtzee","快艇骰子 · 记分"));
    const d=document.createElement("div");
    d.innerHTML="<div style='font-size:20px;font-weight:700;letter-spacing:4px;margin:6px 0'>"
      +(s.dice||[]).join("　")+"</div>"
      +"<div style='font-size:11px;color:var(--dim)'>第 "+s.round+" 动 · 回合 → "+esc(gnick(s.turn_uid))
      +"（可再重掷 "+s.rolls_left+" 次）　"+Object.entries(s.totals||{}).map(([u,v])=>esc(gnick(+u))+"="+v).join("　")+"</div>";
    d.innerHTML+="<div class='gsec'>记分表</div><div style='display:grid;grid-template-columns:repeat(auto-fill,96px);gap:2px'>"
      +Object.entries(s.cats||{}).map(([k,v])=>"<div style='font-size:11px'>"+v+"："+(s.scores[state.uid]?.[k]??"<span style='color:var(--dim)'>-</span>")+"</div>").join("")
      +"</div>";
    box.appendChild(d);
    if(s.turn_uid!==state.uid)return;
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center";
    bar.appendChild(gBtn("🎲 掷骰",{op:"roll"}));
    const I=Object.assign(document.createElement("input"),{placeholder:"保留位如 0 1 2",style:"width:130px;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px"});
    const br=document.createElement("button");br.className="gbtn";br.textContent="🔁 重掷其余";
    br.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"reroll",keep:I.value.trim().split(/\\s+/).map(Number)}});
    bar.append(I,br);box.appendChild(bar);
    const bar2=document.createElement("div");bar2.style.cssText="display:flex;gap:6px;margin-top:6px;align-items:center";
    const S=document.createElement("select");
    Object.entries(s.cats||{}).forEach(([k,v])=>{const o=document.createElement("option");o.value=k;o.textContent=v;S.appendChild(o)});
    const bs=document.createElement("button");bs.className="gbtn go";bs.textContent="📝 记分";
    bs.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"score",cat:S.value}});
    bar2.append(document.createTextNode("选分类 "),S,bs);box.appendChild(bar2);
  },
  nimmt(box,s){
    box.appendChild(gTitle("nimmt","牛头王 · 避牛头"));
    const d=document.createElement("div");
    const rowHtml=(row,i)=>row.map((c,j)=>"<span title='"+c+"' style='padding:0 3px'>"+(j===0?"<b>"+c+"</b>":c)
      +"</span>").join(" ");
    d.innerHTML="<div style='font-size:11px;color:var(--dim)'>第 "+s.round+"/10 轮 · "
      +Object.entries(s.bulls||{}).map(([u,v])=>esc(gnick(+u))+"🐂"+v).join("　")+"</div>"
      +"<div class='gsec'>桌面 4 列</div>"
      +[0,1,2,3].map((i,ix)=>"<div style='font-size:11px'>第"+(ix+1)+"列："+(s.table[ix]?rowHtml(s.table[ix],ix):"")+"</div>").join("");
    box.appendChild(d);
    const p=state.gpriv;
    if(p&&p.hand){
      const w=document.createElement("div");w.style.cssText="margin-top:6px";
      w.innerHTML="<div class='gsec'>我的手牌（选一张打出）</div>"+p.hand.map(c=>{
        const b=document.createElement("button");b.className="gbtn";b.style.marginRight="6px";b.textContent=c;
        b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"choose",card:c}});
        return b.outerHTML;}).join("");
      box.appendChild(w);
      if(Object.keys(s.chosen||{}).includes(String(state.uid)))
        box.appendChild(Object.assign(document.createElement("div"),
          {style:"color:var(--dim);font-size:12px;margin-top:4px",textContent:"✅ 本赛季已暗选"}));
    }
  },
  davinci(box,s){
    box.appendChild(gTitle("davinci","达芬奇密码 · 猜牌淘汰"));
    const label=s.label||{};
    const lv=v=>label[v]!=null?label[v]:v;
    const w=document.createElement("div");w.style.cssText="font-size:12px;line-height:22px";
    const rows=(s.dead||[]).map(u=>"<div style='color:var(--dim)'>💀 "+esc(gnick(u))+" 出局</div>").join("");
    w.innerHTML="<div class='gsec'>牌堆剩 "+s.draw_left+" 张</div>"
      +Object.keys(s.hands||{}).map(u=>{
        const tiles=(s.hands[u]||[]).map(t=>t.open?"<b>"+esc(String(lv(t.v)))+"</b>":"<span style='color:var(--dim)'>▮?</span>").join("　");
        return "<div style='display:flex;gap:6px'><span style='min-width:64px;color:var(--dim)'>"+esc(gnick(+u))+":</span><span>"+tiles+"</span></div>";
      }).join("")+rows;
    box.appendChild(w);
    const me=state.uid, mine=(s.hands||{})[me]||[];
    const myrow=(state.gpriv&&state.gpriv.row)||mine;
    if(myrow.length)box.appendChild(Object.assign(document.createElement("div"),
      {style:"font-size:11px;color:var(--dim);margin-top:4px",
        textContent:"我的手牌："+myrow.map((t,i)=>i+"位="+(t.open&&t.v!=null?"公开 "+esc(String(lv(t.v))):"▮?")).join(" ，")}));
    const bar=document.createElement("div");bar.style.cssText="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px";
    if(s.turn===me&&!s.winner_uid){
      bar.appendChild(gBtn("摸明牌",{op:"draw",open:true}));
      bar.appendChild(gBtn("摸暗牌",{op:"draw",open:false}));
      bar.appendChild(Object.assign(document.createElement("span"),{textContent:" 猜:"}));
      const ts=document.createElement("select");
      Object.keys(s.hands||{}).forEach(u=>{if(+u!==me)ts.appendChild(Object.assign(document.createElement("option"),{value:u,textContent:gnick(+u)}))});
      const ps=document.createElement("select");
      let maxInst=0;Object.keys(s.hands||{}).forEach(u=>maxInst=Math.max(maxInst,(s.hands[u]||[]).length));
      for(let i=0;i<maxInst;i++)ps.appendChild(Object.assign(document.createElement("option"),{value:i,textContent:"第"+(i+1)+"位"}));
      const vs=document.createElement("select");
      for(let v=0;v<=11;v++)vs.appendChild(Object.assign(document.createElement("option"),{value:v,textContent:"数字"+v}));
      vs.appendChild(Object.assign(document.createElement("option"),{value:"black",textContent:"黑牌"}));
      const gb=document.createElement("button");gb.className="gbtn";gb.textContent="🎯 猜";
      gb.onclick=()=>{const v=vs.value;gameAPI("action",{room_id:state.groom,
        action:{op:"guess",target:+ts.value,pos:+ps.value,val:isNaN(+v)?v:+v}})};
      bar.append(ts,ps,vs,gb);
    }else if(s.winner_uid){
      bar.appendChild(document.createTextNode("🏁 对局结束"));
    }else{
      bar.appendChild(document.createTextNode("⏳ 等待 "+esc(gnick(s.turn))));
    }
    box.appendChild(bar);
  },
  kalah(box,s){
    box.appendChild(gTitle("kalah","非洲播棋 · 多子者胜"));
    const c=s.cells||[],A=s.p0,B=s.p1,st=s.stores||{};
    const chip=n=>n?"<b>"+n+"</b>":"<span style='color:var(--dim)'>·</span>";
    const cell=(n,i,btn)=>{
      if(!btn)return "<span style='display:inline-block;min-width:24px;text-align:center;border:1px solid var(--line,#ddd);border-radius:8px;padding:8px 2px;margin:1px'>"+chip(n)+"</span>";
      const b=document.createElement("button");b.className="gbtn";b.style.minWidth="28px";b.style.padding="7px 2px";b.textContent=n;
      b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{hole:i+1}});return b.outerHTML;
    };
    const w=document.createElement("div");w.style.cssText="font-size:12px";
    w.innerHTML=
      "<div style='display:flex;align-items:stretch'>"
      +"<div style='align-self:center;border:1px solid var(--line,#ddd);border-radius:10px;padding:6px;text-align:center'>"+chip(st[B]||0)+"<div style='font-size:9px;color:var(--dim)'>"+esc(gnick(B))+"</div></div>"
      +"<div style='flex:1'>"+c.slice(13,7).reverse().map((n,i)=>cell(n,12-i,false)).join("")+"</div>"
      +"</div>"
      +"<div style='display:flex;align-items:stretch'>"
      +"<div style='flex:1'>"+c.slice(0,6).map((n,i)=>cell(n,i,true)).join("")+"</div>"
      +"<div style='align-self:center;border:1px solid var(--line,#ddd);border-radius:10px;padding:6px;text-align:center'>"+chip(st[A]||0)+"<div style='font-size:9px'>"+esc(gnick(A))+"</div></div>"
      +"</div>"
      +"<div style='margin-top:4px;color:var(--dim)'>点己方洞播子"+(s.turn===A?"（轮到你）":"　轮到 "+esc(gnick(s.turn)))+"</div>";
    box.appendChild(w);
  },
  lovelove(box,s){
    box.appendChild(gTitle("lovelove","情书 · 递给心上人"));
    const w=document.createElement("div");w.style.cssText="font-size:12px;line-height:20px";
    const dead=((s.dead||[]).map(u=>esc(gnick(u))).join("、")||"无");
    w.innerHTML="<div class='gsec'>存活："+(s.alive||[]).map(u=>esc(gnick(u))).join("　")
      +"</div><div><span style='color:var(--dim)'>出局：</span>"+dead
      +"　<span style='color:var(--dim)'>废牌：</span>"+((s.discard||[]).map(x=>x[1]).join(","))+"　牌堆剩 "+s.deck_left+"</div>";
    box.appendChild(w);
    const me=state.uid, mine=state.gpriv?state.gpriv.hand:null;
    const bar=document.createElement("div");bar.style.cssText="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px";
    if(s.winner_uid){bar.appendChild(document.createTextNode("🏁 对局结束"));}
    else if(s.cur!==me){bar.appendChild(document.createTextNode("⏳ 等待 "+esc(gnick(s.cur))));}
    else if(mine!=null){
      bar.appendChild(Object.assign(document.createElement("div"),
        {textContent:"我的手牌："+mine}));
      const ts=document.createElement("select");
      ts.appendChild(Object.assign(document.createElement("option"),{value:"",textContent:"(无需目标)"}));
      (s.alive||[]).forEach(u=>{if(u!==me)ts.appendChild(Object.assign(document.createElement("option"),{value:u,textContent:gnick(u)}))});
      const vs=document.createElement("select");
      vs.appendChild(Object.assign(document.createElement("option"),{value:"",textContent:"(不影响)"}));
      for(let v=1;v<=8;v++)vs.appendChild(Object.assign(document.createElement("option"),{value:v,textContent:"数值"+v}));
      const db=document.createElement("button");db.className="gbtn";db.textContent="🂠 弃牌出效果";
      db.onclick=()=>{const a={op:"discard",play:mine};
        if(ts.value!=="")a.target=+ts.value;
        if(vs.value!=="")a.val=+vs.value;
        gameAPI("action",{room_id:state.groom,action:a})};
      bar.append(ts,vs,db);
    }
    box.appendChild(bar);
  },
  halloween(box,s){
    box.appendChild(gTitle("halloween","德国心脏病 · 翻牌抢铃"));
    const w=document.createElement("div");w.style.cssText="font-size:12px;line-height:20px";
    w.innerHTML="<div class='gsec'>轮到："+esc(gnick(s.turn))+"</div>"
      +"<div>"+(Object.entries(s.counts||{}).map(([f,n])=>"<span style='margin-right:10px'>"+f+"×"+n+"</span>").join("")||"旁观")+"</div>"
      +"<div style='margin-top:4px'>桌上：「"+(s.area&&s.area.length?s.area.join(" "):"空")+"」</div>"
      +(s.can_slap?"<div style='color:#c2362c;font-weight:700'>🔔 桌上已有 5 个相同水果！</div>":"");
    box.appendChild(w);
    const me=state.uid;
    if(s.turn===me&&!s.winner_uid){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;margin-top:8px";
      bar.appendChild(gBtn(s.flipped?"(已翻)":"🫲 翻牌",{op:"flip"}));
      if(s.flipped){
        bar.appendChild(gBtn(s.can_slap?"🔔 拍铃收牌!":"拍铃(未5会扣分)",{op:"slap"}));
        bar.appendChild(gBtn("过",{op:"pass"}));
      }
      box.appendChild(bar);
    }
    const sc=Object.entries(s.score||{}).map(([u,v])=>esc(gnick(+u))+" "+v).join("　");
    box.appendChild(Object.assign(document.createElement("div"),
      {style:"font-size:11px;color:var(--dim);margin-top:6px",textContent:"得分："+sc}));
  },
  tictactoe(box,s){
    const n=s.size||3;
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :(s.draw?"平局":"轮到 "+esc(gnick(s.turn_uid))+(s.turn_uid===state.uid?"（你执子 ✕）":"")));
    box.appendChild(info);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+n+",30px);gap:3px;justify-content:center;margin:0 auto";
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const c=document.createElement("div");c.className="gcell";c.style.cssText="font-weight:800";
      const v=s.board[y][x];
      c.textContent=v===1?"✕":(v===2?"○":"·");
      c.style.color=v===1?"#2955b8":(v===2?"#c2362c":"var(--dim)");
      if(s.winner_uid==null&&!s.draw&&v===0)
        c.onclick=()=>gameAPI("action",{room_id:state.groom,action:{x:x,y:y}});
      grid.appendChild(c);}
    box.appendChild(grid);
  },
  halma(box,s){
    const n=s.size||9;const ARMCOL=["#e05555","#3f6fe0","#3ba55d","#e8b93c"];
    const armOf={};(s.players||[]).forEach(u=>{armOf[u]=parseInt((s.owners&&s.owners[u])||0)});
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜":"轮到 "+esc(gnick(s.turn_uid)));
    box.appendChild(info);
    const sel=(state.halmaSel&&state.halmaSel.room===state.groom)?state.halmaSel.sel:null;
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+n+",22px);gap:2px;justify-content:center;margin:0 auto";
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const c=document.createElement("div");c.className="gcell";c.style.cssText="padding:0;border-radius:6px;min-height:22px";
      const v=s.board[y][x],valid=s.valid[y][x];
      if(v){
        c.style.background=ARMCOL[armOf[+v]||0];
        if(sel&&sel[0]===x&&sel[1]===y)c.style.outline="3px solid #222";
        c.onclick=()=>{if(s.winner_uid!=null)return;
          if(+v===state.uid)state.halmaSel={room:state.groom,sel:[x,y]};};
      }else if(valid){
        c.style.background=sel?"rgba(255,255,255,.5)":"rgba(0,0,0,.12)";
        if(sel&&s.winner_uid==null){c.style.cursor="pointer";
          c.onclick=()=>{gameAPI("action",{room_id:state.groom,action:{fx:sel[0],fy:sel[1],tx:x,ty:y}});state.halmaSel=null;};}
      }else{c.style.background="transparent";}
      grid.appendChild(c);}
    box.appendChild(grid);
  },
  checkers(box,s){
    const n=s.board.length;
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜":"轮到 "+esc(gnick(s.turn_uid)));
    box.appendChild(info);
    const sel=(state.chkSel&&state.chkSel.room===state.groom)?state.chkSel.sel:null;
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+n+",26px);gap:1px;justify-content:center;margin:0 auto";
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const c=document.createElement("div");c.className="gcell";c.style.cssText="padding:0;border-radius:0;min-height:26px;display:flex;align-items:center;justify-content:center";
      c.style.background=(y+x)%2===1?"#8a5a2b":"#e9ddd0";
      const v=s.board[y][x];
      if(v){
        const me=(v===1||v===3);const color=me?"#222":"#e05555";
        const d=document.createElement("div");d.style.cssText="width:18px;height:18px;border-radius:50%;background:"+color+";box-shadow:inset 0 0 0 2px rgba(255,255,255,.35)";
        if(v===3||v===4)d.textContent="♛";
        c.appendChild(d);
        if(sel&&sel[0]===x&&sel[1]===y)c.style.outline="3px solid #ffd54f";
        c.onclick=()=>{if(s.winner_uid!=null)return;
          if(me&&state.uid===s.players[0])state.chkSel={room:state.groom,sel:[x,y]};
          else if(!me&&state.uid===s.players[1])state.chkSel={room:state.groom,sel:[x,y]};};
      }else if(sel&&s.winner_uid==null){
        c.style.cursor="pointer";
        c.onclick=()=>{gameAPI("action",{room_id:state.groom,action:{fx:sel[0],fy:sel[1],tx:x,ty:y}});state.chkSel=null;};
      }
      grid.appendChild(c);}
    box.appendChild(grid);
  },
  blokus(box,s){
    const n=s.size||20;
    const idxOf={};(s.players||[]).forEach((u,i)=>idxOf[u]=i);
    const colFor=(u)=>(s.colors&&s.colors[idxOf[u]])||"#888";
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜":"轮到 "+esc(gnick(s.turn_uid)));
    box.appendChild(info);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat(20,15px);gap:1px;justify-content:center;margin:0 auto;max-width:340px";
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const c=document.createElement("div");c.className="gcell";c.style.cssText="padding:0;min-height:15px;border-radius:1px;background:"+(s.board[y][x]!=null?colFor(s.board[y][x]):"rgba(0,0,0,.06)");
      if(s.board[y][x]==null&&state.blockMode&&s.winner_uid==null){
        c.style.cursor="pointer";c.onclick=()=>{placeBlokus({x:x,y:y});};
      }
      grid.appendChild(c);}
    box.appendChild(grid);
    if(state.uid==null)return;
    const meh=s.has_piece?s.has_piece[String(state.uid)]:[];
    if(s.winner_uid!=null)return;
    if(s.turn_uid!==state.uid){box.appendChild(document.createElement("div")).textContent="";return;}
    const zone=document.createElement("div");zone.style.cssText="margin-top:8px";
    const row=document.createElement("div");row.style.cssText="display:flex;flex-wrap:wrap;gap:4px;align-items:center";
    const cat=s.pieces||{};
    const pick=state.blokP||(meh[0]||"");
    const ots=cat[pick]||[];
    const oi=state.blokO||0;
    row.appendChild(Object.assign(document.createElement("span"),{textContent:"拼块:"}));
    (meh||[]).forEach(pc=>{
      const b=document.createElement("button");b.className="gbtn"+(pc===pick?" go":"");b.textContent=pc;
      b.onclick=()=>{state.blokP=pc;state.blokO=0;};row.appendChild(b);});
    const prev=document.createElement("span");prev.style.cssText="display:inline-block;margin-left:6px";
    if(ots.length){const oc=ots[oi];let mini="";
      for(let r=0;r<6;r++){for(let ccol=0;ccol<6;ccol++){mini+=oc.has(r+","+ccol)?"▣":"·";}mini+="<br>";}
      prev.innerHTML=mini;
      row.appendChild(prev);
    }
    zone.appendChild(row);
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;margin-top:6px;align-items:center";
    if(ots.length){
      const rot=document.createElement("button");rot.className="gbtn";rot.textContent="↻ 方向 "+oi+"/"+ots.length;
      rot.onclick=()=>{state.blokO=(oi+1)%(ots.length||1);box.innerHTML="";renderGamePanel();};
      bar.appendChild(rot);
    }
    bar.appendChild(gBtn("🙋 跳过回合",{op:"pass"}));
    const allow=document.createElement("button");allow.className="gbtn go";allow.textContent=state.blockMode?"已完成预览 · 点棋盘落子":"🔍 预览放置位置";
    allow.onclick=()=>{state.blockMode=!state.blockMode;box.innerHTML="";renderGamePanel();};
    bar.appendChild(allow);
    zone.appendChild(bar);
    box.appendChild(zone);
    function placeBlokus(corner){gameAPI("action",{room_id:state.groom,action:{op:"place",piece:pick,oi:oi||0,x:corner.x,y:corner.y}});}
  },
  ludo(box,s){
    const tr=s.track||40,per=11,ARMCOL=["#e05555","#3f6fe0","#3ba55d","#e8b93c"];
    const idxOf={};(s.players||[]).forEach((u,i)=>idxOf[u]=i);
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :"轮到 "+esc(gnick(s.turn_uid))+" · 🎲 "+((s.dice!=null)?s.dice:"—"));
    box.appendChild(info);
    const ring=(t)=>{if(t<per)return [t,0];const t2=t-per;if(t2<per)return [10,1+t2];
      const t3=t-2*per;if(t3<per)return [10-t3,10];const t4=t-3*per;return [0,10-t4];};
    const rc={};for(let t=0;t<tr;t++){const p=ring(t);rc[t]=[p[1],p[0]];}
    // 中心基地的四格也映射到每玩家停机坪显示位
    const stallPos=[[5,4],[6,5],[5,6],[4,5]];
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat(11,23px);gap:1px;justify-content:center;margin:0 auto";
    for(let yy=0;yy<11;yy++)for(let xx=0;xx<11;xx++){
      const cell=document.createElement("div");
      cell.style.cssText="min-height:23px;border-radius:5px;display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:1px";
      grid.appendChild(cell);}
    // 环格
    for(let t=0;t<tr;t++){const [ry,rx]=rc[t];const cell=grid.children[ry*11+rx];cell.style.background="#efca63";cell.style.border="1px solid #caa832";}
    // 中心基地底色
    for(let pl=0;pl<(s.players||[]).length;pl++){const [sy,sx]=stallPos[pl%4];
      for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++){const g=grid.children[(sy+dy)*11+(sx+dx)];g.style.background=ARMCOL[pl%4];g.style.opacity="0.9";}}
    // 子
    for(let pl=0;pl<(s.players||[]).length;pl++){
      const u=s.players[pl];const col=ARMCOL[pl%4];
      (s.positions[String(u)]||[]).forEach((t,pdx)=>{
        const st=document.createElement("div");st.style.cssText="width:16px;height:16px;border-radius:50%;background:"+col+";box-shadow:inset 0 0 0 2px rgba(255,255,255,.4)";
        st.title="玩家"+u+" 机"+(pdx+1);
        if(typeof t==="number"){
          if(t<0){const [sy,sx]=stallPos[pl%4];grid.children[(sy+(pdx>>1))*11+(sx+(pdx%2))].appendChild(st);}
          else{const [ry,rx]=rc[t];grid.children[ry*11+rx].appendChild(st);}
        }else{ // FIN 停到基地
          const [sy,sx]=stallPos[pl%4];grid.children[sy*11+sx].appendChild(st);
        }});
    }
    box.appendChild(grid);
    const u=state.uid;
    if(s.turn_uid===u&&s.winner_uid==null){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;justify-content:center;margin-top:8px";
      if(s.dice==null)bar.appendChild(gBtn("🎲 掷骰",{op:"roll"}));
      else{
        const pieceRow=document.createElement("div");pieceRow.style.cssText="margin-top:6px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap";
        (s.positions[String(u)]||[]).forEach((t,pdx)=>{
          const b=document.createElement("button");b.className="gbtn";b.textContent="机"+(pdx+1)+((t===-1)?"(起飞)":(t==="FIN"?"(到)":" →"));
          if(t!=="FIN")b.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"move",idx:pdx}});
          pieceRow.appendChild(b);});
        box.appendChild(pieceRow);
        bar.appendChild(gBtn("🙅 结束本回合",{op:"skip"}));
      }
      box.appendChild(bar);
    }
  },
  // ---- W4 重型棋类：通用"选中→目标"落子 ----
  _move_click(box,s,rows,cols,col_bg,getText,onMove){
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:6px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 获胜"
      :"轮到 "+esc(gnick(s.turn_uid))+(s.turn_uid===state.uid?"（你）":""));
    box.appendChild(info);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat("+cols+",34px);gap:1px;justify-content:center;margin:0 auto";
    const sel=state.gsel;
    for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
      const code=s.board[y][x];
      const c=document.createElement("div");c.className="gcell";
      c.style.cssText="min-height:34px;display:flex;align-items:center;justify-content:center";
      if(col_bg)c.style.background=col_bg(y,x,code)||"#e6d3b0";
      c.innerHTML=(code!==null&&code!==0&&getText)?getText(code,y,x):"";
      c.style.fontSize="19px";
      if(sel&&sel[0]===x&&sel[1]===y)c.style.outline="2px solid #e33";
      const clickable=(s.winner_uid==null&&s.turn_uid===state.uid);
      c.onclick=()=>{if(!clickable){showStatus("还没轮到你");return;} onMove(x,y,code);};
      grid.appendChild(c);
    }
    box.appendChild(grid);
  },
  // 走子类通用逻辑：sideOf(code)∈{0,1}；tt.move / tt.drop
  _clickMove(s,sideOf,tt){
    const mySide = (s.players[0]===state.uid)?0:1;
    return function(x,y,code){
      if(state.gdrop!=null){
        gameAPI("action",{room_id:state.groom,action:{op:"drop",t:state.gdrop,x:x,y:y}});
        state.gdrop=null;state.gsel=null;renderGamePanel();return;
      }
      if(!state.gsel && code && sideOf(code)===mySide){
        state.gsel=[x,y];renderGamePanel();return;
      }
      if(state.gsel){
        const [fx,fy]=state.gsel;
        gameAPI("action",{room_id:state.groom,action:{fx:fx,fy:fy,tx:x,ty:y}});
        state.gsel=null;renderGamePanel();return;
      }
      showStatus("先点选己方棋子");
    };
  },
  xiangqi(box,s){
    const name={1:"帅",2:"仕",3:"相",4:"马",5:"车",6:"炮",7:"兵",
                11:"将",12:"士",13:"象",14:"马",15:"车",16:"炮",17:"卒"};
    const color=(code)=>code<=10?"#c22828":"#111";
    const sideOf=(code)=>code<=10?0:1;
    const onMove=GRENDER._clickMove(s,sideOf,null);
    GRENDER._move_click(box,s,10,9,(y,x)=>((y+x)%2?"#f4e8cf":"#e6d3b0"),
      code=>`<span style="color:${color(code)}">${name[code]}</span>`,onMove);
  },
  chess(box,s){
    const sym={1:"♔",2:"♕",3:"♖",4:"♗",5:"♘",6:"♙",11:"♚",12:"♛",13:"♜",14:"♝",15:"♞",16:"♟"};
    const sideOf=(code)=>code<=6?0:1;
    const onMove=GRENDER._clickMove(s,sideOf,null);
    GRENDER._move_click(box,s,8,8,(y,x)=>((y+x)%2?"#eee":"#aaa"),
      code=>sym[code],onMove);
  },
  go(box,s){
    const n=s.size||9;
    const cell=26, pad=8, W=n*cell+pad*2;
    const sc=s.scores||[0,0];
    const info=document.createElement("div");info.style.cssText="text-align:center;margin-bottom:4px;font-size:13px";
    info.innerHTML=(s.winner_uid!=null?"🏆 "+esc(gnick(s.winner_uid))+" 胜"
      :(s.over?"终局　":"轮到 "+esc(gnick(s.turn_uid))+(s.turn_uid===state.uid?"（你）":""))
      +`　⚫ ${sc[0]} ⚪ ${sc[1]}`);
    box.appendChild(info);
    const cv=document.createElement("canvas");cv.width=W;cv.height=W;
    cv.style.cssText="display:block;margin:0 auto;background:#d9a45b;border-radius:6px;cursor:pointer";
    box.appendChild(cv);
    const ctx=cv.getContext("2d");
    ctx.strokeStyle="#333";ctx.lineWidth=1;
    ctx.strokeRect(pad-0.5,pad-0.5,(n-1)*cell+1,(n-1)*cell+1);
    for(let i=1;i<n-1;i++){
      ctx.beginPath();ctx.moveTo(pad+i*cell,pad);ctx.lineTo(pad+i*cell,W-pad);ctx.stroke();
      ctx.beginPath();ctx.moveTo(pad,pad+i*cell);ctx.lineTo(W-pad,pad+i*cell);ctx.stroke();
    }
    for(let y=0;y<n;y++)for(let x=0;x<n;x++){
      const v=s.board[y][x];if(!v)continue;
      ctx.beginPath();ctx.arc(pad+x*cell,pad+y*cell,cell*0.42,0,2*Math.PI);
      ctx.fillStyle=v===1?"#111":"#fff";ctx.fill();ctx.stroke();
    }
    if(s.last_move){ctx.beginPath();
      ctx.arc(pad+s.last_move[0]*cell,pad+s.last_move[1]*cell,3,0,2*Math.PI);
      ctx.fillStyle="#e22";ctx.fill();}
    if(!s.over&&s.winner_uid==null)
      cv.onclick=e=>{const r=cv.getBoundingClientRect();
        const x=Math.round((e.clientX-r.left-pad)/cell),y=Math.round((e.clientY-r.top-pad)/cell);
        if(x<0||y<0||x>=n||y>=n)return;
        gameAPI("action",{room_id:state.groom,action:{x:x,y:y}});};
    const bar=document.createElement("div");bar.style.cssText="display:flex;gap:6px;justify-content:center;margin-top:10px";
    if(!s.over&&s.winner_uid==null)bar.appendChild(gBtn("👋 过",()=>gameAPI("action",{room_id:state.groom,action:{pass:true}})));
    box.appendChild(bar);
  },
  shogi(box,s){
    const sym={1:"玉",2:"飛",3:"角",4:"金",5:"銀",6:"桂",7:"香",8:"歩",9:"龍",10:"馬",
               11:"玉",12:"飛",13:"角",14:"金",15:"銀",16:"桂",17:"香",18:"歩",19:"龍",20:"馬"};
    const color=(code)=>code<=10?"#111":"#c22";
    const sideOf=(code)=>code<=10?0:1;
    const mySide=(s.players[0]===state.uid)?0:1;
    const onMove=(x,y,code)=>{
      if(state.gdrop!=null){
        gameAPI("action",{room_id:state.groom,action:{op:"drop",t:state.gdrop,x:x,y:y}});
        state.gdrop=null;state.gsel=null;renderGamePanel();return;
      }
      if(!state.gsel && code && sideOf(code)===mySide){
        state.gsel=[x,y];renderGamePanel();return;
      }
      if(state.gsel){
        const [fx,fy]=state.gsel;
        gameAPI("action",{room_id:state.groom,action:{fx:fx,fy:fy,tx:x,ty:y}});
        state.gsel=null;renderGamePanel();return;
      }
      showStatus("先点选己方棋子");
    };
    GRENDER._move_click(box,s,9,9,(y,x)=>((y+x)%2?"#f1f1f1":"#ddd"),
      code=>`<span style="color:${color(code)};font-weight:bold">${sym[code]}</span>`,onMove);
    if(s.hand&&s.winner_uid==null){
      const my_hand=s.hand[String(mySide)]||[];
      if(my_hand.length){
        const z=document.createElement("div");z.style.cssText="margin-top:8px;text-align:center";
        z.innerHTML="<b style='font-size:13px'>你的持子：</b> ";
        my_hand.forEach(t=>{
          const b=document.createElement("button");b.className="gbtn"+(state.gdrop===t?" go":"");
          b.textContent=sym[t];
          b.onclick=()=>{state.gdrop=t;state.gsel=null;renderGamePanel();};
          z.appendChild(b);
        });
        box.appendChild(z);
      }
    }
  },
  junqi(box,s){
    const name = {0:"🚩",1:"💣",2:"💥",3:"🔧",4:"排",5:"连",6:"营",7:"团",8:"旅",9:"师",10:"军",11:"司"};
    const rankOf = code=>code>=40?(code-40):(code-10);
    const sideOf = code=>code>=40?1:0;
    const mySide=(s.players[0]===state.uid)?0:1;
    const onMove=(x,y,code)=>{
      if(!state.gsel && code && sideOf(code)===mySide){
        if(rankOf(code)<=1)return;                 // 军旗/地雷不能动
        state.gsel=[x,y];renderGamePanel();return;
      }
      if(state.gsel){
        const [fx,fy]=state.gsel;
        gameAPI("action",{room_id:state.groom,action:{fx:fx,fy:fy,tx:x,ty:y}});
        state.gsel=null;renderGamePanel();return;
      }
      showStatus("先点选己方可移动棋子");
    };
    GRENDER._move_click(box,s,10,5,(y,x)=>y<5?"#e8f0ff":"#ffe8e8",
      code=>name[rankOf(code)],onMove);
  },
  dou(box,s){
    const emoj={1:"🐭",2:"🐱",3:"🐶",4:"🐺",5:"🐆",6:"🐅",7:"🦁",8:"🐘"};
    const sideOf = code=>code>8?1:0;
    const animalOf = code=>code>8?(code-10):code;
    const mySide=(s.players[0]===state.uid)?0:1;
    const onMove=(x,y,code)=>{
      if(!state.gsel && code && sideOf(code)===mySide){
        state.gsel=[x,y];renderGamePanel();return;
      }
      if(state.gsel){
        const [fx,fy]=state.gsel;
        gameAPI("action",{room_id:state.groom,action:{fx:fx,fy:fy,tx:x,ty:y}});
        state.gsel=null;renderGamePanel();return;
      }
      showStatus("先点选己方动物");
    };
    GRENDER._move_click(box,s,s.rows,s.cols,(y,x)=>s.water[y][x]?"#7ec8f7":"#dfb87c",
      code=>emoj[animalOf(code)],onMove);
  },
  coc(box,s){
    // 阶段 1：setup 选卡
    if(s.phase==="setup"){
      const pv=state.gpriv||{};
      const deck=pv.deck||[];
      const picked=s.picked||{};
      const remaining=(s.players||[]).length-Object.keys(picked).length;
      const t=document.createElement("div");t.style.cssText="text-align:center;padding:6px";
      t.innerHTML="<div class='gsec'>🔰 选择调查员 · KP："+esc(gnick(s.kp_uid))
        +"　<span style='color:var(--dim)'>剩余 "+remaining+" 人未选</span></div>";
      box.appendChild(t);
      const grid=document.createElement("div");
      grid.style.cssText="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0";
      deck.forEach(c=>{
        const cid=c.id;if(picked[cid])return;   // 已被他人选走，不显示
        const el=document.createElement("div");el.className="gcard";
        el.innerHTML="<div style='height:40px;border-radius:8px;margin:-8px -8px 6px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#1f5236,#123022);font-size:22px'>"+c.emoji+"</div>"
          +"<b>"+esc(c.name)+"</b><span style='color:var(--dim);font-size:11px'>"+esc(c.desc||"")+"</span>";
        const b=document.createElement("button");b.className="gbtn go";b.textContent="选这张卡";
        b.onclick=()=>{gameAPI("action",{room_id:state.groom,action:{op:"choose_card",card_id:cid}});renderGamePanel()};
        el.appendChild(b);grid.appendChild(el);});
      if(!deck.length)grid.innerHTML="<div style='color:var(--dim)'>没有可选调查员（可能都已选）</div>";
      box.appendChild(grid);
      if(s.kp_uid===state.uid){
        const bar=document.createElement("div");bar.style.cssText="margin:8px 0;text-align:center";
        const b=document.createElement("button");b.className="gbtn go";b.textContent="🎭 开始调查";
        b.onclick=()=>{gameAPI("action",{room_id:state.groom,action:{op:"begin"}});renderGamePanel()};
        bar.appendChild(b);box.appendChild(bar);}
      if(remaining>0){const w=document.createElement("div");w.style.cssText="color:var(--dim);font-size:12px;text-align:center";
        w.textContent="等待全部玩家选卡后由 KP 开始…";box.appendChild(w);}
      return;
    }
    // 阶段 2：play 自由剧情
    const isKP=s.kp_uid===state.uid;
    const kb=document.createElement("div");
    kb.style.cssText="border-radius:10px;padding:8px 12px;margin-bottom:8px;color:#fff;background:linear-gradient(135deg,#1f5236,#123022)";
    kb.innerHTML="🕰️ KP："+esc(gnick(s.kp_uid))+(isKP?"（你）":"");
    box.appendChild(kb);
    if(s.scene){
      const sc=document.createElement("div");sc.style.cssText="margin:6px 0;padding:8px;border:1px solid var(--line,#eee);border-radius:8px;background:rgba(0,0,0,.03)";
      sc.innerHTML="🗒️ <b>场景</b>："+esc(s.scene);box.appendChild(sc);}
    const logs=document.createElement("div");logs.style.cssText="margin:6px 0;font-size:12px;max-height:140px;overflow:auto";
    logs.innerHTML="<span class='gsec'>剧情/检定记录</span>"+((s.logs||[]).slice(-12).map(l=>"<div class='glogl'>"+esc(l)+"</div>").join("")||"<div style='color:var(--dim)'>暂无记录</div>");
    box.appendChild(logs);
    const bar=document.createElement("div");bar.style.cssText="margin:8px 0;display:flex;flex-wrap:wrap;gap:6px";
    const inp=document.createElement("input");inp.placeholder="输入技能名（如 侦查）";
    inp.style.cssText="flex:1;min-width:130px;border:1px solid var(--line,#ddd);border-radius:8px;padding:5px 8px";
    const go=document.createElement("button");go.className="gbtn go";go.textContent="🎲 检定";
    go.onclick=()=>{const v=inp.value.trim();if(!v){showStatus("请输入技能名");return}
      gameAPI("action",{room_id:state.groom,action:{op:"check",skill:v}});inp.value="";};
    bar.append(inp,go);
    box.appendChild(bar);
    if(isKP){
      const sb=document.createElement("div");sb.style.cssText="margin:6px 0;display:flex;gap:6px";
      const si=document.createElement("input");si.placeholder="输入新场景文案";
      si.style.cssText="flex:1;min-width:140px;border:1px solid var(--line,#ddd);border-radius:8px;padding:5px 8px";
      const sbg=document.createElement("button");sbg.className="gbtn";sbg.textContent="🗒️ 更新场景";
      sbg.onclick=()=>{const v=si.value.trim();if(!v){showStatus("场景不能为空");return}
        gameAPI("action",{room_id:state.groom,action:{op:"set_scene",scene:v}});si.value="";};
      sb.append(si,sbg);box.appendChild(sb);
      const eb=document.createElement("button");eb.className="gbtn";eb.textContent="🏁 结束调查";
      eb.onclick=()=>{gameAPI("action",{room_id:state.groom,action:{op:"end"}});renderGamePanel()};
      box.appendChild(eb);
    }
  },
  balatro(box,s){
    // 小丑牌 Balatro · Web 端主游戏区渲染（暗红绒布牌桌 + 复古街机画风）
    const me=state.uid, num=u=>+u;
    const g=(u,k,d)=>{const x=s[k];if(x==null)return d;return x[u]!=null?x[u]:x[""+u];};
    const n=u=>esc(gnick(num(u)));
    const SU={h:"♥",s:"♠",d:"♦",c:"♣"};
    const RANK={T:"10"};
    const isRed=c=>c.s==="h"||c.s==="d";
    const rk=c=>RANK[c.c]||c.c;
    const jd={pair:["对子王","含对子得分×2"],flush:["同花狂热","同花得分×3"],straight:["顺子推进","顺子得分×3"],sf:["同花顺神","同花顺得分×5"],four:["四条杀神","四条得分×4"],full:["葫芦压阵","葫芦得分×3"],heart:["红心暖手","有♥时 +30"],spade:["黑桃猎手","有♠时 +20"]};
    if(!document.getElementById("bzstyle")){
      const st=document.createElement("style");st.id="bzstyle";
      st.textContent=`.bz{padding:10px;border-radius:14px;background:radial-gradient(120% 90% at 18% 0%,rgba(255,42,157,.16),transparent 50%),radial-gradient(120% 90% at 85% 100%,rgba(24,217,200,.15),transparent 50%),radial-gradient(70% 60% at 50% 45%,rgba(143,91,255,.12),transparent 60%),linear-gradient(160deg,#241448,#150a30,#0a0516);color:#f3e6c8;box-shadow:inset 0 0 90px rgba(0,0,0,.5),0 0 0 1px #18d9c8,0 0 22px rgba(24,217,200,.25),0 0 0 2px rgba(255,42,157,.35),var(--shadow-lg);font-family:system-ui,-apple-system,sans-serif}
.bcc{position:relative;width:50px;height:72px;background:linear-gradient(180deg,#fffdf6,#f2ead6);border-radius:6px;box-shadow:0 2px 5px rgba(0,0,0,.45),inset 0 0 0 1px #e8dcbc;display:inline-block;vertical-align:top;user-select:none;margin:0 1px}
.bcc .bct{position:absolute;top:3px;left:5px;font-size:12px;font-weight:800;line-height:1;text-align:center}
.bcc .bcm{position:absolute;left:0;right:0;top:34%;text-align:center;font-size:26px}
.bcc .bcbr{position:absolute;bottom:3px;right:5px;font-size:12px;font-weight:800;line-height:1;text-align:center;transform:rotate(180deg)}
.bch{cursor:pointer;transition:transform .12s cubic-bezier(.2,1.4,.4,1),box-shadow .12s ease}
.bch:hover{transform:translateY(-8px);box-shadow:0 12px 18px rgba(0,0,0,.5)}
.bch.on{outline:3px solid #ffd977;transform:translateY(-5px)}
.bslot{width:56px;height:80px;border:2px dashed rgba(255,217,119,.55);border-radius:8px;background:rgba(0,0,0,.16);display:inline-block;margin:2px 3px;vertical-align:top;text-align:center;color:#ffd977;font-size:24px;line-height:80px;box-shadow:inset 0 0 12px rgba(255,217,119,.12)}
.bslot.fill{border-style:solid;border-color:#ffd977;background:linear-gradient(180deg,rgba(255,217,119,.18),transparent);line-height:normal;padding-top:3px;box-shadow:inset 0 0 14px rgba(255,217,119,.22)}
.bslot .bcc{width:48px;height:68px;box-shadow:0 0 0 2px #ffd977,0 3px 8px rgba(0,0,0,.5)}
.bjs{width:118px;height:64px;border-radius:9px;background:linear-gradient(150deg,#3d116d,#180a33);border:2px solid #c9a227;color:#ffe9a8;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;box-shadow:0 2px 8px rgba(0,0,0,.5),0 0 16px rgba(143,91,255,.30),0 0 0 1px rgba(255,255,255,.07);padding:3px 4px;text-align:center;transition:transform .15s ease,box-shadow .2s ease,border-color .2s ease}
.bjs:hover{transform:translateY(-2px);border-color:#ffd977;box-shadow:0 0 14px 3px rgba(255,217,119,.6),0 0 0 2px #ffd977,0 6px 14px rgba(0,0,0,.55)}
.bfloat{position:absolute;left:50%;top:24px;transform:translateX(-50%);font-size:22px;font-weight:800;color:#ffd977;text-shadow:0 0 10px rgba(255,217,119,.9),0 2px 0 rgba(0,0,0,.5);pointer-events:none;white-space:nowrap;z-index:9;animation:bfloat .7s cubic-bezier(.17,.84,.44,1) forwards}
@keyframes bfloat{0%{opacity:0;transform:translateX(-50%) translateY(8px) scale(.9)}14%{opacity:1;transform:translateX(-50%) translateY(0) scale(1.06)}100%{opacity:0;transform:translateX(-50%) translateY(-46px) scale(1)}}
.bdat{border:2px solid rgba(255,217,119,.45);border-radius:12px;padding:8px 10px;background:rgba(0,0,0,.28);display:inline-block;text-align:center}
.bgold{color:#ffd977}`;
      document.head.appendChild(st);
    }
    const myTurn=(s.turn!=null)&&num(s.turn)===num(me);
    const pv=state.gpriv||{};
    const myHand=pv.hand||[];
    const selSet={};(pv.sel||[]).forEach(id=>selSet[id]=true);
    const mySelC=(pv.sel||[]).map(id=>myHand.find(c=>c.id===id)).filter(Boolean);
    function makeCard(c,onClick,on){
      const el=document.createElement("div");
      el.className="bcc"+((onClick?" bch":"")+(on?" on":""));
      el.style.color=isRed(c)?"#c92a2a":"#1f1f24";
      el.innerHTML="<span class='bct'>"+rk(c)+"<br>"+SU[c.s]+"</span>"
        +"<span class='bcm'>"+SU[c.s]+"</span>"
        +"<span class='bcbr'>"+rk(c)+SU[c.s]+"</span>";
      if(onClick)el.onclick=onClick;
      return el;
    }
    const root=document.createElement("div");root.className="bz";
    // 顶部：盲注金边条
    const top=document.createElement("div");
    top.style.cssText="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;padding:7px 12px;background:linear-gradient(135deg,#8a6a1c,#55420f);border:1px solid #e3c15c;border-radius:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.25),0 2px 8px rgba(0,0,0,.4)";
    top.innerHTML="<span style='font-weight:800;color:#1c1506;letter-spacing:1px'>BLIND <span style='font-size:16px'>"+s.blind+"</span> <span style='font-size:10px;opacity:.7'>· ROUND</span></span>"
      +"<span class='bgold' style='font-size:12px'>▶ 轮到 "+(s.turn==null?"—":(num(s.turn)===num(me)?"你":n(s.turn)))+"</span>";
    root.appendChild(top);
    // 玩家信息条
    const pb=document.createElement("div");pb.style.cssText="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px";
    (s.players||[]).forEach(u=>{
      const isT=num(u)===num(s.turn), isMe=num(u)===num(me), dead=!(s.alive||[]).includes(num(u));
      const c=document.createElement("div");
      c.style.cssText="flex:1;min-width:118px;padding:6px 8px;border-radius:8px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.14)"+(isT?";border-color:#ffd977;box-shadow:0 0 0 1px #ffd977":"");
      c.innerHTML="<div style='display:flex;justify-content:space-between;align-items:center'>"
        +"<b style='font-size:12px'>"+n(u)+(isMe?"（你）":"")+"</b>"
        +"<span class='bgold' style='font-size:11px'>"+g(u,"score",0)+" 筹码</span></div>"
        +"<div style='margin-top:3px;font-size:11px'>🩸"+g(u,"hp",0)
        +(g(u,"cleared",false)?" ✨已过":"")
        +(dead?" ☠️":(isT?" ⏳":""))
        +"　🂠"+g(u,"hand_size",0)+"张　◆"+g(u,"sel_size",0)+"</div>";
      pb.appendChild(c);});
    root.appendChild(pb);
    // 出战区（5 槽位），显示自己已选牌
    const area=document.createElement("div");area.style.cssText="margin-top:10px;text-align:center;position:relative";
    area.innerHTML="<div class='bdat'><div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:4px'>PLAY · 出战区 "+(mySelC.length)+"/5</div>"
      +[0,1,2,3,4].map(i=>{
        const c=mySelC[i];
        if(c){const el=document.createElement("span");el.className="bslot fill";el.appendChild(makeCard(c));return el.outerHTML;}
        return "<span class='bslot'>"+(i+1)+"</span>";}).join("")+"</div>";
    root.appendChild(area);
    // 结算加分 → 出战区上飘（CSS animation；balatroLastScore 为前端状态）
    const ms0=g(me,"score",0);
    if(state.balatroLastScore==null)state.balatroLastScore=ms0;
    const dS=ms0-state.balatroLastScore;state.balatroLastScore=ms0;
    if(dS>0){
      const f=document.createElement("div");f.className="bfloat";
      f.textContent="+"+dS;
      area.appendChild(f);
      setTimeout(()=>{try{f.remove();}catch(e){}},760);
    }
    // 手牌（私有），仅在轮到自己时可交互
    if(pv.hand){
      const hw=document.createElement("div");hw.style.cssText="margin-top:10px;text-align:center";
      hw.innerHTML="<div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:4px'>YOUR HAND · 你的手牌</div>";
      const row=document.createElement("div");row.style.cssText="display:flex;flex-wrap:wrap;justify-content:center;align-items:flex-end";
      pv.hand.forEach(c=>{
        const on=!!selSet[c.id];
        const wrap=document.createElement("span");wrap.style.cssText="display:inline-flex;flex-direction:column;align-items:center;margin:0 1px";
        const el=makeCard(c,myTurn?(()=>{gameAPI("action",{room_id:state.groom,action:on?{op:"unselect",cid:c.id}:{op:"select",cid:c.id}})}):null,on);
        wrap.appendChild(el);
        if(myTurn){
          const db=document.createElement("button");db.className="gbtn";
          db.style.cssText="font-size:10px;line-height:1;padding:2px 6px;margin-top:3px";
          db.textContent="🗑 弃牌";
          db.disabled=on;
          db.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"discard",cid:c.id}});
          wrap.appendChild(db);}
        row.appendChild(wrap);});
      hw.appendChild(row);root.appendChild(hw);
    } else {
      const w=document.createElement("div");w.style.cssText="margin-top:10px;text-align:center;color:#d9c6a5;font-size:12px";
      w.textContent="🂠 手牌："+g(me,"hand_size",0)+" 张";root.appendChild(w);}
    // 操作条
    if(myTurn){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:8px;justify-content:center;margin:12px 0 2px;flex-wrap:wrap";
      const play=document.createElement("button");
      play.style.cssText="padding:7px 18px;border:none;border-radius:9px;font-weight:800;font-size:13px;color:#3a2a05;background:linear-gradient(180deg,#ffe9a0,#e6b84f);cursor:pointer;box-shadow:0 2px 8px rgba(230,184,79,.5)";
      play.textContent="🎰 出牌结算";
      play.disabled=(pv.sel||[]).length===0;
      play.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"play"}});
      bar.appendChild(play);
      const tip=document.createElement("span");tip.style.cssText="color:#d9c6a5;font-size:11px;align-self:center";
      tip.textContent="点牌=选入出战区 / 再点=撤回，"+(pv.sel||[]).length+" 张已选中";bar.appendChild(tip);
      root.appendChild(bar);}
    else if(s.turn!=null){
      const w=document.createElement("div");w.style.cssText="margin-top:10px;text-align:center;color:#d9c6a5;font-size:12px";
      w.textContent="⏳ 等待 "+n(s.turn)+" 出牌结算…（其余玩家手牌保密，仅见张数）";root.appendChild(w);}
    // 我的小丑牌
    const jl=s.jokers||{};const myj=jl[""+me]||jl[me]||[];
    if(myj.length){
      const jw=document.createElement("div");jw.style.cssText="margin-top:12px;text-align:center";
      jw.innerHTML="<div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:5px'>🎭 YOUR JOKERS · 小丑特效</div>";
      const jrow=document.createElement("div");jrow.style.cssText="display:flex;flex-wrap:wrap;justify-content:center;gap:6px";
      myj.forEach(id=>{const def=jd[id]||[id,""];
        const j=document.createElement("div");j.className="bjs";
        // 三层：图案层（圆底徽）→ 名字层（金氰字）→ 描述层（小字）
        j.innerHTML="<div style='width:26px;height:26px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#7a44c8,#2a1150);border:1px solid rgba(255,217,119,.6);display:flex;align-items:center;justify-content:center;font-size:15px;line-height:1;flex:none'>🎭</div><b style='font-size:11px;letter-spacing:.5px;line-height:1.15'>"+esc(def[0])+"</b><span style='font-size:8.5px;opacity:.92;line-height:1.15;padding:0 2px'>"+esc(def[1])+"</span>";
        jrow.appendChild(j);});
      jw.appendChild(jrow);root.appendChild(jw);}
    // 胜负
    if(s.done&&s.winner!=null){
      const w=document.createElement("div");w.style.cssText="margin-top:12px;text-align:center;font-weight:800;font-size:16px;color:#ffd977";
      w.textContent="🏆 "+esc(gnick(s.winner))+" 获胜！";root.appendChild(w);}
    box.appendChild(root);
  },
  balatro_solo(box,s){
    // 小丑牌·单人闯关 · Web 端（复用 .bz/.bcc/.bch/.bjs CSS，扩展 金币/卡角标/消耗品/商店）
    const me=state.uid, num=u=>+u;
    const g=(u,k,d)=>{const x=s[k];if(x==null)return d;return x[u]!=null?x[u]:x[""+u];};
    const SU={h:"♥",s:"♠",d:"♦",c:"♣"};
    const RANK={T:"10"};
    const isRed=c=>c.s==="h"||c.s==="d";
    const rk=c=>RANK[c.c]||c.c;
    const jd={pair:["对子王","打出对子时 得分×2"],triple:["三条锋芒","打出三条时 得分×3"],flush:["同花狂热","打出同花时 得分×3"],straight:["顺子推进","打出顺子时 得分×3"],sf:["同花顺神","开出同花顺时 得分×5"],full:["葫芦压阵","开出葫芦时 得分×4"],four:["四条杀神","开出四条时 得分×5"],heart_x:["红心领域","出战含♥时 得分×2"],spade_x:["黑桃锋芒","出战含♠时 得分×2"],diamond_x:["方块棱晶","出战含♦时 得分×2"],club_x:["梅花壁垒","出战含♣时 得分×2"],heart:["红心暖手","有♥时 +30 chips"],spade:["黑桃猎手","有♠时 +20 chips"],pairadd:["对子核心","打出对子时 +30 chips"],flushadd:["同花洪流","打出同花时 +90 chips"],straightadd:["顺子疾风","打出顺子时 +60 chips"],face:["脸牌大王","出战含 J/Q/K 时 得分×3"],xmult:["万乘之灵","所有牌型 得分×1.5"],growth:["枯木逢春","每破一盲注 得分永久×1.1"],discard:["弃牌回收","本盲注每弃一次 +40 chips"],highcard:["白手起家","打出高牌时 +100 chips"],random:["命运骰子","得分随机 ×2~×4"]};
    const JRR={pair:"c",triple:"c",flush:"c",straight:"c",heart_x:"c",spade_x:"c",diamond_x:"c",club_x:"c",heart:"c",spade:"c",pairadd:"c",full:"u",flushadd:"u",straightadd:"u",face:"u",discard:"u",random:"u",sf:"r",four:"r",xmult:"r",growth:"r",highcard:"r"};
    const JRC={c:["白","#c9cfd8","#5a5f6e"],u:["青","#4fc3f7","#1f5a86"],r:["金","#ffd54f","#8a6a1c"]};
    const HCN={sf:"同花顺",four:"四条",full:"葫芦",flush:"同花",straight:"顺子",triple:"三条",two_pair:"两对",pair:"对子",high:"高牌"};
    const ED={foil:["箔","#e6b64c"],holo:["全","#4fc3f7"],poly:["彩","#e06ac8"]};
    const EN={bonus:["宝","#1a5f8a"],mult:["曙","#c98a3d"],face:["节","#8a5fbf"],glass:["琉","#37a25f"],stone:["磐","#5a6a7a"],steel:["钢","#a0a0a0"]};
    const SE={red:["赤","#c0392b"],gold:["金","#e6b64c"],purple:["紫","#8a4fc0"]};
    const CONS={ct_bonus:["宝珠卷","塔罗","enh"],ct_mult:["曙光卷","塔罗","enh"],ct_face:["节庆卷","塔罗","enh"],ct_glass:["琉璃卷","塔罗","enh"],ct_foil:["箔之炼","塔罗","edition"],ct_holo:["全息术","塔罗","edition"],ct_strength:["升阶","塔罗","rank"],cp_pair:["星辉·对子","星球","level"],cp_flush:["星辉·同花","星球","level"],cp_straight:["星辉·顺子","星球","level"],cp_full:["星辉·葫芦","星球","level"],cs_grim:["冥狱","灵体","destroy_joker"],cs_cash:["碎镜","灵体","destroy_cash"],cs_dupe:["双生","灵体","destroy_dupe"]};
    const NEEDS={enh:1,edition:1,rank:1,"destroy_joker":1,"destroy_dupe":1};
    const CCR={塔罗:["#6a4a12","#ffe9b0"],星球:["#165e5a","#a7efe0"],灵体:["#5e1230","#ffc2d1"]};
    if(!document.getElementById("bzstyle")){
      const st=document.createElement("style");st.id="bzstyle";
      st.textContent=`.bz{padding:10px;border-radius:14px;background:radial-gradient(120% 90% at 18% 0%,rgba(255,42,157,.16),transparent 50%),radial-gradient(120% 90% at 85% 100%,rgba(24,217,200,.15),transparent 50%),radial-gradient(70% 60% at 50% 45%,rgba(143,91,255,.12),transparent 60%),linear-gradient(160deg,#241448,#150a30,#0a0516);color:#f3e6c8;box-shadow:inset 0 0 90px rgba(0,0,0,.5),0 0 0 1px #18d9c8,0 0 22px rgba(24,217,200,.25),0 0 0 2px rgba(255,42,157,.35),var(--shadow-lg);font-family:system-ui,-apple-system,sans-serif}
.bcc{position:relative;width:50px;height:72px;background:linear-gradient(180deg,#fffdf6,#f2ead6);border-radius:6px;box-shadow:0 2px 5px rgba(0,0,0,.45),inset 0 0 0 1px #e8dcbc;display:inline-block;vertical-align:top;user-select:none;margin:0 1px}
.bcc .bct{position:absolute;top:3px;left:5px;font-size:12px;font-weight:800;line-height:1;text-align:center}
.bcc .bcm{position:absolute;left:0;right:0;top:34%;text-align:center;font-size:26px}
.bcc .bcbr{position:absolute;bottom:3px;right:5px;font-size:12px;font-weight:800;line-height:1;text-align:center;transform:rotate(180deg)}
.bch{cursor:pointer;transition:transform .12s cubic-bezier(.2,1.4,.4,1),box-shadow .12s ease}
.bch:hover{transform:translateY(-8px);box-shadow:0 12px 18px rgba(0,0,0,.5)}
.bch.on{outline:3px solid #ffd977;transform:translateY(-5px)}
.bslot{width:56px;height:80px;border:2px dashed rgba(255,217,119,.55);border-radius:8px;background:rgba(0,0,0,.16);display:inline-block;margin:2px 3px;vertical-align:top;text-align:center;color:#ffd977;font-size:24px;line-height:80px;box-shadow:inset 0 0 12px rgba(255,217,119,.12)}
.bslot.fill{border-style:solid;border-color:#ffd977;background:linear-gradient(180deg,rgba(255,217,119,.18),transparent);line-height:normal;padding-top:3px;box-shadow:inset 0 0 14px rgba(255,217,119,.22)}
.bslot .bcc{width:48px;height:68px;box-shadow:0 0 0 2px #ffd977,0 3px 8px rgba(0,0,0,.5)}
.bjs{width:118px;height:64px;border-radius:9px;background:linear-gradient(150deg,#3d116d,#180a33);border:2px solid #c9a227;color:#ffe9a8;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;box-shadow:0 2px 8px rgba(0,0,0,.5),0 0 16px rgba(143,91,255,.30),0 0 0 1px rgba(255,255,255,.07);padding:3px 4px;text-align:center;transition:transform .15s ease,box-shadow .2s ease,border-color .2s ease}
.bjs:hover{transform:translateY(-2px);border-color:#ffd977;box-shadow:0 0 14px 3px rgba(255,217,119,.6),0 0 0 2px #ffd977,0 6px 14px rgba(0,0,0,.55)}
.bfloat{position:absolute;left:50%;top:24px;transform:translateX(-50%);font-size:22px;font-weight:800;color:#ffd977;text-shadow:0 0 10px rgba(255,217,119,.9),0 2px 0 rgba(0,0,0,.5);pointer-events:none;white-space:nowrap;z-index:9;animation:bfloat .7s cubic-bezier(.17,.84,.44,1) forwards}
@keyframes bfloat{0%{opacity:0;transform:translateX(-50%) translateY(8px) scale(.9)}14%{opacity:1;transform:translateX(-50%) translateY(0) scale(1.06)}100%{opacity:0;transform:translateX(-50%) translateY(-46px) scale(1)}}
.bdat{border:2px solid rgba(255,217,119,.45);border-radius:12px;padding:8px 10px;background:rgba(0,0,0,.28);display:inline-block;text-align:center}
.bgold{color:#ffd977}
.b-badge{position:absolute;font-size:8px;font-weight:800;line-height:12px;padding:0 2px;border-radius:4px;text-align:center;border:1px solid}
.b-edit{top:2px;right:2px;background:rgba(42,31,14,.9);color:#ffd75e;border-color:#e6b64c}
.b-enh{left:2px;bottom:2px;background:#1a5f8a;color:#fff;border-color:#7fd1ff;width:13px;height:13px;line-height:12px;padding:0}
.b-seal{right:2px;bottom:2px;background:#5e1230;color:#ffc2d1;border-color:#ff6f91}
.bcons{display:inline-block;min-width:64px;padding:4px 6px;border-radius:8px;border:1px solid #e6b64c;color:#ffe9b0;text-align:center;cursor:pointer;user-select:none;margin:0 3px;transition:box-shadow .12s}
.bcons:hover{box-shadow:0 0 10px 2px rgba(255,217,119,.4)}
.bcons.on{outline:2px solid #ffd977;box-shadow:0 0 10px 2px rgba(255,217,119,.6)}
.bshop{border:2px solid #e3c15c;border-radius:14px;margin-top:12px;padding:10px;background:linear-gradient(180deg,rgba(60,15,20,.8),rgba(20,8,24,.85));box-shadow:inset 0 0 40px rgba(0,0,0,.4)}
.bitem{display:flex;align-items:center;justify-content:space-between;border-radius:8px;padding:7px 10px;margin:6px 0;background:rgba(0,0,0,.28);cursor:pointer;border:1px solid rgba(255,255,255,.12);transition:box-shadow .12s}
.bitem:hover{box-shadow:0 0 8px 1px rgba(255,217,119,.35)}
.bitem.sold{opacity:.4;cursor:not-allowed}
.bitem b{font-size:12px}
.bitem .pr{color:#ffd977;font-size:11px;white-space:nowrap}`;
      document.head.appendChild(st);
    }
    const pv=state.gpriv||{};
    const myHand=pv.hand||[];
    const selSet={};(pv.sel||[]).forEach(id=>selSet[id]=true);
    const mySelC=(pv.sel||[]).map(id=>myHand.find(c=>c.id===id)).filter(Boolean);
    function makeCard(c,onClick,on){
      const el=document.createElement("div");
      el.className="bcc"+((onClick?" bch":"")+(on?" on":""));
      el.style.color=isRed(c)?"#c92a2a":"#1f1f24";
      let badges="";
      if(c.edt&&ED[c.edt]){const d=ED[c.edt];badges+="<div class='b-badge b-edit' style='color:"+d[1]+";border-color:"+d[1]+"'>"+d[0]+"</div>";}
      if(c.enh&&EN[c.enh]){const d=EN[c.enh];badges+="<div class='b-badge b-enh' style='color:"+d[1]+";border-color:"+d[1]+"'>"+d[0]+"</div>";}
      if(c.seal&&SE[c.seal]){const d=SE[c.seal];badges+="<div class='b-badge b-seal' style='color:"+d[1]+";border-color:"+d[1]+"'>"+d[0]+"</div>";}
      el.innerHTML="<span class='bct'>"+rk(c)+"<br>"+SU[c.s]+"</span>"
        +"<span class='bcm'>"+SU[c.s]+"</span>"
        +"<span class='bcbr'>"+rk(c)+SU[c.s]+"</span>"
        +badges;
      if(c.edt&&ED[c.edt]){ // 全息/箔饰/多彩 → 卡牌霓虹发光
        const ec=ED[c.edt][1];
        el.style.boxShadow="0 0 10px 1px "+ec+", 0 0 0 2px "+ec+", 0 3px 8px rgba(0,0,0,.5)";
      }
      if(onClick)el.onclick=onClick;
      return el;
    }
    const root=document.createElement("div");root.className="bz";
    const done=!!s.done, winner=s.winner;
    const blind=s.blind||1, tgt=s.blind_target||0, lives=s.lives||0;
    const hu=s.hands_used||0, hm=s.hands_max||4;
    const cur=g(me,"score",0)||0;
    const hearts=("❤").repeat(Math.max(0,lives))+("🖤").repeat(Math.max(0,3-lives));
    // 顶部：盲注金边条（加【桥/层/Ante】＋店铺阶段）
    const top=document.createElement("div");
    top.style.cssText="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;padding:7px 12px;background:linear-gradient(135deg,#8a6a1c,#55420f);border:1px solid #e3c15c;border-radius:10px;box-shadow:inset 0 1px 0 rgba(255,255,255,.25),0 2px 8px rgba(0,0,0,.4)";
    const tTitle=done&&winner!=null?"🏆 第 "+blind+" 桥 · 全部通关夺冠！"
      :done?"💀 第 "+blind+" 桥 · 生命归零，本局结束"
      :"第 "+blind+"/"+(s.max_blind||18)+" 桥 · "+esc(s.blind_layer||"")+" · Ante "+(s.blind_ante||1);
    top.innerHTML="<span style='font-weight:800;color:#1c1506;letter-spacing:1px'>第 <span style='font-size:16px'>"+blind+"/"+(s.max_blind||18)+"</span> 桥</span>"
      +"<span class='bgold' style='font-size:12px'>"+tTitle+"</span>";
    root.appendChild(top);
    // 单人信息条：❤命数 / 💰金币 / 出牌手数 / 目标进度（＋店铺标签）
    if(!done){
      const pb=document.createElement("div");
      pb.style.cssText="display:flex;align-items:center;justify-content:center;gap:14px;flex-wrap:wrap;margin-top:8px;padding:6px 10px;border-radius:8px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.14)";
      pb.innerHTML="<span style='font-size:12px'>"+hearts+"</span>"
        +"<span style='font-size:12px;color:#ffd977'>💰 "+s.dollars+" 金币</span>"
        +"<span style='font-size:12px;color:#d9c6a5'>🂠 已出 "+hu+"/"+hm+" 手</span>"
        +"<span style='font-size:12px'>🎯 目标 "+tgt+" · 累计 <b class='bgold'>"+cur+"</b></span>"
        +(s.passed?"<span style='font-size:11px;color:#7ee081'>✅已达标</span>":"")
        +(s.shop_phase?"<span style='font-size:11px;color:#ffd977'>🛒 商店中</span>":"");
      root.appendChild(pb);
      // 已升级牌型
      const hl=s.hand_level||{};
      if(Object.keys(hl).length){
        const hw2=document.createElement("div");
        hw2.style.cssText="margin-top:6px;text-align:center;color:#7ee081;font-size:11px";
        hw2.textContent="✨ 已升级牌型  "+Object.keys(hl).map(k=>"「"+(HCN[k]||k)+"」Lv"+hl[k]).join(" · ");
        root.appendChild(hw2);
      }
      // Boss 盲注 → 红色警告条（Boss 名 + debuff）
      if(s.is_boss){
        const bb=document.createElement("div");
        bb.style.cssText="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:6px;padding:5px 10px;border-radius:8px;background:rgba(120,20,20,.55);border:1px solid #ff6b6b;color:#ffb3b3;font-weight:700;font-size:12px;text-shadow:0 1px 0 rgba(0,0,0,.4)";
        bb.innerHTML="⚠ BOSS·"+esc(s.boss_name||"未知Boss")+"　<span style='color:#ffd0d0'>"+esc(s.boss_debuff||"")+"</span>";
        root.appendChild(bb);
      }
      // 商店面板（shop_phase 时弹出）
      if(s.shop_phase&&s.shop){
        const sp=document.createElement("div");sp.className="bshop";
        const sh=s.shop;
        const head=document.createElement("div");
        head.style.cssText="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap";
        head.innerHTML="<b style='font-size:15px;color:#ffd977'>🛒 商　店</b><span style='color:#ffe9b0;font-size:12px'>💰 "+s.dollars+" 金币</span>";
        const rbtn=document.createElement("button");rbtn.className="gbtn";
        rbtn.textContent="刷新 ⟳ "+sh.reroll_cost+" 💰";
        rbtn.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"reroll"}});
        head.appendChild(rbtn);sp.appendChild(head);
        const col=document.createElement("div");
        col.style.cssText="display:flex;gap:10px;flex-wrap:wrap";
        const jc=document.createElement("div");jc.style.cssText="flex:1;min-width:150px";
        jc.innerHTML="<div style='color:#ffd977;font-size:12px;font-weight:800;margin-bottom:2px'>🎭 Joker 商品</div>";
        (sh.jokers||[]).forEach((it,idx)=>{
          const rr=JRC[JRR[it.id]||"c"]||JRC.c;
          const itel=document.createElement("div");itel.className="bitem"+(it.sold?" sold":"");
          itel.style.borderColor=it.sold?"#555":rr[1];
          itel.innerHTML="<b style='color:"+(it.sold?"#888":"#ffe9b0")+"'>"+esc(it._nm||it.id)+"</b>"
            +"<span class='pr'>"+(it.sold?"已购":("💲"+it.price+" 💰"))+"</span>";
          if(!it.sold)itel.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"buy",what:"joker",idx:idx}});
          jc.appendChild(itel);
        });
        col.appendChild(jc);
        const cc2=document.createElement("div");cc2.style.cssText="flex:1;min-width:150px";
        cc2.innerHTML="<div style='color:#ffd977;font-size:12px;font-weight:800;margin-bottom:2px'>🧪 消耗品</div>";
        (sh.cons||[]).forEach((it,idx)=>{
          const cui=CCR[it.cat]||["#3a3a3a","#e0e0e0"];
          const itel=document.createElement("div");itel.className="bitem"+(it.sold?" sold":"");
          itel.style.borderColor=it.sold?"#555":"#e6b64c";
          itel.innerHTML="<b style='color:"+(it.sold?"#888":cui[1])+"'>"+esc(it._nm||it.id)+"</b>"
            +"<span class='pr'>"+(it.sold?"已购":("💲"+it.price+" 💰"))+"</span>";
          if(!it.sold)itel.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"buy",what:"cons",idx:idx}});
          cc2.appendChild(itel);
        });
        col.appendChild(cc2);sp.appendChild(col);
        const cont=document.createElement("button");cont.className="gbtn";
        cont.style.cssText="display:block;margin:10px auto 2px;padding:8px 22px;font-size:13px;font-weight:800;background:linear-gradient(180deg,#b0f0a0,#6fd97e);color:#0c3014;border:none;border-radius:9px;cursor:pointer";
        cont.textContent="继续 ▶ 下一盲注";
        cont.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"next"}});
        sp.appendChild(cont);
        root.appendChild(sp);
      }
    }
    // 出战区（5 槽位）
    const area=document.createElement("div");area.style.cssText="margin-top:10px;text-align:center;position:relative";
    area.innerHTML="<div class='bdat'><div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:4px'>PLAY · 出战区 "+(mySelC.length)+"/5</div>"
      +[0,1,2,3,4].map(i=>{
        const c=mySelC[i];
        if(c){const el=document.createElement("span");el.className="bslot fill";el.appendChild(makeCard(c));return el.outerHTML;}
        return "<span class='bslot'>"+(i+1)+"</span>";}).join("")+"</div>";
    root.appendChild(area);
    // 结算加分上飘
    const ms0=g(me,"score",0);
    if(state.balatroLastScore==null)state.balatroLastScore=ms0;
    const dS=ms0-state.balatroLastScore;state.balatroLastScore=ms0;
    if(dS>0){
      const f=document.createElement("div");f.className="bfloat";
      f.textContent="+"+dS;
      area.appendChild(f);
      setTimeout(()=>{try{f.remove();}catch(e){}},760);
    }
    // 手牌（单人总是可交互；待选消耗品时点牌=应用到目标）
    if(pv.hand){
      const hw=document.createElement("div");hw.style.cssText="margin-top:10px;text-align:center";
      hw.innerHTML="<div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:4px'>YOUR HAND · 你的手牌</div>";
      const row=document.createElement("div");row.style.cssText="display:flex;flex-wrap:wrap;justify-content:center;align-items:flex-end";
      pv.hand.forEach(c=>{
        const on=!!selSet[c.id];
        const wrap=document.createElement("span");wrap.style.cssText="display:inline-flex;flex-direction:column;align-items:center;margin:0 1px";
        const el=makeCard(c,!done?(()=>{
          if(state.bSoloUse){
            const su=state.bSoloUse;state.bSoloUse=null;
            gameAPI("action",{room_id:state.groom,action:{op:"use",slot:su.slot,cid:c.id}});return;
          }
          gameAPI("action",{room_id:state.groom,action:on?{op:"unselect",cid:c.id}:{op:"select",cid:c.id}});
        }):null,on);
        if(state.bSoloUse)el.style.outline="2px dashed #7ee081";
        wrap.appendChild(el);
        if(!done){
          const db=document.createElement("button");db.className="gbtn";
          db.style.cssText="font-size:10px;line-height:1;padding:2px 6px;margin-top:3px";
          db.textContent="🗑 弃牌";
          db.disabled=on;
          db.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"discard",cid:c.id}});
          wrap.appendChild(db);}
        row.appendChild(wrap);});
      hw.appendChild(row);root.appendChild(hw);
      // 消耗品槽（非商店阶段）
      if(!s.shop_phase&&(pv.cons||[]).length){
        const cw=document.createElement("div");cw.style.cssText="margin-top:8px;text-align:center";
        cw.innerHTML="<div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:4px'>🧪 消耗品槽</div>";
        const ccrow=document.createElement("div");ccrow.style.cssText="display:flex;flex-wrap:wrap;justify-content:center;align-items:center";
        (pv.cons||[]).forEach((cid,slot)=>{
          const d=CONS[cid]||[cid,"消耗",""];
          const cui=CCR[d[1]]||["#3a3a3a","#e0e0e0"];
          const el=document.createElement("div");
          const onc=state.bSoloUse&&state.bSoloUse.slot===slot;
          el.className="bcons"+(onc?" on":"");
          el.style.background=cui[0];el.style.color=cui[1];
          el.innerHTML="<div style='font-size:8px;opacity:.85'>"+d[1]+"</div><b style='font-size:11px'>"+d[0]+"</b>";
          el.onclick=()=>{
            if(onc){state.bSoloUse=null;return;}
            if(NEEDS[d[2]]){state.bSoloUse={slot};}
            else{gameAPI("action",{room_id:state.groom,action:{op:"use",slot:slot,cid:null}});}
          };
          ccrow.appendChild(el);
        });
        cw.appendChild(ccrow);root.appendChild(cw);
        if(state.bSoloUse){
          const h=document.createElement("div");
          h.style.cssText="margin-top:4px;text-align:center;color:#7ee081;font-size:11px";
          h.textContent="✨ 已选消耗品 → 点一张手牌使用（再点消耗品取消）";root.appendChild(h);
        }
      }
    } else {
      const w=document.createElement("div");w.style.cssText="margin-top:10px;text-align:center;color:#d9c6a5;font-size:12px";
      w.textContent="🂠 手牌："+g(me,"hand_size",0)+" 张";root.appendChild(w);}
    // 操作条（未结束时总是可操作，含逛店/继续）
    if(!done){
      const bar=document.createElement("div");bar.style.cssText="display:flex;gap:8px;justify-content:center;margin:12px 0 2px;flex-wrap:wrap";
      const play=document.createElement("button");
      play.style.cssText="padding:7px 18px;border:none;border-radius:9px;font-weight:800;font-size:13px;color:#3a2a05;background:linear-gradient(180deg,#ffe9a0,#e6b84f);cursor:pointer;box-shadow:0 2px 8px rgba(230,184,79,.5)";
      play.textContent="🎰 出牌结算";
      play.disabled=(pv.sel||[]).length===0;
      play.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"play"}});
      bar.appendChild(play);
      const shop=document.createElement("button");
      shop.textContent="🛒 逛店";
      shop.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"shop"}});
      bar.appendChild(shop);
      const nx=document.createElement("button");
      nx.textContent="▶ 继续";
      nx.onclick=()=>gameAPI("action",{room_id:state.groom,action:{op:"next"}});
      bar.appendChild(nx);
      const tip=document.createElement("span");tip.style.cssText="color:#d9c6a5;font-size:11px;align-self:center";
      tip.textContent="点牌=选入出战区 / 再点=撤回，"+(pv.sel||[]).length+" 张已选中";bar.appendChild(tip);
      root.appendChild(bar);}
    // 我的小丑牌
    const jl=s.jokers||{};const myj=jl[""+me]||jl[me]||[];
    if(myj.length){
      const jw=document.createElement("div");jw.style.cssText="margin-top:12px;text-align:center";
      jw.innerHTML="<div class='bgold' style='font-size:11px;letter-spacing:2px;margin-bottom:5px'>🎭 YOUR JOKERS · 小丑特效</div>";
      const jrow=document.createElement("div");jrow.style.cssText="display:flex;flex-wrap:wrap;justify-content:center;gap:6px";
      myj.forEach(id=>{const def=jd[id]||[id,""];
        const rr=JRC[JRR[id]||"c"]||JRC.c;
        const j=document.createElement("div");j.className="bjs";
        j.style.borderColor=rr[1];j.style.boxShadow="0 2px 8px rgba(0,0,0,.5), 0 0 0 1px "+rr[2];
        j.innerHTML="<div style='position:relative;font-size:8px;font-weight:800;color:#fff;background:"+rr[2]+";border:1px solid "+rr[1]+";border-radius:6px;padding:0 4px;line-height:12px;margin-bottom:1px'>"+rr[0]+"</div><div style='width:24px;height:24px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#7a44c8,#2a1150);border:1px solid "+rr[1]+";display:flex;align-items:center;justify-content:center;font-size:14px;line-height:1;flex:none'>🎭</div><b style='font-size:11px;letter-spacing:.5px;line-height:1.15'>"+esc(def[0])+"</b><span style='font-size:8px;opacity:.92;line-height:1.12;padding:0 2px'>"+esc(def[1])+"</span>";
        jrow.appendChild(j);});
      jw.appendChild(jrow);root.appendChild(jw);}
    // 胜负
    if(done&&winner!=null){
      const w=document.createElement("div");w.style.cssText="margin-top:12px;text-align:center;font-weight:800;font-size:16px;color:#ffd977";
      w.textContent="🏆 通关全部盲注！";root.appendChild(w);}
    else if(done){
      const w=document.createElement("div");w.style.cssText="margin-top:12px;text-align:center;font-weight:800;font-size:16px;color:#e0a0a0";
      w.textContent="💀 生命归零，本局结束";root.appendChild(w);}
    box.appendChild(root);
  },
};
</script>
</body>
</html>
"""


class _LoginGuard:
    """web 登录失败限速（P0）：同 IP 连续失败 ≥max_fails 次后指数退避锁定。

    内存态（重启即清），按 hub 挂载（每 Hub 实例独立，测试互不污染）。
    """

    def __init__(self, max_fails: int = 5, base: float = 2.0, cap: float = 900.0):
        self._max = max_fails
        self._base = base
        self._cap = cap
        self._rec = {}                     # ip -> [fails, locked_until]

    def check(self, ip: str) -> float:
        """返回剩余锁定秒数；0 = 放行"""
        rec = self._rec.get(ip)
        if not rec:
            return 0.0
        wait = rec[1] - time.time()
        return max(0.0, wait)

    def fail(self, ip: str) -> float:
        """记一次失败；达到阈值返回本次施加的锁定时长"""
        rec = self._rec.setdefault(ip, [0, 0.0])
        rec[0] += 1
        if rec[0] < self._max:
            return 0.0
        lock = min(self._base * (2 ** min(rec[0] - self._max, 20)), self._cap)
        rec[1] = time.time() + lock
        return lock

    def success(self, ip: str) -> None:
        self._rec.pop(ip, None)

    def _gc(self, limit: int = 4096) -> None:
        """条目过多时清掉已过期记录（防长期运行内存缓慢增长）"""
        if len(self._rec) <= limit:
            return
        now = time.time()
        for k in [k for k, v in self._rec.items() if v[1] < now]:
            self._rec.pop(k, None)


class _Handler(BaseHTTPRequestHandler):
    hub = None                       # 由 web.serve 注入
    protocol_version = "HTTP/1.1"

    def handle(self):
        """Keep idle HTTP/1.1 readers cancellable, including buffered pipelines.

        Windows socket.makefile readers can remain blocked after another
        thread shuts down the socket. Wait before starting the next request;
        the existing parser/body handling and buffering stay unchanged.
        """
        self.close_connection = False
        try:
            while not self.close_connection and self._service_available():
                timeout = self.connection.gettimeout()
                try:
                    self.connection.setblocking(False)
                    try:
                        buffered = bool(self.rfile.peek(1))
                    except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                        buffered = False
                finally:
                    self.connection.settimeout(timeout)
                readable = buffered
                if not readable:
                    ready, _, _ = select.select([self.connection], [], [], 0.2)
                    readable = bool(ready)
                if readable and self._service_available():
                    self.handle_one_request()
        except (OSError, ValueError):
            pass
        finally:
            self.close_connection = True

    def _service_available(self):
        stop = getattr(getattr(self, 'server', None), '_hub_stop', None)
        check = getattr(self.hub, '_service_available', None)
        return not (stop is not None and stop.is_set()) and (check is None or check())

    def _reject_stopping(self):
        if self._service_available():
            return False
        self.close_connection = True
        self._json(503, {'ok': False, 'error': '服务器正在停止或存储状态未确认'})
        return True

    def log_message(self, *args):
        pass

    def end_headers(self):                       # Web 安全头统一附加（覆盖全部响应路径）
        for k, v in _SEC_HEADERS:
            self.send_header(k, v)
        super().end_headers()

    def send_error(self, code, message=None, explain=None):   # 兜底统一为 JSON
        try:
            self.send_response(code)
            body = json.dumps({"ok": False, "error": message or "error"},
                              ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:            # 客户端已断开属常态；非 ConnectionError 需可见
            if not isinstance(e, (BrokenPipeError, ConnectionResetError)):
                print(f"[web] 写错误响应失败 code={code}: {e!r}", file=sys.stderr)

    # ---------- 工具 ----------
    def _json(self, code: int, obj: dict, set_cookie: str | None = None) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self, *, strict=False) -> dict:
        try:
            if strict and (self.headers.get('Transfer-Encoding')
                           or len(self.headers.get_all('Content-Length', [])) > 1):
                self.close_connection = True
                raise credential_mod.CredentialError('invalid_json')
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > 1 << 20:
                if strict:
                    self.close_connection = True
                    raise credential_mod.CredentialError('invalid_json')
                return {}
            raw = self.rfile.read(length)
            if strict:
                value = credential_mod.strict_json(raw.decode('utf-8') or '{}')
                if len(raw) != length or not isinstance(value, dict):
                    raise credential_mod.CredentialError('invalid_json')
                return value
            return json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            if strict:
                raise credential_mod.CredentialError('invalid_json') from None
            return {}

    def _read_raw(self, limit: int) -> bytes:
        """读取原始 body（upload 用：base64 图片/文件可达数 MB，_read_json 不适用）。"""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return b""
        if length <= 0 or length > limit:
            return b""
        return self.rfile.read(length)

    def _query(self) -> dict:
        return {k: v[0] for k, v in urllib.parse.parse_qs(
            urllib.parse.urlparse(self.path).query).items()}

    def _cookie_token(self) -> str:
        """登录态 Cookie（HttpOnly，P0：token 不走 URL）"""
        raw = self.headers.get("Cookie") or ""
        try:
            return SimpleCookie(raw)[COOKIE_NAME].value
        except (CookieError, KeyError, TypeError, ValueError):
            return ""

    def _tok_any(self, d: dict) -> str:
        """鉴权 token 统一入口：Cookie 优先；body/query token 为旧客户端兼容回退"""
        return self._cookie_token() or str(d.get("token") or "")

    def _is_tls(self) -> bool:
        return isinstance(getattr(self, "connection", None), ssl.SSLSocket)

    def _guard(self) -> _LoginGuard:
        g = getattr(self.hub, "_web_login_guard", None)
        if g is None:
            g = _LoginGuard()
            self.hub._web_login_guard = g
        return g

    def _session(self, body: dict) -> "Session | None":
        return self.hub.session_by_token(self._tok_any(body))

    @staticmethod
    def _credential_status(reason):
        if reason == 'credential_pending':
            return 202
        if reason == 'credential_upgrade_required':
            return 426
        if reason == 'context_required':
            return 428
        if reason in ('context_changed', 'credential_conflict', 'request_parameter_conflict',
                      'credential_already_bound',
                      'claim_required', 'auth_context_changed'):
            return 409
        if reason in ('session_inactive', 'unauthorized'):
            return 401
        if reason in ('service_unavailable', 'credential_store_unavailable',
                      'credential_unknown', 'credential_write_failed', 'credential_store_busy',
                      'credential_capacity', 'credential_authority_unverified',
                      'credential_candidate_invalid', 'login_not_attached'):
            return 503
        if reason in ('invalid_password', 'old_password_invalid', 'credential_not_set',
                      'credential_admin_managed', 'retired', 'reserved_identity'):
            return 403
        return 400

    def _credential_error_response(self, reason, *, text=None, credential=None):
        payload = {'ok': False, 'error': text or str(credential_mod.AuthFailure(reason)),
                   'reason': reason}
        if credential is not None:
            payload['credential'] = credential.payload(server_epoch=self.hub._server_epoch)
        self._json(self._credential_status(reason), payload)

    def _credential_session(self, data):
        """Credential routes never use a body token to override any mt_token Cookie."""
        raw_cookie = self.headers.get('Cookie') or ''
        cookie_present = re.search(r'(?:^|;)\s*' + re.escape(COOKIE_NAME) + r'\s*=', raw_cookie) is not None
        token = self._cookie_token() if cookie_present else data.get('token', '')
        if not isinstance(token, str):
            token = ''
        sess = self.hub.session_by_token(token)
        if sess is None:
            self._credential_error_response('unauthorized')
            return None
        try:
            headers = self.headers.get_all('X-Moyu-Context', [])
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
            values = query.get('moyu_ctx', [])
            if len(headers) > 1 or len(values) > 1:
                raise credential_mod.CredentialError('context_invalid')
            supplied = [credential_mod.WebContext.decode(raw) for raw in headers + values]
            if not supplied:
                raise credential_mod.CredentialError('context_required')
            if any(item != supplied[0] for item in supplied[1:]):
                raise credential_mod.CredentialError('context_invalid')
            context = supplied[0]
            if context != self.hub.web_auth_context(sess):
                raise credential_mod.CredentialError('context_changed')
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return None
        return sess, context, token

    def _credential_response(self, payload, *, query=False):
        status, reason = payload.get('status'), payload.get('reason')
        code = (200 if status == 'confirmed' or (query and reason == 'operation_unavailable')
                else 202 if status == 'pending' else self._credential_status(reason))
        response = {'ok': status == 'confirmed', **payload}
        if status != 'confirmed':
            response['error'] = ('凭据操作仍在处理中' if status == 'pending'
                                 else str(credential_mod.AuthFailure(reason)))
        self._json(code, response)

    def _same_origin(self) -> bool:
        """退出 POST 若带 Origin，必须与当前请求 Host/协议同源。"""
        raw = self.headers.get("Origin")
        if raw is None:
            return True                         # 兼容无 Origin 的程序化客户端
        origin = raw.strip()
        if not origin or origin.lower() == "null":
            return False
        try:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            if parsed.username is not None or parsed.password is not None:
                return False
            if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                return False
            expected_scheme = "https" if self._is_tls() else "http"
            if parsed.scheme != expected_scheme:
                return False
            host = (self.headers.get("Host") or "").strip()
            if not host:
                return False
            request_host = urllib.parse.urlsplit(f"{expected_scheme}://{host}")
            if not request_host.hostname:
                return False
            origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            request_port = request_host.port or (443 if expected_scheme == "https" else 80)
            return (parsed.hostname.rstrip(".").lower()
                    == request_host.hostname.rstrip(".").lower()
                    and origin_port == request_port)
        except (TypeError, ValueError):
            return False

    def _clear_login_cookie(self) -> str:
        cookie = (f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
        if self._is_tls():
            cookie += "; Secure"
        return cookie

    def _logout(self, body: dict):
        if not self._same_origin():
            self._json(403, {"ok": False, "error": "退出请求来源不合法"})
            return
        sess = self._session(body)
        clear_cookie = self._clear_login_cookie()
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"},
                       set_cookie=clear_cookie)
            return
        self.hub.unregister(sess, "web_logout")
        self._json(200, {"ok": True}, set_cookie=clear_cookie)

    # ---------- 路由 ----------
    def do_GET(self):
        if self._reject_stopping():
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            data = _SERVED_PAGE()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")   # R41G：页面随服务器更新，禁浏览器陈旧缓存
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/events":
            self._events(self._tok_any(self._query()))
        elif path == "/api/whoami":
            self._whoami()                   # R47-A2：Cookie 会话恢复
        elif path == "/api/meta":
            self._meta()                     # R48：登录页探测站点口令开关
        elif path == "/api/credential_result":
            self._credential_get()
        elif path == "/api/game_list":
            self._game_list()                # R49：大厅初始快照（游戏元数据+房间）
        elif path == "/api/fish_board":
            self._fish_board(self._query())  # R70H：摸鱼排行榜只读快照
        elif path == "/api/history":
            self._history(self._query())
        elif path == "/api/export":
            self._export(self._query())                 # R63：会话导出（下载 .txt）
        elif path == "/api/group_detail":
            self._group_detail(self._query())
        elif path == "/api/convos":
            self._convos(self._query())
        elif path == "/api/resource_result":
            self._resource_result(self._query())
        elif path == "/api/file":
            self._file(self._query())
        elif path == "/api/room":
            self._room_api(self._query())               # R72：语音房只读名册
        elif path == "/api/vmemo":
            self._vmemo_api(self._query())              # R72：视频留言首帧/原始
        elif path == "/api/avatar":
            self._avatar_get(self._query())          # R52：网页端头像直出
            return
        elif path == "/api/group_avatar":
            self._group_avatar_get(self._query())    # R9H：网页端群头像直出
            return
        elif path == "/api/moments":
            self._moments()                          # 朋友圈：全量时间轴
        elif path == "/api/mcover":
            self._mcover_get(self._query())          # 朋友圈：我的封面元数据
            return
        elif path == "/api/mcovimg":
            self._mcovimg(self._query())             # 朋友圈：封面图片直出
            return
        elif path == "/api/packcover":
            self._pack_cover_img(self._query())      # R65：自定义贴纸包封面直出
            return
        else:
            m = re.fullmatch(r"/api/moment_img/([A-Za-z0-9_\.-]+)", path)
            if m:                                    # 朋友圈动态图片直出
                self._moment_img(m.group(1))
                return
            m2 = re.fullmatch(r"/api/sticker/([A-Za-z0-9_]{1,24})", path)
            if m2:                                   # R30C：自定义贴纸图片直出
                self._sticker_image(m2.group(1))
                return
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self._reject_stopping():
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/upload":
            self._upload()
            return
        try:
            body = self._read_json(strict=path in ('/api/login', '/api/passwd'))
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return
        if path == "/api/login":
            self._login(body)
        elif path == "/api/logout":
            self._logout(body)
        elif path == "/api/block":
            self._block(body)                # R50：网页端屏蔽/解除
        elif path == "/api/nudge":
            self._nudge(body)                # R67：网页端拍一拍
        elif path == "/api/shake":
            self._shake(body)                # R68：网页端窗口抖动
        elif path == "/api/passwd":
            self._passwd(body)               # R47-B：昵称密码管理
        elif path == "/api/send":
            self._send(body)
        elif path == "/api/poll":
            self._poll(body)
        elif path == "/api/reaction":
            self._reaction(body)
        elif path == "/api/draft":
            self._draft(body)               # R29B：草稿同步
        elif path == "/api/group":
            self._group(body)
        elif path == "/api/read":
            self._read(body)
        elif path == "/api/read_detail":
            self._read_detail(body)         # R33③：已读详情
        elif path == "/api/readers":
            self._msg_readers(body)         # C9②：群@已读 by N 逐人统计
        elif path == "/api/thread":
            self._thread(body)              # R34：话题回复拉取
        elif path == "/api/sched":
            self._sched(body)               # R51：网页端定时消息
        elif path == "/api/del":
            self._del(body)                 # R51：网页端撤回（scope=self/both）
        elif path == "/api/edit":
            self._edit(body)                # R55-3：网页端编辑消息
        elif path == "/api/avatar":
            self._avatar_post(body)          # R52：网页端头像上传/删除
        elif path == "/api/profile":
            self._profile(body)              # R52：网页端个性签名
        elif path == "/api/admin":
            self._admin(body)                # R53：网页端管理员（踢人/清空）
        elif path == "/api/invis":
            self._invis(body)                # R56：网页端隐身上线开关（GET 查 / POST 设）
        elif path == "/api/status":
            self._status(body)               # R68：网页端在线状态（GET 查 / POST 设）
        elif path == "/api/remark":
            self._remark(body)               # R69C9：好友备注名（GET 列 / POST 设）
        elif path == "/api/game":
            self._game(body)                # R49：网页端桌游操作（REST→GAME 帧）
        elif path == "/api/moment":
            self._moment_post(body)          # 朋友圈：发布图文动态
        elif path == "/api/moment_like":
            self._moment_like_post(body)     # 朋友圈：点赞/取消
        elif path == "/api/moment_comment":
            self._moment_comment_post(body)  # 朋友圈：评论
        elif path == "/api/moment_del":
            self._moment_del_post(body)      # 朋友圈：删除自己的动态
        elif path == "/api/mcover":
            self._mcover_post(body)          # 朋友圈：设置封面（预设/上传）
        elif path == "/api/mcover_del":
            self._mcover_del_post(body)      # 朋友圈：恢复默认封面
        elif path == "/api/shop":
            self._shop_post(body)            # R65：贴纸商店（拉目录/订阅）
        elif path == "/api/pack":
            self._pack_post(body)            # R65：自定义贴纸包管理（改名/删包/封面/排序）
        else:
            self._json(404, {"ok": False, "error": "not found"})

    # ---------- 接口 ----------
    def _login(self, body: dict):
        ip = self.client_address[0]
        guard = self._guard()
        guard._gc()
        wait = guard.check(ip)
        if wait > 0:                        # P0：锁定期内直接拒绝，不给爆破口令的机会
            self.hub.audit.log(type="web_login_limited", ip=ip,
                               retry_after=round(wait, 1))
            self._json(429, {"ok": False,
                             "error": f"登录尝试过于频繁，请 {int(wait) + 1} 秒后再试"})
            return
        if not self._same_origin():
            self._json(403, {"ok": False, "reason": "forbidden", "error": "请求来源不允许"})
            return
        try:
            intent = credential_mod.LoginIntent.parse(body)
            site_password = body.get('password', '')
            if not isinstance(site_password, str):
                raise credential_mod.CredentialError('invalid_password_fields')
            if self.hub._web_password and not hmac.compare_digest(
                    site_password.encode('utf-8'), str(self.hub._web_password).encode('utf-8')):
                guard.fail(ip)
                self.hub.audit.log(type='web_login_failed', ip=ip, reason='password')
                self._json(403, {'ok': False, 'reason': 'site_password_invalid', 'error': '口令错误'})
                return
            if intent.version == 1:
                if not self.hub._web_password and site_password:
                    raise credential_mod.CredentialError('unexpected_site_password')
                nick_pwd = body.get('nick_pwd', '')
            else:
                nick_pwd = body.get('nick_pwd', '') if self.hub._web_password else site_password
            if not isinstance(nick_pwd, str):
                raise credential_mod.CredentialError('invalid_password_fields')
        except (credential_mod.CredentialError, UnicodeError) as exc:
            self._credential_error_response(getattr(exc, 'reason', 'invalid_password_fields'))
            return
        sess, token = self.hub.login_web(body.get('nick', ''), self.client_address[0],
                                         nick_pwd, auth_header=body)
        if not sess:
            guard.fail(ip)
            self.hub.audit.log(type='web_login_failed', ip=ip, reason='nick')
            self._credential_error_response(getattr(token, 'reason', 'invalid_password'),
                                            text=str(token), credential=getattr(token, 'credential', None))
            return
        try:
            metadata = self.hub.auth_capabilities()
        except credential_mod.CredentialError as exc:
            self.hub.unregister(sess, 'login_metadata_failed')
            credential = (None if getattr(sess, '_claim_replay', False)
                          else getattr(sess, '_login_credential', None))
            if credential is not None:
                credential = replace(credential, login_status='not_attached')
            self._credential_error_response(exc.reason,
                                            credential=credential)
            return
        guard.success(ip)
        cookie = (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict"
                  + ("; Secure" if self._is_tls() else ""))
        self._json(200, {"ok": True, "uid": sess.uid, "nick": sess.nick,
                         "auth": metadata, "session_binding_id": sess.session_binding_id,
                         **({"credential": sess._login_credential.payload(server_epoch=self.hub._server_epoch)}
                            if getattr(sess, '_login_credential', None) is not None else {}),
                         "is_admin": sess.is_admin,             # R53：管理员标识
                         "token": token, "roster": self.hub._roster(),
                         "known": self.hub._known_list(sess.uid),   # R63：已知用户（含离线 last_online）
                         "groups": self.hub._group_list(sess.uid),   # R54：按查看者过滤
                         "bots": [{"uid": b.uid, "nick": b.nick, "desc": b.desc}
                                  for b in _bots.BOTS],     # R46：网页端机器人入口
                         "convos": self.hub._convo_list(sess.uid),
                         "stickers": self.hub.stickers,
                         "custom_stickers": self.hub._custom_list(),  # R30C
                         "sticker_pack_meta": self.hub._pack_meta_payload(),  # R65：包封面元数据
                         "sticker_subs": self.hub._sticker_subs_for(sess.uid),  # R65：贴纸订阅
                         "history": self.hub.bus.history("all"),
                         "drafts": self.hub._drafts_for(sess.uid),
                         "blocked": sorted(self.hub._blocked(sess.uid)),  # R50
                         "scheds": self.hub._sched_payload(sess.uid)},    # R51：待发定时消息
                   set_cookie=cookie)

    def _meta(self):
        """R48：登录页探测——站点口令是否启用，决定表单拆双密码框（无需鉴权）。"""
        try:
            metadata = self.hub.auth_capabilities()
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return
        self._json(200, {"ok": True, "site_pwd": bool(self.hub._web_password), "auth": metadata})

    def _game_list(self):
        """R49：大厅初始快照——游戏元数据 + 房间列表（与 TCP game_list 帧同构）。"""
        sess = self._session({})
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        payload = self.hub._game_list_payload()
        payload["ok"] = True
        self._json(200, payload)

    def _fish_board(self, d: dict):
        """R70H：摸鱼排行榜只读快照（与 TCP fish_board 帧同构；网页端不上报积分）。"""
        sess = self._session(d)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        game = str(d.get("game") or "").strip()
        enabled = bool(self.hub.cfg.fish_board_enabled)
        if not game or not enabled:          # 开关关闭 / 未指定游戏：回空榜，不泄露数据
            self._json(200, {"ok": True, "game": game, "entries": [],
                             "enabled": enabled})
            return
        payload = self.hub._fish_board_payload(game)
        payload["ok"] = True
        payload["enabled"] = True
        self._json(200, payload)

    def _game(self, body: dict):
        """R49：网页端桌游——REST 映射 GAME_* 帧（结果经 SSE 异步回推）。

        body: {op: create|join|spectate|leave|start|action,
               room_id?, game?, action?}"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        op = str(body.get("op") or "")
        mapping = {
            "create": (MsgType.GAME_CREATE, "game"),
            "join": (MsgType.GAME_JOIN, "room_id"),
            "spectate": (MsgType.GAME_SPECTATE, "room_id"),
            "leave": (MsgType.GAME_LEAVE, "room_id"),
            "start": (MsgType.GAME_START, "room_id"),
            "action": (MsgType.GAME_ACTION, "room_id"),
            "sync": (MsgType.GAME_SYNC, "room_id"),
        }
        if op not in mapping:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        t, key = mapping[op]
        header = {"t": t.value}
        if key == "game":
            header["game"] = str(body.get("game") or "")[:24]
        if key == "room_id":
            header["room_id"] = str(body.get("room_id") or "")[:16]
        if op == "action":
            action = body.get("action")
            if not isinstance(action, dict):
                self._json(400, {"ok": False, "error": "动作格式错误"})
                return
            header["action"] = action
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _whoami(self):
        """R47-A2：Cookie 会话恢复——页面加载探活，命中返回登录同款数据包。"""
        tok = self._tok_any(self._query())
        sess = self.hub.session_by_token(tok)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        try:
            metadata = self.hub.auth_capabilities()
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return
        sess.touch()
        self._json(200, {"ok": True, "uid": sess.uid, "nick": sess.nick,
                         "auth": metadata, "session_binding_id": sess.session_binding_id,
                         "is_admin": sess.is_admin,             # R53：管理员标识
                         "token": tok, "roster": self.hub._roster(),
                         "known": self.hub._known_list(sess.uid),   # R63：已知用户（含离线 last_online）
                         "groups": self.hub._group_list(sess.uid),   # R54：按查看者过滤
                         "bots": [{"uid": b.uid, "nick": b.nick, "desc": b.desc}
                                  for b in _bots.BOTS],
                         "convos": self.hub._convo_list(sess.uid),
                         "stickers": self.hub.stickers,
                         "custom_stickers": self.hub._custom_list(),
                         "sticker_pack_meta": self.hub._pack_meta_payload(),   # R65：包封面元数据
                         "sticker_subs": self.hub._sticker_subs_for(sess.uid),  # R65：贴纸订阅
                         "history": self.hub.bus.history("all"),
                         "drafts": self.hub._drafts_for(sess.uid),
                         "blocked": sorted(self.hub._blocked(sess.uid))})  # R50

    def _passwd(self, body: dict):
        if not self._same_origin():
            self._json(403, {'ok': False, 'reason': 'forbidden', 'error': '请求来源不允许'})
            return
        # Report upgrade before requiring a context unknown to old pages. They
        # retain ordinary authenticated browsing but cannot use the old writer.
        try:
            credential_mod.UpdateRequest.parse(body, password_max=64)
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return
        binding = self._credential_session(body)
        if binding is None:
            return
        sess, context, token = binding
        result = self.hub.credential_update(sess, body, context=context, token=token)
        self._credential_response(result)

    def _credential_get(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            self._credential_error_response('invalid_credential_request')
            return
        data = {key: values[0] for key, values in query.items()}
        # HTTP query values are strings; only the exact wire literal "1" is
        # translated. All other values remain invalid, not int-coerced.
        if data.get('credential_v') == '1':
            data['credential_v'] = 1
        try:
            credential_mod.QueryRequest.parse(data)
        except credential_mod.CredentialError as exc:
            self._credential_error_response(exc.reason)
            return
        binding = self._credential_session(data)
        if binding is None:
            return
        sess, context, token = binding
        self._credential_response(self.hub.credential_query(
            sess, data, context=context, token=token), query=True)

    def _block(self, body: dict):
        """R50：网页端屏蔽/解除（复用 BLOCK_SET 帧，服务器权威持久化）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        op = body.get("op")
        if op == "block":
            header = {"t": MsgType.BLOCK_SET.value, "on": True}
        elif op == "unblock":
            header = {"t": MsgType.BLOCK_SET.value, "on": False}
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        try:
            header["target"] = int(body.get("uid"))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "缺少目标用户"})
            return
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    # ---------- R52 头像与个人资料（昵称=登录标识不可改） ----------
    def _avatar_get(self, q: dict):
        """GET /api/avatar?uid=：直出头像图片字节（鉴权走 Cookie/token；无头像 404）。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            uid = int(q.get("uid") or 0)
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "参数错误"})
            return
        ext = self.hub._avatar_known(uid)
        path = self.hub._avatar_file(uid, ext) if ext else ""
        data = None
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as e:            # 读失败不能与「无头像」混同 → 落 stderr 可排障
                print(f"[web] 读取头像文件失败 {path}: {e!r}", file=sys.stderr)
                data = None
        if data is None:
            self._json(404, {"ok": False, "error": "无头像"})
            return
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "max-age=60")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _group_avatar_get(self, q: dict):
        """R9H：GET /api/group_avatar?gid=：直出群头像图片字节（鉴权走 Cookie/token；无头像 404）。
        群头像 ext 存于后端 groups[gid]["avatar"]，图片字节落盘 avatar_dir/g<gid>.<ext>，
        与用户头像 _avatar_get 同法直接读盘。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            gid = int(q.get("gid") or 0)
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "参数错误"})
            return
        g = self.hub.groups.get(gid)
        ext = g.get("avatar", "") if g else ""
        path = self.hub._group_avatar_file(gid, ext) if ext else ""
        data = None
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as e:            # 读失败不能与「无群头像」混同 → 落 stderr 可排障
                print(f"[web] 读取群头像文件失败 {path}: {e!r}", file=sys.stderr)
                data = None
        if data is None:
            self._json(404, {"ok": False, "error": "无群头像"})
            return
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "max-age=60")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- 朋友圈（图文动态；与 TCP 端同 Hub 状态） ----------
    def _moments(self):
        """GET /api/moments：全量时间轴（pid 倒序），鉴权走 Cookie。"""
        sess = self.hub.session_by_token(self._tok_any(self._query()))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        posts = sorted((dict(p) for p in self.hub.moments.values()),
                       key=lambda p: p.get("pid", 0), reverse=True)
        self._json(200, {"ok": True, "posts": posts})

    def _moment_img(self, fn):
        """GET /api/moment_img/{fn}：已登录用户读取现存动态引用的图片。"""
        sess = self._session(self._query())
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        base = os.path.basename(fn)
        if base != fn or "." not in base:
            self._json(400, {"ok": False, "error": "非法文件名"})
            return
        if not self.hub._moment_image_active(base):
            self._json(404, {"ok": False, "error": "图片不存在"})
            return
        path = os.path.join(self.hub.moment_dir, base)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self._json(404, {"ok": False, "error": "图片不存在"})
            return
        ext = base.rsplit(".", 1)[-1].lower()
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Vary", "Cookie")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ----- 朋友圈封面（每人一个：预设渐变 / 上传图片） -----
    def _mcover_get(self, q: dict):
        sess = self._session(q)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        cover = self.hub.moment_covers.get(sess.uid)
        self._json(200, {"ok": True, "cover": cover})

    def _mcovimg(self, q: dict):
        """GET /api/mcovimg：我的封面图片直出（仅 covers 目录）。"""
        sess = self._session(q)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        meta = self.hub.moment_covers.get(sess.uid)
        if not meta or meta.get("mode") != "img":
            self._json(404, {"ok": False, "error": "无自定义封面"})
            return
        path = os.path.join(self.hub.cover_dir, f"{sess.uid}.jpg")
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self._json(404, {"ok": False, "error": "封面不存在"})
            return
        ext = (meta.get("ext") or "jpg").lower()
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "max-age=3600")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _mcover_post(self, body: dict):
        """POST /api/mcover：{preset:n} 或 {img:{ext,data(base64)}}。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        if "preset" in body:
            try:
                n = int(body.get("preset"))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "非法预设封面"})
                return
            if not 0 <= n < self.hub._COVER_PRESETS:
                self._json(400, {"ok": False, "error": "预设封面序号越界"})
                return
            self.hub.dispatch(sess,
                              {"t": MsgType.MOMENT_COVER_SET.value,
                               "preset": n})
            self._json(200, {"ok": True})
            return
        img = body.get("img") or {}
        ext = str(img.get("ext") or "").lower().strip(". ")
        try:
            blob = base64.b64decode(str(img.get("data") or ""))
        except Exception:
            self._json(400, {"ok": False, "error": "封面图片解码失败"})
            return
        if not blob or ext not in self.hub._COVER_EXTS:
            self._json(400, {"ok": False, "error": "封面图片为空或格式不支持"})
            return
        if len(blob) > self.hub._COVER_MAX:
            self._json(400, {"ok": False, "error": "封面图片不能超过 2MB"})
            return
        self.hub.dispatch(sess, {"t": MsgType.MOMENT_COVER_SET.value,
                                 "ext": ext}, blob)
        self._json(200, {"ok": True})

    def _mcover_del_post(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        self.hub.dispatch(sess, {"t": MsgType.MOMENT_COVER_DEL.value})
        self._json(200, {"ok": True})

    def _moment_post(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        text = str(body.get("text") or "").strip()
        imgs = [x for x in (body.get("images") or []) if isinstance(x, dict)][:9]
        parts, exts = [], []
        for it in imgs:
            ext = str(it.get("ext") or "jpg").lower().strip(". ")
            if "." in ext:
                ext = ext.rsplit(".", 1)[-1]
            try:
                data = __import__("base64").b64decode(it.get("base64") or it.get("b64") or "")
            except Exception:
                data = b""
            if data:
                parts.append(data)
                exts.append(ext or "jpg")
        bodyb = b"".join(len(p).to_bytes(4, "big") + p for p in parts)
        header = {"t": MsgType.MOMENT_PUBLISH.value, "text": text}
        if exts:
            header["exts"] = exts
        self.hub.dispatch(sess, header, bodyb)
        self._json(200, {"ok": True})

    def _moment_like_post(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        self.hub.dispatch(sess, {"t": MsgType.MOMENT_LIKE.value,
                                 "pid": int(body.get("pid") or 0),
                                 "on": bool(body.get("on"))})
        self._json(200, {"ok": True})

    def _moment_comment_post(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        self.hub.dispatch(sess, {"t": MsgType.MOMENT_COMMENT.value,
                                 "pid": int(body.get("pid") or 0),
                                 "text": str(body.get("text") or "")})
        self._json(200, {"ok": True})

    def _moment_del_post(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        self.hub.dispatch(sess, {"t": MsgType.MOMENT_DEL.value,
                                 "pid": int(body.get("pid") or 0)})
        self._json(200, {"ok": True})

    def _avatar_post(self, body: dict):
        """POST /api/avatar：{op: set|del, ext?, data?(base64)} → 复用 AVATAR_SET/DEL 帧。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        op = body.get("op")
        if op == "del":
            self.hub.dispatch(sess, {"t": MsgType.AVATAR_DEL.value})
            self._json(200, {"ok": True})
            return
        if op != "set":
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        try:
            data = __import__("base64").b64decode(body.get("data") or "", validate=True)
        except Exception:
            self._json(400, {"ok": False, "error": "数据解码失败"})
            return
        ext = str(body.get("ext") or "").lower().lstrip(".")[:8]
        if ext not in self.hub.cfg.avatar_exts:
            self._json(400, {"ok": False, "error": "不支持的图片格式"})
            return
        if not data or len(data) > self.hub.cfg.avatar_max_bytes:
            self._json(400, {"ok": False, "error": "头像为空或超过 1MB 上限"})
            return
        self.hub.dispatch(sess, {"t": MsgType.AVATAR_SET.value, "ext": ext}, data)
        self._json(200, {"ok": True})

    def _profile(self, body: dict):
        """POST /api/profile：{sign} → 设置个性签名（服务器权威广播全员）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        sign = str(body.get("sign") or "").strip()[:self.hub.cfg.sign_max_len]
        self.hub.dispatch(sess, {"t": MsgType.SIGN_SET.value, "sign": sign})
        self._json(200, {"ok": True})

    def _invis(self, body: dict):
        """R56 网页端隐身上线：GET（无 on）查当前状态；POST {on} 切换。
        服务器权威持久；回帧经 SSE 推回 invis_ack。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        if "on" not in body:      # 查询
            known = (self.hub.known.get(sess.uid) or {})
            self._json(200, {"ok": True, "on": bool(known.get("invisible"))})
            return
        on = bool(body.get("on"))
        self.hub.dispatch(sess, {"t": MsgType.INV_SET.value, "on": on})
        self._json(200, {"ok": True, "on": on})

    def _status(self, body: dict):
        """R68 网页端在线状态：GET（无 status）查当前；POST {status} 切换。
        服务器权威持久；回帧经 SSE 推回 status_ack。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        if "status" not in body:      # 查询
            known = (self.hub.known.get(sess.uid) or {})
            self._json(200, {"ok": True,
                             "status": str(known.get("status") or "online")})
            return
        status = str(body.get("status") or "").strip().lower()
        if status not in ("online", "away", "busy"):
            self._json(400, {"ok": False, "error": "状态无效"})
            return
        self.hub.dispatch(sess, {"t": MsgType.STATUS_SET.value, "status": status})
        self._json(200, {"ok": True, "status": status})

    def _remark(self, body: dict):
        """R69C9 网页端好友备注名：GET（无 uid）列本人全部备注；POST {uid,remark} 设置。
        服务器按 owner 持久（remark 空=清除），回帧经 SSE 推回 remark_ack。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        if "uid" not in body:      # 查询：本人视角的备注表 {uid: remark}
            rem = (self.hub.known.get(sess.uid) or {}).get("remarks") or {}
            self._json(200, {"ok": True, "remarks": rem})
            return
        try:
            uid = int(body.get("uid"))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "uid 无效"})
            return
        remark = str(body.get("remark") or "").strip()[:24]
        self.hub.dispatch(sess, {"t": MsgType.REMARK_SET.value, "uid": uid,
                                 "remark": remark})
        self._json(200, {"ok": True, "uid": uid, "remark": remark})

    def _send(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        header = {"t": "chat", "channel": body.get("channel") or "public",
                  "text": body.get("text") or "", "sticker": body.get("sticker") or ""}
        if isinstance(body.get("rich"), list):      # R59：网页端富文本段
            header["rich"] = body["rich"]
        if isinstance(body.get("forward"), dict) and (
                body["forward"].get("text") or body["forward"].get("nick")):
            fw = {}
            for k in ("nick", "text", "sticker", "seq"):
                if body["forward"].get(k) is not None:
                    fw[k] = body["forward"][k]
            if fw:
                header["forward"] = fw                 # R13 转发快照透传
        # R64 合并转发：只透传「源会话 + 源消息 seq」，条目由服务器按真实历史
        # 聚合生成——浏览器无法伪造合并转发卡（昵称/正文一律取自服务器历史）。
        seqs = body.get("fwd_seqs")
        if isinstance(seqs, list) and seqs:
            safe_seqs = []
            for s in seqs[:30]:
                if isinstance(s, bool):
                    continue
                try:
                    v = int(s)
                except (TypeError, ValueError):
                    continue
                if v > 0:
                    safe_seqs.append(v)
            if safe_seqs:
                header["fwd_seqs"] = safe_seqs
                src = body.get("fwd_from")
                if isinstance(src, dict):
                    safe_src = {}
                    if src.get("type") in ("public", "private", "group"):
                        safe_src["type"] = src["type"]
                    for k in ("uid", "gid"):
                        try:
                            safe_src[k] = int(src[k])
                        except (KeyError, TypeError, ValueError):
                            pass
                    if safe_src:
                        header["fwd_from"] = safe_src
        if body.get("silent"):                      # R26C 静默发送
            header["silent"] = True
        if body.get("disguise"):                    # R70E 消息伪装（白名单风格）
            _dis = str(body["disguise"])
            if _dis in self.cfg.disguise_styles:
                header["disguise"] = _dis
        if body.get("burn"):                        # R14 阅后即焚：全体读完自动删除
            header["burn"] = True
        if body.get("thread_root") is not None:     # R34 群内话题回复
            try:
                header["thread_root"] = int(body["thread_root"])
            except (TypeError, ValueError):
                pass
        reply = body.get("reply")
        if isinstance(reply, dict):                 # R41G 网页端引用回复快照
            safe = {}
            if isinstance(reply.get("nick"), str):
                safe["nick"] = reply["nick"][:64]
            if isinstance(reply.get("text"), str):
                safe["text"] = reply["text"][:200]
            try:
                safe["seq"] = int(reply.get("seq"))
            except (TypeError, ValueError):
                pass
            if safe.get("nick") or safe.get("text"):
                header["reply"] = safe
        if isinstance(body.get("file"), dict):      # R23 图片/文件消息
            header["file"] = body["file"]
        if body.get("to") is not None:
            header["to"] = body["to"]
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _nudge(self, body: dict):
        """R67 网页端拍一拍：转 nudge 帧入 hub.dispatch（校验/限速/广播全在 Hub）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        header = {"t": MsgType.NUDGE.value, "channel": body.get("channel") or "public",
                  "target": body.get("target")}
        if body.get("to") is not None:
            header["to"] = body["to"]
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _shake(self, body: dict):
        """R68 网页端窗口抖动：转 shake 帧入 hub.dispatch（校验/限速/广播全在 Hub）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        header = {"t": MsgType.SHAKE.value, "channel": body.get("channel") or "public"}
        if body.get("to") is not None:
            header["to"] = body["to"]
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _poll(self, body: dict):
        """R26A 网页端投票：action=create 发起 / action=vote 投票（改票）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        action = body.get("action")
        if action == "create":
            header = {"t": MsgType.POLL.value, "channel": body.get("channel") or "public",
                      "question": body.get("question") or "",
                      "options": list(body.get("options") or []),
                      "anonymous": bool(body.get("anonymous")),   # R70C
                      "multi": bool(body.get("multi"))}
            if body.get("quiz"):                                      # R70C：测验
                header["quiz"] = True
                header["correct"] = int(body.get("correct") or 0)
            if body.get("to") is not None:
                header["to"] = body["to"]
        elif action == "vote":
            header = {"t": MsgType.POLL_VOTE.value,
                      "seq": int(body.get("seq") or 0),
                      "option": int(body.get("option") or 0)}
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _reaction(self, body: dict):
        """R27 网页端表情回应：on=true 加回应 / false 摘下（协议复用 REACTION）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        header = {"t": MsgType.REACTION.value,
                  "seq": int(body.get("seq") or 0),
                  "emoji": str(body.get("emoji") or "")[:8],
                  "on": bool(body.get("on", True))}
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _sched(self, body: dict):
        """R51 网页端定时消息：action=set/cancel/list（复用服务器 SCHED 帧，服务器权威）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        action = body.get("action")
        if action == "list":
            self._json(200, {"ok": True,
                             "scheds": self.hub._sched_payload(sess.uid)})
            return
        if action == "set":
            fire_at = 0.0
            try:
                fire_at = float(body.get("fire_at") or 0)
            except (TypeError, ValueError):
                pass
            if not fire_at and body.get("minutes"):
                try:
                    fire_at = time.time() + max(1, int(body["minutes"])) * 60
                except (TypeError, ValueError):
                    pass
            header = {"t": MsgType.SCHED_SET.value,
                      "channel": body.get("channel") or "public",
                      "text": str(body.get("text") or ""),
                      "fire_at": fire_at}
            if body.get("to") is not None:
                header["to"] = body["to"]
        elif action == "cancel":
            header = {"t": MsgType.SCHED_CANCEL.value,
                      "rid": str(body.get("rid") or "")}
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _del(self, body: dict):
        """R51 网页端撤回：scope=self 仅本人；scope=both 私聊双方可删。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            seq = int(body.get("seq") or 0)
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "缺少 seq"})
            return
        header = {"t": MsgType.MSG_DEL.value, "seq": seq,
                  "scope": body.get("scope") or "self"}
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _edit(self, body: dict):
        """R55-3 网页端编辑消息：复用 MSG_EDIT 帧，权限由 hub 校验（仅本人）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            seq = int(body.get("seq") or 0)
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "缺少 seq"})
            return
        text = (body.get("text") or "").strip()
        if not text:
            self._json(400, {"ok": False, "error": "消息不能为空"})
            return
        header = {"t": MsgType.MSG_EDIT.value, "seq": seq, "text": text}
        if isinstance(body.get("rich"), list):      # R59：网页端编辑同步富文本
            header["rich"] = body["rich"]
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _admin(self, body: dict):
        """R53 网页端管理员：op=kick|clear_all|clear_uid。
        复用 ADMIN_KICK / CLEAR_ALL / CLEAR_UID 帧，权限由 hub 校验（仅管理员）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        if not sess.is_admin:
            self._json(403, {"ok": False, "error": "仅管理员可执行"})
            return
        op = body.get("op")
        if op == "groups":
            # 系统管理员：群目录+成员花名册（复用超管 _admin_groups_payload）
            payload = self.hub._admin_groups_payload()
            payload["ok"] = True
            self._json(200, payload)
            return
        if op == "user_groups":
            # 系统管理员：某人信息+所属群（uid/昵称均可）
            payload = self.hub._admin_user_payload(body.get("uid"))
            if payload is None:
                self._json(404, {"ok": False, "error": "目标 uid/昵称 无效"})
                return
            payload["ok"] = True
            self._json(200, payload)
            return
        if op == "audit":
            # 系统管理员：最近管理操作审计（今日已落盘）
            rows = self.hub.audit.recent(
                limit=int(body.get("limit") or 60), type_prefix="admin")
            self._json(200, {"ok": True, "rows": rows})
            return
        if op == "users":
            # R58：系统管理员全量账号（在线/离线都有），供管理面板管理所有账户
            self._json(200, {"ok": True, "users": self.hub._admin_users()})
            return
        if op in ("group_add", "group_remove", "group_dissolve", "group_add_nick"):
            # 系统管理员：群增删成员 / 解散群（add_nick 允许昵称，服务器权威解析）
            try:
                gid = int(body.get("gid") or 0)
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "缺少 gid"})
                return
            sub = {"group_add": "add", "group_remove": "remove",
                   "group_dissolve": "dissolve",
                   "group_add_nick": "add"}[op]
            header = {"t": MsgType.ADMIN_GROUP_SET.value, "op": sub, "gid": gid}
            if sub in ("add", "remove"):
                raw = body.get("uid")
                if op == "group_add_nick":
                    header["uid"] = str(raw or "")   # 可能是昵称，交服务器解析
                else:
                    try:
                        header["uid"] = int(raw or 0)
                    except (TypeError, ValueError):
                        header["uid"] = str(raw or "")  # 容忍昵称
            self.hub.dispatch(sess, header)
            self._json(200, {"ok": True})
            return
        if op == "clear_all":
            header = {"t": MsgType.CLEAR_ALL.value}
        elif op == "clear_uid":
            try:
                header = {"t": MsgType.CLEAR_UID.value,
                          "uid": int(body.get("uid") or 0)}
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "缺少目标用户"})
                return
        elif op == "kick":
            # 支持 uid 或昵称（服务器权威解析；非管理员 → 403）
            header = {"t": MsgType.ADMIN_KICK.value, "uid": body.get("uid")}
        elif op == "force_invis":
            # R56B：强制某用户显身/隐身（uid 或昵称，服务器权威解析）
            try:
                header = {"t": MsgType.ADMIN_INVIS_SET.value,
                          "uid": body.get("uid"), "on": bool(body.get("on"))}
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "缺少目标用户"})
                return
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _read_detail(self, body: dict):
        """R33③ 网页端已读详情：复用 hub._readers_for（含权限校验）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        key = str(body.get("key") or "")
        lst = self.hub._readers_for(key, sess.uid)
        if lst is None:
            self._json(403, {"ok": False, "error": "无权查看该会话已读详情"})
            return
        self._json(200, {"ok": True, "key": key, "readers": lst})

    def _msg_readers(self, body: dict):
        """C9② 群@已读 by N：复用 hub._on_msg_readers 的同源逻辑，HTTP 直连返回。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        key = str(body.get("key") or "")
        try:
            seq = int(body.get("seq") or 0)
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "seq 无效"})
            return
        if not key.startswith("group:"):
            self._json(400, {"ok": False, "error": "仅群会话支持逐人已读统计"})
            return
        try:
            gid = int(key.split(":", 1)[1])
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "key 无效"})
            return
        g = self.hub.groups.get(gid)
        if not g or (sess.uid not in g["members"] and not sess.is_admin):
            self._json(403, {"ok": False, "error": "无权查看该群已读统计"})
            return
        readers = self.hub.reads.get(key) or {}
        members = dict(g["members"])
        read_m, unread_m = [], []
        for u, nick in sorted(members.items()):
            (read_m if readers.get(u, 0) >= seq else unread_m) \
                .append({"uid": u, "nick": nick})
        self._json(200, {"ok": True, "key": key, "seq": seq,
                         "count": len(read_m), "total": len(members),
                         "members": read_m, "unread": unread_m})

    def _thread(self, body: dict):
        """R34 群内话题：拉取某根消息的全部回复（复用 hub._history_key 权限校验）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        channel = body.get("channel") or "public"
        to = body.get("to")
        key = self.hub._history_key(sess, channel, to)
        if key is None:
            self._json(403, {"ok": False, "error": "无权查看该话题"})
            return
        try:
            root = int(body.get("root_seq"))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "root_seq 无效"})
            return
        msgs = [m for m in self.hub.bus.history(key)
                if m.get("thread_root") == root]
        self._json(200, {"ok": True, "root_seq": root, "msgs": msgs})

    def _draft(self, body: dict):
        """R29B 网页端草稿同步：推给服务器（空文本=清除）；换端登录/重连时登录响应带回。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        header = {"t": MsgType.DRAFT_SET.value, "channel": body.get("channel") or "public",
                  "text": body.get("text") or ""}
        if body.get("to") is not None:
            header["to"] = body["to"]
        self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _history(self, q: dict):
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        channel = q.get("channel") or "public"
        to = q.get("to")
        if to is not None:
            try:
                to = int(to)
            except ValueError:
                to = None
        key = self.hub._history_key(sess, channel, to)
        if key is None:
            self._json(200, {"ok": False, "error": "无权限", "msgs": []})
            return
        self._json(200, {"ok": True, "msgs": self.hub.bus.history(key)})

    def _export(self, q: dict):
        """R63 GET /api/export：会话导出为可读 .txt（时间/昵称/内容，纯文本下载）。
        鉴权同一 /api/history 的 Cookie/？token 通道。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        channel = q.get("channel") or "public"
        to = q.get("to")
        if to is not None:
            try:
                to = int(to)
            except (TypeError, ValueError):
                to = None
        key = self.hub._history_key(sess, channel, to)
        if key is None:
            self._json(200, {"ok": False, "error": "无权限", "msgs": []})
            return
        msgs = self.hub.bus.history(key)
        name = "公共频道" if channel == "public" else \
            (f"私聊{to}" if channel == "private" else f"群{to}")
        lines = ["# 会话导出", "", f"会话：{name}", f"条数：{len(msgs)}",
                 f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for m in msgs:
            if m.get("deleted"):
                lines.append("- （消息已撤回）")
                continue
            nick = m.get("nick", "?")
            hh = time.strftime("%H:%M", time.localtime(m.get("ts", 0)))
            lines.append(f"- **{nick}** {hh}: {self._export_body(m)}")
        data = ("\n".join(lines) + "\n").encode("utf-8")
        fn = f"chat_{name}-{time.strftime('%Y%m%d-%H%M')}.txt"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition",
                         f"attachment; filename*=UTF-8''{urllib.parse.quote(fn)}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _export_body(m: dict) -> str:
        """把单条消息转导出纯文本（富文本转纯文本、贴纸、语音、文件引用）。"""
        parts = []
        text = m.get("text", "")
        r = m.get("rich")
        if isinstance(r, list) and r:
            text = "".join(str(s[0]) if isinstance(s, (list, tuple)) else "" for s in r)
        sticker = m.get("sticker", "")
        if sticker:
            parts.append(sticker)
        if text:
            parts.append(text)
        if m.get("image_path"):
            parts.append(f"[图片] {os.path.basename(m['image_path'])}")
        if m.get("voice"):
            parts.append(f"[语音] {m.get('duration', 0):g} 秒")
        if isinstance(m.get("poll"), dict):
            parts.append(f"[投票] {str(m['poll'].get('question') or '')[:60]}")
        f = m.get("file") if isinstance(m.get("file"), dict) else None
        if f:
            tag = "图片" if f.get("kind") == "image" else "文件"
            parts.append(f"[{tag}] {str(f.get('name') or '')[:24]}")
        if m.get("reply"):
            parts.append(f"(回复 {m['reply'].get('nick', '?')})")
        return " ".join(p for p in parts if p).strip()

    def _convos(self, q: dict):
        """R22 最近私聊会话列表（含未读数）：登录响应也带一份，此接口供刷新。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        self._json(200, {"ok": True, "convos": self.hub._convo_list(sess.uid)})

    # ---------- R23 网页端图片/文件 ----------
    def _upload(self):
        """POST /api/upload：新上传走 RESOURCE body→manifest 发布。"""
        raw = self._read_raw(int(self.hub.cfg.web_file_max * 1.34) + 1024)
        if not raw:     # body 为空或超过上限：_read_raw 直接丢空
            self._json(400, {"ok": False, "error": "请求体为空或过大"})
            return
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"ok": False, "error": "非法请求体"})
            return
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        kind = body.get("kind")
        if kind not in ("image", "file"):
            self._json(400, {"ok": False, "error": "未知文件类型"})
            return
        try:
            data = __import__("base64").b64decode(body.get("data") or "", validate=True)
        except Exception:
            self._json(400, {"ok": False, "error": "数据解码失败"})
            return
        if not data or len(data) > self.hub.cfg.web_file_max:
            self._json(400, {"ok": False, "error": "文件为空或超过 20MB 上限"})
            return
        name = str(body.get("name") or "未命名").replace("\\", "/").split("/")[-1][:128]
        if kind == "file" and _IMG_EXT_RE.search(name):
            kind = "image"        # 📎 发的是图片扩展名 → 自动按图片消息内联显示
        op = body.get("resource_operation_id")
        try:
            saved = self.hub._save_web_file(
                name, data, kind, sess=sess,
                resource_operation_id=str(op) if op is not None else None)
        except Exception as exc:
            result = getattr(exc, "result", None)
            code = getattr(exc, "code", "resource_io")
            if code in ("resource_pending", "resource_busy"):
                self._json(202, {"ok": False, "error": code,
                                 "resource": result or {}})
            elif code in ("resource_unknown", "superseded"):
                self._json(409, {"ok": False, "error": code,
                                 "resource": result or {}})
            elif isinstance(exc, (PermissionError, ValueError)) \
                    or code in ("invalid_operation", "unknown_operation",
                                "payload_mismatch"):
                self._json(400, {"ok": False, "error": str(exc)})
            else:
                self._json(500, {"ok": False, "error": code,
                                 "resource": result or {}})
            return
        resource = saved.pop("resource", None)
        payload = {"ok": True, "file": saved}
        if resource:
            payload["resource"] = resource
        self._json(200, payload)

    def _file(self, q: dict):
        """GET /api/file?fid=：下载网页端文件（图片原图 / 附件；鉴权走 Cookie）。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        fid = q.get("fid") or ""
        meta = self.hub._web_file_meta(fid)
        path = self.hub._web_file_path(fid)
        if not meta or not path:
            self._json(404, {"ok": False, "error": "文件不存在"})
            return
        try:
            data = self.hub._web_file_read(sess, fid, meta)
        except OSError:
            self._json(404, {"ok": False, "error": "文件读取失败"})
            return
        except PermissionError:
            self._json(404, {"ok": False, "error": "文件不存在"})
            return
        ext = os.path.splitext(meta.get("name", ""))[1].lower()
        ctype = (_IMG_CTYPES.get(ext) or
                 ("image/png" if meta.get("kind") == "image"
                  else "application/octet-stream"))
        disp = f'attachment; filename="{urllib.parse.quote(meta.get("name", "file"))}"'
        if meta.get("kind") == "image":
            disp = f'inline; filename="{urllib.parse.quote(meta.get("name", "img"))}"'
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", disp)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _resource_result(self, q: dict):
        """GET /api/resource_result：owner 或明确 owner 的认证管理员查询。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        op = q.get("resource_operation_id") or ""
        explicit = q.get("resource_owner_uid")
        owner = None
        if explicit is not None:
            try:
                owner = int(explicit)
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "resource_owner_uid 无效"})
                return
            if not sess.is_admin:
                self._json(403, {"ok": False, "error": "无资源查询权限"})
                return
        try:
            result = self.hub._resource_query(sess, op, explicit_owner=owner)
        except PermissionError:
            self._json(403, {"ok": False, "error": "无资源查询权限"})
            return
        except LookupError:
            self._json(404, {"ok": False, "error": "资源结果不可用"})
            return
        except ValueError:
            self._json(400, {"ok": False, "error": "resource_operation_id 无效"})
            return
        self._json(200, {"ok": True, "resource": result})

    def _room_api(self, q: dict):
        """R72 GET /api/room?room=：语音房只读名册快照（网页端无法加入 UDP mesh）。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        room = (q.get("room") or "").strip()
        if not room:
            self._json(400, {"ok": False, "error": "缺少 room 参数"})
            return
        members = self.hub.voice_rooms.get(room)
        if not members:
            self._json(200, {"ok": True, "room": room, "count": 0,
                             "max": self.hub.cfg.voice_room_max, "members": []})
            return
        out = []
        for uid, d in members.items():
            nick = (self.hub.known.get(uid) or {}).get("nick", f"用户{uid}")
            out.append({"uid": uid, "nick": nick})
        self._json(200, {"ok": True, "room": room, "count": len(out),
                         "max": self.hub.cfg.voice_room_max, "members": out})

    def _vmemo_api(self, q: dict):
        """R72 GET /api/vmemo?seq=N：视频留言首帧 PNG（缩略图）；?raw=1 返回完整 VMA1。"""
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            seq = int(q.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        blob = self.hub._vmemo.get(seq)
        if not blob:
            self._json(404, {"ok": False, "error": "视频留言不存在或已过期"})
            return
        raw = q.get("raw") in ("1", "true", "True")
        if raw:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
            return
        import vmemo_api
        png = vmemo_api.first_frame_png(blob)
        if not png:
            self._json(500, {"ok": False, "error": "视频留言解码失败"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def _sticker_image(self, code: str):
        """R30C GET /api/sticker/<code>：自定义贴纸图片（免 token，便于 <img> 直引；
        本身不涉聊天内容，图片由登录用户主动上传共享）。"""
        import re as _re
        code = _re.fullmatch(r"[A-Za-z0-9_]{1,24}", code or "").group(0) \
            if _re.fullmatch(r"[A-Za-z0-9_]{1,24}", code or "") else ""
        meta = self.hub.custom_stickers.get(code) if code else None
        path = os.path.join(self.hub.sticker_dir,
                            f"{code}.{meta.get('ext')}") if meta else None
        data = None
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as e:            # 读失败不能与「贴纸不存在」混同 → 落 stderr 可排障
                print(f"[web] 读取贴纸文件失败 {path}: {e!r}", file=sys.stderr)
                data = None
        if data is None:
            self._json(404, {"ok": False, "error": "贴纸不存在"})
            return
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(str(meta.get("ext")), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "max-age=300")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- R65 网页端贴纸包深化（导航/封面/商店/包内排序） ----------
    def _pack_cover_img(self, q: dict):
        """GET /api/packcover?pack=：自定义包封面直出（路径由包名 md5 派生，防穿越）。"""
        sess = self._session(q)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        pack = str(q.get("pack") or "").strip()[:16]
        meta = self.hub.pack_meta.get(pack) or {}
        ext = str(meta.get("cover") or "").lower()
        data = None
        if ext:
            try:
                with open(self.hub._pack_cover_path(pack, ext), "rb") as f:
                    data = f.read()
            except OSError as e:            # 读失败不能与「该包暂无封面」混同 → 落 stderr 可排障
                print(f"[web] 读取贴纸包封面失败 {pack}: {e!r}", file=sys.stderr)
                data = None
        if data is None:
            self._json(404, {"ok": False, "error": "该包暂无封面"})
            return
        ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "gif": "image/gif", "webp": "image/webp",
                 "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "max-age=300")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _shop_post(self, body: dict):
        """POST /api/shop：{op: list|sub, pack_id?, on?} → 复用 STICKER_SHOP/STICKER_SUB 帧
        （结果经 SSE 异步回推 sticker_shop_list / sticker_sub）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        op = str(body.get("op") or "list")
        if op == "list":
            self.hub.dispatch(sess, {"t": MsgType.STICKER_SHOP.value})
        elif op == "sub":
            self.hub.dispatch(sess, {"t": MsgType.STICKER_SUB.value,
                                     "pack_id": str(body.get("pack_id") or ""),
                                     "on": bool(body.get("on"))})
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        self._json(200, {"ok": True})

    def _pack_post(self, body: dict):
        """POST /api/pack：自定义贴纸包管理，映射 STICKER_PACK_* / STICKER_REORDER 帧。
        body: {op: rename|del|cover_set|cover_del|reorder, ...}（结果经 SSE 回推）。"""
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        op = str(body.get("op") or "")
        pack = str(body.get("pack") or "").strip()[:16]
        if op == "rename":
            self.hub.dispatch(sess, {"t": MsgType.STICKER_PACK_RENAME.value,
                                     "old": pack,
                                     "new": str(body.get("new") or "").strip()[:16]})
        elif op == "del":
            if not pack:
                self._json(400, {"ok": False, "error": "缺少包名"})
                return
            self.hub.dispatch(sess, {"t": MsgType.STICKER_PACK_DEL.value, "pack": pack})
        elif op == "cover_del":
            if not pack:
                self._json(400, {"ok": False, "error": "缺少包名"})
                return
            self.hub.dispatch(sess, {"t": MsgType.STICKER_PACK_COVER.value, "pack": pack})
        elif op == "cover_set":
            img = body.get("img") or {}
            ext = str(img.get("ext") or "").lower().strip(". ")
            try:
                blob = base64.b64decode(str(img.get("data") or ""))
            except Exception:
                blob = b""
            if not pack or not blob or ext not in self.hub._STICKER_EXTS:
                self._json(400, {"ok": False, "error": "封面为空或格式不支持"})
                return
            if len(blob) > self.hub.cfg.sticker_max_bytes:
                self._json(400, {"ok": False,
                                 "error": f"封面超过 {self.hub.cfg.sticker_max_bytes // 1024}KB 上限"})
                return
            self.hub.dispatch(sess, {"t": MsgType.STICKER_PACK_COVER.value,
                                     "pack": pack, "ext": ext}, blob)
        elif op == "reorder":
            self.hub.dispatch(sess, {"t": MsgType.STICKER_REORDER.value,
                                     "code": str(body.get("code") or "").strip(),
                                     "dir": str(body.get("dir") or "").strip().lower()})
        else:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        self._json(200, {"ok": True})

    # ---------- R20 网页端群管理 / 已读 ----------
    _GROUP_ACTIONS = {"create": MsgType.GROUP_CREATE.value, "join": MsgType.GROUP_JOIN.value,
                      "leave": MsgType.GROUP_LEAVE.value, "kick": MsgType.GROUP_KICK.value,
                      "mute": MsgType.GROUP_MUTE.value, "admin": MsgType.GROUP_SET_ADMIN.value,
                      "announce": MsgType.GROUP_ANNOUNCE.value,
                      "ann_mode": MsgType.GROUP_ANN_MODE.value,       # C9①：仅公告说话模式开关
                      "slow": MsgType.GROUP_SLOW.value,              # R70D：群慢速档位
                      "invite": MsgType.GROUP_INVITE_GET.value,      # R28：群主/管理员取邀请码
                      "join_invite": MsgType.GROUP_JOIN_INVITE.value,  # R28：凭邀请码入群
                      "rename": MsgType.GROUP_RENAME.value,            # R28：群改名
                      "about": MsgType.GROUP_ABOUT.value,              # R9H：群简介（改/清）
                      "avatar_set": MsgType.GROUP_AVATAR_SET.value,    # R9H：群头像上传
                      "avatar_del": MsgType.GROUP_AVATAR_DEL.value,    # R9H：群头像清除
                      # R69B6/B7 群待办 / 接龙 / 签到（服务端权威）
                      "task_add": MsgType.TASK_ADD.value,
                      "task_do": MsgType.TASK_DO.value,
                      "task_list": MsgType.TASK_LIST.value,
                      "task_del": MsgType.TASK_DEL.value}

    def _group(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        action = body.get("action")
        t = self._GROUP_ACTIONS.get(action)
        if t is None:
            self._json(400, {"ok": False, "error": "未知操作"})
            return
        sess.touch()
        # 组装帧：各动作共用目标群，target 用于踢/禁言/设管理员；frame_body 承载群头像字节
        frame = {"t": t, "gid": body.get("gid")}
        frame_body = b""
        if action == "create":
            frame["name"] = body.get("name") or ""
            frame["public"] = bool(body.get("public"))   # R54：公开群标记
        elif action == "admin":
            frame["target"] = body.get("target")
            frame["enable"] = bool(body.get("enable", True))
        elif action == "mute":
            frame["target"] = body.get("target")
            frame["duration"] = int(body.get("duration") or 0)
        elif action in ("kick",):
            frame["target"] = body.get("target")
        elif action == "announce":
            frame["text"] = body.get("text") or ""
        elif action == "ann_mode":                 # C9①：仅公告说话模式开关
            frame["on"] = bool(body.get("on"))
        elif action == "slow":                     # R70D：群慢速档位（秒，0=关闭）
            frame["seconds"] = int(body.get("seconds") or 0)
        elif action == "join_invite":
            frame["code"] = body.get("code") or ""
        elif action == "rename":
            frame["name"] = body.get("name") or ""
        elif action == "about":                        # R9H：群简介（空=清除，服务器限长）
            frame["about"] = body.get("text") or ""
        elif action == "avatar_set":                   # R9H：群头像上传（base64 → body 字节）
            try:
                data = base64.b64decode(body.get("data") or "", validate=True)
            except Exception:
                self._json(400, {"ok": False, "error": "数据解码失败"})
                return
            ext = str(body.get("ext") or "").lower().lstrip(".")[:8]
            if ext not in self.hub.cfg.avatar_exts:
                self._json(400, {"ok": False, "error": "不支持的图片格式"})
                return
            if not data or len(data) > self.hub.cfg.avatar_max_bytes:
                self._json(400, {"ok": False, "error": "头像为空或超过 1MB 上限"})
                return
            frame["ext"] = ext
            frame_body = data
        elif action == "task_add":                     # R69B6/B7：发起群任务
            frame["text"] = body.get("text") or ""
            frame["mode"] = body.get("mode") or "todo"    # todo|relay|checkin
        elif action in ("task_do", "task_del"):        # R69B6/B7：参与/关闭
            try:
                frame["tid"] = int(body.get("tid") or 0)
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "任务号非法"})
                return
            if action == "task_do":
                frame["on"] = 1 if body.get("on", True) else 0
        self.hub.dispatch(sess, frame, frame_body)
        # dispatch 把权限/字段错误经 SSE error 事件回给前端展示；HTTP 统一回 ok+最新群列表
        self._json(200, {"ok": True, "groups": self.hub._group_list(sess.uid)})

    def _read(self, body: dict):
        sess = self._session(body)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            seq = int(body.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        if seq > 0:
            header = {"t": MsgType.READ.value, "channel": body.get("channel") or "public",
                      "seq": seq}
            if body.get("to") is not None:
                header["to"] = body["to"]
            self.hub.dispatch(sess, header)
        self._json(200, {"ok": True})

    def _group_detail(self, q: dict):
        sess = self.hub.session_by_token(self._tok_any(q))
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        sess.touch()
        try:
            gid = int(q.get("gid"))
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "gid 不合法"})
            return
        d = self.hub.group_detail(gid, sess.uid)
        if d is None:
            self._json(404, {"ok": False, "error": "群不存在"})
            return
        g = self.hub.groups.get(gid)               # R9H：补群简介/头像 ext（供资料面板与判权）
        if g:
            d["about"] = g.get("about", "")
            d["avatar"] = g.get("avatar", "")
        self._json(200, {"ok": True, **d})

    def _events(self, token: str):
        global _sse_active
        sess = self.hub.session_by_token(token)
        if not sess:
            self._json(401, {"ok": False, "error": "未登录"})
            return
        # SSE 连接上限：防单账号/恶意客户端用无限 EventSource 耗尽线程与队列
        with _sse_lock:
            admitted = int(_sse_active) < _SSE_MAX
            if admitted:
                _sse_active += 1
        if not admitted:
            self._json(503, {"ok": False,
                             "error": "连接数已满，请稍后再试"})
            return
        try:
            self._sse_loop(sess)
        finally:
            with _sse_lock:
                _sse_active -= 1

    def _sse_loop(self, sess):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = queue.Queue(maxsize=256)      # R49：连接级队列（fanout），多开/刷新互不抢帧
        sess.send.attach(q)
        last_keep = time.time()
        def active():
            check = getattr(self.hub, '_session_is_active', None)
            return not getattr(sess, 'closed', False) and (check is None or check(sess))
        try:
            while self._service_available() and active():
                try:
                    payload, _body = q.get(timeout=0.5)
                    terminal = (isinstance(payload, dict) and payload.get('t') == MsgType.ERROR.value
                                and payload.get('code') in ('deleted', 'kicked'))
                    if not self._service_available() or (not active() and not terminal):
                        break
                    self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False)
                                      + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                    if terminal:
                        break
                    if active():
                        sess.touch()
                    last_keep = time.time()
                except queue.Empty:
                    if not self._service_available() or not active():
                        break
                    if time.time() - last_keep >= 15.0:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        if active():
                            sess.touch()
                        last_keep = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            sess.send.detach(q)           # R49：断开即注销，防旧连接偷帧
            self.close_connection = True


class _QuietServer(ThreadingHTTPServer):
    """握手失败/对端重置静默化（HTTPS 端口被明文探测属正常噪音，不刷屏）"""

    def process_request(self, request, client_address):
        start = getattr(self.hub, '_start_worker', None)
        if start is None:
            return super().process_request(request, client_address)
        thread = start(self.process_request_thread, args=(request, client_address),
                       name='http-request', connection=request)
        if thread is None:
            self.shutdown_request(request)

    def _available(self):
        stop = getattr(self, '_hub_stop', None)
        check = getattr(self.hub, '_service_available', None)
        return not (stop is not None and stop.is_set()) and (check is None or check())

    def process_request_thread(self, request, client_address):
        """Track raw accept first, then transfer ownership before TLS IO."""
        original = request
        try:
            context = getattr(self, '_tls_context', None)
            if context is not None:
                request = context.wrap_socket(request, server_side=True, do_handshake_on_connect=False)
                replace_connection = getattr(self.hub, '_replace_managed_connection', None)
                if replace_connection is not None and not replace_connection(original, request):
                    return
                original_timeout = request.gettimeout()
                request.setblocking(False)
                deadline = time.monotonic() + max(0.1, float(getattr(self.hub.cfg, 'handshake_timeout', 5)))
                while self._available():
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError('TLS handshake timed out')
                    try:
                        request.do_handshake()
                        break
                    except ssl.SSLWantReadError:
                        select.select([request], [], [], min(left, 0.2))
                    except ssl.SSLWantWriteError:
                        select.select([], [request], [], min(left, 0.2))
                else:
                    return
                request.settimeout(original_timeout)
            if self._available():
                self.finish_request(request, client_address)
        except Exception:
            if self._available():
                self.handle_error(request, client_address)
        finally:
            try:
                self.shutdown_request(request)
            finally:
                forget = getattr(self.hub, '_forget_managed_connection', None)
                if forget is not None:
                    forget(request)
                if request is not original:
                    original.close()

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ssl.SSLError, ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def serve(hub, port: int | None = None, stop: threading.Event | None = None,
          https: bool | None = None):
    """启动网页端 HTTP(S) 服务（异步返回 httpd，供外部 shutdown）。

    https=None 时按 hub.cfg.web_https（缺省 False，供测试/内嵌场景）；
    生产入口 server.serve 显式传 True（环境变量 MOYU_WEB_HTTPS=0 可关）。
    HTTPS 证书由 tls_cert 零依赖自签生成，缓存在 audit_dir 同级的 web_tls/ 下。
    """
    check = getattr(hub, '_service_available', None)
    if check is not None and not check():
        from server_recovery import StoreError
        raise StoreError('service_unavailable')
    port = hub.cfg.web_port if port is None else port
    # Keep each listener bound to its own Hub, including embedded test servers.
    handler_type = type('BoundHandler', (_Handler,), {'hub': hub})
    # REL-01: the web listener follows the same literal IPv4 bind address as
    # the TCP listener.  getattr keeps embedded/legacy test doubles that
    # predate Cfg.bind_host compatible while real Cfg instances always carry
    # the validated value.
    bind_host = getattr(hub.cfg, "bind_host", "0.0.0.0")
    httpd = _QuietServer((bind_host, port), handler_type)
    httpd.hub = hub
    httpd._hub_stop = stop if stop is not None else getattr(hub, '_service_stop', None)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    if https is None:
        https = bool(getattr(hub.cfg, "web_https", False))
    try:
        if https:
            import tls_cert
            tls_dir = os.path.join(
                os.path.dirname(os.path.abspath(hub.cfg.audit_dir)), "web_tls")
            cert, key = tls_cert.ensure_cert(tls_dir)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            httpd._tls_context = ctx
        hub.audit.log(type="web_start", port=httpd.server_address[1], https=bool(https))
        start = getattr(hub, '_start_http_listener', None)
        if start is not None:
            start(httpd)
        else:
            threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.1},
                             daemon=True).start()
    except BaseException:
        httpd.server_close()
        raise
    return httpd
