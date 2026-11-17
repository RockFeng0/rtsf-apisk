#! python3
# -*- encoding: utf-8 -*-

"""apisk —— 通用接口自动化测试框架。

**框架不含任何业务、不含任何身份概念、零 env var**：端点类、业务服务、
服务门禁探测与契约常量全部由**领域包**声明。每个 Service 在自己的
``__init__`` 里 new ``HttpClient``，框架只负责装配与探测。

三层结构
--------
===============  ==================================================
**框架 apisk**   通用原语：HTTP 客户端 / 夹具 / 标记 / 结果收集 / 报告
**领域包**       业务实现，如 ``mydomain``（端点、服务、常量、领域夹具）
**套件工程**     用例，如 ``test_mydomain``（脚手架生成）
===============  ==================================================

框架各层
--------
==========================  ==========================================
``apisk.core``              运行时内核：HTTP 客户端 / 响应包络 / 异常 / 日志 / 部署探测
``apisk.api``               端点基类与请求头工具（无具体端点）
``apisk.services``          服务容器（Services，按领域声明装配）
``apisk.domain``            **领域扩展协议**（Domain / ServiceSpec / load_domains）
``apisk.support``           业务侧用例支撑（标记 / 语料降级 / 报告夹具 / 红线断言）
``apisk.pytest_plugin``     pytest 插件：夹具、标记与领域加载
``apisk.scaffold``          脚手架：一条命令生成测试骨架
==========================  ==========================================

最小接入（套件工程根 conftest.py）::

    pytest_plugins = ["apisk.pytest_plugin"]

再声明业务领域（三选一）::

    # pytest.ini
    apisk_domains = mydomain

    # 命令行
    pytest --apisk-domain mydomain

    # 环境变量
    AUTO_TEST_DOMAINS=mydomain pytest

领域包被 pip 安装后，还可通过入口点 ``apisk.domains`` 自动发现。
"""

from importlib import import_module

__version__ = "3.0.0"

#: 公开 API —— 惰性导入，保证 ``import apisk`` 不引入任何重依赖
_LAZY_API = {
    # 扩展协议
    "Domain": ("apisk.domain", "Domain"),
    "ServiceSpec": ("apisk.domain", "ServiceSpec"),
    "register_domain": ("apisk.domain", "register_domain"),
    "load_domains": ("apisk.domain", "load_domains"),
    "loaded_domains": ("apisk.domain", "loaded_domains"),
    # 分层基类
    "BaseApi": ("apisk.api", "BaseApi"),
    "Services": ("apisk.services", "Services"),
    # 日志
    "get_logger": ("apisk.core.logger", "get_logger"),
}

__all__ = ["__version__", *sorted(_LAZY_API)]


def __getattr__(name):
    try:
        module_name, attr = _LAZY_API[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None
    return getattr(import_module(module_name), attr)


def __dir__():
    return sorted(set(globals()) | set(_LAZY_API))
