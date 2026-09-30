# -*- coding: utf-8 -*-
"""R38B 可选依赖统一探测与调用门面：vosk（本地转文字）/ deep-translator（翻译）
/ rlottie+Pillow（Lottie 动画表情）。

原则（守住"纯标准库可打包"卖点）：
- 全部软依赖：缺失时 has_* 返回 False，UI 隐藏入口/降级渲染，绝不崩；
- 探测用 importlib.util.find_spec（不真正 import，重依赖在用户真正使用时才加载）；
- 转文字纯本地（vosk 模型在本地跑，语音/文本不上传）；翻译需联网，
  由调用方先征得用户同意（prefs 默认关 + 隐私提示）。
"""
import importlib.util
import json
import os
import sys
import threading

from config import STT_MODEL_SUBDIR, _log_dir

_lock = threading.Lock()
_cache: dict = {}


class OptionalMissing(RuntimeError):
    """可选依赖未安装（UI 应降级而非抛栈）。"""


def has(name: str) -> bool:
    """模块是否存在（结果缓存；探测失败视为不存在）。"""
    with _lock:
        if name in _cache:
            return _cache[name]
    try:
        found = importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        found = False
    with _lock:
        _cache[name] = found
    return found


def has_stt() -> bool:            # 本地语音转文字（vosk）
    return has("vosk")


def has_translator() -> bool:     # 消息翻译（deep_translator）
    return has("deep_translator")


def has_lottie() -> bool:         # Lottie 动画表情（rlottie + Pillow）
    return has("rlottie") and has("PIL")


# ---------- 语音转文字（纯本地） ----------

def _valid_model_dir(path: str) -> bool:
    """目录是否像 vosk 模型（含 am/final.mdl；模型解压后必有此文件）。"""
    return bool(path) and os.path.isdir(path) and os.path.isfile(
        os.path.join(path, "am", "final.mdl"))


def find_model_dir(pref_dir: str = "") -> str:
    """定位 vosk 模型目录，按优先级：
        1) prefs 显式配置（vosk_model_dir）
        2) 环境变量 VOSK_MODEL
        3) 打包内置模型 <sys._MEIPASS>/models/vosk（R71：onefile 解包目录）
        4) 可写用户目录 <_log_dir()>/models/vosk（R71：持久，可手动放外部模型）
        5) 源码运行的项目目录 models/vosk
    返回空串表示未找到（UI 提示配置）。
    保留 1/2/4 的意义：用户可指向外部模型副本，绕开 onefile 每次启动解包。"""
    meipass = getattr(sys, "_MEIPASS", None)
    cands = [
        pref_dir or "",
        os.environ.get("VOSK_MODEL", ""),
        os.path.join(meipass, STT_MODEL_SUBDIR) if meipass else "",
        os.path.join(_log_dir(), STT_MODEL_SUBDIR),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     STT_MODEL_SUBDIR),
    ]
    for cand in cands:
        if _valid_model_dir(cand):
            return cand
    return ""


def transcribe_wav(path: str, model_dir: str, lang: str = "zh-cn") -> str:
    """WAV → 文本（vosk 本地识别；8/16k 单声道均可，R19 录音为 16k）。
    懒加载模型（首用慢属正常）；失败抛 OptionalMissing/RuntimeError。"""
    if not has_stt():
        raise OptionalMissing("vosk 未安装（pip install vosk）")
    if not model_dir or not os.path.isdir(model_dir):
        raise OptionalMissing("未配置 vosk 模型目录")
    import wave

    from vosk import KaldiRecognizer, Model, SetLogLevel
    try:
        SetLogLevel(-1)                    # 静默 C 层日志
    except Exception:
        pass
    model = Model(model_dir)
    with wave.open(path, "rb") as wf:
        rec = KaldiRecognizer(model, wf.getframerate(), lang)
        texts = []
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                texts.append(str(json.loads(rec.Result()).get("text") or ""))
        texts.append(str(json.loads(rec.FinalResult()).get("text") or ""))
    return " ".join(t for t in texts if t).strip()


# ---------- 消息翻译（需联网） ----------

def translate_text(text: str, target: str = "zh-CN",
                   source: str = "auto") -> str:
    """deep-translator 翻译（Google 免费端点；调用方须已获用户同意并自担网络）。"""
    if not has_translator():
        raise OptionalMissing("deep-translator 未安装（pip install deep-translator）")
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=source or "auto",
                            target=target or "zh-CN").translate(text)
