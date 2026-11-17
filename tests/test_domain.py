#! python3
# -*- encoding: utf-8 -*-

"""领域扩展协议：声明校验、注册表、加载来源。"""

import sys
import types

import pytest

from apisk.core.exceptions import DomainError
from apisk.domain import (
    Domain,
    ServiceSpec,
    freeze_domains,
    load_domains,
    loaded_domains,
    register_domain,
)


def _domain(name="demo", **kwargs):
    return Domain(name=name, **kwargs)


def test_domain_requires_name():
    with pytest.raises(DomainError, match="需要 name"):
        Domain(name="")


def test_apis_mapping_is_read_only_copy():
    source = {"ping": object}
    domain = _domain(apis=source)

    source["injected"] = object          # 外部改动不应影响已声明的领域
    assert "injected" not in domain.apis
    with pytest.raises(TypeError):
        domain.apis["x"] = object        # MappingProxyType 只读


def test_services_are_frozen_tuple():
    specs = [ServiceSpec("one", lambda: 1)]
    domain = _domain(services=specs)

    specs.append(ServiceSpec("two", lambda: 2))
    assert [s.name for s in domain.services] == ["one"]
    assert isinstance(domain.services, tuple)


def test_api_lookup_reports_declared_names():
    domain = _domain(apis={"ping": object})

    with pytest.raises(DomainError, match="未声明端点 'pong'"):
        domain.api("pong")


def test_service_lookup_by_name():
    spec = ServiceSpec("device", lambda: "svc")
    domain = _domain(services=[spec])

    assert domain.service("device") is spec
    assert spec.build() == "svc"
    with pytest.raises(DomainError, match="未声明服务 'missing'"):
        domain.service("missing")


def test_register_rejects_duplicate_name():
    register_domain(_domain("dup"))

    with pytest.raises(DomainError, match="已注册"):
        register_domain(_domain("dup"))


def test_register_rejects_non_domain():
    with pytest.raises(DomainError, match="期望 Domain 实例"):
        register_domain({"name": "not-a-domain"})


def test_frozen_registry_rejects_register():
    freeze_domains()

    with pytest.raises(DomainError, match="已冻结"):
        register_domain(_domain("late"))


def test_load_domains_flattens_and_dedupes():
    module = types.ModuleType("_apisk_demo_flatten")
    module.DOMAINS = [_domain("alpha"), _domain("beta")]
    sys.modules[module.__name__] = module

    try:
        names = load_domains(f"{module.__name__},{module.__name__}\n{module.__name__}")
    finally:
        sys.modules.pop(module.__name__, None)

    # 同一个模块只导入一次，逗号/换行都作为分隔符
    assert [d.name for d in names] == ["alpha", "beta"]


def test_load_domains_missing_module_is_actionable():
    with pytest.raises(DomainError, match="无法导入领域包"):
        load_domains("no_such_domain_module_xyz")


def test_load_domains_requires_declaration():
    module = types.ModuleType("_apisk_demo_empty")
    sys.modules[module.__name__] = module

    try:
        with pytest.raises(DomainError, match="未导出"):
            load_domains(module.__name__)
    finally:
        sys.modules.pop(module.__name__, None)


def test_loaded_domains_is_snapshot():
    register_domain(_domain("snap"))

    snapshot = loaded_domains()
    register_domain(_domain("later"))

    assert [d.name for d in snapshot] == ["snap"]
    assert [d.name for d in loaded_domains()] == ["snap", "later"]
