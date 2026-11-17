#! python3
# -*- encoding: utf-8 -*-

"""现场留痕：凭据脱敏、片段截断、收集开关。"""

import json

from apisk.core.exchange import (
    MASK,
    HttpExchange,
    mask_body,
    mask_headers,
    record_exchange,
    recording,
    snippet,
)


def test_mask_headers_is_case_insensitive():
    masked = mask_headers({
        "Authorization": "Bearer secret",
        "X-API-KEY": "abc",
        "Set-Cookie": "sid=1",
        "Accept": "application/json",
    })

    assert masked["Authorization"] == MASK
    assert masked["X-API-KEY"] == MASK
    assert masked["Set-Cookie"] == MASK
    assert masked["Accept"] == "application/json"


def test_mask_headers_handles_none():
    assert mask_headers(None) == {}


def test_mask_body_recurses_into_nested_structures():
    body = {
        "user": {"name": "alice", "password": "p@ss"},
        "items": [{"token": "t-1"}, {"ok": 1}],
        "access_token": "at",
    }

    masked = mask_body(body)

    assert masked["user"]["password"] == MASK
    assert masked["items"][0]["token"] == MASK
    assert masked["items"][1]["ok"] == 1
    assert masked["access_token"] == MASK


def test_mask_body_keeps_plain_values():
    assert mask_body("plain text") == "plain text"
    assert mask_body(42) == 42


def test_snippet_flattens_whitespace():
    assert snippet("line1\n  line2\t line3") == "line1 line2 line3"


def test_snippet_truncates_with_total_length():
    text = "x" * 700
    result = snippet(text, limit=10)

    assert result.startswith("x" * 10)
    assert "共 700 字符" in result


def test_recording_collects_inside_context_only():
    exchange = HttpExchange(method="GET", url="http://host/", status_code=200, elapsed_ms=1.0)

    with recording() as buffer:
        record_exchange(exchange)
        assert buffer == [exchange]

    record_exchange(exchange)            # 上下文已退出，应是空操作
    assert len(buffer) == 1


def test_recording_is_isolated_between_contexts():
    with recording() as outer:
        record_exchange(HttpExchange("GET", "http://host/a", 200, 1.0))
        with recording() as inner:
            record_exchange(HttpExchange("GET", "http://host/b", 200, 1.0))
        assert len(inner) == 1
        assert len(outer) == 1


def test_exchange_summary_is_single_line():
    exchange = HttpExchange("POST", "http://host/api", 500, 123.44)

    summary = exchange.summary()

    assert "\n" not in summary
    assert "POST http://host/api" in summary
    assert "500" in summary
    assert "123.4ms" in summary


def test_exchange_describe_masks_nothing_extra():
    exchange = HttpExchange(
        method="GET",
        url="http://host/api",
        status_code=200,
        elapsed_ms=12.0,
        request_headers={"Authorization": MASK},
        request_body={"password": MASK},
        response_snippet="ok",
    )

    text = exchange.describe()

    assert "请求: GET http://host/api" in text
    assert MASK in text
    assert "响应片段: ok" in text


def test_exchange_to_dict_is_json_serializable():
    exchange = HttpExchange(
        method="GET",
        url="http://host/api",
        status_code=200,
        elapsed_ms=12.3456,
        request_headers={"Accept": "application/json"},
        request_body={"a": 1},
        response_headers={"Content-Type": "application/json"},
        response_snippet="{}",
    )

    payload = json.loads(json.dumps(exchange.to_dict(), ensure_ascii=False))

    assert payload["request"]["url"] == "http://host/api"
    assert payload["response"]["elapsed_ms"] == 12.346
