#! python3
# -*- encoding: utf-8 -*-


# 统一响应包络的四个标准字段（平台规范）
_ENVELOPE_FIELDS = ("request_id", "code", "message", "timestamp")


class ApiResponse:
    """HTTP 响应包装"""

    __slots__ = ("_response", "status_code", "headers", "text", "json", "exchange")

    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.text = response.text
        try:
            self.json = response.json()
        except ValueError:
            self.json = None
        self.exchange = None

    @property
    def payload(self) -> dict:
        """完整响应体；非 JSON 时返回空 dict。"""
        return self.json if isinstance(self.json, dict) else {}

    @property
    def code(self):
        return self.payload.get("code")

    @property
    def message(self):
        return self.payload.get("message")

    @property
    def data(self) -> dict:
        value = self.payload.get("data")
        return value if isinstance(value, dict) else {}

    @property
    def request_id(self):
        return self.payload.get("request_id")

    @property
    def retryable(self):
        return self.payload.get("retryable")

    # ---------- 判定 ----------

    @property
    def ok(self) -> bool:
        """业务成功：HTTP 200 且 code == OK。"""
        return self.status_code == 200 and self.code == "OK"

    @property
    def is_error(self) -> bool:
        return self.code is not None and self.code != "OK"

    def has_envelope(self) -> bool:
        """响应体是否具备完整统一包络。"""
        return all(field in self.payload for field in _ENVELOPE_FIELDS)

    def __repr__(self):
        return f"<ApiResponse {self.status_code} code={self.code!r}>"
