"""Importing this package registers every built-in guard with the registry."""

from app.guards import pii, secrets  # noqa: F401
