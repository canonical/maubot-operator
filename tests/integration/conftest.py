# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubot integration tests."""

import json
from typing import Any, Callable, Coroutine

import pytest
import pytest_asyncio
import kubernetes.config
import kubernetes.stream
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

