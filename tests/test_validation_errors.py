from pydantic import ValidationError

from app.tools.validation import format_validation_error
from app.tools.schemas import ReadFileArgs


def test_validation_error_becomes_structured_observation() -> None:
    try:
        ReadFileArgs(path="app/main.py", max_bytes=-1)
    except ValidationError as error:
        observation = format_validation_error("read_file", error)

    assert observation["error_type"] == "tool_argument_validation"
    assert observation["tool_name"] == "read_file"
    assert len(observation["errors"]) == 1
    assert observation["errors"][0]["field"] == "max_bytes"
