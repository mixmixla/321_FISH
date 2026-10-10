"""DPI startup order and scaling contracts; no OS settings are changed."""
import ctypes
from types import SimpleNamespace

import pytest
import dpi


def test_declared_context_is_system_aware_not_per_monitor(monkeypatch):
    seen=[]
    monkeypatch.setattr(dpi.os,'name','nt')
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(
        SetProcessDpiAwarenessContext=lambda context:seen.append(context.value) or 1)))
    assert dpi.apply_early(True)
    assert seen==[ctypes.c_void_p(-2).value]


def test_main_declares_before_early_tray(monkeypatch):
    import client
    import launcher
    import prefs
    order=[]
    monkeypatch.setattr(client.CFG,'tray_enabled',True)
    monkeypatch.setattr(client,'_start_early_tray',lambda:order.append('tray-tk'))
    monkeypatch.setattr(dpi,'apply_early',lambda enabled:order.append(('dpi',enabled)))
    class MemoryPrefs:
        def get(self,key,default=None):return default
    monkeypatch.setattr(prefs,'Prefs',MemoryPrefs)
    monkeypatch.setattr(launcher,'run_chat',lambda *args:order.append('chat'))
    monkeypatch.setattr(client.sys,'argv',['client.py','--nick','DPI合成'])
    assert client.main()==0
    assert order==[('dpi',True),'tray-tk','chat']


def test_dpi_disabled_does_not_read_or_change_tk_scaling(monkeypatch):
    def forbidden(*args):
        raise AssertionError('Disabled DPI path attempted scaling')
    monkeypatch.setattr(dpi,'_system_dpi',forbidden)
    root=SimpleNamespace(tk=SimpleNamespace(call=forbidden))
    assert dpi.fix_scaling(root,enabled=False)==1.0


@pytest.mark.parametrize('dpi_value',[96,120,144,192])
def test_tk_scaling_matrix_is_points_to_pixels(monkeypatch,dpi_value):
    calls=[]
    root=SimpleNamespace(tk=SimpleNamespace(call=lambda *args:calls.append(args)))
    monkeypatch.setattr(dpi.os,'name','nt')
    monkeypatch.setattr(dpi,'_system_dpi',lambda:dpi_value)
    assert dpi.fix_scaling(root)==pytest.approx(dpi_value/96)
    assert calls==[('tk','scaling',dpi_value/72)]
