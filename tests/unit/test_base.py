# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more about testing at: https://juju.is/docs/sdk/testing

# pylint: disable=duplicate-code,missing-function-docstring
"""Unit tests."""

import unittest

import ops
import ops.testing

from charm import MaubotCharm


class TestCharm(unittest.TestCase):
    """Test class."""

    def setUp(self):
        """Set up the testing environment."""
        self.harness = ops.testing.Harness(MaubotCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_maubot_pebble_ready(self):
        """
        arrange: initialize the testing harness.
        act: retrieve the pebble plan for maubot.
        assert: ensure the maubot pebble plan matches the expectations,
            the service is running and the charm is active.
        """
        expected_plan = {
            "services": {
                "maubot": {
                    "override": "replace",
                    "summary": "maubot",
                    "command": 'bash -c "hello -t; sleep 10"',
                    "startup": "enabled",
                }
            },
        }

        self.harness.container_pebble_ready("maubot")

        updated_plan = self.harness.get_container_pebble_plan("maubot").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("maubot").get_service("maubot")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())
