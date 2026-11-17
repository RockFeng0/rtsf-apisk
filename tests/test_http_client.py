#! python3
# -*- encoding: utf-8 -*-

"""HTTP 客户端：URL 拼接、凭据不可变、查询串与探活。

其中「参数真的到了对端」一类断言必须打真实回显服务 —— 只 mock
``requests.request`` 无法证明查询串被拼进了 URL。
"""

import pytest

from apisk.core.http_client import HttpClient, probe_deployment


# ---------- URL 拼接 ----------

def test_base_url_trailing_slash_is_normalized():
    assert HttpClient("http://host/api/").url("/v1") == "http://host/api/v1"


def test_path_without_leading_slash_is_fixed():
    assert HttpClient("http://host").url("v1/ping") == "http://host/v1/ping"


def test_absolute_url_passes_through():
    client = HttpClient("http://host")

    assert client.url("https://other/api") == "https://other/api"


def test_empty_base_url_supports_absolute_urls():
    assert HttpClient("").url("http://host/x") == "http://host/x"


# ---------- 凭据 ----------

def test_token_becomes_bearer_header():
    client = HttpClient("http://host", token="abc")

    assert client.is_anonymous is False
    assert client.token == "abc"
    assert dict(client._auth_headers) == {"Authorization": "Bearer abc"}


def test_anonymous_client_has_no_authorization():
    client = HttpClient("http://host")

    assert client.is_anonymous is True
    assert client._auth_headers == {}


def test_auth_headers_are_immutable():
    client = HttpClient("http://host", token="abc")

    with pytest.raises(TypeError):
        client._auth_headers["Authorization"] = "Bearer other"


def test_with_base_url_keeps_identity_and_does_not_mutate():
    client = HttpClient("http://host", token="abc", timeout=5)
    derived = client.with_base_url("http://other")

    assert client.base_url == "http://host"
    assert derived.base_url == "http://other"
    assert derived.token == "abc"
    assert derived.timeout == 5


# ---------- 真实请求 ----------

def test_get_query_string_reaches_server(echo_server):
    client = HttpClient(echo_server)

    resp = client.get("/search", params={"wd": "天气", "page": 2})

    assert resp.status_code == 200
    assert resp.json["path"].startswith("/search?")
    assert "wd=%E5%A4%A9%E6%B0%94" in resp.json["path"]
    assert "page=2" in resp.json["path"]


def test_post_json_body_reaches_server(echo_server):
    client = HttpClient(echo_server)

    resp = client.post("/items", json_body={"name": "alice"})

    assert resp.status_code == 200
    assert '"name": "alice"' in resp.json["body"]
    assert resp.json["content_type"] == "application/json"


def test_explicit_content_type_wins(echo_server):
    client = HttpClient(echo_server)

    resp = client.post(
        "/items",
        json_body={"a": 1},
        headers={"Content-Type": "application/xml"},
    )

    assert resp.json["content_type"] == "application/xml"


def test_authorization_header_is_sent(echo_server):
    client = HttpClient(echo_server, token="abc")

    resp = client.get("/whoami")

    assert resp.json["authorization"] == "Bearer abc"


def test_exchange_snapshot_masks_credentials(echo_server):
    client = HttpClient(echo_server, token="super-secret")

    resp = client.get("/echo")

    assert resp.exchange.request_headers["Authorization"] == "***"
    assert resp.exchange.method == "GET"
    assert "/echo" in resp.exchange.url


def test_timeout_is_passed_through():
    client = HttpClient("http://host", timeout=7)

    assert client.timeout == 7


# ---------- 部署探测 ----------

def test_probe_none_means_reachability(echo_server):
    deployed, reason = probe_deployment(HttpClient(echo_server), None)

    assert deployed is True
    assert reason.startswith("OK")


def test_probe_endpoint_ok(echo_server):
    deployed, reason = probe_deployment(HttpClient(echo_server), "/envelope")

    assert deployed is True
    assert reason == "OK"


def test_probe_endpoint_detects_nginx_fallback(echo_server):
    deployed, reason = probe_deployment(HttpClient(echo_server), "/nginx-404")

    assert deployed is False
    assert reason.startswith("NOT_DEPLOYED")
    assert "未部署" in reason


def test_probe_endpoint_reports_unreachable(dead_url):
    deployed, reason = probe_deployment(HttpClient(dead_url, timeout=1), "/api/ping")

    assert deployed is False
    assert reason.startswith("UNREACHABLE")


def test_probe_callable_is_used_as_is():
    calls = []

    def custom(client):
        calls.append(client)
        return True, "CUSTOM"

    client = HttpClient("http://host")

    assert probe_deployment(client, custom) == (True, "CUSTOM")
    assert calls == [client]
