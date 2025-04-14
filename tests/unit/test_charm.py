# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Maubot module using testing."""

import re
from unittest.mock import MagicMock

import yaml
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


def test_config_changed_with_postgresql(base_state: dict, postgresql_relation):
    """
    arrange: prepare maubot container.
    act: run config_changed.
    assert: status is blocked because there is no postgresql integration.
    """
    base_state["relations"] = [postgresql_relation]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )

    out = context.run(context.on.config_changed(), state)

    assert out.unit_status == testing.ActiveStatus()
    container_root_fs = list(base_state["containers"])[0].get_filesystem(context)
    config_file = container_root_fs / "data" / "config.yaml"
    pattern = r"postgresql:\/\/[^:]+:[^@]+@[^\/]+\/[^\/]+"
    assert re.search(pattern, config_file.read_text())


def test_postgresql_relation_departed(base_state: dict, postgresql_empty_relation):
    """
    arrange: prepare maubot container.
    act: emit postgresql relation departed event.
    assert: status is blocked because there is no postgresql integration.
    """
    base_state["relations"] = [postgresql_empty_relation]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )

    out = context.run(context.on.relation_departed(postgresql_empty_relation), state)

    assert out.unit_status == testing.BlockedStatus("postgresql integration is required")


def test_matrix_auth_request_processed(
    base_state: dict,
    monkeypatch: MonkeyPatch,
    postgresql_relation,
    matrix_auth_relation,
    matrix_auth_secret,
):
    """
    arrange: prepare maubot container.
    act: trigger custom event matrix_auth_request_processed.
    assert: reconcile is called.
    """
    base_state["relations"] = [postgresql_relation, matrix_auth_relation]
    base_state["secrets"] = [matrix_auth_secret]
    state = testing.State(**base_state)
    context = testing.Context(
        charm_type=MaubotCharm,
    )
    reconcile_mock = MagicMock()
    monkeypatch.setattr("charm.MaubotCharm._reconcile", reconcile_mock)

    context.run(context.on.relation_changed(matrix_auth_relation), state)

    reconcile_mock.assert_called_once()


def test_delete_admin_action_success(base_state: dict, monkeypatch: MonkeyPatch):
    """
    arrange: prepare maubot container and add test admin with create-admin action.
    act: run delete-admin action.
    assert: test admin is not in config and no error is raised.
    """
    state = testing.State(**base_state)
    context = testing.Context(charm_type=MaubotCharm)
    maubot_ready_mock = MagicMock(return_value=True)
    monkeypatch.setattr("charm.MaubotCharm._is_maubot_ready", maubot_ready_mock)

    state = context.run(context.on.action("create-admin", {"name": "test"}), state)
    assert "password" in context.action_results
    assert "error" not in context.action_results
    _ = context.run(context.on.action("delete-admin", {"name": "test"}), state)

    assert "error" not in context.action_results
    assert context.action_results["delete-user"] is True
    container_root_fs = list(base_state["containers"])[0].get_filesystem(context)
    config_file = container_root_fs / "data" / "config.yaml"
    with open(config_file, "r") as file:
        config_data = yaml.safe_load(file)
    assert "test" not in config_data["admins"]
