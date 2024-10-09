# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubotunit tests."""

import json

import pytest
import pytest_asyncio
from ops.testing import Harness
from pytest_operator.plugin import OpsTest

from charm import MaubotCharm


@pytest.fixture(scope="function", name="harness")
def harness_fixture():
    """Enable ops test framework harness."""
    harness = Harness(MaubotCharm)
    harness.set_model_name("test")
    harness.handle_exec(
        "maubot",
        ["cp", "--update=none", "/example-config.yaml", "/data/config.yaml"],
        result=0,
    )
    harness.handle_exec(
        "maubot", ["mkdir", "-p", "/data/plugins", "/data/trash", "/data/dbs"], result=0
    )
    root = harness.get_filesystem_root("maubot")
    (root / "data").mkdir()
    yaml_content = """\
database: sqlite:maubot.db
server:
    hostname: 0.0.0.0
    port: 29316
    public_url: https://example.com
admins:
    root:
"""
    (root / "data" / "config.yaml").write_text(yaml_content)
    yield harness
    harness.cleanup()


@pytest_asyncio.fixture(scope="module", name="get_unit_ips")
async def fixture_get_unit_ips(ops_test: OpsTest):
    """Return an async function to retrieve unit ip addresses of a certain application."""

    async def get_unit_ips(application_name: str):
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
