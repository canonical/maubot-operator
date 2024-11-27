# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubot integration tests."""

import json
import textwrap
from typing import Any, Callable, Coroutine

import pytest
import pytest_asyncio
import requests
import yaml
from juju.application import Application
from juju.model import Model
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


@pytest_asyncio.fixture(scope="function", name="any_loki")
async def any_loki_fixture(model: Model):
    """Deploy loki using AnyCharm and relating it to maubot"""
    any_app_name = "any-loki"
    loki_lib_url = "https://github.com/canonical/loki-k8s-operator/raw/refs/heads/main/lib/charms/loki_k8s/v1/loki_push_api.py"  # pylint: disable=line-too-long
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


@pytest_asyncio.fixture(scope="function", name="loki_relation_data")
async def loki_relation_data_fixture(any_loki: Application):
    """Return relation data from any-loki unit"""
    loki_unit = any_loki.units[0]
    action = await loki_unit.run_action("rpc", method="get_relation_id")
    results = await action.wait()
    relation_id = results.results["return"]
    relation_get_cmd = f"relation-get --format=yaml -r {relation_id} - {loki_unit.name}"
    result = await loki_unit.run(relation_get_cmd, block=True)
    assert (
        result.results["return-code"] == 0
    ), f"cmd `{relation_get_cmd}` failed with error `{result.results.get('stderr')}`"
    relation_data = yaml.safe_load(result.results["stdout"])
    return relation_data
