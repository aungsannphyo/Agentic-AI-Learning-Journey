from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base abstraction for all agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name exposed to the LLM."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Human/model-readable description of the tool."""
        raise NotImplementedError

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the tool's input."""
        raise NotImplementedError

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError

    def definition(self) -> dict[str, Any]:
        """Return provider-independent tool metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
