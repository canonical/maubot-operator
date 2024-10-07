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
from charms.synapse.v0.matrix_auth import MatrixAuthRequestProcessed, MatrixAuthRequires
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops import pebble

logger = logging.getLogger(__name__)

MAUBOT_NAME = "maubot"
NGINX_NAME = "nginx"


class MissingRelationDataError(Exception):
    """Custom exception to be raised in case of malformed/missing relation data."""

    def __init__(self, message: str, relation_name: str = "") -> None:
        """Init custom exception.

        Args:
            message: Exception message.
            relation_name: Relation name that raised the exception.
        """
        super().__init__(message)
        self.relation_name = relation_name


class MaubotCharm(ops.CharmBase):
    """Maubot charm."""

    def __init__(self, *args: typing.Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self.ingress = IngressPerAppRequirer(self, port=8080)
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.app.name
        )
        self.matrix_auth = MatrixAuthRequires(self)
        self.framework.observe(self.on.maubot_pebble_ready, self._on_maubot_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # Integrations events handlers
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(self.postgresql.on.endpoints_changed, self._on_endpoints_changed)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(
            self.matrix_auth.on.matrix_auth_request_processed,
            self._on_matrix_auth_request_processed,
        )

    def _configure_maubot(self, container: ops.Container) -> None:
        """Configure maubot.

        Args:
            container: Container of the charm.
        """
        commands = [
            ["cp", "--update=none", "/example-config.yaml", "/data/config.yaml"],
            ["mkdir", "-p", "/data/plugins", "/data/trash", "/data/dbs"],
        ]
        for command in commands:
            process = container.exec(command, combine_stderr=True)
            process.wait()
        config_content = str(container.pull("/data/config.yaml", encoding="utf-8").read())
        config = yaml.safe_load(config_content)
        config["database"] = self._get_postgresql_credentials()
        config["homeservers"] = self._get_matrix_credentials()
        config["server"]["public_url"] = self.config.get("public-url")
        container.push("/data/config.yaml", yaml.safe_dump(config))

    def _reconcile(self) -> None:
        """Reconcile workload configuration."""
        self.unit.status = ops.MaintenanceStatus()
        container = self.unit.get_container(MAUBOT_NAME)
        if not container.can_connect():
            return
        try:
            self._configure_maubot(container)
        except MissingRelationDataError as e:
            self.unit.status = ops.BlockedStatus(f"{e.relation_name} integration is required")
            try:
                container.stop(MAUBOT_NAME)
            except RuntimeError:
                logging.info("maubot is not running, no action taken")
            except ops.pebble.ChangeError as pe:
                logging.exception("failed to stop maubot", exc_info=pe)
            return
        container.add_layer(MAUBOT_NAME, self._pebble_layer, combine=True)
        container.restart(MAUBOT_NAME)
        container.restart(NGINX_NAME)
        self.unit.status = ops.ActiveStatus()

    def _on_maubot_pebble_ready(self, _: ops.PebbleReadyEvent) -> None:
        """Handle maubot pebble ready event."""
        self._reconcile()

    def _on_config_changed(self, _: ops.ConfigChangedEvent) -> None:
        """Handle changed configuration."""
        self._reconcile()

    # Integrations events handlers
    def _on_ingress_ready(self, _: IngressPerAppReadyEvent) -> None:
        """Handle ingress ready event."""
        self._reconcile()

    def _on_ingress_revoked(self, _: IngressPerAppRevokedEvent) -> None:
        """Handle ingress revoked event."""
        self._reconcile()

    def _on_database_created(self, _: DatabaseCreatedEvent) -> None:
        """Handle database created event."""
        self._reconcile()

    def _on_endpoints_changed(self, _: DatabaseEndpointsChangedEvent) -> None:
        """Handle endpoints changed event."""
        self._reconcile()

    def _on_matrix_auth_request_processed(self, _: MatrixAuthRequestProcessed) -> None:
        """Handle matrix auth request processed event."""
        self._reconcile()

    # Relation data handlers
    def _get_postgresql_credentials(self) -> str:
        """Get postgresql credentials from the postgresql integration.

        Returns:
            postgresql credentials.

        Raises:
            MissingRelationDataError: if relation is not found.
        """
        relation = self.model.get_relation("postgresql")
        if not relation or not relation.app:
            raise MissingRelationDataError(
                "No postgresql relation data", relation_name="postgresql"
            )
        endpoints = self.postgresql.fetch_relation_field(relation.id, "endpoints")
        database = self.postgresql.fetch_relation_field(relation.id, "database")
        username = self.postgresql.fetch_relation_field(relation.id, "username")
        password = self.postgresql.fetch_relation_field(relation.id, "password")

        if not endpoints:
            raise MissingRelationDataError(
                "Missing mandatory relation data", relation_name="postgresql"
            )
        primary_endpoint = endpoints.split(",")[0]
        if not all((primary_endpoint, database, username, password)):
            raise MissingRelationDataError(
                "Missing mandatory relation data", relation_name="postgresql"
            )
        return f"postgresql://{username}:{password}@{primary_endpoint}/{database}"

    def _get_matrix_credentials(self) -> dict[str, dict[str, str]]:
        """Get Matrix credentials from the matrix-auth integration.

        Returns:
            matrix credentials.

        Raises:
            MissingRelationDataError: if relation is not found.
        """
        relation = self.model.get_relation("matrix-auth")
        if not relation or not relation.app:
            logging.warning("no matrix-auth relation found, getting default matrix credentials")
            return {"matrix": {"url": "https://matrix-client.matrix.org", "secret": "null"}}
        relation_data = self.matrix_auth.get_remote_relation_data()
        homeserver = relation_data.homeserver
        shared_secret_id = relation_data.shared_secret.get_secret_value()
        if not all((homeserver, shared_secret_id)):
            raise MissingRelationDataError(
                "Missing mandatory relation data", relation_name="matrix-auth"
            )
        return {"synapse": {"url": homeserver, "secret": shared_secret_id}}

    # Properties
    @property
    def _pebble_layer(self) -> pebble.LayerDict:
        """Return a dictionary representing a Pebble layer."""
        return {
            "summary": "maubot layer",
            "description": "pebble config layer for maubot",
            "services": {
                NGINX_NAME: {
                    "override": "replace",
                    "summary": "nginx",
                    "command": "/usr/sbin/nginx",
                    "startup": "enabled",
                    "after": [MAUBOT_NAME],
                },
                MAUBOT_NAME: {
                    "override": "replace",
                    "summary": "maubot",
                    "command": "python3 -m maubot -c /data/config.yaml",
                    "startup": "enabled",
                    "working-dir": "/data",
                },
            },
        }


if __name__ == "__main__":  # pragma: nocover
    ops.main(MaubotCharm)
