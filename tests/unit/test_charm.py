# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Maubot module using testing."""

import re
from unittest.mock import MagicMock

import yaml
from ops import testing
from pytest import MonkeyPatch, mark, param

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


def test_delete_admin_action_success(base_state: dict):
    """
    arrange: prepare maubot container and add test admin with create-admin action.
    act: run delete-admin action.
    assert: test admin is not in config and no error is raised.
    """
    state = testing.State(**base_state)
    context = testing.Context(charm_type=MaubotCharm)

    _ = context.run(context.on.action("create-admin", {"name": "test"}), state)
    assert context.action_results is not None
    action_results: dict[str, str | bool] = context.action_results
    # action_results can also be None, so pylint complains even though it's checked
    assert "password" in action_results  # pylint: disable=unsupported-membership-test
    assert "error" not in action_results  # pylint: disable=unsupported-membership-test

    _ = context.run(context.on.action("delete-admin", {"name": "test"}), state)

    assert context.action_results is not None
    action_results = context.action_results
    # action_results can also be None, so pylint complains even though it's checked
    assert "error" not in action_results  # pylint: disable=unsupported-membership-test
    assert action_results["delete-admin"] is True  # pylint: disable=unsubscriptable-object

    # Test if actually not in config_data
    container_root_fs = list(base_state["containers"])[0].get_filesystem(context)
    config_file = container_root_fs / "data" / "config.yaml"
    with open(config_file, "r", encoding="utf-8") as file:
        config_data = yaml.safe_load(file)
    assert "test" not in config_data["admins"]


@mark.parametrize(
    "name,expected_message",
    [
        param("root", "root can not be deleted", id="root"),
        param("test", "test not found", id="user_not_found"),
    ],
)
def test_delete_admin_action_failure(name: str, expected_message: str, base_state: dict):
    """
    arrange: prepare maubot container.
    act: run delete-admin action.
    assert: no test user is found and returns error.
    """
    state = testing.State(**base_state)
    context = testing.Context(charm_type=MaubotCharm)

    try:
        _ = context.run(context.on.action("delete-admin", {"name": name}), state)
    except testing.ActionFailed:
        if isinstance(context.action_results, dict):
            # action_results can also be None, so pylint complains even though it's checked
            assert (
                context.action_results["error"]  # pylint: disable=unsubscriptable-object
                == expected_message
            )
            assert (
                context.action_results["delete-admin"]  # pylint: disable=unsubscriptable-object
                is False
            )


def test_path_error(base_state: dict):
    """
    arrange: prepare maubot container.
    act: run delete-admin action.
    assert: no test user is found and returns error.
    """
    container = list(base_state["containers"])[0]
    # mypy throws an error because it validates against ops.Container.
    modified_container = testing.Container(  # type: ignore[call-arg, attr-defined]
        name=container.name,
        can_connect=container.can_connect,
        execs=container.execs,
        mounts={},  # Empty mounts
        layers=container.layers,
        service_statuses=container.service_statuses,
    )
    state = testing.State(**{**base_state, "containers": {modified_container}})
    context = testing.Context(charm_type=MaubotCharm)

    try:
        _ = context.run(context.on.action("create-admin", {"name": "test"}), state)
    except testing.ActionFailed:
        if isinstance(context.action_results, dict):
            # action_results can also be None, so pylint complains even though it's checked
            assert (
                context.action_results["error"]  # pylint: disable=unsubscriptable-object
                == "Pushing changes to container failed. Check the logs for more info."
            )
