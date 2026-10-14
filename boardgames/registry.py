# -*- coding: utf-8 -*-
"""展示包注册表：把「每款游戏的版面/渲染/素材」从巨石里解耦。

设计要点：
- 包模块必须轻量（只导出元数据与字符串引用），不得在 import 期拉起 tkinter；
  桌面画师 / 网页片段 / 素材模块都用 "mod:attr" 字符串引用，按需 importlib 解析。
- 未迁移的游戏不在注册表内，调用方走旧实现（零回归）。
- 任何解析失败都吞掉并返回 None/空，绝不让渲染路径抛异常。
"""
from __future__ import annotations

import importlib
from typing import NamedTuple, Optional


class GamePackage(NamedTuple):
    name: str
    label: str
    rules: str
    icon: Optional[str] = None
    desktop: Optional[str] = None
    web_js: Optional[str] = None
    web_css: Optional[str] = None
    assets: Optional[str] = None


PACKAGE_MODULES: tuple = ("boardgames.azul",)

_REGISTRY: dict = {}
_LOADED = False


def register(pkg: GamePackage) -> GamePackage:
    _REGISTRY[pkg.name] = pkg
    return pkg


def load_all() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for mod in PACKAGE_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:
            continue


def all_packages() -> list:
    load_all()
    return list(_REGISTRY.values())


def get(name: str) -> Optional[GamePackage]:
    load_all()
    return _REGISTRY.get(name)


def _resolve(ref: Optional[str]):
    if not ref or ":" not in ref:
        return None
    mod, attr = ref.split(":", 1)
    try:
        return getattr(importlib.import_module(mod), attr)
    except Exception:
        return None


def desktop_painter(name: str):
    pkg = get(name)
    return _resolve(pkg.desktop) if pkg else None


def web_parts() -> tuple:
    js, css = [], []
    for pkg in all_packages():
        j = _resolve(pkg.web_js)
        c = _resolve(pkg.web_css)
        if j:
            js.append(j)
        if c:
            css.append(c)
    return "\n".join(js), "\n".join(css)


def package_assets() -> dict:
    out: dict = {}
    for pkg in all_packages():
        a = _resolve(pkg.assets)
        if isinstance(a, dict):
            out.update(a)
    return out


def asset_keys() -> tuple:
    keys: list = []
    for pkg in all_packages():
        a = _resolve(pkg.assets)
        if isinstance(a, dict):
            keys.extend(a.keys())
    return tuple(keys)
