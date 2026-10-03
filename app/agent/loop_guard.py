import json
from collections import Counter
from typing import Any


def call_fingerprint(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Return a stable string fingerprint for a tool call.

    Argument order is normalised so that two dicts with
    the same keys/values always produce the same fingerprint.
    """
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{tool_name}:{canonical}"


class LoopGuard:
    def __init__(
        self,
        max_repeated_calls: int = 3,
    ) -> None:
        if max_repeated_calls < 1:
            raise ValueError(
                "max_repeated_calls must be >= 1"
            )

        self._max_repeated_calls = (
            max_repeated_calls
        )

        self._counts: Counter[str] = Counter()

    def record(self, fingerprint: str) -> bool:
        """
        Record a call fingerprint.

        Returns True when the repetition limit
        has been reached.
        """

        self._counts[fingerprint] += 1

        return (
            self._counts[fingerprint]
            >= self._max_repeated_calls
        )
