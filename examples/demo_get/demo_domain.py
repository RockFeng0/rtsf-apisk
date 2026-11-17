#! python3
# -*- encoding: utf-8 -*-

"""示例领域包 —— 用公开的百度搜索演示 GET 接口测试。

领域包是框架与业务的唯一接缝：端点、服务、探活、配置都在这里声明，
框架本身不含任何业务。
"""

from dataclasses import dataclass

from apisk.api import BaseApi
from apisk.core import HttpClient
from apisk.domain import Domain, ServiceSpec


@dataclass(frozen=True)
class DemoConfig:
    """业务常量由领域自己持有，不写进框架。"""

    BASE_URL = "https://www.baidu.com"
    SEARCH_URL = "https://www.baidu.com/s"
    TIMEOUT = 10


config = DemoConfig()


class DemoApi(BaseApi):
    """端点映射层：一个方法一个 URL。"""

    def search(self, keyword: str):
        return self._get(config.SEARCH_URL, params={"wd": keyword})


class DemoService:
    """服务层：自建 HttpClient，无参构造。"""

    def __init__(self):
        self.api = DemoApi(HttpClient(
            base_url=config.BASE_URL,
            timeout=config.TIMEOUT,
        ))

    def search(self, keyword: str):
        return self.api.search(keyword)


DOMAIN = Domain(
    name="demo_get",
    apis={"demo": DemoApi},
    services=[ServiceSpec("demo", DemoService)],
    probe=None,          # 缺省语义：目标地址可达即视为已部署
    config=config,
)

__all__ = ["DOMAIN", "DemoApi", "DemoConfig", "DemoService", "config"]
