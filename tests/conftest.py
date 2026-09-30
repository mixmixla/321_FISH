# -*- coding: utf-8 -*-
"""tests/conftest.py —— 全量回归稳定性兜底。

背景：widget 用例会创建/销毁多个 Tk root，Python 3.14 下长进程退出阶段
Tcl 清理偶发于错误线程执行（Tcl_AsyncDelete / 0x80000003 断点崩溃），
测试结果本身全部通过。此处在 pytest 完全收尾后（summary 已输出、
退出码已定）直接带码退出，跳过解释器关闭阶段的 Tcl 清理。

另外：运行期「Tcl_AsyncDelete: async handler deleted by the wrong
thread」崩溃的根因是 Font/Image/Variable 对象被后台线程的 GC 连带回收、
__del__ 跨线程调 Tcl —— 由 tkguard 在主线程守卫拦截（本文件 import 即生效，
覆盖所有测试文件进程）。
"""
import os
import sys

import tkguard            # noqa: F401  在首个 Tk/Font 创建前安装线程守卫


def pytest_addoption(parser):
    parser.addoption("--run-visual", action="store_true", default=False,
                     help="run visual/screenshot tests (Windows, needs Pillow)")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "visual: 截屏比对测试（需 --run-visual + Pillow + 可见显示器）")


def pytest_unconfigure(config):
    code = int(getattr(config, "exitcode", 0) or 0)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)
