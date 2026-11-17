#! python3
# -*- encoding: utf-8 -*-


from apisk.core.http_client import HttpClient


class BaseApi:
    """所有接口类的基类。"""

    def __init__(self, http: HttpClient):
        self._http = http

    @property
    def http(self) -> HttpClient:
        return self._http

    # ---------- HTTP 动词（薄封装，返回原始响应） ----------
    # 只做转发，响应解析由 common.ApiResponse 完成。
    # path 可以是完整路径（/api/v1/xxx）或绝对 URL（http://...），
    # 由 HttpClient.url() 决定最终去向。

    def _get(self, path: str, **kwargs):
        return self._http.get(path, **kwargs)

    def _post(self, path: str, **kwargs):
        return self._http.post(path, **kwargs)

    def _put(self, path: str, **kwargs):
        return self._http.put(path, **kwargs)

    def _patch(self, path: str, **kwargs):
        return self._http.request("PATCH", path, **kwargs)

    def _delete(self, path: str, **kwargs):
        return self._http.delete(path, **kwargs)

    def _request(self, method: str, path: str, **kwargs):
        """需要其他动词时的逃生口（只转发，不做业务）。"""
        return self._http.request(method, path, **kwargs)

    def __repr__(self):
        return f"<{type(self).__name__} http={self._http!r}>"


# ============ 请求头构造 ============

def merge_headers(*header_dicts):
    """按顺序合并请求头，后者覆盖前者，忽略 None/空。"""
    merged = {}
    for item in header_dicts:
        if item:
            merged.update(item)
    return merged
