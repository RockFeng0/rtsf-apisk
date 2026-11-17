#! python3
# -*- encoding: utf-8 -*-

"""套件入口框架 —— 提供可继承的 ``SuiteRunner`` 基类，让套件里的 ``run.py``
只做业务定制（套件别名、领域包）。

pytest 的 ``--html`` 相对路径、``rootdir`` 判定都跟着**调用方的工作目录**走，
这是「换个目录执行报告就跑到别处」的根因。这里固定把套件目录（``pytest.ini``
所在目录）作为唯一收集目标，于是无论从哪里执行，命中的都是本套件自己的配置。

最小用法（脚手架生成的套件根 ``run.py``）::

    import sys
    from pathlib import Path

    _HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(_HERE.parents[2]))

    from apisk.runner import SuiteRunner, run_suite

    # 方式一：直接用基类（等价于 run_suite）
    raise SystemExit(SuiteRunner(_HERE).run())

    # 方式二：继承后定制
    class MyRunner(SuiteRunner):
        SUITES = {"mydomain": "mydomain"}
        DOMAINS = ("domain.mydomain_domain",)

    raise SystemExit(MyRunner(_HERE).run())

    # 方式三：保持函数式调用（向后兼容）
    raise SystemExit(run_suite(_HERE))

CLI 约定
--------
``python run.py [target] [--suite NAME] [--html PATH] [--show-config] [-- pytest_args...]``

- ``target``      可选位置参数，直接指定测试文件或目录（可相对套件根）
                  例如 ``python run.py jk_model/test_asr.py``
- ``--suite``     只跑某个子套件（由子类在 ``SUITES`` 里声明别名）
- ``--html``      指定 HTML 报告输出路径；缺省 ``reports/report.html``
- ``--show-config`` 打印生效配置后退出
- ``--``          之后的所有参数原样透传给 pytest

优先级：位置参数 target > ``--suite`` > 套件根目录（pytest.ini 的 testpaths）。
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence


class SuiteRunner:
    """可继承的套件运行器基类。

    子类可以覆写以下类属性 / 方法来注入业务逻辑：

    ==============  ========================================================
    ``SUITES``      套件别名 → 子目录名映射。缺省空字典。
    ``DOMAINS``     业务领域包列表（用于 ``--show-config`` 打印）。
    ``discover_tests()`` 自动发现测试用例的策略（缺省返回 ``self.suite_dir``）。
    ``build_args()``    组装 pytest 参数（缺省追加 ``--html`` + 透传 CLI）。
    ``before_run()``    pytest 启动前的钩子（如 load_domains）。
    ``after_run()``     pytest 结束后的钩子。
    ``print_config()``  ``--show-config`` 的打印内容。
    ==============  ========================================================
    """

    #: 套件别名 → 子目录名（子类覆写）
    SUITES: dict = {}

    #: 业务领域包（子类覆写）
    DOMAINS: Iterable[str] = ()

    # ---------- 构造 ----------

    def __init__(
        self,
        suite_dir: str | Path,
        argv: Optional[Sequence[str]] = None,
    ) -> None:
        self.suite_dir = Path(suite_dir).resolve()
        self.argv = list(argv) if argv is not None else sys.argv[1:]
        self.args: argparse.Namespace = None  # _parse_args 后填充
        self.pytest_args: list[str] = []       # build_args 后填充

    # ---------- CLI 解析 ----------

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="python run.py",
            description=f"apisk 套件入口（{self.suite_dir.name}）",
        )
        parser.add_argument(
            "target",
            nargs="?",
            default=None,
            help="可选：直接指定测试文件或目录（相对套件根也可），"
                 "如 jk_model/test_asr.py",
        )
        parser.add_argument(
            "--suite",
            choices=sorted(self.SUITES) or None,
            help="只跑某个子套件",
        )
        parser.add_argument("--html", default=None, help="指定 HTML 报告输出路径")
        parser.add_argument(
            "--show-config",
            action="store_true",
            help="打印生效配置后退出",
        )
        args, extra = parser.parse_known_args(self.argv)
        args.pytest_args = self._strip_separator(extra)
        return args

    @staticmethod
    def _strip_separator(argv: Sequence[str]) -> list:
        """剔除分隔符 ``--``，其余参数原样透传。"""
        args = list(argv)
        if "--" in args:
            args.remove("--")
        return args

    # ---------- 路径 ----------

    def _fix_cwd(self) -> None:
        """固定工作目录为套件根，使 pytest.rootdir 稳定。"""
        os.chdir(self.suite_dir)

    def _ensure_importable(self) -> None:
        """把框架 + 共享层所在目录加入 ``sys.path``。

        逐级上溯查找 ``apisk/__init__.py`` 和 ``shared/__init__.py``，找不到
        就不动（pip 安装场景下两者都已就位）。
        """
        for parent in self.suite_dir.parents:
            p = str(parent)
            if (parent / "apisk" / "__init__.py").is_file() and p not in sys.path:
                sys.path.insert(0, p)
            if (parent / "shared" / "__init__.py").is_file() and p not in sys.path:
                sys.path.insert(0, p)

    # ---------- 测试发现 ----------

    def discover_tests(self) -> Path:
        """返回本次要执行的测试目标（目录或文件）。

        优先级：
        1. 位置参数 ``target``（直接指定文件或目录，相对于套件根可解析）
        2. ``--suite``（子类在 ``SUITES`` 里声明的别名 → 子目录）
        3. 套件根目录 ``suite_dir``（交给 pytest.ini 的 testpaths 收集）

        子类可覆写实现更复杂的自动发现策略。
        """
        # 1. 位置参数优先
        if self.args.target:
            tgt = Path(self.args.target)
            if not tgt.is_absolute():
                tgt = self.suite_dir / tgt
            if tgt.exists():
                return tgt.resolve()
            print(
                f"[警告] target {self.args.target!r} 不存在，回退到默认逻辑",
                file=sys.stderr,
            )

        # 2. --suite 别名
        if self.args.suite and self.SUITES:
            sub = self.SUITES[self.args.suite]
            sub_dir = self.suite_dir / sub
            if sub_dir.is_dir():
                return sub_dir
            print(
                f"[警告] --suite {self.args.suite!r} "
                f"(= {sub!r}) 不存在，仍跑根目录",
                file=sys.stderr,
            )

        return self.suite_dir

    # ---------- pytest 参数 ----------

    def build_args(self, target: Path) -> list[str]:
        """组装 pytest 的完整参数列表。"""
        args = [str(target), *self.args.pytest_args]

        # 自动追加 HTML 报告（用户显式给 --html 时尊重用户）
        user_gave_html = (
            "--html" in self.args.pytest_args
            or any(a.startswith("--html=") for a in self.args.pytest_args)
        )
        if self.args.html:
            report = Path(self.args.html)
            if not report.is_absolute():
                report = self.suite_dir / report
            report.parent.mkdir(parents=True, exist_ok=True)
            args += ["--html", str(report), "--self-contained-html"]
        elif not user_gave_html:
            report = self.suite_dir / "reports" / "report.html"
            report.parent.mkdir(parents=True, exist_ok=True)
            args += ["--html", str(report), "--self-contained-html"]

        return args

    # ---------- 钩子 ----------

    def before_run(self) -> None:
        """pytest 启动前的钩子。子类可覆写（如 ``load_domains``）。"""

    def after_run(self, exit_code: int) -> None:
        """pytest 结束后的钩子。子类可覆写。"""

    # ---------- 配置打印 ----------

    def print_config(self) -> None:
        """``--show-config`` 的打印内容。子类可覆写以追加业务字段。"""
        target = self.discover_tests()
        print(f"套件根       : {self.suite_dir}")
        print(f"测试目标     : {target}")
        print(f"CLI 透传     : {self.args.pytest_args}")
        print(f"业务领域     : {', '.join(self.DOMAINS) or '（无）'}")

    # ---------- 主流程 ----------

    def run(self) -> int:
        """执行完整流程并返回 pytest 退出码。"""
        self.args = self._build_parser()
        self._ensure_importable()

        if self.args.show_config:
            self.print_config()
            return 0

        target = self.discover_tests()
        self._fix_cwd()

        # 确保 reports / logs 目录存在
        (self.suite_dir / "reports").mkdir(exist_ok=True)
        (self.suite_dir / "logs").mkdir(exist_ok=True)

        self.pytest_args = self.build_args(target)

        self.before_run()

        import pytest

        print(f"[run] suite={self.args.suite or 'all'} target={target}")
        exit_code = int(pytest.main(self.pytest_args))

        self.after_run(exit_code)
        return exit_code


# ---------- 向后兼容的函数式 API ----------

def run_suite(suite_dir, argv: Optional[Sequence[str]] = None) -> int:
    """以 ``suite_dir`` 为套件根运行 pytest，返回其退出码。

    等价于 ``SuiteRunner(suite_dir, argv).run()``，保留给脚手架生成的
    run.py 以及直接函数式调用的场景。

    Args:
        suite_dir: 套件工程根（``pytest.ini`` / ``conftest.py`` 所在目录）。
        argv: 透传给 pytest 的参数；``None`` 时取 ``sys.argv[1:]``。
            习惯上写成 ``python run.py -- -v -k smoke``，命令行里的第一个
            ``--`` 只是分隔符，会被剔除。

    Returns:
        pytest 退出码（0 通过、1 有用例失败、5 未收集到用例……）。
    """
    return SuiteRunner(suite_dir, argv).run()


__all__ = ["SuiteRunner", "run_suite"]
