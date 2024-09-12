#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Maubot charm service."""

import logging
import typing

import ops
import yaml
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from ops import pebble

logger = logging.getLogger(__name__)

MAUBOT_SERVICE_NAME = "maubot"
MAUBOT_CONTAINER_NAME = "maubot"


class MissingPostgreSQLRelationDataError(Exception):
    """Custom exception to be raised in case of malformed/missing Postgresql relation data."""


class MaubotCharm(ops.CharmBase):
    """Maubot charm."""

    def __init__(self, *args: typing.Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.app.name
        )
        self.framework.observe(self.on.maubot_pebble_ready, self._on_maubot_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # Integrations events handlers
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(self.postgresql.on.endpoints_changed, self._on_endpoints_changed)

    def _configure_maubot(self, container: ops.Container) -> None:
        """Configure maubot.

        Args:
            container: Container of the charm.

        Raises:
            ExecError: something went wrong executing command.
            PathError: error while interacting with path.
        """
        commands = [
            ["cp", "--update=none", "/example-config.yaml", "/data/config.yaml"],
            ["mkdir", "-p", "/data/plugins", "/data/trash", "/data/dbs"],
        ]
        try:
            for command in commands:
                process = container.exec(command, combine_stderr=True)
                process.wait()
            config_content = str(container.pull("/data/config.yaml", encoding="utf-8").read())
            config = yaml.safe_load(config_content)
            config["database"] = self._get_postgresql_credentials()
            container.push("/data/config.yaml", yaml.safe_dump(config))
        except (ops.pebble.ExecError, ops.pebble.PathError) as exc:
            logger.exception("Failed to execute command: %r", exc)
            raise

    def _reconcile(self) -> None:
        """Reconcile workload configuration."""
        self.unit.status = ops.MaintenanceStatus()
        container = self.unit.get_container(MAUBOT_CONTAINER_NAME)
        if not container.can_connect():
            return
        try:
            self._configure_maubot(container)
        except MissingPostgreSQLRelationDataError:
            self.unit.status = ops.BlockedStatus("postgresql integration is required")
            return
        container.add_layer(MAUBOT_CONTAINER_NAME, self._pebble_layer, combine=True)
        container.replan()
        self.unit.status = ops.ActiveStatus()

    def _on_maubot_pebble_ready(self, _: ops.PebbleReadyEvent) -> None:
        """Handle maubot pebble ready event."""
        self._reconcile()

    def _on_config_changed(self, _: ops.ConfigChangedEvent) -> None:
        """Handle changed configuration."""
        self._reconcile()

    # Integrations events handlers
    def _on_database_created(self, _: DatabaseCreatedEvent) -> None:
        """Handle database created event."""
        self._reconcile()

    def _on_endpoints_changed(self, _: DatabaseEndpointsChangedEvent) -> None:
        """Handle endpoints changed event."""
        self._reconcile()

    # Relation data handlers
    def _get_postgresql_credentials(self) -> str:
        """Get postgresql credentials from the postgresql integration.

        Returns:
            postgresql credentials.

        Raises:
            MissingPostgreSQLRelationDataError: if relation is not found.
        """
        relation = self.model.get_relation("postgresql")
        if not relation or not relation.app:
            raise MissingPostgreSQLRelationDataError("No postgresql relation data")
        endpoints = self.postgresql.fetch_relation_field(relation.id, "endpoints")
        database = self.postgresql.fetch_relation_field(relation.id, "database")
        username = self.postgresql.fetch_relation_field(relation.id, "username")
        password = self.postgresql.fetch_relation_field(relation.id, "password")

        primary_endpoint = endpoints.split(",")[0]
        if not all((primary_endpoint, database, username, password)):
            raise MissingPostgreSQLRelationDataError("Missing mandatory relation data")
        return f"postgresql://{username}:{password}@{primary_endpoint}/{database}"

    # Properties
    @property
    def _pebble_layer(self) -> pebble.LayerDict:
        """Return a dictionary representing a Pebble layer."""
        return {
            "summary": "maubot layer",
            "description": "pebble config layer for maubot",
            "services": {
                MAUBOT_SERVICE_NAME: {
                    "override": "replace",
                    "summary": "maubot",
                    "command": "python3 -m maubot -c /data/config.yaml",
                    "startup": "enabled",
                    "working-dir": "/data",
                }
            },
        }


if __name__ == "__main__":  # pragma: nocover
    ops.main.main(MaubotCharm)
