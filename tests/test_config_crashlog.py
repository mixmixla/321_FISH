# -*- coding: utf-8 -*-
"""crash.log 轮转：超过阈值归档为 crash.log.1，新写入落到新文件，防无限膨胀。"""
import os

from config import _MAX_CRASH_LOG, _open_crash, _crash_write, crash_log_path


def test_crash_log_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr("config._log_dir", lambda: str(tmp_path))
    path = crash_log_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write("x" * (_MAX_CRASH_LOG + 1))      # 构造超阈值旧文件

    _open_crash()                                # 打开即轮转
    assert os.path.exists(path + ".1")
    assert os.path.getsize(path) == 0            # 新文件空

    _crash_write("[boot] test\n")
    with open(path, encoding="utf-8") as f:
        assert f.read() == "[boot] test\n"
    assert os.path.getsize(path) < 100

    _open_crash()                                # 小文件再打开不重复轮转
    assert os.path.exists(path + ".1")
    with open(path, encoding="utf-8") as f:
        assert f.read() == "[boot] test\n"
