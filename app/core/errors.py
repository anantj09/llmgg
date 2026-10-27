class GatewayError(Exception):
    """Base class for gateway errors."""


class PolicyError(GatewayError):
    """Raised when a guardrail policy is invalid."""


class UpstreamError(GatewayError):
    """Raised when the upstream LLM provider fails."""
