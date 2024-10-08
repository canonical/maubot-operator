# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=protected-access, duplicate-code

"""Unit tests."""

import ops
import ops.testing
from charms.synapse.v0.matrix_auth import MatrixAuthProviderData


def set_postgresql_integration(harness) -> None:
    """Set postgresql integration.

    Args:
        harness: harness instance.
    """
    relation_data = {
        "database": "maubot",
        "endpoints": "dbhost:5432",
        "password": "somepasswd",  # nosec
        "username": "someuser",
    }
    db_relation_id = harness.add_relation(  # pylint: disable=attribute-defined-outside-init
        "postgresql", "postgresql"
    )
    harness.add_relation_unit(db_relation_id, "postgresql/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql",
        relation_data,
    )


def test_maubot_pebble_ready_postgresql_required(harness):
    """
    arrange: initialize the testing harness with handle_exec and
        config.yaml file.
    act: emit container pebble ready event.
    assert: Charm is blocked due to the missing PostgreSQL integration.
    """
    harness.begin_with_initial_hooks()

    harness.container_pebble_ready("maubot")

    assert harness.model.unit.status == ops.BlockedStatus("postgresql integration is required")


def test_maubot_pebble_ready(harness):
    """
    arrange: initialize the testing harness with handle_exec and
        config.yaml file.
    act: retrieve the pebble plan for maubot.
    assert: ensure the maubot pebble plan matches the expectations,
        the service is running and the charm is active.
    """
    harness.begin()
    harness.set_can_connect("maubot", True)
    set_postgresql_integration(harness)

    expected_plan = {
        "services": {
            "maubot": {
                "override": "replace",
                "summary": "maubot",
                "command": "python3 -m maubot -c /data/config.yaml",
                "startup": "enabled",
                "working-dir": "/data",
            },
            "nginx": {
                "override": "replace",
                "summary": "nginx",
                "command": "/usr/sbin/nginx",
                "startup": "enabled",
                "after": ["maubot"],
            },
        },
    }

    harness.container_pebble_ready("maubot")

    updated_plan = harness.get_container_pebble_plan("maubot").to_dict()
    assert expected_plan == updated_plan
    service = harness.model.unit.get_container("maubot").get_service("maubot")
    assert service.is_running()
    assert harness.model.unit.status == ops.ActiveStatus()


def test_database_created(harness):
    """
    arrange: initialize harness and verify that there is no credentials.
    act: set postgresql integration.
    assert: postgresql credentials are set as expected.
    """
    harness.begin_with_initial_hooks()

    set_postgresql_integration(harness)

    assert (
        harness.charm._get_postgresql_credentials()
        == "postgresql://someuser:somepasswd@dbhost:5432/maubot"
    )


def test_public_url_config_changed(harness, monkeypatch):
    """
    arrange: initialize harness and set postgresql integration.
    act: change public-url config.
    assert: charm is active.
    """
    harness.begin_with_initial_hooks()
    set_postgresql_integration(harness)
    set_matrix_auth_integration(harness, monkeypatch)

    harness.update_config({"public-url": "https://example1.com"})

    service = harness.model.unit.get_container("maubot").get_service("maubot")
    assert service.is_running()
    assert harness.model.unit.status == ops.ActiveStatus()


def test_matrix_credentials_registered(harness, monkeypatch):
    """
    arrange: initialize harness and verify that there is no credentials.
    act: set matrix-auth integration.
    assert: matrix credentials are set as expected.
    """
    harness.begin_with_initial_hooks()

    set_matrix_auth_integration(harness, monkeypatch)

    assert harness.charm._get_matrix_credentials() == {
        "synapse": {"secret": "test-shared-secret", "url": "https://example.com"}
    }


def set_matrix_auth_integration(harness, monkeypatch) -> None:
    """Set matrix-auth integration.

    Args:
        harness: harness instance.
        monkeypatch: monkeypatch instance.
    """
    monkeypatch.setattr(
        MatrixAuthProviderData, "get_shared_secret", lambda *args: "test-shared-secret"
    )
    relation_data = {"homeserver": "https://example.com", "shared_secret_id": "test-secret-id"}
    matrix_relation_id = harness.add_relation("matrix-auth", "synapse", app_data=relation_data)
    harness.add_relation_unit(matrix_relation_id, "synapse/0")
    harness.update_relation_data(
        matrix_relation_id,
        "synapse",
        relation_data,
    )
