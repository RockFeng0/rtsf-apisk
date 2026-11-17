#! python3
# -*- encoding: utf-8 -*-

"""业务服务容器 —— 按声明装配**已加载领域**的全部服务。

框架不硬编码任何服务：装配表来自 ``apisk.domain.loaded_domains()``。两种扩展方式：

1. **领域包**（推荐）：在 ``Domain.services`` 里声明 ``ServiceSpec(name, 服务类)``；
2. **直接子类化**：在不走领域包的场景，继承 ``Services`` 并覆盖 ``specs``::

       from apisk.domain import ServiceSpec
       from apisk.services import Services

       class MyServices(Services):
           specs = (ServiceSpec("device", DeviceService),)

       MyServices()                     # 领域声明 + 本类声明 一起装配
       MyServices(domains=[])           # 只要本类声明（不看已加载领域）

用例侧看到的是同一套写法::

    svc = Services()                   # 或 metric_svc fixture
    svc.order.detail(...)              # 领域声明的服务
    svc.search.query(...)              # 自有凭据的服务

每个 Service 在自己的 ``__init__`` 里 new HttpClient，
框架不持有凭据、不注入身份。Services 容器只做声明合并和属性挂载。
"""

from typing import Any, ClassVar, Iterable, Optional, Sequence, Tuple

from apisk.core.exceptions import DomainError
from apisk.domain import ServiceSpec, loaded_domains


class Services:
    """业务服务集合（纯声明装配，零身份概念）。

    Args:
        domains: 参与装配的领域；缺省取 ``loaded_domains()``，
            传 ``[]`` 表示只装配 ``specs`` 声明的内容。
        **extra: 额外挂载的服务实例（``name=instance``），用于临时注入。

    Raises:
        DomainError: 同一个服务名被声明多次（无论来自领域还是子类）。
    """

    #: 子类可直接声明本业务域的装配表（与 ``Domain.services`` 等价）
    specs: ClassVar[Sequence[ServiceSpec]] = ()

    def __init__(self, domains: Optional[Iterable] = None, **extra):
        self._specs = _merge_specs(self.specs, domains)

        for spec in self._specs:
            setattr(self, spec.name, spec.build())
        for name, value in extra.items():
            setattr(self, name, value)

    # ---------- 查询 ----------

    @property
    def service_names(self) -> Tuple[str, ...]:
        """本次装配出的服务属性名。"""
        return tuple(spec.name for spec in self._specs)

    @property
    def domains(self) -> Tuple[str, ...]:
        """参与装配的领域名。"""
        return tuple(domain.name for domain in loaded_domains())

    def get(self, name: str, default=None):
        """按名取服务；不存在时返回默认值。"""
        return getattr(self, name, default)

    def __repr__(self):
        return f"<Services services={list(self.service_names)}>"


def _merge_specs(declared: Sequence[ServiceSpec],
                 domains: Optional[Iterable]) -> Tuple[ServiceSpec, ...]:
    """合并「子类声明」与「领域声明」，并拒绝重名。

    ``domains=None`` 表示取已加载领域；``domains=[]`` 表示不取领域。
    """
    collected = [(spec, "Services.specs") for spec in declared]
    source = loaded_domains() if domains is None else tuple(domains)
    for domain in source:
        collected.extend((spec, domain.name) for spec in domain.services)

    merged: list = []
    seen: dict = {}
    for spec, owner in collected:
        previous = seen.get(spec.name)
        if previous is not None:
            raise DomainError(
                f"服务名 {spec.name!r} 被重复声明（{previous} 与 {owner}）"
            )
        seen[spec.name] = owner
        merged.append(spec)
    return tuple(merged)


__all__ = ["Services"]
