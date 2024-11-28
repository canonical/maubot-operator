# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubot integration tests."""

import json
import textwrap
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Coroutine

import pytest
import pytest_asyncio
import requests
from juju.application import Application
from juju.model import Model
from juju.unit import Unit
from pytest_operator.plugin import OpsTest


@pytest_asyncio.fixture(scope="function", name="get_unit_ips")
async def fixture_get_unit_ips(
    ops_test: OpsTest,
) -> Callable[..., Coroutine[Any, Any, tuple[Any, ...]]]:
    """Return an async function to retrieve unit ip addresses of a certain application."""

    async def get_unit_ips(application_name: str) -> tuple[Any, ...]:
        """Retrieve unit ip addresses of a certain application.

        Args:
            application_name: application to get the ip address.

        Returns:
            A list containing unit ip addresses.
        """
        _, status, _ = await ops_test.juju("status", "--format", "json")
        status = json.loads(status)
        units = status["applications"][application_name]["units"]
        return tuple(
            unit_status["address"]
            for _, unit_status in sorted(units.items(), key=lambda kv: int(kv[0].split("/")[-1]))
        )

    return get_unit_ips


@pytest.fixture(scope="module", name="model")
def model_fixture(ops_test: OpsTest) -> Model:
    """The testing model."""
    assert ops_test.model
    return ops_test.model


@pytest_asyncio.fixture(scope="module", name="charm")
async def charm_fixture(pytestconfig: pytest.Config, ops_test: OpsTest) -> str | Path:
    """The path to charm."""
    charms = pytestconfig.getoption("--charm-file")
    if not charms:
        charm = await ops_test.build_charm(".")
        assert charm, "Charm not built"
        return charm
    return charms


@pytest_asyncio.fixture(scope="module", name="application")
async def maubot_application_fixture(
    model: Model,
    charm: str | Path,
    pytestconfig: pytest.Config,
) -> AsyncGenerator[Application, None]:
    """Deploy the maubot charm."""
    maubot_image = pytestconfig.getoption("--maubot-image")
    assert maubot_image
    maubot = await model.deploy(f"./{charm}", resources={"maubot-image": maubot_image})

    await model.wait_for_idle(timeout=600, status="blocked")

    yield maubot


@pytest.fixture(scope="module", name="unit")
def unit_fixture(application: Application) -> Unit:
    """The maubot charm application unit."""
    return application.units[0]


@pytest_asyncio.fixture(scope="module", name="postgresql-related")
async def postgresql_related_fixture(model: Model, application: Application):
    """Deploy postgresql-k8s charm and relate to maubot"""
    postgresql_k8s = await model.deploy("postgresql-k8s", channel="14/stable", trust=True)
    await model.wait_for_idle(timeout=900)

    await model.add_relation(application.name, postgresql_k8s.name)
    await model.wait_for_idle(timeout=900, status="active")

    return postgresql_k8s


@pytest_asyncio.fixture(scope="module", name="any_loki")
async def any_loki_fixture(model: Model) -> Application:
    """Deploy loki using AnyCharm and relating it to maubot"""
    any_app_name = "any-loki"
    loki_lib_url = (
        "https://github.com/canonical/loki-k8s-operator/raw/refs/heads/main"
        "/lib/charms/loki_k8s/v1/loki_push_api.py"
    )
    loki_lib = requests.get(loki_lib_url, timeout=10).text
    any_charm_src_overwrite = {
        "loki_push_api.py": loki_lib,
        "any_charm.py": textwrap.dedent(
            """\
        from loki_push_api import LokiPushApiProvider
        from any_charm_base import AnyCharmBase
        class AnyCharm(AnyCharmBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.loki_provider = LokiPushApiProvider(self, relation_name="provide-logging")
            def get_relation_id(self):
                relation = self.model.get_relation("provide-logging")
                return relation.id
        """
        ),
    }
    loki_any = await model.deploy(
        "any-charm",
        application_name=any_app_name,
        channel="beta",
        config={"src-overwrite": json.dumps(any_charm_src_overwrite), "python-packages": "cosl"},
    )

    await model.add_relation(any_app_name, "maubot:logging")
    await model.wait_for_idle(status="active")

    return loki_any
