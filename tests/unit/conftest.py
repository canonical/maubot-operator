# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for the Maubot module using testing."""

import textwrap
from pathlib import Path
from secrets import token_hex

import pytest
from ops import pebble, testing


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
        admins:
            admin1: "2b$12$Rr4ZZctE6WATvCl/X7cmRuTJM3pS5hemqhkZWnl25bg1kQtqoQsVW"
            root: ""
        """
        ),
        encoding="utf-8",
    )
    layer_tmp = pebble.Layer(
        {
            "summary": "maubot layer",
            "description": "pebble config layer for maubot",
            "services": {
                "maubot": {},
            },
        }
    )
    yield {
        "leader": True,
        "containers": {
            # mypy throws an error because it validates against ops.Container.
            testing.Container(  # type: ignore[call-arg]
                name="maubot",
                can_connect=True,
                execs={
                    testing.Exec(
                        command_prefix=["cp"],
                        return_code=0,
                    ),
                    testing.Exec(
                        command_prefix=["mkdir"],
                        return_code=0,
                    ),
                },
                mounts={
                    "data": testing.Mount(location="/data/config.yaml", source=config_file_path)
                },
                layers={"mock-layer": layer_tmp},
            )
        },
    }


@pytest.fixture(name="matrix_auth_secret")
def matrix_auth_secret_fixture(matrix_auth_secret_id):
    """Matrix Auth secret fixture."""
    yield testing.Secret(
        id=matrix_auth_secret_id, tracked_content={"shared-secret-content": "abc"}
    )


@pytest.fixture(name="matrix_auth_secret_id")
def matrix_auth_secret_id_fixture():
    """Secret ID used by matrix-auth."""
    yield token_hex(16)


@pytest.fixture(name="matrix_auth_relation")
def matrix_auth_relation_fixture(matrix_auth_secret_id):
    """Matrix auth relation fixture."""
    yield testing.Relation(
        endpoint="matrix-auth",
        interface="matrix_auth",
        remote_app_name="synapse",
        remote_app_data={
            "homeserver": "https://test.com",
            "shared_secret_id": matrix_auth_secret_id,
        },
    )


@pytest.fixture(name="postgresql_relation")
def postgresql_relation_fixture():
    """Postgresql relation fixture."""
    relation_data = {
        "database": "maubot",
        "endpoints": "postgresql-k8s-primary.local:5432",
        "password": token_hex(16),
        "username": "user1",
    }
    yield testing.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
        remote_app_data=relation_data,
    )


@pytest.fixture(name="postgresql_empty_relation")
def postgresql_empty_relation_fixture():
    """Postgresql empty relation fixture."""
    yield testing.Relation(
        endpoint="postgresql",
        interface="postgresql_client",
    )
