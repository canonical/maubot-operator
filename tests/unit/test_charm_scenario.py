# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the Maubot module using Scenario."""

import textwrap
from pathlib import Path

import ops
import pytest
import scenario
from scenario.context import _Event  # needed for custom events for now

from charm import MaubotCharm


@pytest.fixture(scope="function", name="base_state")
def base_state_fixture(tmp_path: Path):
    """State with container and config file set."""
    config_file_path = tmp_path / "config.yaml"
    config_file_path.write_text(
        textwrap.dedent(
            """
        databases: null
        server:
            public_url: maubot.local
        """
        ),
        encoding="utf-8",
    )
    yield {
        "leader": True,
        "containers": {
            scenario.Container(
                name="maubot",
                can_connect=True,
                execs={
                    scenario.Exec(
                        command_prefix=["cp"],
                        return_code=0,
                    ),
                    scenario.Exec(
                        command_prefix=["mkdir"],
                        return_code=0,
                    ),
                },
                mounts={
                    "data": scenario.Mount(location="/data/config.yaml", source=config_file_path)
                },
            )
        },
    }


def test_config_changed_no_postgresql(base_state: dict):
    """
    arrange: prepare maubot container.
    act: run config_changed.
    assert: status is blocked because there is no postgresql integration.
    """
    state = ops.testing.State(**base_state)
    context = ops.testing.Context(
        charm_type=MaubotCharm,
    )
    out = context.run(context.on.config_changed(), state)
    assert out.unit_status == ops.testing.BlockedStatus("postgresql integration is required")


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
    postgresql_relation = scenario.Relation(
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
    state = ops.testing.State(**base_state)
    context = ops.testing.Context(
        charm_type=MaubotCharm,
    )
    out = context.run(context.on.config_changed(), state)
    assert out.unit_status == ops.testing.ActiveStatus()
    container_root_fs = list(base_state["containers"])[0].get_filesystem(context)
    config_file = container_root_fs / "data" / "config.yaml"
    assert f"postgresql://{username}:{password}@{endpoints}/{database}" in config_file.read_text()


def test_postgresql_relation_departed(base_state: dict):
    """
    arrange: prepare maubot container.
    act: run config_changed.
    assert: status is blocked because there is no postgresql integration.
    """
    postgresql_relation = scenario.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
        remote_app_name="postgresql",
    )
    base_state["relations"] = [postgresql_relation]
    state = ops.testing.State(**base_state)
    context = ops.testing.Context(
        charm_type=MaubotCharm,
    )
    postgresql_relation_departed_event = _Event(
        "postgresql_relation_departed", relation=postgresql_relation
    )
    out = context.run(postgresql_relation_departed_event, state)
    assert out.unit_status == ops.testing.BlockedStatus("postgresql integration is required")
