#! python3
# -*- encoding: utf-8 -*-

"""HTTP 客户端。

核心约束（架构红线）
--------------------
1. **构造时写死**：凭据在 ``HttpClient`` 构造时一次性写入，实例内不提供
   任何修改凭据的入口。需要不同凭据时新建一个 ``HttpClient`` 实例。
2. **鉴权头冻结**：鉴权头在 ``__init__`` 中计算并冻结为只读映射，运行期
   不可变。这从根上杜绝了「上一个用例把 token 改掉，污染下一个用例」。
3. **无全局可变状态**：不持有模块级可变对象，不使用全局 Session；并发用例
   各自持有一份请求头，互不干扰。

本层只负责「发请求 → 收原始响应」，不做任何业务判断与字段裁剪。
每次请求都会留下一份现场快照（``HttpExchange``，凭据已脱敏），挂在返回的
``ApiResponse.exchange`` 上，并由 ``record_exchange()`` 交给当前用例的收集器
（未开启 ``--apisk-dump-http`` 时为空操作）——失败时断言辅助据此打印现场。
"""

import time
import types
from typing import Optional

import requests

from apisk.core.exceptions import ConfigError
from apisk.core.exchange import (
    HttpExchange,
    mask_body,
    mask_headers,
    record_exchange,
    snippet,
)
from apisk.core import logger
from apisk.core.response import ApiResponse

DEFAULT_TIMEOUT = 120


class HttpClient:
    """绑定单一身份的 HTTP 客户端（不可变凭据）。"""

    __slots__ = (
        "_base_url",
        "_token",
        "_timeout",
        "_auth_headers",
        "_default_headers",
    )

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        default_headers: Optional[dict] = None,
    ):
        """
        Args:
            base_url: 接口根地址。可选——端点方法传 ``http(s)://`` 开头的
                完整 URL 时不会用到此值。留空则所有端点方法必须传完整 URL。
            token: 该身份的凭据。None 表示**匿名**（不带 Authorization 头），
                用于验证未授权路径；空串等非法值可用于验证无效凭据路径。
            timeout: 默认超时（秒）。
            default_headers: 追加的固定请求头。
        """
        self._base_url = str(base_url or "").rstrip("/")
        self._token = token
        self._timeout = int(timeout)

        # 凭据在此一次性写入并冻结：运行期无法再改
        auth = {}
        if token is not None:
            auth["Authorization"] = f"Bearer {token}"
        self._auth_headers = types.MappingProxyType(auth)

        headers = {"Accept": "application/json"}
        if default_headers:
            headers.update(default_headers)
        self._default_headers = types.MappingProxyType(headers)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> Optional[str]:
        """只读凭据。需要不同凭据时新建一个 ``HttpClient`` 实例。"""
        return self._token

    @property
    def timeout(self) -> int:
        return self._timeout

    @property
    def is_anonymous(self) -> bool:
        return self._token is None

    # ---------- 派生 ----------

    def url(self, path: str) -> str:
        """拼出绝对 URL；path 已是绝对地址时原样返回。"""
        if path.startswith(("http://", "https://")):
            return path
        root = self._base_url
        if not path.startswith("/"):
            path = "/" + path
        return f"{root}{path}"

    def with_base_url(self, base_url: str) -> "HttpClient":
        """派生一个指向其他环境的同身份客户端（不修改自身）。"""
        return HttpClient(
            base_url=base_url,
            token=self._token,
            timeout=self._timeout,
            default_headers=dict(self._default_headers),
        )

    # ---------- 请求 ----------

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        data=None,
        files=None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[int] = None,
        model: bool = False,
    ) -> ApiResponse:
        """发起请求并返回原始响应包装。

        Args:
            params: URL 查询参数（GET / DELETE 的主用通道）。值为 ``None`` 的键
                由调用方负责剔除——本层不做过滤，保证「发出去的请求 = 调用方
                构造的请求」，请求构造错误应在用例里被看见。

        不做重试、不抛断言——错误响应同样作为结果返回，交由用例按契约断言。
        """
        merged = dict(self._default_headers)
        merged.update(self._auth_headers)
        if headers:
            merged.update(headers)
        # 有 JSON 正文且调用方未显式指定 Content-Type 时补默认值
        # （用例可覆盖为非法值，以验证请求头校验）
        if json_body is not None and "Content-Type" not in merged:
            merged["Content-Type"] = "application/json"

        url = self.url(path)
        body = json_body if json_body is not None else data
        started = time.perf_counter()
        response = requests.request(
            method,
            url,
            json=json_body,
            data=data,
            files=files,
            params=params,
            headers=merged,
            timeout=timeout or self._timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        result = ApiResponse(response)
        # 现场交易快照（请求头脱敏）：失败时断言辅助据此打印「到底发了什么」
        result.exchange = HttpExchange(
            method=method.upper(),
            url=response.url,
            status_code=result.status_code,
            elapsed_ms=elapsed_ms,
            request_headers=mask_headers(merged),
            request_body=mask_body(body),
            response_headers=mask_headers(response.headers),
            response_snippet=snippet(result.text),
        )
        record_exchange(result.exchange)
        # 记 ``response.url``：查询串拼上后才是真实请求地址，排查 GET 用例必需
        logger.log_request(method, response.url, result.status_code, result.code)
        return result

    def get(self, path: str, **kwargs) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def __repr__(self):
        identity = "anonymous" if self.is_anonymous else f"token=…{str(self._token)[-4:]}"
        return f"<HttpClient {self._base_url} {identity}>"


# ============ 部署探测 ============

def probe_deployment(client: HttpClient, probe=None):
    """探测目标地址是否真正部署了目标业务接口。

    框架不知道业务端点的存在，因此探测策略由领域声明（``Domain.probe``）：

    * **callable**：``callable(client) -> (deployed, reason)``，领域自定义策略；
    * **str**：端点路径。部分环境只部署了模型能力接口，业务路径由 nginx 兜底并
      返回自身 404（``{"error": {"code": "UnknownVersion"}}``）。这属于「未部署」，
      而非「契约不满足」，用例应据此跳过；
    * **None**：退化为「地址可达即视为已部署」——只区分连不上（UNREACHABLE）
      与其他情况。

    Returns:
        (deployed: bool, reason: str)，reason 取 OK / NOT_DEPLOYED:* / UNREACHABLE:*
    """
    if callable(probe):
        return probe(client)

    if probe is None:
        return _probe_reachability(client)

    return _probe_endpoint(client, probe)


def _probe_reachability(client: HttpClient):
    """通用可达性探测：能拿到任何 HTTP 响应即视为可达。"""
    try:
        resp = client.request("GET", "/", timeout=8)
    except requests.RequestException as exc:
        return False, f"UNREACHABLE: {exc}"
    return True, f"OK (reachable, HTTP {resp.status_code})"


def _probe_endpoint(client: HttpClient, probe_path: str):
    """按业务端点探测部署情况。"""
    try:
        resp = client.request("POST", probe_path, json_body={}, timeout=8)
    except requests.RequestException as exc:
        return False, f"UNREACHABLE: {exc}"

    payload = resp.json if isinstance(resp.json, dict) else {}

    error = payload.get("error")
    if isinstance(error, dict) and error.get("code") == "UnknownVersion":
        return False, f"NOT_DEPLOYED: nginx 未匹配到 {probe_path}（服务未部署）"

    # 平台自身的统一响应包络（含鉴权失败）说明服务已部署
    if "error" not in payload and ("request_id" in payload or "code" in payload):
        return True, "OK"

    # 2xx 且无错误包络：端点存在但没有统一包络（如自定义健康检查）
    if 200 <= resp.status_code < 300:
        return True, "OK"

    # 跳因要能整行读完：把响应片段压成单行再截断
    snippet = " ".join((resp.text or "").split())[:120]
    return False, f"NOT_DEPLOYED: HTTP {resp.status_code} {snippet}"
