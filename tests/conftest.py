"""Shared pytest fixtures."""


def pytest_configure(config: object) -> None:  # noqa: ARG001
    """Test environment setup hook.

    PAIC v0.2 needs no env defaults. Settings has sensible defaults for every
    field, but the hook stays so future shared setup has a home.
    """
