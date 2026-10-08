"""Ephemeral administrator retirement ledger. No Tk, network, or persistence.

Every outbound request is registered before returning it to ClientCore. The
caller sends outside this model's short lock, then records the send result.
Server facts and the current local request phase are deliberately separate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import re
import threading
import time
import uuid


class RetirementError(ValueError):
    """An action is unavailable; its text can be shown to the administrator."""


@dataclass(frozen=True)
class Scope:
    host: str
    port: int
    admin_uid: int


@dataclass(frozen=True)
class Receipt:
    status: str
    operation_id: str
    target_uid: int
    target_nick: str
    origin: str | None = None
    content_sha256: str | None = None
    content_length: int | None = None
    failed_stage: str | None = None
    error_code: str | None = None
    retryable: bool = False
    persistence_phase: str | None = None
    identity_effect: str | None = None

    @classmethod
    def parse(cls, value, uid, nick):
        if not isinstance(value, dict):
            raise RetirementError('服务器退役结果结构无效')
        if (value.get('status') not in ('pending', 'failed', 'unknown', 'confirmed')
                or type(value.get('target_uid')) is not int or value['target_uid'] != uid
                or value.get('target_nick') != nick
                or not isinstance(value.get('operation_id'), str) or not value['operation_id'].strip()):
            raise RetirementError('服务器退役目标、操作号或状态不一致')
        origin, digest, length = (value.get(k) for k in ('origin', 'content_sha256', 'content_length'))
        if origin not in (None, 'written', 'reconciled_current_json', 'restored_valid_json'):
            raise RetirementError('服务器结果来源无效')
        if digest is not None and (not isinstance(digest, str) or re.fullmatch(r'[a-fA-F0-9]{64}', digest) is None):
            raise RetirementError('服务器结果摘要无效')
        if length is not None and (type(length) is not int or length < 0):
            raise RetirementError('服务器结果长度无效')
        if value['status'] != 'confirmed' and any(item is not None for item in (origin, digest, length)):
            raise RetirementError('未确认结果不能携带持久确认来源或内容证明')
        if any(value.get(k) is not None and not isinstance(value[k], str) for k in ('failed_stage', 'error_code')):
            raise RetirementError('服务器失败信息结构无效')
        if type(value.get('retryable', False)) is not bool:
            raise RetirementError('服务器重试标记无效')
        phase, effect = value.get('persistence_phase'), value.get('identity_effect')
        if 'persistence_phase' in value or 'identity_effect' in value:
            allowed = {
                'pending': (('intent', 'not_started'), ('snapshot', 'revoked')),
                'failed': (('intent', 'not_started'), ('snapshot', 'revoked')),
                'unknown': (('intent', 'unverified'), ('snapshot', 'revoked')),
                'confirmed': (('snapshot', 'revoked'),),
            }
            if (phase, effect) not in allowed[value['status']]:
                raise RetirementError('服务器撤权阶段组合无效；请重新查询')
        return cls(value['status'], value['operation_id'], uid, nick, origin, digest, length,
                   value.get('failed_stage'), value.get('error_code'),
                   value['status'] == 'failed' and value.get('retryable') is True,
                   phase, effect)


@dataclass(frozen=True)
class Outbound:
    request_id: str
    intent_id: str
    scope: Scope
    epoch: int
    purpose: str
    target: int | str
    operation_id: str | None

    def frame(self) -> dict:
        frame = {'t': 'admin_user_del' if self.purpose in ('delete', 'retry') else 'admin_user_get',
                 'uid': self.target, 'request_id': self.request_id}
        if self.operation_id is not None:
            frame['operation_id'] = self.operation_id
        return frame


@dataclass(frozen=True)
class View:
    intent_id: str
    scope: Scope
    target: int | str
    uid: int | None
    nick: str | None
    phase: str
    diagnostic: str
    receipt: Receipt | None
    confirmed: Receipt | None
    current_verified: bool
    ever_del: bool
    can_query: bool
    can_retry: bool
    can_cancel: bool


@dataclass(frozen=True)
class Outcome:
    changed: bool = False
    outbound: tuple[Outbound, ...] = ()
    detail: dict | None = None


@dataclass
class _Record:
    intent_id: str
    scope: Scope
    target: int | str
    uid: int | None
    nick: str | None
    phase: str = 'idle'
    diagnostic: str = ''
    operation_id: str | None = None
    receipt: Receipt | None = None
    confirmed: Receipt | None = None
    confirmed_epoch: int | None = None
    verified_epoch: int | None = None
    ever_del: bool = False
    history: bool = False
    generation: int = 0
    observation_serial: int = 0
    query_id: str | None = None
    mutation_id: str | None = None
    late_ids: list[str] = field(default_factory=list)


@dataclass
class _Request:
    out: Outbound
    generation: int
    deadline: float
    serial: int
    seen: bool = False
    final: bool = False


class RetirementBook:
    def __init__(self, *, clock=time.monotonic, limit=64, timeout=10.0):
        self._clock = clock
        self._limit = limit
        self._timeout = timeout
        self._lock = threading.RLock()
        self._records: dict[str, _Record] = {}
        self._requests: dict[str, _Request] = {}
        self._scope: Scope | None = None
        self._epoch = 0
        self._online = False
        self._auth_epoch: int | None = None
        self._serial = 0

    def begin_connection(self, epoch: int) -> bool:
        with self._lock:
            if type(epoch) is not int or epoch <= self._epoch:
                return False
            self._invalidate()
            self._scope, self._epoch, self._online = None, epoch, False
            self._auth_epoch = epoch
            return True

    def authenticate(self, scope: Scope | None, epoch: int) -> bool:
        """Only the current pending connection may acquire its WELCOME scope."""
        with self._lock:
            if self._auth_epoch != epoch or epoch != self._epoch:
                return False
            self._auth_epoch = None  # Invalid WELCOME scope also consumes the one-time permit.
            if scope is not None and (not isinstance(scope, Scope) or type(scope.admin_uid) is not int
                                      or scope.admin_uid <= 0):
                raise RetirementError('管理员身份编号无效')
            self._scope, self._online = scope, scope is not None
            return True

    def connect(self, scope: Scope | None, epoch: int) -> bool:
        """Convenience for an already authenticated *new* connection."""
        with self._lock:
            return self.begin_connection(epoch) and self.authenticate(scope, epoch)

    def disconnect(self, epoch: int) -> None:
        with self._lock:
            if epoch != self._epoch:
                return
            self._online = False
            self._auth_epoch = None
            self._invalidate()

    def _invalidate(self):
        self._requests.clear()
        for record in self._records.values():
            record.query_id = record.mutation_id = None
            record.late_ids.clear()
            record.verified_epoch = None
            record.phase = 'unverified'
            record.diagnostic = '连接已改变；保留历史结果，请在原服务器和管理员身份下重新查询'

    @staticmethod
    def _target(value):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise RetirementError('请输入有效的 UID 或昵称')
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise RetirementError('请输入 UID 或昵称')
            try:
                value = int(value)
            except ValueError:
                return value
        if value <= 0:
            raise RetirementError('UID 必须大于零')
        return value

    def _record_for(self, target, nick=None):
        for record in self._records.values():
            if record.scope != self._scope:
                continue
            if record.target == target or record.uid == target or (isinstance(target, str) and record.nick == target):
                return record
        if len(self._records) >= self._limit:
            disposable = next((r for r in self._records.values() if not r.ever_del and not r.history
                               and r.query_id is None and r.mutation_id is None), None)
            if disposable is None:
                raise RetirementError('本次会话退役记录已满；已有关联记录仍可查询，不能再创建新事项')
            del self._records[disposable.intent_id]
        record = _Record(uuid.uuid4().hex, self._scope, target,
                         target if isinstance(target, int) else None,
                         nick if nick is not None else target if isinstance(target, str) else None)
        self._records[record.intent_id] = record
        return record

    def _require_online(self):
        if not self._online or self._scope is None:
            raise RetirementError('请先连接服务器并以系统管理员身份登录')

    def begin(self, target, *, nick=None, purpose='query') -> Outbound:
        """preflight requires a fresh explicit confirmation; query/detail never mutate."""
        with self._lock:
            self._require_online()
            self._expire()
            if purpose not in ('preflight', 'query', 'detail'):
                raise RetirementError('无效的查询用途')
            target = self._target(target)
            record = self._record_for(target, nick)
            if nick is not None and record.nick is not None and nick != record.nick:
                raise RetirementError('目标昵称已改变，请刷新目标并重新确认')
            if record.query_id is not None:
                raise RetirementError('该目标正在查询，请等待结果或取消本地预核对')
            if purpose == 'preflight':
                if record.mutation_id is not None:
                    raise RetirementError('退役结果仍在处理中，请查询状态')
                if record.ever_del or record.history:
                    purpose = 'query'
                elif not record.nick:
                    raise RetirementError('请先刷新目标资料并确认昵称')
            return self._register(record, purpose)

    def query(self, intent_id: str) -> Outbound:
        with self._lock:
            record = self._current_record(intent_id)
            return self.begin(record.uid or record.target, nick=record.nick, purpose='query')

    def retry(self, intent_id: str) -> Outbound:
        with self._lock:
            self._expire()
            record = self._current_record(intent_id)
            if not self._can_retry(record):
                raise RetirementError('必须在当前连接核验为可重试的失败后，才能明确重试原操作')
            return self._register(record, 'retry')

    def _current_record(self, intent_id):
        self._require_online()
        record = self._records.get(intent_id)
        if record is None or record.scope != self._scope:
            raise RetirementError('此事项属于其它服务器或管理员身份；请使用无操作号的手工查询')
        return record

    def _register(self, record, purpose):
        is_mutation = purpose in ('delete', 'retry')
        if is_mutation:
            record.generation += 1
            record.ever_del = True  # Conservative even when sending later fails/partially succeeds.
            record.verified_epoch = None
        out = Outbound(uuid.uuid4().hex, record.intent_id, record.scope, self._epoch, purpose,
                       record.uid or record.target, record.operation_id)
        self._serial += 1
        self._requests[out.request_id] = _Request(out, record.generation, self._clock()+self._timeout, self._serial)
        if is_mutation:
            record.mutation_id = out.request_id
        else:
            record.query_id = out.request_id
        record.phase = 'sending' if is_mutation else 'preflight' if purpose == 'preflight' else 'querying'
        record.diagnostic = '正在核对目标，尚未发送退役命令' if purpose == 'preflight' else ''
        return out

    def sent(self, request_id: str, epoch: int, success: bool) -> None:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.out.epoch != epoch or epoch != self._epoch or request.seen:
                return  # A synchronous/fast receipt wins over a later send return value.
            record = self._records[request.out.intent_id]
            if request.generation < record.generation or request.serial < record.observation_serial:
                return
            mutation = request.out.purpose in ('delete', 'retry')
            if success:
                if mutation:
                    record.phase = 'waiting'
                    record.diagnostic = '已发送，等待服务器持久结果'
                return
            record.phase = 'unknown' if mutation else 'query_failed'
            record.verified_epoch = None
            record.diagnostic = '发送未能确认，结果可能已发生；请查询' if mutation else '查询未能发出；未因此发送退役命令'
            self._finish(request, keep_confirmation=mutation)

    def cancel(self, intent_id: str) -> bool:
        with self._lock:
            record = self._records.get(intent_id)
            request = self._requests.get(record.query_id) if record else None
            if not request or request.out.purpose != 'preflight':
                return False
            self._finish(request)
            record.phase, record.diagnostic = 'cancelled', '已取消本地预核对，未发送退役命令'
            return True

    def _finish(self, request, *, keep_confirmation=False):
        rid = request.out.request_id
        record = self._records.get(request.out.intent_id)
        if record is None:
            self._requests.pop(rid, None)
            return
        if record.query_id == rid:
            record.query_id = None
        if record.mutation_id == rid:
            record.mutation_id = None
        if keep_confirmation:
            if rid not in record.late_ids:
                record.late_ids.append(rid)
            while len(record.late_ids) > 2:
                self._requests.pop(record.late_ids.pop(0), None)
        else:
            self._requests.pop(rid, None)
            if rid in record.late_ids:
                record.late_ids.remove(rid)

    def _expire(self):
        now = self._clock()
        for request in list(self._requests.values()):
            record = self._records[request.out.intent_id]
            rid = request.out.request_id
            if rid in record.late_ids or now < request.deadline:
                continue
            mutation = request.out.purpose in ('delete', 'retry')
            record.phase = 'unknown' if mutation else 'query_failed'
            record.verified_epoch = None
            record.diagnostic = ('等待已超过10秒；结果可能已发生，请查询' if mutation
                                 else '未收到可关联的核对结果；本次查询未触发退役命令')
            self._finish(request, keep_confirmation=mutation)

    @staticmethod
    def _matches(record, frame):
        uid, nick = frame.get('uid'), frame.get('nick')
        return (type(uid) is int and uid > 0 and isinstance(nick, str) and bool(nick)
                and (record.uid is None or record.uid == uid)
                and (record.nick is None or record.nick == nick))

    def _merge_resolved(self, record, request, uid, nick):
        existing = next((r for r in self._records.values()
                         if r is not record and r.scope == record.scope and r.uid == uid), None)
        if existing is None:
            record.uid, record.nick = uid, nick
            return record, False
        if existing.nick is not None and existing.nick != nick:
            raise RetirementError('目标别名与已记录昵称冲突，请核对服务器身份')
        # The unresolved alias only owns reads. Cancel duplicate preflight
        # authority on both records; preserve any already registered mutation.
        for candidate in (record, existing):
            pending = self._requests.get(candidate.query_id)
            if pending and (candidate is record or pending.out.purpose == 'preflight'):
                self._finish(pending)
        existing.history = existing.history or record.history
        if existing.nick is None:
            existing.nick = nick
        if existing.phase == 'preflight':
            existing.phase, existing.diagnostic = 'unverified', '目标别名已合并，请重新查询并确认'
        del self._records[record.intent_id]
        return existing, True

    def receive(self, frame: dict, epoch: int) -> Outcome:
        with self._lock:
            if not self._online or epoch != self._epoch or frame.get('t') not in ('admin_user_info', 'error'):
                return Outcome()
            self._expire()
            rid = frame.get('request_id')
            request = self._requests.get(rid) if isinstance(rid, str) else None
            if request is None:
                # Old servers may answer a user-requested detail without echo.
                # Never infer an error, preflight or operation from its ordering.
                if 'request_id' not in frame and frame.get('t') == 'admin_user_info':
                    candidates = [q for q in self._requests.values() if q.out.purpose == 'detail'
                                  and self._matches(self._records[q.out.intent_id], frame)]
                    if len(candidates) == 1:
                        legacy = candidates[0]
                        legacy_record = self._records[legacy.out.intent_id]
                        self._finish(legacy)
                        legacy_record.phase = 'unverified' if legacy_record.history or legacy_record.ever_del else 'no_record'
                        legacy_record.verified_epoch = None
                        legacy_record.diagnostic = '旧服务器详情未关联；不能用于确认退役或开放重试'
                        return Outcome(True, detail={**copy.deepcopy(frame), 'correlated': False})
                return Outcome()
            if request.out.epoch != epoch or request.out.scope != self._scope:
                return Outcome()
            record = self._records[request.out.intent_id]
            request.seen = True
            stale_attempt = (request.generation < record.generation
                             or request.serial < record.observation_serial)
            if frame.get('t') == 'error':
                if not stale_attempt:
                    record.observation_serial = max(record.observation_serial, request.serial)
                    record.diagnostic = str(frame.get('text') or frame.get('code') or '请求被拒绝')[:240]
                    if not record.confirmed or request.out.purpose not in ('delete', 'retry'):
                        record.phase = 'rejected' if request.out.purpose in ('delete', 'retry') else 'query_failed'
                        record.verified_epoch = None
                self._finish(request, keep_confirmation=stale_attempt and request.out.purpose in ('delete', 'retry'))
                return Outcome(True)
            if not self._matches(record, frame):
                return self._invalid(record, request, '目标UID或昵称不一致；未采纳此结果')
            uid, nick = frame['uid'], frame['nick']
            try:
                record, merged = self._merge_resolved(record, request, uid, nick)
            except RetirementError as exc:
                return self._invalid(record, request, str(exc))
            stale_attempt = (request.generation < record.generation
                             or request.serial < record.observation_serial)
            detail = ({**copy.deepcopy(frame), 'correlated': True} if request.out.purpose == 'detail' else None)
            if 'retirement' not in frame:
                if (not merged and request.out.purpose == 'preflight' and not record.ever_del and not record.history):
                    self._finish(request)
                    return Outcome(True, (self._register(record, 'delete'),))
                if request.out.purpose in ('delete', 'retry') or record.history or record.ever_del:
                    return self._invalid(record, request, '当前连接未能核验已有退役事项；只能查询，不能重新退役', detail)
                if not merged:
                    self._finish(request)
                    record.phase, record.diagnostic = 'no_record', '服务器未报告退役记录；查询不会触发退役'
                return Outcome(True, detail=detail)
            record.history = True  # Even malformed retirement data is never a fresh-delete permit.
            try:
                receipt = Receipt.parse(frame['retirement'], uid, nick)
                if record.operation_id is not None and record.operation_id != receipt.operation_id:
                    raise RetirementError('退役操作号不匹配；只保留原事项')
            except RetirementError as exc:
                return self._invalid(record, request, str(exc), detail)
            if (stale_attempt or request.final) and receipt.status != 'confirmed':
                if request.out.purpose not in ('delete', 'retry'):
                    self._finish(request)
                return Outcome(detail=detail)
            record.observation_serial = max(record.observation_serial, request.serial)
            active = self._requests.get(record.mutation_id)
            if (active is not None and active is not request and active.serial < request.serial
                    and receipt.status != 'pending'):
                active.final = True
                self._finish(active, keep_confirmation=True)
            record.operation_id = receipt.operation_id
            if record.confirmed is not None and receipt.status != 'confirmed':
                # A new-epoch contradiction is current diagnostic, not a rollback
                # of historical confirmation and never a retry permission.
                record.phase, record.diagnostic = 'unverified', '当前结果与历史确认不一致，请核对服务器保存状态'
                record.verified_epoch = None
                self._finish(request, keep_confirmation=request.out.purpose in ('delete', 'retry'))
                return Outcome(True, detail=detail)
            record.receipt = receipt
            record.verified_epoch = epoch
            record.phase, record.diagnostic = receipt.status, ''
            if receipt.status == 'confirmed':
                record.confirmed = receipt
                record.confirmed_epoch = epoch
            if request.out.purpose not in ('delete', 'retry'):
                if not merged:
                    self._finish(request)
            elif receipt.status != 'pending':
                request.final = True
                self._finish(request, keep_confirmation=True)
            return Outcome(True, detail=detail)

    def _invalid(self, record, request, diagnostic, detail=None):
        if request.generation >= record.generation:
            if request.serial < record.observation_serial:
                return Outcome(detail=detail)
            record.observation_serial = max(record.observation_serial, request.serial)
            record.phase = 'unverified' if record.confirmed or record.history or record.ever_del else 'query_failed'
            record.verified_epoch = None
            record.diagnostic = diagnostic
        self._finish(request, keep_confirmation=request.out.purpose in ('delete', 'retry'))
        return Outcome(True, detail=detail)

    def _can_retry(self, record):
        return bool(self._online and record.scope == self._scope and record.verified_epoch == self._epoch
                    and record.receipt and record.receipt.status == 'failed' and record.receipt.retryable
                    and record.confirmed is None and record.query_id is None and record.mutation_id is None
                    and record.phase == 'failed')

    def snapshot(self) -> tuple[View, ...]:
        with self._lock:
            self._expire()
            result = []
            for record in self._records.values():
                current = self._online and record.scope == self._scope
                pending = self._requests.get(record.query_id)
                result.append(View(record.intent_id, record.scope, record.target, record.uid, record.nick,
                                   record.phase, record.diagnostic, record.receipt, record.confirmed,
                                   bool(current and record.verified_epoch == self._epoch), record.ever_del,
                                   bool(current and record.query_id is None), self._can_retry(record),
                                   bool(current and pending and pending.out.purpose == 'preflight')))
            return tuple(result)

    def confirmed_uids(self, epoch: int) -> frozenset[int]:
        with self._lock:
            if not self._online or epoch != self._epoch:
                return frozenset()
            return frozenset(r.uid for r in self._records.values() if r.scope == self._scope
                             and r.confirmed and r.confirmed_epoch == epoch)
