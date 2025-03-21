# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Maubot module using testing."""

from unittest.mock import MagicMock

from charms.synapse.v0.matrix_auth import MatrixAuthRequires
from ops import testing
from pytest import MonkeyPatch

from charm import MaubotCharm


def test_config_changed_no_postgresql(base_state: dict):
    """
    arrange: prepare maubot container.
    act: run config_changed.
    assert: status is blocked because there is no postgresql integration.
    """
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )

    out = context.run(context.on.config_changed(), state)

    assert out.unit_status == testing.BlockedStatus("postgresql integration is required")


def test_config_changed_with_postgresql(base_state: dict):
    """
    arrange: prepare maubot container.
    act: run config_changed.
    assert: status is blocked because there is no postgresql integration.
    """
    endpoints = "1.2.3.4:5432"
    username = "user"
    password = "pass"  # nosec
    database = "maubot"
    postgresql_relation = testing.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
        remote_app_name="postgresql",
        remote_app_data={
            "endpoints": endpoints,
            "username": username,
            "password": password,
            "database": database,
        },
    )
    base_state["relations"] = [postgresql_relation]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )

    out = context.run(context.on.config_changed(), state)

    assert out.unit_status == testing.ActiveStatus()
    container_root_fs = list(base_state["containers"])[0].get_filesystem(context)
    config_file = container_root_fs / "data" / "config.yaml"
    assert f"postgresql://{username}:{password}@{endpoints}/{database}" in config_file.read_text()


def test_postgresql_relation_departed(base_state: dict):
    """
    arrange: prepare maubot container.
    act: emit postgresql relation departed event.
    assert: status is blocked because there is no postgresql integration.
    """
    postgresql_relation = testing.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
        remote_app_name="postgresql",
    )
    base_state["relations"] = [postgresql_relation]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )

    out = context.run(context.on.relation_departed(postgresql_relation), state)

    assert out.unit_status == testing.BlockedStatus("postgresql integration is required")


def test_matrix_auth_request_processed(base_state: dict, monkeypatch: MonkeyPatch):
    """
    arrange: prepare maubot container.
    act: trigger custom event matrix_auth_request_processed.
    assert: reconcile is called.
    """
    endpoints = "1.2.3.4:5432"
    username = "user"
    password = "pass"  # nosec
    database = "maubot"
    postgresql_relation = testing.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
        remote_app_name="postgresql",
        remote_app_data={
            "endpoints": endpoints,
            "username": username,
            "password": password,
            "database": database,
        },
    )
    base_state["relations"] = [postgresql_relation]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )
    reconcile_mock = MagicMock()
    monkeypatch.setattr("charm.MaubotCharm._reconcile", MagicMock())

    context.run(context.on.custom(MatrixAuthRequires.on.matrix_auth_request_processed), state)

    reconcile_mock.assert_called_once()
