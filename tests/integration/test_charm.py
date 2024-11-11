#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""

# Disabling it due any_charm configuration.
# pylint: disable=line-too-long

import json
import logging
import textwrap

import pytest
import requests
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(
    ops_test: OpsTest,
    pytestconfig: pytest.Config,
):
    """
    arrange: set up the test Juju model.
    act: build and deploy the Maubot charm, check if is blocked and deploy postgresql.
    assert: the Maubot charm becomes active once is integrated with postgresql.
        Charm is still active after integrating it with Nginx and the request
        is successful.
    """
    charm = pytestconfig.getoption("--charm-file")
    maubot_image = pytestconfig.getoption("--maubot-image")
    assert maubot_image
    if not charm:
        charm = await ops_test.build_charm(".")
    assert ops_test.model
    maubot = await ops_test.model.deploy(f"./{charm}", resources={"maubot-image": maubot_image})

    await ops_test.model.wait_for_idle(timeout=600, status="blocked")

    postgresql_k8s = await ops_test.model.deploy("postgresql-k8s", channel="14/stable", trust=True)
    await ops_test.model.wait_for_idle(timeout=900)
    await ops_test.model.add_relation(maubot.name, postgresql_k8s.name)
    await ops_test.model.wait_for_idle(timeout=900, status="active")

    nginx_ingress_integrator = await ops_test.model.deploy(
        "nginx-ingress-integrator",
        channel="edge",
        config={
            "path-routes": "/",
            "service-hostname": "maubot.local",
            "service-namespace": ops_test.model.name,
            "service-name": "maubot",
        },
        trust=True,
    )
    await ops_test.model.add_relation(maubot.name, nginx_ingress_integrator.name)

    await ops_test.model.wait_for_idle(timeout=600, status="active")

    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/manifest.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )
    assert response.status_code == 200
    assert "Maubot Manager" in response.text


@pytest.mark.abort_on_fail
async def test_cos_integration(ops_test: OpsTest):
    """
    arrange: deploy Anycharm.
    act: integrate Maubot with Anycharm.
    assert: Run action that validates if dashboard is present.
    """
    any_app_name = "any-grafana"
    grafana_lib_url = "https://github.com/canonical/grafana-k8s-operator/raw/refs/heads/main/lib/charms/grafana_k8s/v0/grafana_dashboard.py"  # noqa: E501
    grafana_lib = requests.get(grafana_lib_url, timeout=10).text
    grafana_lib = grafana_lib.replace(
        'DEFAULT_PEER_NAME = "grafana"', 'DEFAULT_PEER_NAME = "peer-any"'
    )
    any_charm_src_overwrite = {
        "grafana_dashboard.py": grafana_lib,
        "any_charm.py": textwrap.dedent(
            """\
        from grafana_dashboard import GrafanaDashboardConsumer
        from any_charm_base import AnyCharmBase
        class AnyCharm(AnyCharmBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.grafana_dashboard_consumer = GrafanaDashboardConsumer(self, relation_name="require-grafana-dashboard")  # noqa: E501
            def validate_dashboard(self):
                relation = self.model.get_relation("require-grafana-dashboard")
                dashboards = self.grafana_dashboard_consumer.get_dashboards_from_relation(relation.id)  # noqa: E501
                if len(dashboards) == 0:
                    raise ValueError("dashboard not found")
                other_app = relation.app
                raw_data = relation.data[other_app].get("dashboards", "")
                if not raw_data:
                    raise ValueError("dashboard has no raw data")
            @property
            def peers(self):
                return self.model.get_relation("peer-any")
        """
        ),
    }
    assert ops_test.model
    await ops_test.model.deploy(
        "any-charm",
        application_name=any_app_name,
        channel="beta",
        config={"src-overwrite": json.dumps(any_charm_src_overwrite)},
    )

    await ops_test.model.add_relation(any_app_name, "maubot:grafana-dashboard")
    await ops_test.model.wait_for_idle(status="active")

    unit = ops_test.model.applications[any_app_name].units[0]
    action = await unit.run_action("rpc", method="validate_dashboard")
    await action.wait()
    assert "return" in action.results
    assert action.results["return"] == "null"


async def test_create_admin_action_success(ops_test: OpsTest):
    """
    arrange: Maubot charm integrated with PostgreSQL.
    act: run the create-admin action.
    assert: the action results contains a password.
    """
    name = "test"
    assert ops_test.model
    unit = ops_test.model.applications["maubot"].units[0]

    action = await unit.run_action("create-admin", name=name)
    await action.wait()

    assert "password" in action.results
    password = action.results["password"]
    response = requests.post(
        "http://127.0.0.1/_matrix/maubot/v1/auth/login",
        timeout=5,
        headers={"Host": "maubot.local"},
        data=f'{{"username":"{name}","password":"{password}"}}',
    )
    assert response.status_code == 200
    assert "token" in response.text


@pytest.mark.parametrize(
    "name,expected_message",
    [
        pytest.param("root", "root is reserved, please choose a different name", id="root"),
        pytest.param("test", "test already exists", id="user_exists"),
    ],
)
async def test_create_admin_action_failed(name: str, expected_message: str, ops_test: OpsTest):
    """
    arrange: Maubot charm integrated with PostgreSQL.
    act: run the create-admin action.
    assert: the action results fails.
    """
    assert ops_test.model
    unit = ops_test.model.applications["maubot"].units[0]

    action = await unit.run_action("create-admin", name=name)
    await action.wait()

    assert "error" in action.results
    error = action.results["error"]
    assert error == expected_message


@pytest.mark.abort_on_fail
async def test_public_url_config(
    ops_test: OpsTest,
):
    """
    arrange: Maubot is active and paths.json contains default value.
    act: change public_url with a different path called /internal/.
    assert: api_path contains the extra subpath /internal/ extracted from the
        public_url.
    """
    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/paths.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "api_path" in data
    assert data["api_path"] == "/_matrix/maubot/v1"

    assert ops_test.model
    application = ops_test.model.applications["maubot"]
    await application.set_config({"public-url": "http://foo.com/internal/"})
    await ops_test.model.wait_for_idle(timeout=600, status="active")

    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/paths.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "api_path" in data
    assert data["api_path"] == "/internal/_matrix/maubot/v1"
