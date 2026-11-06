# -*- coding: utf-8 -*-
"""2048 展示包：规则与桌面/Web 渲染分离。"""
from games_pkg.tile2048 import Tile2048Game  # noqa: F401
from boardgames.registry import GamePackage, register


PKG = GamePackage(
    name="tile2048",
    label="2048 · 方块合成",
    rules="games_pkg.tile2048:Tile2048Game",
    icon="tile2048",
    desktop="boardgames.tile2048.desktop:paint",
    web_js="boardgames.tile2048.web:WEB_JS",
    web_css="boardgames.tile2048.web:WEB_CSS",
)
register(PKG)
