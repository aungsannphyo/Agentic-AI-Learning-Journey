import re

import openai

from .retry import ErrorKind

_TRANSIENT: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

_HINT = re.compile(
    r"try again in\s+(\d+(?:\.\d+)?(?:ms|s|m)(?:\s*\d+(?:\.\d+)?(?:ms|s|m))*)",
    re.IGNORECASE,
)
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0}


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


def _from_header(error: Exception) -> float | None:
    headers = getattr(getattr(error, "response", None), "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form is not supported
    return value if value >= 0 else None


def _from_message(error: Exception) -> float | None:
    match = _HINT.search(str(error))
    if match is None:
        return None
    parts = _PART.findall(match.group(1))
    if not parts:
        return None
    return sum(float(num) * _UNIT_SECONDS[unit] for num, unit in parts)


def retry_after_seconds(error: Exception) -> float | None:
    """Provider's own suggestion for how long to wait, if it gave one.

    Header first, then the "try again in 1m30.5s" phrase in the message.
    Returns None when neither is present or parseable.
    """
    header = _from_header(error)
    if header is not None:
        return header
    return _from_message(error)
