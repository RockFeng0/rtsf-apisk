#! python3
# -*- encoding: utf-8 -*-


class ConfigError(Exception):
    """配置缺失或非法。"""


class DomainError(ConfigError):
    """业务领域声明或加载错误（领域包缺失、重复注册、冻结后注册等）。"""
