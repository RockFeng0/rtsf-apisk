#! python3
# -*- encoding: utf-8 -*-

"""feature / story / title 标记：构造正确、插件已注册。"""

from apisk.support.markers import feature, story, title


def test_feature_mark_carries_name():
    mark = feature("用户管理")

    assert mark.name == "feature"
    assert mark.args == ("用户管理",)


def test_story_and_title_marks():
    assert story("账号注册").name == "story"
    assert story("账号注册").args == ("账号注册",)
    assert title("TC-001 用户名重复注册被拒绝").name == "title"


def test_plugin_registers_all_three_markers(pytestconfig):
    declared = list(pytestconfig.getini("markers"))

    for name in ("feature", "story", "title"):
        assert any(item.startswith(name) for item in declared), (
            f"marker {name!r} 未被 apisk 插件注册；已注册: {declared}"
        )
