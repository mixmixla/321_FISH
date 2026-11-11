"""Dou presentation; rule state and all ranks remain server authoritative."""
from boardgames.registry import GamePackage, register

register(GamePackage(name="dou", label="斗兽棋 · 兽娘森境", rules="games_pkg.dou:DouGame",
                     web_js="boardgames.chess_dou.web:WEB_JS",
                     web_css="boardgames.chess_dou.web:WEB_CSS"))
