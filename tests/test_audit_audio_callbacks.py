# -*- coding: utf-8 -*-
"""离线 fakeWinMM 回归：wave 回调只排队，普通线程完成 native 生命周期。"""
import ctypes
import threading
import time

import pytest

import voice_api


class FakeWinMM:
    def __init__(self, *, mic_prepare=0, mic_add=0):
        self.mic_prepare = mic_prepare
        self.mic_add = mic_add
        self.mic_add_calls = []
        self.mic_unprepare_calls = []
        self.mic_reset_calls = 0
        self.mic_close_calls = 0
        self.out_prepare_calls = []
        self.out_write_calls = []
        self.out_unprepare_calls = []
        self.out_reset_calls = 0
        self.out_close_calls = 0
        self.out_proc = None
        self.in_callback = False
        self.callback_thread = None
        self.native_from_callback = []

    def _record_native(self, name):
        if self.in_callback and threading.get_ident() == self.callback_thread:
            self.native_from_callback.append(name)

    def waveInGetNumDevs(self):
        return 1

    @staticmethod
    def _set_handle(out, value):
        ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p)).contents.value = value

    @staticmethod
    def _hdr(ptr):
        return ctypes.cast(ptr, ctypes.POINTER(voice_api.WAVEHDR)).contents

    def waveInOpen(self, out, _mapper, _fmt, proc, _instance, _flags):
        self._record_native("waveInOpen")
        self._set_handle(out, 0x1001)
        return 0

    def waveInPrepareHeader(self, h, ptr, size):
        self._record_native("waveInPrepareHeader")
        return self.mic_prepare

    def waveInAddBuffer(self, h, ptr, size):
        self._record_native("waveInAddBuffer")
        self.mic_add_calls.append(ctypes.addressof(self._hdr(ptr)))
        return self.mic_add

    def waveInUnprepareHeader(self, h, ptr, size):
        self._record_native("waveInUnprepareHeader")
        self.mic_unprepare_calls.append(ctypes.addressof(self._hdr(ptr)))
        return 0

    def waveInStart(self, h):
        self._record_native("waveInStart")
        return 0

    def waveInReset(self, h):
        self._record_native("waveInReset")
        self.mic_reset_calls += 1
        return 0

    def waveInClose(self, h):
        self._record_native("waveInClose")
        self.mic_close_calls += 1
        return 0

    def waveOutOpen(self, out, _mapper, _fmt, proc, _instance, _flags):
        self._record_native("waveOutOpen")
        self._set_handle(out, 0x2001)
        self.out_proc = proc
        return 0

    def waveOutPrepareHeader(self, h, ptr, size):
        self._record_native("waveOutPrepareHeader")
        self.out_prepare_calls.append(ctypes.addressof(self._hdr(ptr)))
        return 0

    def waveOutWrite(self, h, ptr, size):
        self._record_native("waveOutWrite")
        self.out_write_calls.append(ctypes.addressof(self._hdr(ptr)))
        return 0

    def waveOutUnprepareHeader(self, h, ptr, size):
        self._record_native("waveOutUnprepareHeader")
        self.out_unprepare_calls.append(ctypes.addressof(self._hdr(ptr)))
        return 0

    def waveOutReset(self, h):
        self._record_native("waveOutReset")
        self.out_reset_calls += 1
        return 0

    def waveOutClose(self, h):
        self._record_native("waveOutClose")
        self.out_close_calls += 1
        return 0

    def trigger_out_done(self, address):
        """用新的 ctypes wrapper 模拟 winmm 回调传回的 WAVEHDR 地址。"""
        hdr = next(h for h, _ in self._out_pool
                   if ctypes.addressof(h) == address)
        self.in_callback = True
        self.callback_thread = threading.get_ident()
        try:
            self.out_proc(ctypes.c_void_p(0x2001), voice_api._WOM_DONE,
                          None, ctypes.c_void_p(ctypes.addressof(hdr)), None)
        finally:
            self.in_callback = False

    def bind_out_pool(self, pool):
        self._out_pool = list(pool)


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.fixture()
def fake(monkeypatch):
    f = FakeWinMM()
    monkeypatch.setattr(voice_api, "available", lambda: True)
    monkeypatch.setattr(voice_api, "_winmm", lambda: f)
    return f


def test_mic_callback_only_queues_and_pcm_nul_bytes_survive(fake):
    mic = voice_api.MicRecorder()
    assert mic.start()
    assert len(mic._hdrs) == 4
    fake_calls = len(fake.mic_add_calls)
    hdr = mic._hdrs[0]
    data = b"\x01\x00\x02\x00\x00\x03\x00"
    ctypes.memmove(hdr.lpData, data, len(data))
    hdr.dwBytesRecorded = len(data)
    fake.in_callback = True
    fake.callback_thread = threading.get_ident()
    try:
        mic._callback(ctypes.c_void_p(0x1001), voice_api._WIM_DATA, None,
                      ctypes.c_void_p(ctypes.addressof(hdr)), None)
    finally:
        fake.in_callback = False
    # 回调返回前没有 waveInAddBuffer；之后由 mic-pump 重挂。
    assert not fake.native_from_callback
    assert _wait_until(lambda: len(fake.mic_add_calls) >= fake_calls + 1)
    assert mic.frames.get(timeout=1) == data

    # 同一组四个 buffer 可重复回收，不会因回调包装对象 identity 不同而耗尽。
    for _ in range(3):
        hdr.dwBytesRecorded = len(data)
        mic._callback(ctypes.c_void_p(0x1001), voice_api._WIM_DATA, None,
                      ctypes.c_void_p(ctypes.addressof(hdr)), None)
        assert _wait_until(lambda: len(fake.mic_add_calls) >= fake_calls + 2)
        fake_calls += 1
    mic.stop()
    assert fake.mic_reset_calls == 1
    assert fake.mic_close_calls == 1
    assert not fake.native_from_callback


def test_mic_start_with_no_valid_buffers_returns_without_reentrant_stop(monkeypatch):
    fake = FakeWinMM(mic_prepare=1)
    monkeypatch.setattr(voice_api, "available", lambda: True)
    monkeypatch.setattr(voice_api, "_winmm", lambda: fake)
    mic = voice_api.MicRecorder()
    assert mic.start() is False
    assert fake.mic_reset_calls == 1
    assert fake.mic_close_calls == 1
    mic.stop()                         # 已清理，不能挂住或重复关闭


def test_spk_callback_queues_done_and_reuses_all_eight_headers(fake):
    spk = voice_api.SpkPlayer()
    assert spk.start()
    fake.bind_out_pool(spk._pool)
    for _ in range(voice_api._POOL + 3):
        spk.feed(b"\x00" * voice_api.FRAME_BYTES)
    assert _wait_until(lambda: len(fake.out_write_calls) >= voice_api._POOL)
    first_batch = list(fake.out_write_calls[:voice_api._POOL])

    for address in first_batch:
        fake.trigger_out_done(address)
    assert _wait_until(lambda: len(fake.out_unprepare_calls) >= voice_api._POOL)
    assert not fake.native_from_callback
    assert _wait_until(lambda: len(spk._free) == voice_api._POOL)

    for _ in range(voice_api._POOL):
        spk.feed(b"\x01" * voice_api.FRAME_BYTES)
    assert _wait_until(lambda: len(fake.out_write_calls) >= voice_api._POOL * 2)
    second_batch = fake.out_write_calls[voice_api._POOL:voice_api._POOL * 2]
    assert set(second_batch) == set(first_batch)
    for address in second_batch:
        fake.trigger_out_done(address)
    assert _wait_until(lambda: len(fake.out_unprepare_calls) >= voice_api._POOL * 2)
    assert not fake.native_from_callback
    spk.stop()
    assert fake.out_reset_calls == 1
    assert fake.out_close_calls == 1
