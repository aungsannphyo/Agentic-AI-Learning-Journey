"""Extract visible reasoning text from provider output items.

Provider-specific on purpose: this is the only place that knows the
Responses-API 'reasoning' item shape. Output is untrusted, so every
access is defensive and the function never raises.
"""

from collections.abc import Iterable
from typing import Any


def extract_reasoning(items: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in items:
        if item.get("type") != "reasoning":
            continue
        for key in ("content", "summary"):
            blocks = item.get(key)
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                text = block.get("text") if isinstance(block, dict) else None
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    return "\n".join(parts)
