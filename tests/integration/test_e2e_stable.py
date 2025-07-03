#!/usr/bin/env python3

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""E2E test."""

import jubilant
import pytest
import requests

# pylint: disable=duplicate-code


@pytest.fixture(scope="module", name="juju")
def juju_fixture():
    """Juju fixture"""
    with jubilant.temp_model() as juju:
        yield juju


@pytest.mark.abort_on_fail
async def test_deploy_stable(juju: jubilant.Juju):
    """Deploy Maubot and integrations"""
    juju.deploy("maubot", channel="latest/stable")
    juju.deploy("postgresql-k8s", channel="14/stable", trust=True)
    juju.deploy(
        "nginx-ingress-integrator",
        channel="latest/stable",
        trust=True,
    )
    assert juju.model
    juju.config(
        "nginx-ingress-integrator",
        values={
            "path-routes": "/",
            "service-hostname": "maubot.local",
            "service-namespace": juju.model,
            "service-name": "maubot",
        },
    )
    juju.wait(jubilant.all_agents_idle, timeout=600)
    juju.integrate("maubot", "postgresql-k8s")
    juju.integrate("maubot", "nginx-ingress-integrator")
    juju.wait(jubilant.all_active, timeout=600)
    juju.wait(jubilant.all_agents_idle, timeout=600)

    response = requests.get(
        "http://127.0.0.1/_matrix/maubot/manifest.json",
        timeout=5,
        headers={"Host": "maubot.local"},
    )

    assert response.status_code == 200
    assert "Maubot Manager" in response.text
