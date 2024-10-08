#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Maubot charm service."""

import logging
import secrets
import typing
from typing import Any, Dict

import ops
import requests
import yaml
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops import pebble

logger = logging.getLogger(__name__)

MAUBOT_CONFIGURATION_PATH = "/data/config.yaml"
MAUBOT_NAME = "maubot"
NGINX_NAME = "nginx"


class MissingPostgreSQLRelationDataError(Exception):
    """Custom exception to be raised in case of malformed/missing Postgresql relation data."""


class EventFailError(Exception):
    """Exception raised when an event fails."""


class MaubotCharm(ops.CharmBase):
    """Maubot charm."""

    def __init__(self, *args: typing.Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self.container = self.unit.get_container(MAUBOT_NAME)
        self.ingress = IngressPerAppRequirer(self, port=8080)
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.app.name
        )
        self.framework.observe(self.on.maubot_pebble_ready, self._on_maubot_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # Actions events handlers
        self.framework.observe(
            self.on.register_client_account_action, self._on_register_client_account_action
        )
        # Integrations events handlers
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(self.postgresql.on.endpoints_changed, self._on_endpoints_changed)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

    def _get_configuration(self) -> Dict[str, Any]:
        """Get Maubot configuration content.

        Returns:
            Maubot configuration file as a dict.
        """
        config_content = str(
            self.container.pull(MAUBOT_CONFIGURATION_PATH, encoding="utf-8").read()
        )
        return yaml.safe_load(config_content)

    def _configure_maubot(self) -> None:
        """Configure maubot."""
        commands = [
            ["cp", "--update=none", "/example-config.yaml", MAUBOT_CONFIGURATION_PATH],
            ["mkdir", "-p", "/data/plugins", "/data/trash", "/data/dbs"],
        ]
        for command in commands:
            process = self.container.exec(command, combine_stderr=True)
            process.wait()
        config = self._get_configuration()
        config["database"] = self._get_postgresql_credentials()
        config["server"]["public_url"] = self.config.get("public-url")
        self.container.push("/data/config.yaml", yaml.safe_dump(config))

    def _reconcile(self) -> None:
        """Reconcile workload configuration."""
        self.unit.status = ops.MaintenanceStatus()
        if not self.container.can_connect():
            return
        try:
            self._configure_maubot()
        except MissingPostgreSQLRelationDataError:
            self.unit.status = ops.BlockedStatus("postgresql integration is required")
            return
        self.container.add_layer(MAUBOT_NAME, self._pebble_layer, combine=True)
        self.container.restart(MAUBOT_NAME)
        self.container.restart(NGINX_NAME)
        self.unit.status = ops.ActiveStatus()

    def _on_maubot_pebble_ready(self, _: ops.PebbleReadyEvent) -> None:
        """Handle maubot pebble ready event."""
        self._reconcile()

    def _on_config_changed(self, _: ops.ConfigChangedEvent) -> None:
        """Handle changed configuration."""
        self._reconcile()

    # Actions events handlers
    def _on_register_client_account_action(self, event: ops.ActionEvent) -> None:
        """Handle register-client-account action.

        Matrix-auth integration required.

        Args:
            event: Action event.

        Raises:
            EventFailError: in case the event fails.
        """
        try:
            results: dict[str, str] = {
                "user-id": "",
                "password": "",
                "access-token": "",
                "device-id": "",
                "error": "",
            }
            if (
                not self.container.can_connect()
                or MAUBOT_NAME not in self.container.get_plan().services
                or not self.container.get_service(MAUBOT_NAME).is_running()
            ):
                raise EventFailError("maubot is not ready")
            # draft if no matrix-auth integration, fail
            admin_name = event.params["admin-name"]
            admin_password = event.params["admin-password"]
            config = self._get_configuration()
            if admin_name not in config["admins"]:
                raise EventFailError(f"{admin_name} not found in admin users")
            # Login in Maubot
            url = "http://localhost:29316/_matrix/maubot/v1/auth/login"
            payload = {"username": admin_name, "password": admin_password}
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            token = response.json().get("token")
            # Register Matrix Account
            account_name = event.params["account-name"]
            url = "http://localhost:29316/_matrix/maubot/v1/client/auth/synapse/register"
            password = secrets.token_urlsafe(10)
            payload = {"username": account_name, "password": password}
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            # Set results
            results["user-id"] = data.get("user_id")
            results["password"] = password
            results["access-token"] = data.get("access_token")
            results["device-id"] = data.get("device_id")
            event.set_results(results)
        except (EventFailError, requests.exceptions.RequestException, TimeoutError) as e:
            results["error"] = f"error while interacting with Maubot: {str(e)}"
            event.set_results(results)
            event.fail(f"error while interacting with Maubot: {str(e)}")

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

        if not endpoints:
            raise MissingPostgreSQLRelationDataError("Missing mandatory relation data")
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
