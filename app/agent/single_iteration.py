import json
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor


class ToolCallingClient(Protocol):
    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        ...

    def continue_with_tool_outputs(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> Any:
        ...


def run_single_iteration(
    *,
    client: ToolCallingClient,
    executor: ToolExecutor,
    tools: list[Tool],
    user_prompt: str,
) -> Any:
    response, tool_calls = client.ask_with_tools(
        user_prompt=user_prompt,
        tools=tools,
    )

    if not tool_calls:
        return response

    conversation: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": user_prompt,
        },
        *response.output,
    ]

    for call in tool_calls:
        execution = executor.execute(
            tool_name=call.tool_name,
            arguments=call.arguments,
        )

        print(
            f"[Tool Call] "
            f"{call.tool_name}({call.arguments})"
        )

        if execution.success:
            print(f"[Tool Result] {execution.result}")
        else:
            print(f"[Tool Error] {execution.error}")

        conversation.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(
                    execution.result
                    if execution.success
                    else {
                        "error": execution.error,
                    }
                ),
            }
        )

    return client.continue_with_tool_outputs(
        conversation=conversation,
        tools=tools,
    )
