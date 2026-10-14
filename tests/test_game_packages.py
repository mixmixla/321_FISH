# -*- coding: utf-8 -*-
"""展示包注册表：契约、惰性解析、失败兜底。"""
import subprocess
import sys
import types

import pytest

from boardgames import registry as reg


def _fake_pkg(name="faketest"):
    return reg.GamePackage(name=name, label="假包", rules="games_pkg.azul:AzulGame",
                           icon="azul",
                           desktop="tests._fakepkg:PAINT_CALLS",
                           web_js="tests._fakepkg:WEB_JS",
                           web_css="tests._fakepkg:WEB_CSS",
                           assets="tests._fakepkg:ASSETS")


def _install_fakepkg():
    mod = types.ModuleType("tests._fakepkg")
    mod.PAINT_CALLS = []
    mod.WEB_JS = "Object.assign(GRENDER,{});"
    mod.WEB_CSS = ".fake{}"
    mod.ASSETS = {"fake_a": "data:image/png;base64,AAAA"}
    sys.modules["tests._fakepkg"] = mod
    return mod


def test_registry_import_headless_and_no_tkinter():
    # 在同进程里断言 sys.modules 不可靠：tests/conftest.py 会 import tkguard，
    # 而 tkguard 会 import tkinter —— 任何其它用例都可能污染解释器状态。
    # 因此在全新子进程里验证「只 import boardgames.registry 不拉起 tkinter/PIL」。
    code = ("import boardgames.registry, sys; "
            "print('tkinter' in sys.modules or 'PIL' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", out.stdout


def test_register_get_and_resolve():
    _install_fakepkg()
    pkg = reg.register(_fake_pkg())
    assert reg.get("faketest") is pkg
    assert reg.desktop_painter("faketest") is sys.modules["tests._fakepkg"].PAINT_CALLS
    js, css = reg.web_parts()
    assert "Object.assign(GRENDER" in js and ".fake{}" in css
    assert reg.package_assets()["fake_a"].startswith("data:image/png;base64,")
    assert "fake_a" in reg.asset_keys()


def test_missing_ref_and_unknown_name_degrade_to_none():
    assert reg.get("does_not_exist") is None
    assert reg.desktop_painter("does_not_exist") is None
    bad = reg.register(reg.GamePackage(name="badtest", label="坏包", rules="x:y",
                                       desktop="no.such.module:paint",
                                       assets="no.such.module:ASSETS"))
    assert reg.desktop_painter("badtest") is None
    assert "badtest" not in reg.package_assets()


def test_client_render_falls_back_to_package_painter():
    import client_gameui as cu
    calls = []
    reg.register(reg.GamePackage(
        name="faketest2", label="假包2", rules="x:y",
        desktop="tests._fakepkg2:PAINT"))
    mod = types.ModuleType("tests._fakepkg2")
    mod.PAINT = lambda cv, st, me, nick, submit, repaint, ui, priv, w, h: calls.append(w)
    sys.modules["tests._fakepkg2"] = mod
    cu._PKG_PAINTERS.pop("faketest2", None)

    class _Cv:
        def delete(self, *a): pass
        def create_text(self, *a, **k): pass
        def bind(self, *a, **k): pass

    cu.render(_Cv(), "faketest2", {}, 1, lambda u: str(u), lambda a: None,
              lambda: None, {}, None, 400, 300)
    assert calls == [400]


def test_client_render_unknown_game_uses_generic_not_package():
    import client_gameui as cu
    cu._PKG_PAINTERS.pop("nope", None)
    assert cu._pkg_painter("nope") is None
