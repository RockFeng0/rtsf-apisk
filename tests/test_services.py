#! python3
# -*- encoding: utf-8 -*-

"""服务容器：按领域声明装配、重名拒绝、短路取领域。"""

import pytest

from apisk.core.exceptions import DomainError
from apisk.domain import Domain, ServiceSpec, register_domain
from apisk.services import Services


class _FakeService:
    def __init__(self, name="fake"):
        self.name = name


def test_assembles_services_from_loaded_domains():
    register_domain(Domain(
        name="alpha",
        services=[ServiceSpec("device", lambda: _FakeService("device"))],
    ))
    register_domain(Domain(
        name="beta",
        services=[ServiceSpec("user", lambda: _FakeService("user"))],
    ))

    services = Services()

    assert services.service_names == ("device", "user")
    assert services.device.name == "device"
    assert services.get("user").name == "user"


def test_subclass_specs_are_merged_with_domains():
    register_domain(Domain(
        name="alpha",
        services=[ServiceSpec("device", lambda: _FakeService("device"))],
    ))

    class MyServices(Services):
        specs = (ServiceSpec("local", lambda: _FakeService("local")),)

    services = MyServices()

    assert services.service_names == ("local", "device")


def test_empty_domains_arg_skips_registry():
    register_domain(Domain(
        name="alpha",
        services=[ServiceSpec("device", lambda: _FakeService("device"))],
    ))

    services = Services(domains=[])

    assert services.service_names == ()


def test_duplicate_service_name_is_rejected():
    register_domain(Domain(
        name="alpha",
        services=[ServiceSpec("shared", lambda: _FakeService())],
    ))
    register_domain(Domain(
        name="beta",
        services=[ServiceSpec("shared", lambda: _FakeService())],
    ))

    with pytest.raises(DomainError, match="重复声明"):
        Services()


def test_extra_instances_are_attached():
    services = Services(domains=[], adhoc=_FakeService("adhoc"))

    assert services.adhoc.name == "adhoc"
    assert services.get("missing", "fallback") == "fallback"
