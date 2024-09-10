#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests."""

import logging

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(
    ops_test: OpsTest,
    pytestconfig: pytest.Config,
):
    """
    arrange: set up the test Juju model.
    act: build and deploy the Maubot charm .
    assert: the Maubot charm becomes blocked (postgresql integration is required)
    """
    charm = pytestconfig.getoption("--charm-file")
    maubot_image = pytestconfig.getoption("--maubot-image")
    assert maubot_image
    if not charm:
        charm = await ops_test.build_charm(".")
    assert ops_test.model
    await ops_test.model.deploy(f"./{charm}", resources={"maubot-image": maubot_image})
    await ops_test.model.wait_for_idle(timeout=600, status="blocked")
