# -*- coding: utf-8 -*-
"""widgets/runs.py —— 富文本分段与布局（@提及 / 链接 渲染，对标 TG 实体绘制）。

纯函数、无 tk 依赖，可单测：
- ``tag_entities(text)`` 把正文切成有序片段 [(text, kind)]，kind ∈ plain|mention|link。
- ``wrap_segments(segments, width, measure)`` 按宽度换行，返回多行，每行若干 (text, kind)；
  供 msg_list 的画布逐段 create_text 与高度估算共用，保证所见即所估。
"""
import re

PLAIN = "plain"
MENTION = "mention"
LINK = "link"
HASHTAG = "hashtag"      # R30E：#话题标签（可点 → 全局搜索）
READ_MARK = "read_mark"  # R33③：✓已读 标记（行头独立段，hover 弹已读详情）
SENT_MARK = "sent_mark"  # R-：自己消息未读单勾（私聊已发但对端未读，仅渲染不互动）
PENDING = "pending"      # P0 三态：本地已发、服务器未确认（发送中）
REPLY = "reply"          # R41F：引用前缀段（可点 → 跳转原消息）
EDIT_MARK = "edit_mark"  # R70B：「✎已编辑」标记（可点 → 查看编辑历史）
DISGUISE = "disguise"    # R70E：消息伪装风格表头（等宽、按风格着色）
KINDS = (PLAIN, MENTION, LINK, HASHTAG, READ_MARK, SENT_MARK, PENDING, REPLY,
         EDIT_MARK, DISGUISE)

_MENTION = re.compile(r"@[^\s@]+")
_HTTP = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>]+")
_HASHTAG = re.compile(r"#[^\s#]{1,32}")


def tag_entities(text: str) -> list:
    """把 text 切成有序 [(seg, kind)]。@提及 与 链接 命中高亮，其余 plain。"""
    if not text:
        return []
    hits = []
    for m in _MENTION.finditer(text):
        hits.append((m.start(), m.end(), MENTION))
    for m in _HTTP.finditer(text):
        hits.append((m.start(), m.end(), LINK))
    for m in _HASHTAG.finditer(text):
        hits.append((m.start(), m.end(), HASHTAG))
    hits.sort(key=lambda x: x[0])
    segs, pos = [], 0
    for s, e, k in hits:
        if s < pos:                  # 重叠（如 @ 内嵌于链接）→ 跳过
            continue
        if s > pos:
            segs.append((text[pos:s], PLAIN))
        segs.append((text[s:e], k))
        pos = e
    if pos < len(text):
        segs.append((text[pos:], PLAIN))
    return segs


def _line_w(words: list, measure) -> int:
    """一行宽度：词宽和 + 词间空格。measure(t, kind)（kind 控制字体档）。"""
    ma = _adapted(measure)
    if not words:
        return 0
    w = sum(ma(t, k) for t, k in _iter2(words))
    return w if isinstance(words, TextLine) else w + ma(" ", "") * (len(words) - 1)


class TextLine(list):
    """Runs contain their exact spacing. hard_break identifies source newlines."""
    hard_break = False


def _wrap_exact(segments, width, measure):
    lines, cur = [], TextLine()
    used = 0

    def flush(hard=False):
        nonlocal cur, used
        cur.hard_break = hard
        lines.append(cur)
        cur, used = TextLine(), 0

    for seg in segments:
        kind = seg[1] if len(seg) > 1 else PLAIN
        for token in re.findall(r"\n|[^\S\n]+|[^\s]+", seg[0]):
            if token == "\n":
                flush(hard=True)
                continue
            if cur and used + measure(token, kind) > width:
                flush()
            for chunk in _split_word(token, width, measure, kind):
                size = measure(chunk, kind)
                if cur and used + size > width:
                    flush()
                cur.append((chunk, kind, seg[2]) if len(seg) >= 3 else (chunk, kind))
                used += size
    if cur or (lines and lines[-1].hard_break):
        flush()
    return lines


def _split_word(word: str, width, measure, kind) -> list:
    """超宽单词/含中文无空格串 → 贪心按字符拆分（≤width 的块）。"""
    ma = _adapted(measure)
    chunks, cur = [], ""
    for ch in word:
        if cur and ma(cur + ch, kind) > width:
            chunks.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        chunks.append(cur)
    return chunks


def _iter2(words):
    """把 2/3 维段统一成 (text, kind)，兼容新旧调用方（third=href 忽略）。"""
    for seg in words:
        t = seg[0]
        k = seg[1] if len(seg) > 1 else PLAIN
        yield t, k


def _adapted(measure):
    """把 measurer 统一成 2 参 (t, kind)。只收 1 参的旧测量函数（如测试 lambda）兼容适配。

    绑定方法 (obj.method) 的 ``__code__`` 复用的是底层函数 code 对象，``co_argcount``
    含 ``self``；需减去 1 才能得到调用方实际可传的参数个数。"""
    func = getattr(measure, "__func__", None)
    bound = func is not None
    try:
        n = (func if bound else measure).__code__.co_argcount
    except AttributeError:
        return measure                       # 无 __code__（builtin 等）→ 信任为 2 参
    n -= 1 if bound else 0                   # 绑定方法去掉已绑定的 self
    if n >= 2:
        return measure
    return (lambda t, k, _m=measure: _m(t))


def wrap_segments(segments: list, width: int, measure, *, preserve_whitespace=False) -> list:
    """按 width 换行。返回 lines：每行是 [[(text, kind)]]（原段结构保留）。

    新行（\\n）硬断；空格处单词换行；超宽单块按字符硬拆（CJK 安全）。
    measure(t, kind)：按段落种类使用对应字体档测量，保证富文本换行与绘制一致。
    """
    lines, cur = [], []
    ma = _adapted(measure)
    if preserve_whitespace:
        return _wrap_exact(segments, width, ma)

    def flush():
        if cur:
            lines.append(list(cur))     # 拷贝再清，避免引用被后续 clear 清空
            cur.clear()

    for seg in segments:
        text = seg[0]
        kind = seg[1] if len(seg) > 1 else PLAIN
        # 切成 token 列表：保留换行做硬断，中文整串视作一个词
        tokens, buf = [], ""
        for ch in text:
            if ch == "\n":
                if buf:
                    tokens.append((buf, kind))
                    buf = ""
                tokens.append(("\n", kind))
            elif ch.isspace():
                if buf:
                    tokens.append((buf, kind))
                    buf = ""
            else:
                buf += ch
        if buf:
            tokens.append((buf, kind))
        for tok, k in tokens:
            if tok == "\n":
                flush()
                continue
            w = ma(tok, k)
            if cur and _line_w(cur, ma) + ma(" ", "") + w > width:
                flush()
            if w > width:
                for chunk in _split_word(tok, width, ma, k):
                    if cur and _line_w(cur, ma) + ma(" ", "") + ma(chunk, k) > width:
                        flush()
                    cur.append((chunk, k) if len(seg) < 3 else (chunk, k, seg[2]))
            else:
                cur.append((tok, k, seg[2]) if len(seg) >= 3 else (tok, k))
    flush()
    return lines


def line_width(line: list, measure) -> int:
    """某行内容像素宽（画气泡宽度用）。"""
    return _line_w(line, measure)


def normalize_url(text: str) -> str:
    """裸 www. 补 http://；其余原样返回。"""
    return ("http://" + text) if text.lower().startswith("www.") else text
