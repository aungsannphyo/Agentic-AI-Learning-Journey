from typing import Any

from pydantic import BaseModel


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Build a provider-strict JSON schema from a Pydantic model.

    Strict function-calling modes generally require:
    - additionalProperties: false
    - every property listed in `required`
    - no `title` / `default` noise

    NOTE: exact provider rules vary; verify against Groq docs.
    Nested models ($defs) are intentionally unsupported for now.
    """
    raw = model.model_json_schema()

    if "$defs" in raw:
        raise ValueError(
            f"{model.__name__}: nested models are not supported "
            "by strict_json_schema yet"
        )

    properties: dict[str, Any] = {}
    for name, spec in raw.get("properties", {}).items():
        cleaned = {
            k: v for k, v in spec.items() if k not in ("title", "default")
        }
        properties[name] = cleaned

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }
