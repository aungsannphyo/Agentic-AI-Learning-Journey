from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.tools import Tool

from .types import LLMResponse


class LLMClient(Protocol):
    """Provider-independent contract used by the agent loop.

    messages are provider-neutral (see app.llm.types message helpers).
    should_abort is consulted only by retry layers; plain provider
    clients accept and ignore it.
    """

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        ...
