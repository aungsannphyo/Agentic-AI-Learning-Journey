from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from .schema_utils import strict_json_schema


class Tool(ABC):
    """Base abstraction for all agent tools.

    A tool declares its argument model ONCE (args_model). Both the
    model-facing JSON schema and runtime validation derive from it.
    """

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
    def args_model(self) -> type[BaseModel]:
        """Pydantic model describing and validating the tool's input."""
        raise NotImplementedError

    @property
    def input_schema(self) -> dict[str, Any]:
        """Model-facing JSON Schema, derived from args_model."""
        return strict_json_schema(self.args_model)

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
