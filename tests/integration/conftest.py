# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubot integration tests."""

import json
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Coroutine

import pytest
import pytest_asyncio
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
    charm = pytestconfig.getoption("--charm-file")
    if not charm:
        charm = await ops_test.build_charm(".")
        assert charm, "Charm not built"
        return charm
    return charm


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
