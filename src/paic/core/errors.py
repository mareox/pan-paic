"""Application-level exception hierarchy."""


class PAICError(Exception):
    """Base class for all PAIC errors."""


class ConfigError(PAICError):
    """Raised when configuration is missing or invalid."""
