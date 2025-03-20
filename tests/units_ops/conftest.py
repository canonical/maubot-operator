# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for the Maubot module using testing."""

import textwrap
from pathlib import Path

import pytest
from ops import testing


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
            )
        },
    }
