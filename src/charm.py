#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# Learn more at: https://juju.is/docs/sdk

"""Maubot charm service."""

import logging
import secrets
from typing import Any, Dict

import ops
import yaml
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.synapse.v0.matrix_auth import MatrixAuthRequestProcessed, MatrixAuthRequires
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from ops import pebble

logger = logging.getLogger(__name__)

BLACKBOX_NAME = "blackbox"
MAUBOT_CONFIGURATION_PATH = "/data/config.yaml"
MAUBOT_NAME = "maubot"
NGINX_NAME = "nginx"


class MissingRelationDataError(Exception):
    """Custom exception to be raised in case of malformed/missing relation data."""

    def __init__(self, message: str, relation_name: str) -> None:
        """Init custom exception.

        Args:
            message: Exception message.
            relation_name: Relation name that raised the exception.
        """
        super().__init__(message)
        self.relation_name = relation_name


class EventFailError(Exception):
    """Exception raised when an event fails."""


class MaubotCharm(ops.CharmBase):
    """Maubot charm."""

    def __init__(self, *args: Any):
        """Construct.

        Args:
            args: Arguments passed to the CharmBase parent constructor.
        """
        super().__init__(*args)
        self.container = self.unit.get_container(MAUBOT_NAME)
        self.grafana_dashboards = GrafanaDashboardProvider(self)
        self.ingress = IngressPerAppRequirer(self, port=8080)
        self._log_forwarder = LogForwarder(self)
        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=self._probes_scraping_job,
        )
        self.postgresql = DatabaseRequires(
            self, relation_name="postgresql", database_name=self.app.name
        )
        self.matrix_auth = MatrixAuthRequires(self)
        self.framework.observe(self.on.maubot_pebble_ready, self._on_maubot_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        # Actions events handlers
        self.framework.observe(self.on.create_admin_action, self._on_create_admin_action)
        # Integrations events handlers
        self.framework.observe(self.postgresql.on.database_created, self._on_database_created)
        self.framework.observe(self.postgresql.on.endpoints_changed, self._on_endpoints_changed)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(
            self.matrix_auth.on.matrix_auth_request_processed,
            self._on_matrix_auth_request_processed,
        )

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
        config["homeservers"] = self._get_matrix_credentials()
        config["server"]["public_url"] = self.config.get("public-url")
        self.container.push(MAUBOT_CONFIGURATION_PATH, yaml.safe_dump(config))

    def _reconcile(self) -> None:
        # Ignoring DC050 for now since RuntimeError is handled/re-raised only
        # because a Harness issue.
        """Reconcile workload configuration."""  # noqa: DCO050
        self.unit.status = ops.MaintenanceStatus()
        if not self.container.can_connect():
            return
        try:
            self._configure_maubot()
        except MissingRelationDataError as e:
            self.unit.status = ops.BlockedStatus(f"{e.relation_name} integration is required")
            try:
                self.container.stop(MAUBOT_NAME)
            except RuntimeError as re:
                if str(re) == '400 Bad Request: service "maubot" does not exist':
                    # Remove this once Harness is fixed
                    # See https://github.com/canonical/operator/issues/1310
                    pass
                else:
                    raise re
            except (ops.pebble.ChangeError, ops.pebble.APIError) as pe:
                logging.exception("failed to stop maubot", exc_info=pe)
            return
        self.container.add_layer(MAUBOT_NAME, self._pebble_layer, combine=True)
        self.container.restart(MAUBOT_NAME)
        self.container.restart(NGINX_NAME)
        self.container.restart(BLACKBOX_NAME)
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

    # Actions events handlers
    def _on_create_admin_action(self, event: ops.ActionEvent) -> None:
        """Handle delete-profile action.

        Args:
            event: Action event.

        Raises:
            EventFailError: in case the event fails.
        """
        try:
            name = event.params["name"]
            results = {"password": "", "error": ""}
            if name == "root":
                raise EventFailError("root is reserved, please choose a different name")
            if (
                not self.container.can_connect()
                or MAUBOT_NAME not in self.container.get_plan().services
                or not self.container.get_service(MAUBOT_NAME).is_running()
            ):
                raise EventFailError("maubot is not ready")
            password = secrets.token_urlsafe(10)
            config = self._get_configuration()
            if name in config["admins"]:
                raise EventFailError(f"{name} already exists")
            config["admins"][name] = password
            self.container.push(MAUBOT_CONFIGURATION_PATH, yaml.safe_dump(config))
            self.container.restart(MAUBOT_NAME)
            results["password"] = password
            event.set_results(results)
        except EventFailError as e:
            results["error"] = str(e)
            event.set_results(results)
            event.fail(str(e))

    # Integrations events handlers
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
        # pylint does not detect get_secret_value because it is dynamically created by pydantic
        shared_secret_id = (
            relation_data.shared_secret.get_secret_value()  # pylint: disable=no-member
        )
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
                BLACKBOX_NAME: {
                    "override": "replace",
                    "summary": "blackbox-exporter",
                    "command": "/usr/bin/blackbox_exporter --config.file=/etc/blackbox.yaml",
                    "startup": "enabled",
                },
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

    @property
    def _probes_scraping_job(self) -> list:
        """The scraping job to execute probes from Prometheus."""
        probe = {
            "job_name": "blackbox_maubot",
            "metrics_path": "/probe",
            "params": {"module": ["http_2xx"]},
            "static_configs": [{"targets": ["http://127.0.0.1:29316/_matrix/maubot/"]}],
        }
        unit_name = self.unit.name.replace("/", "-")
        app_name = self.app.name
        endpoint_address = f"{unit_name}.{app_name}-endpoints.{self.model.name}.svc.cluster.local"
        # The relabel configs come from the official Blackbox Exporter docs; please refer
        # to that for further information on what they do
        probe["relabel_configs"] = [
            {"source_labels": ["__address__"], "target_label": "__param_target"},
            {"source_labels": ["__param_target"], "target_label": "instance"},
            # Copy the scrape job target to an extra label for dashboard usage
            {"source_labels": ["__param_target"], "target_label": "probe_target"},
            # Set the address to scrape to the blackbox exporter url
            {"target_label": "__address__", "replacement": f"{endpoint_address}:9115"},
        ]

        return [probe]


if __name__ == "__main__":  # pragma: nocover
    ops.main(MaubotCharm)
