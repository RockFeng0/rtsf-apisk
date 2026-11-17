#! python3
# -*- encoding: utf-8 -*-

"""HTML 报告接入 —— 一行 ``apisk_report()``，不必自己写渲染代码。

报告**渲染**由 `pytest-html <https://pytest-html.readthedocs.io>`_ 负责，
本模块只做套件真正关心的四件事：

1. **落点固定**：把 ``--html`` 钉在 ``<rootdir>/reports/report.html``
   （``AUTO_TEST_REPORT_DIR`` 可改到别处），于是「换个目录执行报告就跑丢」
   不再发生；
2. **标题与列**：报告标题 + 中文列名，并把用例自报的指标
   （``report_data("status_code", 200)``）渲染成独立列；
3. **缺依赖可诊断**：没装 pytest-html 时给出告警与安装指引，而不是静默不生成。
4. **file:// 兼容修补**：``fix_report_html()`` 修掉 pytest-html 4.x 里
   ``unescape(url.href)`` 这个缺陷，使报告在**路径含中文**时也能双击打开
   （详见 ``fix_report_html`` 的说明）。

用法（**套件工程根** ``conftest.py``）::

    from apisk.support.reporting import apisk_report

    pytest_plugins = ["apisk.pytest_plugin"]

    apisk_report(
        title="百度demo测试报告",
        metrics=(("status_code", "状态码"), ("elapsed_ms", "响应时间(ms)")),
    )

实现说明
--------
pytest 只把**模块级函数 / 插件对象**当作钩子载体，而套件根 conftest 正是
一个模块。``apisk_report()`` 因此把需要的钩子函数注入**调用方模块的全局
命名空间**：conftest 的模块体执行完之后才被注册为插件，所以注入必然早于
注册，钩子一定能生效。套件侧只需一行，无需抄一遍 pytest-html 钩子。

本模块**不实现任何 HTML 渲染**，也不产生 JSON 报告；``fix_report_html()``
只对 pytest-html 生成的报告做一处定点修补。
"""

import html
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

#: 报告默认展示的指标列：(``report_data`` 的键, 列名)
DEFAULT_METRICS: Tuple[Tuple[str, str], ...] = (
    ("status_code", "状态码"),
    ("elapsed_ms", "响应时间(ms)"),
)

#: 报告文件相对报告目录的名字
REPORT_FILENAME = "report.html"


def _derive_report_filename(config) -> str:
    """根据 pytest 收集目标自动推导报告文件名。

    规则：
    - 命令行显式指定**单个文件** → 取 stem（如 ``test_asr.py`` → ``test_asr.html``）
    - 命令行显式指定**单个目录** → 取目录名（如 ``jk_model/`` → ``jk_model.html``）
    - 未指定或指定多个 → 退化为 ``report.html``（pytest.ini 的 testpaths 全量收集）
    """
    # config.args 是 pytest 解析后的位置参数列表（不含 flag）
    args = list(getattr(config, "args", []) or [])

    if len(args) == 1:
        from pathlib import Path
        p = Path(args[0])
        if p.is_file() or (p.suffix and p.suffix != ""):
            return f"{p.stem}.html"
        return f"{p.name}.html"

    return REPORT_FILENAME


def apisk_report(
    title: Optional[str] = None,
    metrics: Sequence[Tuple[str, str]] = DEFAULT_METRICS,
    report_dir=None,
    report_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """在套件工程根 conftest.py 里一行接入 HTML 报告。

    Args:
        title: 报告标题；``None`` 时沿用框架缺省标题（含 env 与随机种子）。
        metrics: 需要渲染成列的指标 ``((键, 列名), ...)``；键取自
            ``report_data`` 写进用例的 ``user_properties``。传空元组即只要
            中文列名、不要指标列。
        report_dir: 报告目录；``None`` 时依次取 ``AUTO_TEST_REPORT_DIR``、
            ``<rootdir>/reports``。
        report_filename: 报告文件名；``None`` 时按 pytest 收集目标自动推导
            （单文件 → 取文件名，单子目录 → 取目录名，多个 → 退化为
            ``report.html``）。显式传值就用固定名。

    Returns:
        注入的钩子字典（便于自测与排查）。
    """
    hooks = _build_hooks(
        title=title, metrics=tuple(metrics), report_dir=report_dir,
        report_filename=report_filename,
    )
    # 注入调用方（套件根 conftest）的模块命名空间，使其成为该模块的钩子
    _inject(sys._getframe(1).f_globals, hooks)
    return hooks


def _build_hooks(title, metrics, report_dir, report_filename=None) -> Dict[str, Any]:
    """构造报告钩子；未安装 pytest-html 时只留一条可诊断的告警钩子。"""
    has_html = _has_pytest_html()

    def pytest_configure(config):
        if not has_html:
            warnings.warn(
                "[apisk] 未安装 pytest-html，本次不会生成 HTML 报告；"
                "安装后即自动生效：pip install pytest-html",
                stacklevel=1,
            )
            return
        # 用户显式给了 --html 就尊重用户，否则钉在套件自己的 reports/ 下
        if getattr(config.option, "htmlpath", None) is None:
            filename = report_filename or _derive_report_filename(config)
            config.option.htmlpath = str(
                resolve_report_dir(config, report_dir) / filename
            )
        # 强制打开--self-contained-html
        config.option.self_contained_html = True

    hooks = {"pytest_configure": _as_hook(pytest_configure, tryfirst=True)}

    if has_html:
        hooks["pytest_html_report_title"] = _title_hook(title)
        hooks["pytest_html_results_table_header"] = _header_hook(metrics)
        hooks["pytest_html_results_table_row"] = _row_hook(metrics)
    return hooks


def resolve_report_dir(config=None, report_dir=None) -> Path:
    """解出报告目录：显式入参 → ``<rootdir>/reports``。"""
    if report_dir:
        return Path(str(report_dir))
    rootdir = getattr(config, "rootpath", None) or os.getcwd()
    return Path(str(rootdir)) / "reports"


# ============ file:// 兼容修补（pytest-html 4.x 的已知缺陷） ============

#: 有缺陷的那行：``unescape`` 会把 URL 里的百分号编码解坏
_BROKEN_PUSHSTATE = "window.history.pushState({}, null, unescape(url.href))"
#: 修好之后：直接用规范 URL，交给浏览器做同源判断
_FIXED_PUSHSTATE = "window.history.pushState({}, null, url.href)"


def fix_report_html(path) -> int:
    """修掉报告里的 ``unescape(url.href)``，返回替换处数（0 = 无需修）。

    背景（pytest-html 4.2.0，上游最新版仍未修）
    ------------------------------------------
    pytest-html 的 ``setSort / hideCategory / showCategory`` 都用
    ``history.pushState({}, null, unescape(url.href))`` 把排序 / 筛选状态写回
    地址栏。而 ``unescape()`` 会把 URL 中的百分号编码按 latin-1 再解一遍：

    * 路径含非 ASCII 字符时（``D:\\立脚本\\...`` → URL 里的
      ``%E7%AB%8B%E8%84%9A%E6%9C%AC``），解出来是一串乱码，重新解析后
      **变成了另一个文件路径**；
    * 于是推入的 URL 与文档 URL 不再同源，而 ``file://`` 文档的 origin 是
      ``null``，Chrome 直接抛 ``SecurityError``：::

          Uncaught SecurityError: Failed to execute 'pushState' on 'History':
          A history state object with URL 'file:///.../%C3%A7%C2%AB%C2%8B...'
          cannot be created in a document with origin 'null' and URL
          'file:///.../%E7%AB%8B%E8%84%9A%E6%9C%AC...'

    * 异常从 ``init()`` 里逃出（栈：``setSort → doInitSort → init``），报告的
      排序 / 筛选 / 展开等交互全部失效。

    纯 ASCII 路径下 ``unescape`` 是恒等变换，所以本地看不出来；**路径含中文
    或盘符被写成 ``%3A`` 时必现**。本函数把 3 处 ``unescape(url.href)`` 换成
    ``url.href``，语义不变（浏览器本就按规范 URL 比较同源）。

    Args:
        path: 报告 HTML 路径；不存在或已是修好的版本时返回 0。

    Returns:
        实际替换的处数。
    """
    file = Path(path)
    if not file.is_file():
        return 0
    text = file.read_text(encoding="utf-8")
    broken = text.count(_BROKEN_PUSHSTATE)
    if not broken:
        return 0
    file.write_text(text.replace(_BROKEN_PUSHSTATE, _FIXED_PUSHSTATE), encoding="utf-8")
    return broken


def _main(argv=None) -> int:
    """``python -m apisk.support.reporting <report.html> [...]``

    就地修补**已经生成**的报告（比如从别的机器上拷过来的），无需重跑用例。
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m apisk.support.reporting",
        description="修补 pytest-html 报告，使其在 file:// 下可用（路径含中文时必需）",
    )
    parser.add_argument("reports", nargs="+", help="一个或多个 report.html 路径")
    args = parser.parse_args(argv)

    failed = 0
    for item in args.reports:
        if not Path(item).is_file():
            print(f"找不到文件: {item}")
            failed += 1
            continue
        fixed = fix_report_html(item)
        print(f"{'已修补' if fixed else '无需修补（已是可用的报告）'} {item} — {fixed} 处")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - 手动修补入口
    raise SystemExit(_main())


# ============ 内部 ============

def _has_pytest_html() -> bool:
    """pytest-html 是否可用（未安装时不注册任何 html 钩子，避免未知钩子告警）。"""
    try:
        import pytest_html  # noqa: F401
    except ImportError:
        return False
    return True


def _as_hook(func, **options):
    """给钩子函数打上 pytest 的 hookimpl 标记（tryfirst / trylast）。"""
    import pytest

    return pytest.hookimpl(**options)(func)


def _inject(namespace: Dict[str, Any], hooks: Dict[str, Any]) -> None:
    """把钩子写入调用方模块的全局命名空间。"""
    namespace.update(hooks)


def _title_hook(title):
    """报告标题：仅当套件显式给了标题时覆盖框架缺省标题。"""
    def pytest_html_report_title(report):
        if title:
            report.title = title

    return pytest_html_report_title


def _header_hook(metrics):
    """表头中文化，并在「链接」列之前插入指标列。"""
    def pytest_html_results_table_header(cells):
        cells[0] = '<th class="sortable" data-column-type="result">执行状态</th>'
        cells[1] = '<th class="sortable" data-column-type="testId">测试用例</th>'
        cells[2] = '<th class="sortable" data-column-type="duration">用例耗时</th>'
        cells[3:3] = [f"<th>{label}</th>" for _, label in metrics]

    return pytest_html_results_table_header


def _row_hook(metrics):
    """每行填入 ``@title`` 文案与指标值（缺值留空，不写占位符）。"""
    def pytest_html_results_table_row(report, cells):
        cells[1] = f'<td class="col-testId">{html.escape(_case_title(report))}</td>'
        values = dict(getattr(report, "user_properties", None) or ())
        cells[3:3] = [
            f"<td>{html.escape(str(values[key]))}</td>" if key in values else "<td></td>"
            for key, _ in metrics
        ]

    return pytest_html_results_table_row


def _case_title(report) -> str:
    """取 ``@title`` 标记的用例标题（由框架插件挂到报告上），缺省退回 nodeid。"""
    return getattr(report, "apisk_title", None) or report.nodeid


__all__ = [
    "DEFAULT_METRICS",
    "REPORT_FILENAME",
    "apisk_report",
    "fix_report_html",
    "resolve_report_dir",
]