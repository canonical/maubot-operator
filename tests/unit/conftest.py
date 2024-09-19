# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubotunit tests."""

import pytest
from ops.testing import Harness

from charm import MaubotCharm


@pytest.fixture(scope="function", name="harness")
def harness_fixture():
    """Enable ops test framework harness."""
    harness = Harness(MaubotCharm)
    harness.set_model_name("test")
    harness.handle_exec(
        "maubot",
        ["cp", "--update=none", "/example-config.yaml", "/data/config.yaml"],
        result=0,
    )
    harness.handle_exec(
        "maubot", ["mkdir", "-p", "/data/plugins", "/data/trash", "/data/dbs"], result=0
    )
    root = harness.get_filesystem_root("maubot")
    (root / "data").mkdir()
    (root / "data" / "config.yaml").write_text("database: sqlite:maubot.db")
    yield harness
    harness.cleanup()
