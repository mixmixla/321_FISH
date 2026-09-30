"""伪造 ratchet 计数应在密钥推导前被拒绝，且不损坏正常收发状态。"""
import struct

import pytest

import crypto_e2ee
from crypto_e2ee import E2EEEngine, E2EEError


@pytest.mark.parametrize("group", [False, True])
def test_huge_counter_is_rejected_without_chain_steps(tmp_path, monkeypatch, group):
    sender = E2EEEngine(str(tmp_path / "sender"))
    receiver = E2EEEngine(str(tmp_path / "receiver"))
    if group:
        epoch, key = sender.new_group_epoch(7)
        receiver.set_peer_sender_key(7, 1, key, epoch)
        blob = sender.seal_group(7, {"text": "正常消息"})
        unseal = lambda payload: receiver.unseal_group(7, 1, payload)
    else:
        sender.establish_session(1, 2, receiver.identity_pub)
        receiver.establish_session(2, 1, sender.identity_pub)
        blob = sender.seal_ratchet(2, {"text": "正常消息"})
        unseal = lambda payload: receiver.unseal_ratchet(1, payload)
    forged = blob[:5] + struct.pack(">I", 0xFFFFFFFF) + blob[9:]
    original_step = crypto_e2ee._step_chain
    def forbidden_step(*args):
        pytest.fail("未认证超大计数不应进入补链循环")
    monkeypatch.setattr(crypto_e2ee, "_step_chain", forbidden_step)
    with pytest.raises(E2EEError) as error:
        unseal(forged)
    assert error.value.code == "counter"
    monkeypatch.setattr(crypto_e2ee, "_step_chain", original_step)
    assert unseal(blob) == {"text": "正常消息"}


def test_normal_counter_gap_still_decrypts(tmp_path):
    sender = E2EEEngine(str(tmp_path / "sender"))
    receiver = E2EEEngine(str(tmp_path / "receiver"))
    sender.establish_session(1, 2, receiver.identity_pub)
    receiver.establish_session(2, 1, sender.identity_pub)
    for _ in range(5):
        sender.seal_ratchet(2, {"text": "未收到"})
    blob = sender.seal_ratchet(2, {"text": "保留正常跳步能力"})
    assert receiver.unseal_ratchet(1, blob)["text"] == "保留正常跳步能力"
