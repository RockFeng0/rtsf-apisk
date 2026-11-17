#! python3
# -*- encoding: utf-8 -*-

"""套件脚手架 —— 一条命令生成**可直接运行**的 apisk 骨架（标准套件风格）。

生成的结构：顶层 ``pytest.ini`` 锁定唯一 rootdir，所有领域包统一放 ``domain/``，
业务子包各持 ``config.py`` / ``conftest.py``，共享夹具在顶层 ``conftest.py``。

用法::

    python -m apisk.scaffold \\
        --name mydomain --base-url http://127.0.0.1:8000 \\
        --out test_mydomain        # 缺省 ./test_<name>

生成::

    test_mydomain/
    ├── pytest.ini                 唯一 rootdir
    ├── config.py                  共享业务常量
    ├── conftest.py                顶层共享夹具
    ├── run.py                     python run.py [--domain NAME]
    ├── domain/
    │   ├── __init__.py
    │   └── mydomain_domain.py    Api / Service / DOMAIN
    └── mydomain/
        ├── __init__.py
        ├── config.py              模块专属配置
        ├── conftest.py            模块专属夹具
        └── test_mydomain.py       冒烟用例
"""

import argparse
import re
import sys
from pathlib import Path
from string import Template

#: 名称合法性：领域包名必须是可导入的模块名
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ============ 模板 ============

def _domain_body(name: str, Name: str, env: str, base_url: str, probe_path: str) -> str:
    return f'''from dataclasses import dataclass

from apisk.api import BaseApi
from apisk.core import HttpClient
from apisk.domain import Domain, ServiceSpec


@dataclass(frozen=True)
class {Name}Config:
    """业务常量（端点、阈值等），由领域自己持有，不写进框架。"""

    BASE_URL = "{base_url}"
    PROBE = "{probe_path}"                 # 完整 URL 或端点路径均可
    TIMEOUT = 15
    EXPECTED_STATUS = 200


config = {Name}Config()


class {Name}Api(BaseApi):
    """端点映射层：一个方法一个 URL。

    端点方法传完整 URL 或端点路径均可：HttpClient.url() 会自动判断并直通完整 URL。
    """

    def ping(self, **kwargs):
        return self._get(config.PROBE, **kwargs)


class {Name}Service:
    """业务服务层：自有 HttpClient，无参构造。"""

    def __init__(self):
        self.api = {Name}Api(HttpClient(
            base_url=config.BASE_URL,
            timeout=config.TIMEOUT,
        ))

    def ping(self):
        return self.api.ping()


DOMAIN = Domain(
    name="{name}",
    apis={{"ping": {Name}Api}},
    services=[ServiceSpec("{name}", {Name}Service)],
    probe=config.PROBE,
    config=config,
)

__all__ = [
    "DOMAIN",
    "{Name}Api",
    "{Name}Config",
    "{Name}Service",
    "config",
]
'''


PYTEST_INI_TEMPLATE = '''[pytest]
; 唯一 rootdir（本目录）；所有子包无 pytest.ini，
; 从而顶层 conftest.py 自动下传到 domain/ 与业务子包。
testpaths = domain ${name}
pythonpath = . ..

apisk_domains =
    domain.${name}_domain

python_files = test_*.py
python_classes = Test*
python_functions = test_*

addopts = -ra --strict-markers
norecursedirs = reports logs .pytest_cache __pycache__ *.egg-info
log_cli = false
log_cli_level = WARNING
'''

ROOT_CONFIG_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""顶层共享业务常量 —— 所有子包共用。"""

PROBE_PATH = "/api/v1/ping"
TEST_SEED = 100
BASE_URL = "${base_url}"


__all__ = ["PROBE_PATH", "TEST_SEED", "BASE_URL"]
'''

ROOT_CONFTEST_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""顶层共享 conftest —— 所有子包都能用的公共夹具。"""

# apisk 框架插件通过 pip install apisk 的 pytest11 entry_point 自动注册，
# 不需要在这里声明 pytest_plugins。

import pytest

from apisk.support.reporting import apisk_report

apisk_report(
    title="${name} 接口自动化测试报告",
    metrics=(
        ("status_code", "状态码"),
        ("elapsed_ms", "响应时间(ms)"),
    ),
)

@pytest.fixture(scope="session")
def report_path():
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return str(report_dir)
'''

DOMAIN_INIT_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""domain —— 所有领域包统一存放。"""
'''

DOMAIN_FILE_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""${name} 领域包。"""

''' + _domain_body("${name}", "${Name}", "${env}", "${base_url}", "${probe_path}")

RUN_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""入口脚本 —— 继承 SuiteRunner 定制套件行为。

用法::

    python run.py                             # 跑所有子包（pytest.ini 的 testpaths）
    python run.py ${name}/test_${name}.py      # 只跑单个文件
    python run.py --suite ${name}             # 只跑 ${name} 子包
    python run.py --html reports/custom.html   # 指定报告路径
    python run.py --show-config               # 打印生效配置后退出
    python run.py -- -v --tb=short            # 透传给 pytest
"""

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
os.chdir(_HERE)                              # 固定 cwd，使 pip install 的 editable finder 能正确定位

from apisk.runner import SuiteRunner


class ${Name}Runner(SuiteRunner):
    """${name} 套件运行器。"""

    SUITES = {
        "${name}": "${name}",
    }
    DOMAINS = (
        "domain.${name}_domain",
    )


if __name__ == "__main__":
    raise SystemExit(${Name}Runner(_HERE).run())
'''

SUB_INIT_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""${name} 业务子包。"""
'''

SUB_CONFIG_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""${name} 模块专属配置。"""

# 模块专属常量（报告文件名、评估阈值等）
${NAME}_REPORT_FILENAME = "test_${name}.csv"

__all__ = ["${NAME}_REPORT_FILENAME"]
'''

SUB_CONFTEST_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""${name} 模块专属 conftest —— 顶层共享夹具自动下传。"""

# 模块级专属夹具放这里（领域专属夹具也可以通过 Domain.plugin 提供）
'''

SMOKE_TEMPLATE = '''#! python3
# -*- encoding: utf-8 -*-

"""${name} 冒烟用例 —— 跑通即说明接入成功。"""

from apisk.support.markers import feature, story, title

pytestmark = [feature("${name}"), story("冒烟")]


@title("SMOKE-01 探活接口返回期望状态码")
def test_ping_status(metric_svc, report_data):
    resp = metric_svc.${name}.ping()
    report_data("status_code", resp.status_code)
    report_data("elapsed_ms", round(resp.exchange.elapsed_ms, 1))
    assert resp.status_code == 200, resp.exchange.summary()


@title("SMOKE-02 探活响应时间在合理范围内")
def test_ping_elapsed(metric_svc, report_data):
    resp = metric_svc.${name}.ping()
    elapsed_ms = round(resp.exchange.elapsed_ms, 1)
    report_data("status_code", resp.status_code)
    report_data("elapsed_ms", elapsed_ms)
    assert elapsed_ms < 5000, f"{{resp.exchange.summary()}} 超过 5000ms 上限"
'''

#: 输出清单
FILES = (
    ("pytest.ini",        PYTEST_INI_TEMPLATE),
    ("config.py",         ROOT_CONFIG_TEMPLATE),
    ("conftest.py",       ROOT_CONFTEST_TEMPLATE),
    ("domain/__init__.py", DOMAIN_INIT_TEMPLATE),
    ("domain/${name}_domain.py", DOMAIN_FILE_TEMPLATE),
    ("${name}/__init__.py", SUB_INIT_TEMPLATE),
    ("${name}/config.py",  SUB_CONFIG_TEMPLATE),
    ("${name}/conftest.py", SUB_CONFTEST_TEMPLATE),
    ("${name}/test_${name}.py", SMOKE_TEMPLATE),
)


# ============ 命令行 ============

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apisk.scaffold",
        description="生成 apisk 测试骨架（标准套件风格：顶层 rootdir + domain/ 统一存放）",
    )
    parser.add_argument("--name", required=True,
                        help="领域包名（小写模块名，如 mydomain）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="被测服务根地址")
    parser.add_argument("--probe", default="/api/v1/ping",
                        help="探活端点路径")
    parser.add_argument("--out", default=None,
                        help="输出目录；缺省 ./test_<name>")
    parser.add_argument("--force", action="store_true",
                        help="目标目录已存在且非空时仍然写入（覆盖同名文件）")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not _NAME_PATTERN.match(args.name):
        print(f"[错误] --name 必须是合法模块名，得到 {args.name!r}",
              file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else Path.cwd() / f"test_{args.name}"

    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        print(f"[错误] 目标目录已存在且非空: {out_dir}\n"
              f"       换 --out 或加 --force 覆盖", file=sys.stderr)
        return 2

    values = {
        "name": args.name,
        "Name": _camel(args.name),
        "NAME": args.name.upper(),
        "env": args.name.upper(),
        "base_url": args.base_url,
        "probe_path": args.probe,
    }

    for relative, template in FILES:
        target = out_dir / Template(relative).substitute(values)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(Template(template).substitute(values), encoding="utf-8")

    _print_next_steps(out_dir, args)
    return 0


def _camel(name: str) -> str:
    """``my_domain`` → ``MyDomain``。"""
    return "".join(part.capitalize() for part in name.split("_") if part)


def _print_next_steps(out_dir: Path, args) -> None:
    print(f"[apisk] 已生成测试骨架: {out_dir}")
    for relative, _ in FILES:
        print("  " + Template(relative).substitute(name=args.name))

    print(
        f"\n下一步：\n"
        f"  1. pip install apisk                   # 装框架（一次即可）\n"
        f"  2. cd {out_dir}\n"
        f"  3. 改 domain/{args.name}_domain.py 里的端点/解析逻辑\n"
        f"     BASE_URL 也可用环境变量 {args.name.upper()}_BASE_URL 覆盖\n"
        f"  4. pytest                              # 跑所有子包\n"
        f"     pytest {args.name}/test_{args.name}.py  # 只跑单个文件\n"
        f"     pytest {args.name}/                 # 只跑本子包\n"
        f"     pytest -k smoke                     # 按标记过滤\n"
        f"     报告见 reports/report.html（自动生成）\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
