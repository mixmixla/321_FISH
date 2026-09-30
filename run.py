# -*- coding: utf-8 -*-
"""一键编排：默认跑 pytest 门禁；支持 server|client|build 子命令。

用法:
    python run.py            # 全量门禁（须全绿）
    python run.py server     # 启动服务器（控制台）
    python run.py client     # 启动客户端（GUI）
    python run.py build      # PyInstaller 打包 server.exe / client.exe
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cmd = args[0] if args else "test"

    # 去掉子命令本身，子模块 argparse 只看自己的参数
    # （README 示例：python run.py client --host 192.168.1.10）
    if cmd != "test":
        sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != cmd]

    if cmd == "test":
        import pytest
        return pytest.main(["-q", os.path.join(os.path.dirname(__file__), "tests")])
    if cmd == "server":
        from server import main as smain
        return smain()
    if cmd == "client":
        from client import main as cmain
        return cmain()
    if cmd == "build":
        from build import main as bmain
        return bmain()
    print(f"未知命令: {cmd}（可用: server | client | build | 默认跑门禁）")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
