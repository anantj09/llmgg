import math


def estimate_tokens(text: str) -> int:
    """Rough fallback (~4 chars/token) when the provider doesn't report usage."""
    return max(1, math.ceil(len(text) / 4))


def estimate_cost(prompt_tokens: int, completion_tokens: int, per_1k_in: float, per_1k_out: float) -> float:
    return prompt_tokens / 1000 * per_1k_in + completion_tokens / 1000 * per_1k_out
