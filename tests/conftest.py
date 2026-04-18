"""Shared pytest fixtures."""

import base64
import os


def pytest_configure(config: object) -> None:  # noqa: ARG001
    """Set required env vars before any test imports settings."""
    # 32 random bytes base64-encoded — valid PAIC_MASTER_KEY for tests
    key = base64.b64encode(bytes(range(32))).decode()
    os.environ.setdefault("PAIC_MASTER_KEY", key)
