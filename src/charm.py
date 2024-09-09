#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Maubot charm service."""

import logging
import typing

import ops
from ops import pebble

logger = logging.getLogger(__name__)

MAUBOT_SERVICE_NAME = "maubot"
MAUBOT_CONTAINER_NAME = "maubot"


class MaubotCharm(ops.CharmBase):
    """Maubot charm."""

    def __init__(self, *args: typing.Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self.framework.observe(self.on.maubot_pebble_ready, self._on_maubot_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_maubot_pebble_ready(self, _: ops.PebbleReadyEvent) -> None:
        """Handle maubot pebble ready event."""
        container = self.unit.get_container(MAUBOT_CONTAINER_NAME)
        if not container.can_connect():
            return
        container.add_layer(MAUBOT_CONTAINER_NAME, self._pebble_layer, combine=True)
        container.replan()
        self.unit.status = ops.ActiveStatus()

    def _on_config_changed(self, _: ops.ConfigChangedEvent) -> None:
        """Handle changed configuration."""
        self.unit.status = ops.MaintenanceStatus()
        container = self.unit.get_container(MAUBOT_CONTAINER_NAME)
        if not container.can_connect():
            return
        container.add_layer(MAUBOT_SERVICE_NAME, self._pebble_layer, combine=True)
        container.replan()
        self.unit.status = ops.ActiveStatus()

    @property
    def _pebble_layer(self) -> pebble.LayerDict:
        """Return a dictionary representing a Pebble layer."""
        return {
            "summary": "maubot layer",
            "description": "pebble config layer for httpbin",
            "services": {
                MAUBOT_SERVICE_NAME: {
                    "override": "replace",
                    "summary": "maubot",
                    "command": "bash -c \"python3 -c 'import maubot'; sleep 10\"",
                    "startup": "enabled",
                }
            },
        }


if __name__ == "__main__":  # pragma: nocover
    ops.main.main(MaubotCharm)
