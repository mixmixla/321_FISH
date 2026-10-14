# -*- coding: utf-8 -*-
"""Azul 展示包：花砖物语·拼花。版面/渲染/素材自成一体（规则仍在 games_pkg.azul）。"""
from games_pkg.azul import AzulGame  # noqa: F401  （对外自包含；规则复用现有实现）
from boardgames.registry import GamePackage, register

PKG = GamePackage(
    name="azul",
    label="花砖物语 · 拼花",
    rules="games_pkg.azul:AzulGame",
    icon="azul",
    desktop="boardgames.azul.desktop:paint",
    web_js="boardgames.azul.web:WEB_JS",
    web_css="boardgames.azul.web:WEB_CSS",
    assets="boardgames.azul._art:ASSETS",
)
register(PKG)
