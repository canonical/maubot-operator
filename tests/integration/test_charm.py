#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""

import logging

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
