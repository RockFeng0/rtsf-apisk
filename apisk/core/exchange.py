#! python3
# -*- encoding: utf-8 -*-

"""请求 / 响应现场留痕。

用例失败时真正有用的信息不是「断言不成立」，而是「实际发出去、收回来的
是什么」。本模块提供两件东西：

* ``HttpExchange`` —— 一次请求/响应的不可变快照（请求头/请求体已脱敏、响应片段截断）；
* ``record_exchange()`` / ``recording()`` —— 收集开关。``HttpClient`` 每发一次
  请求都会调用 ``record_exchange()``，但**只有当前上下文开启了收集**才真的缓存；
  平时是一次空操作，框架因此不持有跨用例的可变状态。

开关按 pytest 用例粒度由框架插件（``--apisk-dump-http``）打开，于是
「哪个用例失败 → 它的请求长什么样」在报告目录里一目了然。
"""

import contextlib
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

#: 凭据类请求头被替换成的占位符
MASK = "***"
#: 需要脱敏的请求头名（大小写不敏感）
SENSITIVE_HEADERS = frozenset({
    "authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token",
})
#: 需要脱敏的请求体字段名（大小写不敏感，递归匹配）
SENSITIVE_FIELDS = frozenset({
    "password", "passwd", "token", "secret", "access_token", "refresh_token",
})
#: 响应片段保留的最大字符数
SNIPPET_LIMIT = 600

_recorder: ContextVar[Optional[List["HttpExchange"]]] = ContextVar(
    "apisk_http_recorder", default=None
)


def mask_headers(headers) -> Dict[str, str]:
    """把凭据类请求头替换成占位符，其余原样保留。"""
    masked = {}
    for key, value in dict(headers or {}).items():
        masked[str(key)] = MASK if str(key).lower() in SENSITIVE_HEADERS else str(value)
    return masked


def mask_body(value):
    """递归把请求体里的凭据字段替换成占位符，其余原样保留。"""
    if isinstance(value, dict):
        return {
            str(key): MASK if str(key).lower() in SENSITIVE_FIELDS else mask_body(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_body(item) for item in value]
    return value


def snippet(text, limit: int = SNIPPET_LIMIT) -> str:
    """把正文压成单行并截断：够定位问题，又不至于淹没报错信息。"""
    flat = " ".join(str(text if text is not None else "").split())
    return flat if len(flat) <= limit else f"{flat[:limit]}…（共 {len(flat)} 字符）"


def record_exchange(exchange: "HttpExchange") -> None:
    """记录一次交换；当前上下文未开启收集时什么都不做。"""
    buffer = _recorder.get()
    if buffer is not None:
        buffer.append(exchange)


@contextlib.contextmanager
def recording() -> Iterator[List["HttpExchange"]]:
    """开启一段收集，退出时归还缓冲（未开启收集时 ``record_exchange`` 空转）。"""
    buffer: List[HttpExchange] = []
    token = _recorder.set(buffer)
    try:
        yield buffer
    finally:
        _recorder.reset(token)


@dataclass(frozen=True)
class HttpExchange:
    """一次请求/响应的现场快照。"""

    method: str
    url: str
    status_code: int
    elapsed_ms: float
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_body: Any = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_snippet: str = ""

    def summary(self) -> str:
        """一行摘要，例如 ``POST http://host/api → status code=500 (123.4ms)``。"""
        return (
            f"{self.method} {self.url} → status code={self.status_code}"
            f"（{self.elapsed_ms:.1f}ms）"
        )

    def describe(self) -> str:
        """多行现场描述，供断言辅助附在 ``AssertionError`` 里。"""
        lines = [
            f"请求: {self.method} {self.url}",
            f"请求头: {json.dumps(self.request_headers, ensure_ascii=False)}",
        ]
        if self.request_body is not None:
            lines.append(f"请求体: {_compact(self.request_body)}")
        lines.append(
            f"响应: status code={self.status_code}（{self.elapsed_ms:.1f}ms）"
        )
        lines.append(f"响应片段: {self.response_snippet}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的字典（用于 ``--apisk-dump-http`` 落盘）。"""
        return {
            "request": {
                "method": self.method,
                "url": self.url,
                "headers": self.request_headers,
                "body": _jsonable(self.request_body),
            },
            "response": {
                "status_code": self.status_code,
                "elapsed_ms": round(self.elapsed_ms, 3),
                "headers": self.response_headers,
                "snippet": self.response_snippet,
            },
        }


def _compact(value) -> str:
    """请求体压成单行字符串，非 JSON 类型退化为 ``str``。"""
    return snippet(json.dumps(_jsonable(value), ensure_ascii=False))


def _jsonable(value):
    """尽力把请求体转成可序列化形式（文件对象等退化为文本描述）。"""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        return str(value)
    return value


__all__ = [
    "MASK",
    "SENSITIVE_FIELDS",
    "SENSITIVE_HEADERS",
    "SNIPPET_LIMIT",
    "HttpExchange",
    "mask_body",
    "mask_headers",
    "record_exchange",
    "recording",
    "snippet",
]