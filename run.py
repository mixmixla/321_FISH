# -*- coding: utf-8 -*-
"""一键编排：默认跑隔离逐文件门禁；支持专项 test/server|client|build。

用法:
    python run.py            # 隔离逐文件全量门禁（须全绿）
    python run.py test-all   # 同上，可用 --resume/--label 等门禁参数
    python run.py test -k x # 保留单进程专项 pytest 入口
    python run.py server     # 启动服务器（控制台）
    python run.py server initialize-new --store-dir <全新目录>  # 显式建库后退出
    python run.py server open --store-dir <状态目录>            # 校验/恢复后启动
    python run.py server inspect --store-dir <状态目录>         # 只读分类
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
    raw_args = list(sys.argv[1:])
    explicit_command = bool(raw_args and not raw_args[0].startswith("-"))
    cmd = raw_args.pop(0) if explicit_command else "test-all"
    args = raw_args

    # 去掉子命令本身，子模块 argparse 只看自己的参数
    # （README 示例：python run.py client --host 192.168.1.10）
    sys.argv = [sys.argv[0]] + args

    if cmd in ("test-all", "gate"):
        from test_gate import main as gate_main
        return gate_main(args)
    if cmd == "test":
        # 保留历史专项入口：显式 `run.py test -k ...` 仍是一次 pytest，
        # 方便调试单个选择器；默认入口和 test-all 统一走逐文件隔离门禁。
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
