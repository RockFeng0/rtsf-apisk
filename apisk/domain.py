#! python3
# -*- encoding: utf-8 -*-

"""业务领域扩展协议 —— 框架与业务之间的**唯一接缝**。

框架本身不含任何业务：端点类、业务服务、身份提供者、服务门禁探测都在
**框架之外**的领域包里声明。一个业务以「领域包」形式接入，在模块级导出
一个 ``Domain``::

    # mydomain/__init__.py
    from apisk.domain import Domain, ServiceSpec
    from mydomain.api.device_api import DeviceApi
    from mydomain.services.device_service import DeviceService

    DOMAIN = Domain(
        name="mydomain",
        apis={"device": DeviceApi},
        services=[ServiceSpec("device", DeviceService)],
        probe="/api/v1/device/probe",
        plugin="mydomain.pytest_plugin",      # 可选：领域自带夹具
    )

框架据此装配 ``Services``，用例侧即得到 ``svc.device.create(...)``。

加载来源（可并用）
------------------
1. 代码显式调用 ``load_domains("mydomain")``
2. 命令行 ``--apisk-domain mydomain``（可重复）
3. ``pytest.ini`` 的 ``apisk_domains = mydomain``
4. 环境变量 ``AUTO_TEST_DOMAINS=mydomain,other``
5. 入口点 ``apisk.domains`` —— 领域包被 pip 安装后**自动发现**

冻结语义
--------
注册只在 pytest 的配置阶段发生，之后 ``freeze_domains()`` 冻结；运行期再注册
一律抛 ``DomainError``。这样「已装配的服务清单」在用例执行期间恒定不变，
与框架「无全局可变状态」的约定一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module, metadata as importlib_metadata
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from apisk.core.exceptions import DomainError

#: 已安装分发包声明领域的入口点组名（``[project.entry-points."apisk.domains"]``）
ENTRY_POINT_GROUP = "apisk.domains"

#: 领域包导出领域声明的属性名（``DOMAIN`` 单个 / ``DOMAINS`` 多个）
DOMAIN_ATTRS = ("DOMAIN", "DOMAINS")


@dataclass(frozen=True)
class ServiceSpec:
    """一个业务服务的装配声明。

    Attributes:
        name: 装配到 ``Services`` 上的属性名，即用例里的 ``svc.<name>``。
        factory: 服务类（或返回服务的工厂）。无参构造——服务自己负责创建 HttpClient。
    """

    name: str
    factory: Callable[..., Any]

    def build(self):
        """按声明装配出一个服务实例（无参构造）。"""
        return self.factory()


@dataclass(frozen=True)
class Domain:
    """一个业务领域的完整声明。

    Attributes:
        name: 领域名（用于去重与日志）。
        apis: 端点类登记表 ``{逻辑名: BaseApi 子类}``，供端点级用例直接取用。
        services: 服务装配表，决定 ``Services`` 上出现哪些 ``svc.<name>``。
        probe: 服务门禁探测，取端点路径字符串，或 ``callable(client) -> (bool, str)``。
            缺省时框架退化为「目标地址可达即视为已部署」。
        plugin: 领域自带的 pytest 插件模块路径，用于提供领域专属夹具。
        config: 领域配置对象，供套件读取（阈值、数据集路径、契约常量等）。
    """

    name: str
    apis: Mapping[str, type] = field(default_factory=dict)
    services: Sequence[ServiceSpec] = ()
    probe: Optional[Any] = None
    plugin: Optional[str] = None
    config: Optional[Any] = None

    def __post_init__(self):
        if not self.name:
            raise DomainError("Domain 需要 name")
        object.__setattr__(self, "apis", MappingProxyType(dict(self.apis)))
        object.__setattr__(self, "services", tuple(self.services))

    # ---------- 查询 ----------

    def api(self, name: str) -> type:
        """按逻辑名取端点类。"""
        try:
            return self.apis[name]
        except KeyError:
            raise DomainError(
                f"领域 {self.name!r} 未声明端点 {name!r}，已声明: {sorted(self.apis)}"
            ) from None

    def service(self, name: str) -> ServiceSpec:
        """按逻辑名取服务装配声明。"""
        for spec in self.services:
            if spec.name == name:
                return spec
        raise DomainError(
            f"领域 {self.name!r} 未声明服务 {name!r}，"
            f"已声明: {sorted(s.name for s in self.services)}"
        )

    def __repr__(self):
        return (
            f"<Domain {self.name} apis={len(self.apis)} "
            f"services={len(self.services)}>"
        )


# ============ 注册表 ============

_domains: list = []
_imported: set = set()
_frozen = False


def _ensure_mutable():
    if _frozen:
        raise DomainError(
            "领域注册已冻结（pytest 配置阶段结束），运行期不再接受新的领域声明"
        )


def register_domain(domain: Domain) -> Domain:
    """登记一个领域声明。重名即报错，避免静默覆盖。"""
    _ensure_mutable()
    if not isinstance(domain, Domain):
        raise DomainError(f"期望 Domain 实例，得到 {type(domain).__name__}")
    if any(existing.name == domain.name for existing in _domains):
        raise DomainError(f"领域 {domain.name!r} 已注册，请检查是否重复加载")
    _domains.append(domain)
    return domain


def freeze_domains() -> Tuple[Domain, ...]:
    """冻结注册表。之后 ``register_domain`` 一律失败。"""
    global _frozen
    _frozen = True
    return tuple(_domains)


def loaded_domains() -> Tuple[Domain, ...]:
    """当前已加载的领域（只读快照）。"""
    return tuple(_domains)


# ============ 加载 ============

def load_domains(*names: str, entry_points: bool = False,
                 freeze: bool = False) -> Tuple[Domain, ...]:
    """按需导入领域包并登记其声明；重复调用幂等。

    Args:
        names: 领域包名（如 ``"mydomain"``）。
        entry_points: 是否同时发现入口点组 ``apisk.domains`` 下已安装的领域。
        freeze: 加载完成后是否冻结注册表（pytest 配置阶段用）。
    """
    for name in _flatten_names(names):
        _import_domain(name)
    if entry_points:
        for module_name in _entry_point_modules():
            _import_domain(module_name)
    return freeze_domains() if freeze else loaded_domains()


def _flatten_names(names: Iterable[str]) -> Tuple[str, ...]:
    """把 ``["a,b", "c"]`` 这类输入摊平成 ``("a", "b", "c")`` 并去重保序。"""
    flat = []
    for item in names or ():
        for piece in str(item).replace("\n", ",").split(","):
            piece = piece.strip()
            if piece and piece not in flat:
                flat.append(piece)
    return tuple(flat)


def _import_domain(module_name: str) -> None:
    """导入领域包并登记其中的 ``DOMAIN`` / ``DOMAINS``。

    以「模块是否已由本加载器导入过」判重（而非领域名），因此领域名与模块路径
    可以不同，重复加载也是幂等的。
    """
    if module_name in _imported:
        return

    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise DomainError(f"无法导入领域包 {module_name!r}: {exc}") from exc

    declared_all = []
    for attr in DOMAIN_ATTRS:
        declared = getattr(module, attr, None)
        if declared is None:
            continue
        declared_all.extend(
            declared if isinstance(declared, (list, tuple)) else (declared,)
        )
        break

    if not declared_all:
        raise DomainError(
            f"领域包 {module_name!r} 未导出 {' / '.join(DOMAIN_ATTRS)} 声明"
        )

    _imported.add(module_name)
    for domain in declared_all:
        register_domain(domain)


def _entry_point_modules() -> Tuple[str, ...]:
    """列出入口点组 ``apisk.domains`` 声明的领域包名。"""
    try:
        discovered = importlib_metadata.entry_points()
    except Exception:                      # pragma: no cover - 元数据不可用时静默跳过
        return ()
    if hasattr(discovered, "select"):
        selected = discovered.select(group=ENTRY_POINT_GROUP)
    else:                                  # Python 3.9 的旧接口
        selected = discovered.get(ENTRY_POINT_GROUP, ())
    modules = []
    for entry_point in selected:
        name = getattr(entry_point, "module", "") or str(entry_point.value).split(":")[0]
        if name and name not in modules:
            modules.append(name)
    return tuple(modules)


# ============ 供框架夹具解析用 ============

def _first_attr(attr_name: str):
    """取已加载领域中第一个非 ``None`` 的同名属性（遍历顺序即加载顺序）。"""
    for domain in _domains:
        value = getattr(domain, attr_name, None)
        if value is not None:
            return value
    return None


def probe_spec():
    """第一个声明了服务门禁探测的领域的探测配置。"""
    return _first_attr("probe")


def domain_config():
    """第一个携带配置对象的领域的配置。"""
    return _first_attr("config")


def domain_plugins() -> Tuple[str, ...]:
    """各领域自带的 pytest 插件模块路径。"""
    return tuple(d.plugin for d in _domains if d.plugin)


__all__ = [
    "DOMAIN_ATTRS",
    "ENTRY_POINT_GROUP",
    "Domain",
    "ServiceSpec",
    "domain_config",
    "domain_plugins",
    "freeze_domains",
    "load_domains",
    "loaded_domains",
    "probe_spec",
    "register_domain",
]
