"""Importing this package registers every built-in guard with the registry."""

from app.guards import keyword_policy, max_length, pii, prompt_injection, secrets  # noqa: F401
