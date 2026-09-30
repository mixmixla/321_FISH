# -*- coding: utf-8 -*-
"""一键编排：默认跑 pytest 门禁；支持 server|client|build 子命令。

用法:
    python run.py            # 全量门禁（须全绿）
    python run.py server     # 启动服务器（控制台）
    python run.py client     # 启动客户端（GUI）
    python run.py build      # PyInstaller 打包 server.exe / client.exe
"""
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    args = list(sys.argv[1:])
    cmd = args.pop(0) if args and not args[0].startswith("-") else "test"

    # 去掉子命令本身，子模块 argparse 只看自己的参数
    # （README 示例：python run.py client --host 192.168.1.10）
    sys.argv = [sys.argv[0]] + args

    if cmd == "test":
        root = os.path.dirname(os.path.abspath(__file__))
        temp_root = os.path.join(root, "_tmp_gui")
        os.makedirs(temp_root, exist_ok=True)
        # 每次门禁使用独立目录，避免不同 Windows 运行身份共享 pytest-of-*
        # 时发生权限/锁冲突。父进程不加载 Tk，子进程可安全跳过 Tcl 收尾，
        # 父进程仍能清理临时文件并返回真实退出码。
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        with tempfile.TemporaryDirectory(prefix="pytest-", dir=temp_root) as temp:
            return subprocess.call(
                [sys.executable, "-m", "pytest", "-q", os.path.join(root, "tests"),
                 "--basetemp", temp, *args], env=env)
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
