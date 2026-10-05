from __future__ import annotations

import openai

from .retry import ErrorKind

_TRANSIENT: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def classify_llm_error(error: Exception) -> ErrorKind:
    """
    Map an LLM-call exception to a retry classification.

    Unknown errors are PERMANENT: retrying something we do not
    understand is worse than failing loudly.

    NOTE: APITimeoutError subclasses APIConnectionError in the SDK;
    both are listed explicitly so intent survives a refactor.
    """
    if isinstance(error, _TRANSIENT):
        return ErrorKind.TRANSIENT
    return ErrorKind.PERMANENT
