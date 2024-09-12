# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=protected-access, duplicate-code

"""Unit tests."""

import ops
import ops.testing


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
    set_postgresql_integration(harness)
    expected_plan = {
        "services": {
            "maubot": {
                "override": "replace",
                "summary": "maubot",
                "command": "python3 -m maubot -c /data/config.yaml",
                "startup": "enabled",
                "working-dir": "/data",
            }
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
