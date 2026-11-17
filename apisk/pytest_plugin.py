#! python3
# -*- encoding: utf-8 -*-

"""apisk pytest 插件 —— 框架对外提供的全部夹具、标记与运行期配置。

套件只需在自己工程根的 ``conftest.py`` 里声明一行，即可获得全部公共能力::

    pytest_plugins = ["apisk.pytest_plugin"]

业务内容（端点、服务、身份、门禁探测、前置编排）**全部来自领域包**，框架不硬编码
任何业务。声明领域有五种方式（可并用）：

1. 命令行 ``--apisk-domain mydomain``（可重复，也支持逗号分隔）
2. ``pytest.ini`` 的 ``apisk_domains = mydomain``
3. 环境变量 ``AUTO_TEST_DOMAINS=mydomain``
4. 套件根 ``conftest.py`` 的模块级常量 ``APIAT_DOMAINS = ["mydomain"]``
   —— 不想动 ini 时用这种纯 Python 声明
5. 入口点 ``apisk.domains`` —— 领域包被 pip 安装后**自动发现**

夹具按用途分五组：

* **身份**：``auth_service`` / ``admin_ctx`` / ``admin_svc`` / ``user_ctx`` /
  ``svc`` / ``metric_ctx`` / ``metric_svc``
* **门禁**：``service_status`` / ``require_service``
* **编排**：``report_path``
* **报告**：``report_data`` —— 用例自报指标，供 HTML 报告渲染成列
* **领域**：由领域自带插件提供（``Domain.plugin`` 声明的模块，如
  ``mydomain.pytest_plugin``）

两条设计约定
------------
1. **Service 自己构造 HttpClient，框架不持有凭据、不注入身份。**
   端点方法传完整 URL，由 ``HttpClient.url()`` 直通。
2. **对被测仓库（``app.utils``）与重依赖（``numpy`` / ``soundfile``）的导入
   一律延迟到夹具函数体内。** 插件注册这一步不引入重依赖，纯本地套件也能在
   最小环境下完成收集。

配置期出错（领域包名写错等）一律转成 ``pytest.exit`` 并给出可操作的提示，
而不是让 pytest 抛出 INTERNALERROR。
"""

import json
import os
import random
import re
from importlib import import_module
from pathlib import Path

import pytest

from apisk.core.exceptions import DomainError
from apisk.core.exchange import recording
from apisk.core.logger import get_logger
from apisk.core.http_client import HttpClient, probe_deployment
from apisk.domain import (
    Domain,
    ServiceSpec,
    domain_config,
    domain_plugins,
    load_domains,
    loaded_domains,
    probe_spec,
)
from apisk.services import Services
from apisk.support.reporting import fix_report_html, resolve_report_dir

logger = get_logger(__name__)


# ---------- 扩展 pytest选项 ----------

def pytest_addoption(parser):
    """注册领域声明与调试选项（命令行 + pytest.ini）。"""
    group = parser.getgroup("apisk", "apisk 框架")
    group.addoption(
        "--apisk-domain",
        action="append",
        default=[],
        dest="apisk_domains",
        metavar="MODULE",
        help="加载的业务领域包（可重复，也支持逗号分隔），如 mydomain",
    )
    group.addoption(
        "--apisk-dump-http",
        action="store_true",
        default=False,
        dest="apisk_dump_http",
        help="失败用例的 HTTP 请求/响应现场写入 <报告目录>/http/<用例>.json",
    )
    parser.addini(
        "apisk_domains",
        "业务领域包列表（每行一个，也支持逗号分隔）；入口点 apisk.domains 会自动发现",
        type="linelist",
    )


def _resolve_domain_names(config):
    """汇总各来源的领域声明（命令行 / ini / conftest 常量）。"""
    names = list(config.getoption("apisk_domains") or [])
    names += list(config.getini("apisk_domains") or [])
    names += _conftest_domain_names(config)
    return names


def _conftest_domain_names(config):
    """读取套件根 ``conftest.py`` 里的 ``APIAT_DOMAINS`` 常量（纯 Python 声明）。

    与 ``pytest_plugins`` 一样是模块级名字，适合不想动 ini 的套件::

        # conftest.py（套件工程根）
        APIAT_DOMAINS = ["mydomain", "otherdomain"]
    """
    root_conftest = Path(str(getattr(config, "rootpath", "") or "")) / "conftest.py"
    wanted = os.path.normcase(str(root_conftest))
    for plugin in config.pluginmanager.get_plugins():
        path = getattr(plugin, "__file__", None)
        if not path or os.path.normcase(str(path)) != wanted:
            continue
        declared = getattr(plugin, "APIAT_DOMAINS", None) or ()
        return [declared] if isinstance(declared, str) else list(declared)
    return []


def _register_domain_plugins(config):
    """把领域自带的 pytest 插件注册进当前会话。"""
    for module_name in domain_plugins():
        plugin_name = f"apisk_domain__{module_name}"
        if config.pluginmanager.hasplugin(plugin_name):
            continue
        module = import_module(module_name)
        config.pluginmanager.register(module, name=plugin_name)


def pytest_configure(config):
    """加载领域、注册标记、固定随机种子，打印一次运行上下文。"""
    for line in (
        "feature(name): 业务特性（模块级）",
        "story(name): 用户故事 / 子能力（模块级）",
        "title(text): 单条用例标题",
    ):
        config.addinivalue_line("markers", line)

    try:
        domains = load_domains(
            *_resolve_domain_names(config), entry_points=True, freeze=True
        )
        _register_domain_plugins(config)
    except (DomainError, ImportError) as exc:
        # 配置阶段直接抛异常只会得到一行 INTERNALERROR 栈，对使用者毫无指导意义
        pytest.exit(_domain_error_hint(config, exc), returncode=4)

    random.seed(0)  # 框架仅在未配置任何种子时保证可预测；业务可自行覆盖
    names = ", ".join(d.name for d in domains) or "（无，纯框架模式）"
    print(f"\n[apisk] domains={names}\n")


def _domain_error_hint(config, exc) -> str:
    """把领域加载失败拼成「试过什么、该改哪里」的提示正文。"""
    declared = _resolve_domain_names(config)
    lines = [
        f"领域加载失败: {exc}",
        "",
        "领域声明来源（可并用，本次已尝试）：",
        "  --apisk-domain MODULE   命令行",
        "  apisk_domains = MODULE  pytest.ini",
        "  AUTO_TEST_DOMAINS      环境变量",
        "  APIAT_DOMAINS           套件根 conftest.py 的模块级常量",
        "  apisk.domains           入口点（pip 安装的领域包自动发现）",
    ]
    if declared:
        lines.append(f"  本次声明: {', '.join(str(item) for item in declared)}")
    lines += [
        "",
        "请确认写的是**可导入的模块路径**（点号分隔），例如：",
        "  apisk_domains = domain.mydomain_domain",
        "且该模块所在目录在 sys.path 上（套件 pytest.ini 可加 pythonpath = .）。",
    ]
    return "\n".join(lines)


# ---------- hookwrapper 勾子函数----------

@pytest.hookimpl(tryfirst=True)
def pytest_html_report_title(report):
    """报告缺省标题（未安装 pytest-html 时该钩子不会被调用）。

    套件用 ``apisk.support.reporting.apisk_report(title=...)`` 指定标题时，
    由套件自己的同名钩子覆盖本缺省值。
    """
    report.title = f"接口自动化测试报告"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """把 ``@title`` 文案与「本用例是否失败」挂到报告/用例上。

    ``TestReport.keywords`` 里只有标记名（值为 1），取不到标题文本，因此在这里
    从 item 上取值后随报告带给 pytest-html 的表格钩子；同时记下失败标记，供
    ``--apisk-dump-http`` 决定是否落盘现场。
    """
    outcome = yield
    report = outcome.get_result()
    mark = item.get_closest_marker("title")
    if mark is not None and mark.args:
        report.apisk_title = str(mark.args[0])
    if report.failed:
        setattr(item, "_apisk_failed", True)

# 修补 HTML unescape
@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session, exitstatus):
    """报告落盘后修掉 pytest-html 在 ``file://`` 下必崩的那行。

    修的是 ``history.pushState({}, null, unescape(url.href))`` —— 路径含中文时
    ``unescape`` 会把百分号编码解成乱码，推入的 URL 与文档不同源，Chrome 抛
    ``SecurityError``，报告的排序/筛选随之失效。细节见
    ``apisk.support.reporting.fix_report_html``。

    必须用 hookwrapper：pytest-html 自己的 ``pytest_sessionfinish`` 声明了
    ``trylast``，同为 trylast 时先后取决于插件注册顺序，靠不住；包一层
    wrapper，``yield`` 之后的代码必然排在**所有** sessionfinish 之后。
    """
    yield
    htmlpath = getattr(session.config.option, "htmlpath", None)
    if not htmlpath:
        return
    fixed = fix_report_html(htmlpath)
    if fixed:
        logger.info("已修补 HTML 报告 %d 处（file:// 中文路径兼容）: %s", fixed, htmlpath)


#  HTTP 现场留痕（--apisk-dump-http）
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """整个用例（含夹具建/拆）期间收集 HTTP 现场，失败时落盘。

    收集范围必须覆盖**夹具阶段**——真实套件的公共请求多半发生在 session 级
    夹具里，只包住用例函数体会一笔都记不到。

    默认关闭（不缓存任何请求，零开销）；加 ``--apisk-dump-http`` 后，失败用例
    的请求/响应现场写到 ``<报告目录>/http/<用例>.json``。
    """
    if not item.config.getoption("apisk_dump_http", False):
        yield
        return

    with recording() as exchanges:
        yield
        _dump_exchanges(item, exchanges)


def _dump_exchanges(item, exchanges):
    """把失败用例收集到的交换写入 JSON；用例通过或没有请求时不写。"""
    if not exchanges or not getattr(item, "_apisk_failed", False):
        return
    directory = resolve_report_dir(item.config) / "http"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_name(item.nodeid)}.json"
    payload = {
        "nodeid": item.nodeid,
        "exchanges": [exchange.to_dict() for exchange in exchanges],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("已记录 HTTP 现场: %s", path)


def _safe_name(nodeid) -> str:
    """把 nodeid 变成合法文件名（非字母数字一律折成下划线）。"""
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(nodeid)).strip("_") or "case"


# ---------- fixture 夹具 ----------

# 服务容器
@pytest.fixture(scope="session")
def metric_svc(require_service) -> Services:
    """session 级服务集合 —— 一次装配，整个 session 复用。

    所有领域的 ServiceSpec 无参 build()，各自在 __init__ 里
    自己 new HttpClient，容器只负责声明合并和属性挂载。
    """
    return Services()


# 服务门禁
def _probe_client() -> HttpClient:
    """从第一个已加载领域的第一个 Service 里拿 HttpClient 做可达性探测。"""
    for domain in loaded_domains():
        for spec in domain.services:
            svc = spec.build()
            api = getattr(svc, "api", None)
            if api is not None:
                return api._http  # BaseApi 把 HttpClient 存在 _http
    return HttpClient(base_url="")  # 兜底空 client（probe_deployment 会处理）


@pytest.fixture(scope="session")
def service_status():
    """探测被测服务是否可用（session 级缓存，全流程只探一次）。

    探测策略由领域声明（``Domain.probe``）。
    无领域声明时用第一个领域的 Service 里的 HttpClient 做通用可达性探测。
    """
    client = _probe_client()
    deployed, reason = probe_deployment(client, probe_spec())
    if deployed:
        logger.info("被测服务可用: %s (%s)", client.base_url, reason)
    else:
        logger.warning("被测服务不可用 (%s): %s", client.base_url, reason)
    return deployed, reason


@pytest.fixture(scope="session")
def require_service(service_status):
    """声明「本用例需要被测服务」：不可用时 skip 而非 fail。

    直接把它列进夹具签名即可获得门禁，无需按目录配置白名单——
    纯本地套件（不请求 ``svc`` / ``metric_svc``）自然不受影响::

        def test_xxx(svc, require_service): ...

    注：``svc`` / ``metric_svc`` / ``admin_ctx`` 等身份夹具已内置该门禁，
    多数场景无需显式声明。
    """
    deployed, reason = service_status
    if not deployed:
        pytest.skip(
            f"被测服务当前不可用（{reason}）；"
            f"请确认服务已部署，或检查领域的 probe 端点 / Service 的 base_url 是否正确"
        )
    return True


# 编排与数据
@pytest.fixture(scope="session")
def report_path(request):
    """报告输出目录。

    依次取 ``AUTO_TEST_REPORT_DIR``、``<pytest rootdir>/reports``（套件工程根
    下的 reports/），与 ``apisk.support.reporting`` 的 HTML 落点保持一致。
    """
    path = resolve_report_dir(request.config)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@pytest.fixture
def report_data(request):
    """把用例关心的指标记进报告表格。

    用法::

        def test_login(svc, report_data):
            resp = svc.user.login()
            report_data("status_code", resp.status_code)
            report_data("elapsed_ms", round(resp.exchange.elapsed_ms, 1))

    记录的键需与 ``apisk_report(metrics=...)`` 声明的一致，才会渲染成报告列。
    """
    def _record(key, value):
        request.node.user_properties.append((str(key), value))

    return _record

# 领域自省（便于排查「领域到底加载上没有」）
@pytest.fixture(scope="session")
def apisk_domains():
    """当前已加载的领域声明（只读）。"""
    return loaded_domains()


@pytest.fixture(scope="session")
def apisk_domain_config():
    """第一个携带配置对象的领域的配置；无领域时为 ``None``。"""
    return domain_config()
