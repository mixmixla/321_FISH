# -*- coding: utf-8 -*-
"""build.py —— PyInstaller 双 EXE 打包（阶段6）。

产出：
  dist/server.exe（console，运行即起 hub + 网页端 + UDP 广播）
  dist/client.exe（windowed，无黑窗；日志/下载/审计落到用户目录）

要点：
  - 函数内动态 import 的模块（server.py 里的 web/discovery）必须显式
    hidden-import，否则 PyInstaller 收集不到、exe 起服即 ImportError；
  - cryptography 的二进制加速子模块显式打包；
  - 图标用 Pillow 现画素色"文档"图（无文字/无摸鱼特征），Pillow 仅打包期可选。
R71 语音转写内置（仅影响 client.exe）：
  - 打包机需先 `pip install vosk`（打包期依赖，运行期由 exe 自带）；
    未装 → 跳过 `--collect-all=vosk` 并醒目警告（不硬失败）；
  - 需准备 models/vosk/（下载 vosk-model-small-cn-0.22 解压放入），
    否则打印醒目警告并跳过 --add-data（开发打包仍可继续）；
  - 代价：client.exe 体积 +百 MB 级，--onefile 每次启动需把模型解包到临时目录，
    首启/冷启偏慢（可用「语音转写设置」把模型目录指到外部副本绕开）。
运行：python build.py （或 python run.py build）
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON_HIDDEN = [
    "--hidden-import=web",
    "--hidden-import=tls_cert",                    # R40：web.py 函数级 import（自签 HTTPS）
    "--hidden-import=discovery",
    "--hidden-import=audit",
    "--hidden-import=stickers",
    "--hidden-import=bots",                        # R35 内置 Bots
    "--hidden-import=widgets.thread_window",       # R34：动态 import
    "--hidden-import=widgets.sticker_shop",        # R35：动态 import
    "--hidden-import=widgets.fingerprint",         # R36：指纹比对窗（函数级 import）
    "--hidden-import=widgets.server_tray",         # R57：服务器常驻托盘（函数级 import）
    "--hidden-import=pystray",                     # R57：托盘图标（函数级 import）
    "--hidden-import=PIL.Image",
    "--hidden-import=PIL.ImageDraw",
    "--hidden-import=voice_api",                   # R38A：winmm 音频（函数级 import）
    "--hidden-import=video_api",                   # R45：MF 视频采集（函数级 import）
    "--hidden-import=cryptography.hazmat.primitives.asymmetric.x25519",
    "--hidden-import=cryptography.hazmat.primitives.kdf.hkdf",
    "--hidden-import=cryptography.hazmat.primitives.ciphers.aead",
]
# R71：vosk 仅 client 用（optional.transcribe_wav 函数内 import）→ 只收集进 client.exe。
STT_MODEL_DIR = os.path.join(HERE, "models", "vosk")


def vosk_args() -> list:
    """R71：仅当打包机装了 vosk 才 `--collect-all`（否则 PyInstaller 直接报错，
    违背「开发环境仍能打包、不硬失败」）；缺依赖 → 醒目警告并跳过。"""
    try:
        import importlib.util
        if importlib.util.find_spec("vosk") is not None:
            return ["--collect-all=vosk"]
    except Exception:
        pass
    print("[build] ⚠ 打包机未安装 vosk —— 语音转写依赖不会打进 client.exe！\n"
          "        请先 pip install vosk 再打包。", flush=True)
    return []


def stt_data_args() -> list:
    """R71：把内置 vosk 中文小模型打进 client.exe；缺模型 → 醒目警告并跳过。

    判定口径与 optional._valid_model_dir 一致（须有 am/final.mdl），
    否则空目录会被「打进包」却不含模型，反而绕过本警告。"""
    if not os.path.isfile(os.path.join(STT_MODEL_DIR, "am", "final.mdl")):
        print("[build] ⚠ models/vosk/ 不存在或未放模型（缺 am/final.mdl）"
              " —— 语音转写内置模型不会随包发布！\n"
              "        请下载 vosk-model-small-cn-0.22 解压到 models/vosk/，"
              "并确认打包机已 pip install vosk。", flush=True)
        return []
    return [f"--add-data={STT_MODEL_DIR}{os.pathsep}models/vosk"]


def make_icon(path: str) -> None:
    """素色"文档"图标：无文字/无摸鱼特征，避免被眼尖同事识破（Pillow 可选）"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, 236, 236), 40, fill=(37, 88, 150))
    d.rounded_rectangle((66, 62, 190, 92), 8, fill=(255, 255, 255))
    d.rounded_rectangle((66, 112, 190, 142), 8, fill=(214, 228, 242))
    d.rounded_rectangle((66, 162, 150, 192), 8, fill=(150, 195, 235))
    img.save(path, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])


def _run(args: list) -> int:
    cmd = [sys.executable, "-m", "PyInstaller", *args]
    print(">>", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=HERE)


def build() -> int:
    icon = os.path.join(HERE, "app.ico")
    try:
        make_icon(icon)
    except Exception as exc:                    # Pillow 未装 → 无图标继续
        print(f"[build] 图标生成跳过（Pillow 不可用？）：{exc}")
        icon = None

    icon_args = [f"--icon={icon}"] if icon else []
    common = COMMON_HIDDEN + icon_args + ["--noconfirm", "--clean"]

    rc = _run(["--onefile", "--console", *common,
               "--name=server", "server.py"])
    if rc != 0:
        return rc
    rc = _run(["--onefile", "--windowed", *common, *vosk_args(),
               *stt_data_args(), "--name=client", "client.py"])
    return rc


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
