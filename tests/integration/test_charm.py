#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""

import logging
import secrets
import typing

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
async def test_cos_integration(
    ops_test: OpsTest, get_unit_ips: typing.Callable[[str], typing.Awaitable[tuple[str, ...]]]
):
    """
    arrange: deploy Prometheus, Grafana and integrate them.
    act: integrate Maubot with Prometheus and Grafana.
    assert: Maubot is a Prometheus target and the dashboard is available.
    """
    assert ops_test.model
    prometheus_k8s = await ops_test.model.deploy(
        "prometheus-k8s",
        channel="latest/edge",
        trust=True,
    )
    await ops_test.model.add_relation("maubot", prometheus_k8s.name)
    await ops_test.model.wait_for_idle(timeout=600, status="active")

    for unit_ip in await get_unit_ips(prometheus_k8s.name):
        query_targets = requests.get(f"http://{unit_ip}:9090/api/v1/targets", timeout=10).json()
        assert len(query_targets["data"]["activeTargets"])

    grafana_k8s = await ops_test.model.deploy(
        "grafana-k8s",
        channel="latest/edge",
        trust=True,
    )
    await ops_test.model.add_relation(
        f"{grafana_k8s.name}:grafana-source", f"{prometheus_k8s.name}:grafana-source"
    )
    await ops_test.model.add_relation("maubot", grafana_k8s.name)
    await ops_test.model.wait_for_idle(timeout=600, status="active")
    action = (
        await ops_test.model.applications[grafana_k8s.name]
        .units[0]
        .run_action("get-admin-password")
    )
    await action.wait()
    password = action.results["admin-password"]
    grafana_ip = (await get_unit_ips(grafana_k8s.name))[0]
    sess = requests.session()
    sess.post(
        f"http://{grafana_ip}:3000/login",
        json={
            "user": "admin",
            "password": password,
        },
    ).raise_for_status()
    datasources = sess.get(f"http://{grafana_ip}:3000/api/datasources", timeout=10).json()
    datasource_types = set(datasource["type"] for datasource in datasources)
    assert "prometheus" in datasource_types
    dashboards = sess.get(
        f"http://{grafana_ip}:3000/api/search",
        timeout=10,
        params={"query": "Prometheus Maubot Blackbox Exporter"},
    ).json()
    assert len(dashboards)


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


async def test_register_client_account_action_success(ops_test: OpsTest):
    """
    arrange: Maubot charm integrated with PostgreSQL and AnyCharm(matrix-auth)
        and admin user is created.
    act: run the register-client-account action.
    assert: the action results contains a password.
    """
    # create user
    name = secrets.token_urlsafe(5)
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
    # relate maubot with synapse
    await ops_test.model.deploy(
        "synapse",
        application_name="synapse",
        channel="latest/edge",
        config={"server_name": "test1"},
    )
    await ops_test.model.wait_for_idle(status="active")
    await ops_test.model.add_relation("synapse:matrix-auth", "maubot:matrix-auth")
    await ops_test.model.wait_for_idle(status="active")

    # run the action
    params = {"account-name": "myaccount", "admin-name": name, "admin-password": password}
    action = await unit.run_action("register-client-account", **params)
    await action.wait()
    assert "access-token" in action.results
