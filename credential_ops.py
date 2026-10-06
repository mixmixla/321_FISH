"""Runtime credential contracts; no files, passwords in receipts, or durable journal.

The Hub owns authentication, derivation, writer admission and disk publication.
This module only validates wire values and retains bounded, epoch-local receipts.
"""
from dataclasses import dataclass, field, replace
import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import uuid


AUTH_VERSION = 1
CREDENTIAL_VERSION = 1
_REQUEST = re.compile(r'[A-Za-z0-9_-]{1,64}', re.ASCII)
_IDENTIFIER = re.compile(r'[0-9a-f]{32}', re.ASCII)


class CredentialError(ValueError):
    """A fixed diagnostic, deliberately excluding submitted values."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


_MESSAGES = {
    'claim_required': '该昵称未绑定密码，请明确选择设置密码，或留空登录',
    'credential_upgrade_required': '请升级客户端后再设置或修改昵称密码',
    'credential_store_unavailable': '当前服务器未启用持久存储，不能设置或修改密码',
    'credential_admin_managed': '管理员凭据由服务器配置管理，不可修改',
    'credential_conflict': '账号状态已变化，请重新核实后发起新的操作',
    'credential_unknown': '凭据保存结果未知，请停止重试并重新核实服务器状态',
    'credential_write_failed': '凭据未保存，请核实存储后重新发起操作',
    'credential_store_busy': '服务器正在处理未确认的存储操作，请稍后核实',
    'credential_capacity': '本次服务的凭据操作记录已达到上限，请联系部署者',
    'credential_not_set': '尚未设置密码',
    'credential_already_bound': '该昵称已有密码，本次仅验证登录，没有重新设置凭据',
    'credential_pending': '同一认领操作仍在处理中，请核实结果后再操作',
    'old_password_invalid': '旧密码错误',
    'invalid_password': '密码错误',
    'password_too_long': '密码过长（最多64字符）',
    'retired': '该昵称对应的 UID 已永久退役',
    'service_unavailable': '服务器正在停止或存储状态未确认',
    'session_inactive': '当前会话已失效，请重新登录',
    'unauthorized': '未登录或登录已失效',
    'auth_context_changed': '服务器身份或运行状态已变化，请重新核实后登录',
    'context_required': '缺少当前会话上下文，请刷新并升级客户端',
    'context_changed': '登录身份已变化，请重新核实当前会话',
    'context_invalid': '会话上下文格式无效',
    'login_not_attached': '身份或凭据已保存，本次登录未完成',
    'operation_unavailable': '无法核实过去的凭据操作',
}


class AuthFailure(str):
    """String-compatible legacy diagnostic with explicit structured metadata."""

    def __new__(cls, reason, text=None, credential=None):
        instance = super().__new__(cls, text or _MESSAGES.get(reason, '认证或凭据请求无效'))
        instance.reason = reason
        instance.credential = credential
        return instance


def request_id(value):
    if not isinstance(value, str) or _REQUEST.fullmatch(value) is None:
        raise CredentialError('invalid_request_id')
    return value


def identifier(value, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CredentialError('invalid_identifier')
    return value


def positive_uid(value):
    if type(value) is not int or value <= 0:
        raise CredentialError('invalid_uid')
    return value


def _version(value, reason):
    if type(value) is not int or value != 1:
        raise CredentialError(reason)


def strict_json(raw):
    """No duplicate fields/nonfinite constants; diagnostics never echo input."""
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise CredentialError('invalid_json')
            result[key] = value
        return result

    def constant(_value):
        raise CredentialError('invalid_json')

    def finite_number(value):
        number = float(value)
        if not math.isfinite(number):
            raise CredentialError('invalid_json')
        return number

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant,
                          parse_float=finite_number)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise CredentialError('invalid_json') from None


@dataclass(frozen=True)
class LoginIntent:
    version: int | None
    request_id: str | None
    server_epoch: str | None
    store_scope_id: str | None
    claim_password: bool

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise CredentialError('invalid_auth_request')
        claim = value.get('claim_password', False)
        if type(claim) is not bool:
            raise CredentialError('invalid_claim')
        if 'auth_v' not in value:
            if claim:
                raise CredentialError('credential_upgrade_required')
            return cls(None, None, None, None, False)
        _version(value['auth_v'], 'unsupported_auth_version')
        if 'expected_store_scope_id' not in value:
            raise CredentialError('invalid_auth_context')
        return cls(1, request_id(value.get('request_id')),
                   identifier(value.get('expected_server_epoch')),
                   identifier(value['expected_store_scope_id'], nullable=True), claim)


@dataclass(frozen=True)
class UpdateRequest:
    request_id: str
    old: str = field(repr=False)
    new: str = field(repr=False)

    @classmethod
    def parse(cls, value, *, password_max):
        if not isinstance(value, dict):
            raise CredentialError('invalid_credential_request')
        _version(value.get('credential_v'), 'credential_upgrade_required')
        rid = request_id(value.get('request_id'))
        old, new = value.get('old', ''), value.get('new')
        if not isinstance(old, str) or not isinstance(new, str):
            raise CredentialError('invalid_password_fields')
        # Existing hashes (and deployment secrets) may predate the new-password
        # UI limit. Only a newly chosen value has the ordinary SET length rule.
        if len(new) > password_max:
            raise CredentialError('password_too_long')
        return cls(rid, old, new)


@dataclass(frozen=True)
class QueryRequest:
    request_id: str
    original_request_id: str
    operation_id: str | None
    operation_epoch: str

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise CredentialError('invalid_credential_request')
        _version(value.get('credential_v'), 'credential_upgrade_required')
        return cls(request_id(value.get('request_id')),
                   request_id(value.get('original_request_id')),
                   identifier(value.get('operation_id'), nullable=True),
                   identifier(value.get('operation_epoch')))


@dataclass(frozen=True)
class ExpectedCredential:
    nick: str
    uid: int | None
    known_present: bool
    password_present: bool
    password_hash: str | None = field(repr=False)
    uid_revision: int
    nick_revision: int


@dataclass(frozen=True)
class WebContext:
    server_epoch: str
    store_scope_id: str | None
    uid: int
    session_binding_id: str

    def payload(self):
        return {'v': 1, 'server_epoch': self.server_epoch,
                'store_scope_id': self.store_scope_id, 'uid': self.uid,
                'session_binding_id': self.session_binding_id}

    def encode(self):
        raw = json.dumps(self.payload(), separators=(',', ':'), ensure_ascii=True).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')

    @classmethod
    def decode(cls, value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 512
                or re.fullmatch(r'[A-Za-z0-9_-]+', value, re.ASCII) is None):
            raise CredentialError('context_invalid')
        try:
            raw = base64.b64decode(value + '=' * (-len(value) % 4),
                                   altchars=b'-_', validate=True)
            obj = strict_json(raw.decode('utf-8'))
            if (not isinstance(obj, dict) or set(obj) != {
                    'v', 'server_epoch', 'store_scope_id', 'uid', 'session_binding_id'}):
                raise CredentialError('context_invalid')
            _version(obj['v'], 'context_invalid')
            result = cls(identifier(obj['server_epoch']),
                         identifier(obj['store_scope_id'], nullable=True),
                         positive_uid(obj['uid']), identifier(obj['session_binding_id']))
            # Reject noncanonical base64 encodings; JSON key order is immaterial.
            if base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii') != value:
                raise CredentialError('context_invalid')
            return result
        except (ValueError, UnicodeError, TypeError):
            raise CredentialError('context_invalid') from None


@dataclass(frozen=True)
class CredentialResult:
    original_request_id: str
    operation_id: str | None
    operation_epoch: str
    uid: int | None
    status: str = 'pending'
    login_status: str = 'not_applicable'
    reason: str | None = None
    retryable: bool = False

    def payload(self, *, server_epoch, query_request_id=None):
        result = {'t': 'credential_result', 'credential_v': 1,
                  'request_id': query_request_id or self.original_request_id,
                  'original_request_id': self.original_request_id,
                  'operation_id': self.operation_id, 'operation_epoch': self.operation_epoch,
                  'server_epoch': server_epoch, 'uid': self.uid, 'status': self.status,
                  'credential_status': self.status, 'login_status': self.login_status,
                  'reason': self.reason, 'retryable': self.retryable}
        if self.status == 'confirmed':
            result['persisted'] = True
        return result


@dataclass(frozen=True)
class _Entry:
    result: CredentialResult
    input_mac: bytes = field(repr=False)


class OperationLedger:
    """Bounded SET receipts; caller must authenticate the exact Session first.

    No automatic eviction: forgetting a request would permit the same id to
    mutate again. A full epoch refuses new operations before derivation/IO;
    queries and existing-id retries remain usable. Pre-auth claims are inline
    only and never enter this UID-authorized query table.
    """

    def __init__(self, server_epoch, *, capacity=1024, max_active=16):
        self.server_epoch = identifier(server_epoch)
        if type(capacity) is not int or capacity < 1 or type(max_active) is not int or max_active < 1:
            raise ValueError('invalid credential capacity')
        self.capacity, self.max_active = capacity, max_active
        self._key = secrets.token_bytes(32)
        self._entries = {}
        self._lock = threading.RLock()

    def begin(self, uid, request):
        uid = positive_uid(uid)
        if not isinstance(request, UpdateRequest):
            raise TypeError('validated update request required')
        raw = json.dumps([request.old, request.new], ensure_ascii=True,
                         separators=(',', ':')).encode('ascii')
        mac = hmac.digest(self._key, raw, hashlib.sha256)
        key = (uid, request.request_id)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                if not hmac.compare_digest(existing.input_mac, mac):
                    raise CredentialError('request_parameter_conflict')
                return existing.result, False
            if (len(self._entries) >= self.capacity
                    or sum(e.result.status == 'pending' for e in self._entries.values()) >= self.max_active):
                raise CredentialError('credential_capacity')
            result = CredentialResult(request.request_id, uuid.uuid4().hex,
                                      self.server_epoch, uid)
            self._entries[key] = _Entry(result, mac)
            return result, True

    def finish(self, result, *, status, reason=None, retryable=False):
        if status not in ('confirmed', 'failed', 'unknown'):
            raise ValueError('invalid terminal credential status')
        key = (result.uid, result.original_request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.result.operation_id != result.operation_id:
                raise ValueError('credential operation is not owned')
            if entry.result.status != 'pending':
                return entry.result
            updated = replace(entry.result, status=status, reason=reason,
                              retryable=bool(retryable and status == 'failed'))
            self._entries[key] = replace(entry, result=updated)
            return updated

    def query(self, uid, request):
        uid = positive_uid(uid)
        if not isinstance(request, QueryRequest):
            raise TypeError('validated query request required')
        with self._lock:
            entry = self._entries.get((uid, request.original_request_id))
            if (request.operation_epoch == self.server_epoch and entry is not None
                    and request.operation_id in (None, entry.result.operation_id)):
                return entry.result
        return CredentialResult(request.original_request_id, request.operation_id,
                                request.operation_epoch, uid, status='unknown',
                                reason='operation_unavailable')


class ClaimLedger:
    """Inline-only claim deduplication; deliberately exposes no query method.

    Same bounded/no-eviction policy as SET. The Hub must reauthenticate a
    confirmed replay against today's UID/password before revealing its receipt.
    A receipt by itself never authorizes another Session.
    """

    def __init__(self, server_epoch, *, capacity=1024, max_active=16):
        self.server_epoch = identifier(server_epoch)
        if type(capacity) is not int or capacity < 1 or type(max_active) is not int or max_active < 1:
            raise ValueError('invalid credential capacity')
        self.capacity, self.max_active = capacity, max_active
        self._key = secrets.token_bytes(32)
        self._entries = {}
        self._lock = threading.RLock()

    def begin(self, nick, password, intent):
        if (not isinstance(nick, str) or not nick or not isinstance(password, str)
                or not isinstance(intent, LoginIntent) or intent.version != 1
                or intent.claim_password is not True or intent.server_epoch != self.server_epoch):
            raise CredentialError('invalid_claim')
        rid = request_id(intent.request_id)
        raw = json.dumps([nick, password, intent.claim_password, intent.version,
                          intent.server_epoch, intent.store_scope_id],
                         ensure_ascii=True, separators=(',', ':')).encode('ascii')
        mac = hmac.digest(self._key, raw, hashlib.sha256)
        key = (self.server_epoch, nick, rid)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                if not hmac.compare_digest(entry.input_mac, mac):
                    raise CredentialError('request_parameter_conflict')
                return entry.result, False
            if (len(self._entries) >= self.capacity
                    or sum(e.result.status == 'pending' for e in self._entries.values()) >= self.max_active):
                raise CredentialError('credential_capacity')
            result = CredentialResult(rid, uuid.uuid4().hex, self.server_epoch, None,
                                      login_status='not_attached')
            self._entries[key] = _Entry(result, mac)
            return result, True

    def finish(self, nick, result):
        if result.status not in ('confirmed', 'failed', 'unknown'):
            raise ValueError('invalid terminal claim status')
        key = (self.server_epoch, nick, result.original_request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.result.operation_id != result.operation_id:
                raise ValueError('claim operation is not owned')
            if entry.result.status != 'pending':
                return entry.result
            # Login delivery is a per-attempt fact, not a reusable authorization.
            stored = replace(result, login_status='not_attached')
            self._entries[key] = replace(entry, result=stored)
            return result
