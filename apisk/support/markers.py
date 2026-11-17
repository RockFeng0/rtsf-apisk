#! python3
# -*- encoding: utf-8 -*-

"""feature / story / title 标记辅助。

用例的可读语义分三层：

* **feature** —— 业务特性（模块级），如「用户管理」；
* **story**   —— 用户故事 / 子能力（模块级），如「账号注册」；
* **title**   —— 单条用例标题（用例级），如「TC-001 用户名重复注册被拒绝」。

用法::

    from apisk.support.markers import feature, story, title

    pytestmark = [feature("用户管理"), story("账号注册")]

    @title("TC-001 用户名重复注册被拒绝")
    def test_duplicate_username_rejected(svc, ...):
        ...

三个标记由 apisk 插件在 ``pytest_configure`` 阶段自动注册，无需在套件
``pytest.ini`` 里重复声明；可用 ``-m "feature: 用户管理"`` 选择用例。
"""

import pytest


def feature(name):
    """标记业务特性（模块级）。"""
    return pytest.mark.feature(name)


def story(name):
    """标记用户故事 / 子能力（模块级）。"""
    return pytest.mark.story(name)


def title(text):
    """标记单条用例标题。"""
    return pytest.mark.title(text)
