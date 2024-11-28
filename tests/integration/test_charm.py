#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""

# Disabling it due any_charm configuration.
# pylint: disable=line-too-long

import json
import logging
import secrets
import textwrap

import pytest
import requests
from juju.application import Application
from juju.model import Model
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(
    model: Model,
    application: Application,
):
    """
    arrange: deploy Maubot and postgresql and integrate them.
    act: send a request to get manifest.json.
    assert: the Maubot charm becomes active once is integrated with postgresql.
        Charm is still active after integrating it with Nginx and the request
        is successful.
    """

    postgresql_k8s = await model.deploy("postgresql-k8s", channel="14/stable", trust=True)
    await model.wait_for_idle(timeout=900)
    await model.add_relation(application.name, postgresql_k8s.name)
    await model.wait_for_idle(timeout=900, status="active")

    nginx_ingress_integrator = await model.deploy(
        "nginx-ingress-integrator",
        channel="edge",
        config={
            "path-routes": "/",
            "service-hostname": "maubot.local",
            "service-namespace": model.name,
            "service-name": "maubot",
        },
        trust=True,
    )
    await model.add_relation(application.name, nginx_ingress_integrator.name)

    await model.wait_for_idle(timeout=600, status="active")

    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/manifest.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )
    assert response.status_code == 200
    assert "Maubot Manager" in response.text


@pytest.mark.abort_on_fail
async def test_cos_integration(model: Model):
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
    await model.deploy(
        "any-charm",
        application_name=any_app_name,
        channel="beta",
        config={"src-overwrite": json.dumps(any_charm_src_overwrite)},
    )

    await model.add_relation(any_app_name, "maubot:grafana-dashboard")
    await model.wait_for_idle(status="active")

    unit = model.applications[any_app_name].units[0]
    action = await unit.run_action("rpc", method="validate_dashboard")
    await action.wait()
    assert "return" in action.results
    assert action.results["return"] == "null"


@pytest.mark.abort_on_fail
async def test_loki_endpoint(ops_test: OpsTest, any_loki: Application):
    """
    arrange: after Maubot is deployed and relations established
    act: any-loki is deployed and joins the relation
    assert: pebble plan inside maubot has logging endpoint configured.
    """
    exit_code, stdout, stderr = await ops_test.juju(
        "ssh", "--container", "maubot", "maubot/0", "pebble", "plan"
    )
    assert exit_code == 0, f"Command failed with exit code {exit_code} and stderr: {stderr}"
    assert "loki" in stdout, f"'loki' not found in pebble plan:\n{stdout}"


async def test_create_admin_action_success(unit: Unit):
    """
    arrange: Maubot charm integrated with PostgreSQL.
    act: run the create-admin action.
    assert: the action results contains a password.
    """
    name = "test"

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
async def test_create_admin_action_failed(name: str, expected_message: str, unit: Unit):
    """
    arrange: Maubot charm integrated with PostgreSQL.
    act: run the create-admin action.
    assert: the action results fails.
    """
    action = await unit.run_action("create-admin", name=name)
    await action.wait()

    assert "error" in action.results
    error = action.results["error"]
    assert error == expected_message


@pytest.mark.abort_on_fail
async def test_public_url_config(
    model: Model,
    application: Application,
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

    await application.set_config({"public-url": "http://foo.com/internal/"})
    await model.wait_for_idle(timeout=600, status="active")

    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/paths.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "api_path" in data
    assert data["api_path"] == "/internal/_matrix/maubot/v1"


async def test_register_client_account_action_success(unit: Unit, model: Model):
    """
    arrange: Maubot charm integrated with PostgreSQL and AnyCharm(matrix-auth)
        and admin user is created.
    act: run the register-client-account action.
    assert: the action results contains a password.
    """
    # create user
    name = secrets.token_urlsafe(5)
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
    # relate maubot with synapse
    # setting public_baseurl to an URL that Maubot can access
    # in production environment, this is the external URL accessed by clients
    matrix_server_name = "test1"
    await model.deploy(
        "synapse",
        application_name="synapse",
        channel="latest/edge",
        config={
            "server_name": matrix_server_name,
            "public_baseurl": "http://synapse-0.synapse-endpoints.testing.svc.cluster.local:8080/",
        },
    )
    await model.wait_for_idle(status="active")
    await model.add_relation("synapse:matrix-auth", "maubot:matrix-auth")
    await model.wait_for_idle(status="active")

    # run the action
    account_name = secrets.token_urlsafe(5).lower()
    params = {"account-name": account_name, "admin-name": name, "admin-password": password}
    action = await unit.run_action("register-client-account", **params)
    await action.wait()
    assert "access-token" in action.results
    assert "device-id" in action.results
    assert action.results["user-id"] == f"@{account_name}:{matrix_server_name}"
