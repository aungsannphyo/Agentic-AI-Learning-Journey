import json
from collections import Counter
from typing import Any


def call_fingerprint(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Stable string fingerprint; argument order does not matter."""
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{tool_name}:{canonical}"


class LoopGuard:
    """Blocks a tool call when the same call is made for the Nth time.

    block_on_nth_call=3 means the 1st and 2nd identical calls are allowed
    and the 3rd is blocked BEFORE execution.
    """

    def __init__(self, block_on_nth_call: int = 3) -> None:
        if block_on_nth_call < 1:
            raise ValueError("block_on_nth_call must be >= 1")

        self._block_on_nth_call = block_on_nth_call
        self._counts: Counter[str] = Counter()

    def record(self, fingerprint: str) -> bool:
        """Record a call. Returns True when this call must be blocked."""
        self._counts[fingerprint] += 1
        return self._counts[fingerprint] >= self._block_on_nth_call


class ConsecutiveCounter:
    """Counts consecutive failures; any success resets it.

    failure() returns True when the Nth consecutive failure is reached.
    """

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._limit = limit
        self._count = 0

    def failure(self) -> bool:
        self._count += 1
        return self._count >= self._limit

    def reset(self) -> None:
        self._count = 0
