from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .execution import ToolExecution
from .registry import ToolRegistry
from .validation import format_validation_error_json


class ToolExecutor:
    """Executes registered tools and records execution metadata."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        started_at = perf_counter()

        def elapsed_ms() -> float:
            return (perf_counter() - started_at) * 1000

        try:
            tool = self._registry.get(tool_name)

            try:
                validated = tool.args_model.model_validate(
                    arguments
                ).model_dump()
            except ValidationError as exc:
                return ToolExecution(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=None,
                    error=format_validation_error_json(tool_name, exc),
                    duration_ms=elapsed_ms(),
                )

            result = tool.run(validated)

            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=None,
                duration_ms=elapsed_ms(),
            )

        except Exception as exc:  # noqa: BLE001
            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
                duration_ms=elapsed_ms(),
            )
