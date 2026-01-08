# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for maubot unit tests."""

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
    yaml_content = """\
database: sqlite:maubot.db
server:
    hostname: 0.0.0.0
    port: 29316
    public_url: https://example.com
admins:
    root: ''
    admin1: $2b$12$Rr4ZZctE6WATvCl/X7cmRuTJM3pS5hemqhkZWnl25bg1kQtqoQsVW
"""
    (root / "data" / "config.yaml").write_text(yaml_content)
    yield harness
    harness.cleanup()
