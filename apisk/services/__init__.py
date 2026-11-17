#! python3
# -*- encoding: utf-8 -*-

"""业务层：按领域声明装配服务。

分层约定
--------
* **core/**      HTTP 客户端（HttpClient）、现场留痕
* **api/**       端点映射基类（只发请求、收 Response）
* **services/**  业务容器（Services，按领域声明装配）
* **domain**     领域协议（业务侧声明端点类、服务与门禁）
* **tests/**     用例（pytest + feature/story/title）

所有 ServiceSpec 都是无参构造——服务自己负责 new HttpClient，
Services 容器只做声明合并和属性挂载。
"""

from apisk.services.container import Services

__all__ = [
    "Services",
]
