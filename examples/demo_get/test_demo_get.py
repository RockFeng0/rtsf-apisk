#! python3
# -*- encoding: utf-8 -*-

"""GET 接口示例：查询串拼装 + 真实请求。

``test_search_returns_html`` 需要联网；网络不可达时由 ``require_service``
门禁自动 skip，不会把环境问题记成用例失败。
"""

from apisk.core.http_client import HttpClient
from apisk.support.markers import feature, story, title

pytestmark = [feature("搜索"), story("关键词查询")]


@title("DEMO-01 查询串按调用方构造拼进 URL")
def test_query_string_is_built_locally():
    """纯本地断言，不依赖网络：验证「发出去的地址」符合预期。"""
    client = HttpClient("https://www.baidu.com")

    url = client.url("/s")

    assert url == "https://www.baidu.com/s"


@title("DEMO-02 搜索接口返回 200 与页面内容")
def test_search_returns_html(metric_svc, require_service):
    resp = metric_svc.demo.search("天气")

    assert resp.status_code == 200
    assert resp.text
    assert "baidu" in resp.text.lower()
