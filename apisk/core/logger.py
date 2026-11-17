#! python3
# -*- encoding: utf-8 -*-

"""统一日志入口。

与 pytest 的 ``log_cli`` 配置配合使用，避免各模块各自 ``print``。

框架日志统一挂在 ``apisk`` 前缀下，因此可以整体过滤::

    pytest -o log_cli=true --log-cli-level=INFO   # 输出全部框架日志
    pytest --log-filter=apisk.http                # 只看 HTTP 请求流水

用法::

    from apisk.core.logger import get_logger

    logger = get_logger(__name__)   # -> apisk.core.http_client（原样保留）
    logger = get_logger("http")     # -> apisk.http（短名自动补前缀）
"""

import logging

#: 框架日志统一前缀。改动它会改变所有日志的 logger 名。
_LOGGER_NAME = "apisk"

__all__ = ["get_logger", "log_precondition", "log_request"]


def get_logger(name: str = None) -> logging.Logger:
    """返回带统一前缀的 logger。

    ``name`` 支持两种写法，都不会出现重复前缀：

    * 短名 —— ``"http"`` → ``apisk.http``（框架内部按用途分组时用）
    * 模块名 —— ``__name__``，如 ``apisk.core.http_client``，原样返回

    """
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    if name == _LOGGER_NAME or name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def log_request(method: str, url: str, status, code=None):
    """记录一次请求的结果（供 HttpClient 调用）。"""
    get_logger("http").info("%s %s -> %s code=%s", method, url, status, code)


def log_precondition(action: str, detail: str = ""):
    """记录前置编排动作。"""
    get_logger("precondition").info("%s %s", action, detail)
