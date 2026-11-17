#! python3
# -*- encoding: utf-8 -*-

"""响应包装：统一包络取值与成功/失败判定。"""

import types

from apisk.core.response import ApiResponse


def _response(payload=None, status_code=200, text=""):
    """构造一个 requests.Response 的最小替身。"""
    return types.SimpleNamespace(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        text=text or "{}",
        json=lambda: payload,
    )


def test_unwraps_envelope_fields():
    resp = ApiResponse(_response({
        "request_id": "req-1",
        "code": "OK",
        "message": "success",
        "timestamp": 0,
        "data": {"id": 7},
    }))

    assert resp.request_id == "req-1"
    assert resp.code == "OK"
    assert resp.message == "success"
    assert resp.data == {"id": 7}
    assert resp.has_envelope() is True


def test_ok_requires_http_200_and_code_ok():
    assert ApiResponse(_response({"code": "OK"})).ok is True
    assert ApiResponse(_response({"code": "OK"}, status_code=201)).ok is False
    assert ApiResponse(_response({"code": "REQUEST_INVALID"})).ok is False


def test_is_error_only_when_code_present():
    assert ApiResponse(_response({"code": "REQUEST_INVALID"})).is_error is True
    assert ApiResponse(_response({"code": "OK"})).is_error is False
    assert ApiResponse(_response({"data": 1})).is_error is False


def test_has_envelope_needs_all_four_fields():
    partial = ApiResponse(_response({"request_id": "r", "code": "OK"}))

    assert partial.has_envelope() is False


def test_non_json_body_degrades_gracefully():
    response = types.SimpleNamespace(
        status_code=502,
        headers={},
        text="<html>bad gateway</html>",
        json=lambda: (_ for _ in ()).throw(ValueError("not json")),
    )

    resp = ApiResponse(response)

    assert resp.json is None
    assert resp.payload == {}
    assert resp.code is None
    assert resp.data == {}
    assert resp.status_code == 502


def test_data_must_be_dict():
    resp = ApiResponse(_response({"code": "OK", "data": [1, 2, 3]}))

    assert resp.data == {}


def test_retryable_passthrough():
    assert ApiResponse(_response({"retryable": True})).retryable is True
    assert ApiResponse(_response({})).retryable is None
