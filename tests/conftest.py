#! python3
# -*- encoding: utf-8 -*-

"""测试公共夹具。

两条原则：

* **绝不联网**：需要 HTTP 行为的用例一律打到本进程内的回显服务；
* **绝不共享全局状态**：``apisk.domain`` 的注册表是模块级变量，每个用例
  独享一份，避免「谁先注册谁赢」这种顺序依赖。
"""

import http.server
import json
import threading

import pytest

from apisk import domain as domain_module


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    """每个用例前重置领域注册表（冻结标记一并复位）。"""
    monkeypatch.setattr(domain_module, "_domains", [])
    monkeypatch.setattr(domain_module, "_imported", set())
    monkeypatch.setattr(domain_module, "_frozen", False)


@pytest.fixture(autouse=True)
def no_ambient_proxy(monkeypatch):
    """屏蔽宿主机代理：否则 127.0.0.1 的请求会绕到代理，探活结果失真。"""
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    """按路径返回不同响应，覆盖客户端与探活分支。"""

    protocol_version = "HTTP/1.1"

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _reply(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        body = self._read_body()
        if self.path.startswith("/nginx-404"):
            # 模拟 nginx 兜底：HTTP 200，但包络里是 UnknownVersion
            self._reply({"error": {"code": "UnknownVersion"}})
            return
        if self.path.startswith("/envelope"):
            self._reply({
                "request_id": "req-1",
                "code": "OK",
                "message": "success",
                "timestamp": 0,
                "data": {"echo": True},
            })
            return
        self._reply({
            "method": self.command,
            "path": self.path,
            "body": body.decode("utf-8", "replace"),
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
        })

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle

    def log_message(self, *args):  # 静音，避免污染测试输出
        pass


@pytest.fixture(scope="session")
def echo_server():
    """本机回显服务，返回请求路径/请求头/请求体。"""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def dead_url():
    """一个确定连不上的地址（端口 1 无人监听）。"""
    return "http://127.0.0.1:1"
