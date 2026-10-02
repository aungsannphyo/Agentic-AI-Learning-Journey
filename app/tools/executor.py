from time import perf_counter
from typing import Any

from .execution import ToolExecution
from .registry import ToolRegistry


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

        try:
            tool = self._registry.get(tool_name)

            result = tool.run(arguments)

            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=None,
                duration_ms=(
                    perf_counter() - started_at
                ) * 1000,
            )

        except Exception as exc:
            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
                duration_ms=(
                    perf_counter() - started_at
                ) * 1000,
            )
