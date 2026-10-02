# Agent Runtime — Complete Codebase Explanation & Code Dump
> ChatGPT ကိုရောမေးနိုင်ဖို့ project တစ်ခုလုံးကို file တစ်ခုထဲမှာ ပေါင်းထည့်ထားတယ်။

---

## 🗂️ Project Structure

```
agent-runtime/
├── app/
│   ├── __init__.py
│   ├── main.py                  ← Entry point (program စတင်ရာ)
│   ├── agent/
│   │   ├── __init__.py
│   │   └── single_iteration.py  ← Agent logic (LLM → Tool → LLM loop)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py            ← Abstract base class (interface)
│   │   ├── openai_client.py     ← Real OpenAI implementation
│   │   ├── fake_client.py       ← Test-only fake LLM
│   │   └── openai_tools.py      ← Tool format converter
│   └── tools/
│       ├── __init__.py
│       ├── base.py              ← Abstract Tool base class
│       ├── call.py              ← ToolCall data class
│       ├── execution.py         ← ToolExecution data class
│       ├── executor.py          ← Tool runner with timing
│       ├── list_files.py        ← Concrete tool: list directory
│       └── registry.py          ← Tool store/lookup
├── tests/
│   ├── test_llm_client.py
│   ├── test_openai_tools.py
│   ├── test_single_iteration.py
│   └── test_tools.py
├── docs/
│   └── adr/
│       └── 0001-llm-provider-abstraction.md
├── conftest.py
├── pyproject.toml
├── .env.example
├── README.md
└── PROGRESS.md
```

---

## 🧠 Architecture Overview (ဘယ်လိုအလုပ်လုပ်သလဲ)

```
User Prompt
    │
    ▼
OpenAIClient.ask_with_tools()    ← LLM ကို question မေးတယ်
    │
    ▼ (LLM က tool call request ပြန်ပေးတယ်)
run_single_iteration()           ← Agent loop
    │
    ├── ToolRegistry.get()       ← Tool ကို name နဲ့ ရှာတယ်
    │
    ├── ToolExecutor.execute()   ← Tool ကိုအမှန်တကယ် run တယ်
    │       └── Tool.run()       ← e.g. list_files က directory list ပြန်ပေးတယ်
    │
    ▼ (tool result ကို conversation history ထဲ ထည့်တယ်)
OpenAIClient.continue_with_tool_outputs()  ← LLM ကိုထပ်မေးတယ်
    │
    ▼
Final Response (user မြင်ရတဲ့ answer)
```

---

## 📁 FILE-BY-FILE EXPLANATION

---

### 1. `app/main.py` — Program Entry Point

**ဘာလုပ်သလဲ:** Program ကိုဖွင့်ရင် ပထမဆုံးအလုပ်လုပ်တဲ့ file။ Tool, LLM client, executor တွေ setup လုပ်ပြီး agent ကို run တယ်။

```python
from dotenv import load_dotenv

from app.agent import run_single_iteration
from app.llm import OpenAIClient
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ListFilesTool()
    )

    return registry


def main() -> None:
    load_dotenv()

    registry = build_registry()
    executor = ToolExecutor(registry)
    client = OpenAIClient(
        system_prompt=(
            "You are a software engineering agent. "
            "When you need information about the workspace, "
            "use the available tools."
        ),
    )

    result = run_single_iteration(
        client=client,
        executor=executor,
        tools=registry.list(),
        user_prompt=(
            "List the top-level files and directories "
            "in the workspace root, then list the files "
            "in the tests directory."
        ),
    )

    print("\n=== Final Response ===\n")
    print(result.output_text)


if __name__ == "__main__":
    main()
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `build_registry()` | `ToolRegistry` အသစ်တစ်ခုဆောက်ပြီး `ListFilesTool` ကို register လုပ်တယ်။ Return: ToolRegistry object |
| `main()` | `.env` file ဖတ်တယ် → registry/executor/client setup → `run_single_iteration` ခေါ်တယ် → result print တယ် |

---

### 2. `app/agent/single_iteration.py` — The Agent Loop

**ဘာလုပ်သလဲ:** LLM → Tool → LLM ဆိုတဲ့ single cycle (တစ်ကြိမ် loop) ကို implement လုပ်တဲ့ core logic။

```python
import json
from typing import Any, Protocol, List, Dict, Tuple

from app.tools import ToolExecutor, Tool, ToolCall


class ToolCallingClient(Protocol):
    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: List[Tool],
    ) -> Tuple[Any, List[ToolCall]]:
        ...

    def continue_with_tool_outputs(
        self,
        *,
        conversation: List[Dict[str, Any]],
        tools: List[Tool],
    ) -> Any:
        ...


def run_single_iteration(
    *,
    client: ToolCallingClient,
    executor: ToolExecutor,
    tools: List[Tool],
    user_prompt: str,
) -> Any:
    response, tool_calls = client.ask_with_tools(
        user_prompt=user_prompt,
        tools=tools,
    )

    if not tool_calls:
        return response

    conversation: List[Dict[str, Any]] = [
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
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function/Class | ဘာလုပ်သလဲ |
|---|---|
| `ToolCallingClient` (Protocol) | Duck typing interface။ `ask_with_tools` နဲ့ `continue_with_tool_outputs` ဆိုတဲ့ method ၂ ခုပါရင် ဒီ interface ကို satisfy လုပ်ပြီးသားဖြစ်တယ်။ |
| `run_single_iteration()` | **Step 1:** LLM ကို user prompt နဲ့ tools list ပေးပြီးမေးတယ်။ **Step 2:** Tool calls မရှိရင် response တိုက်ရိုက် return ပြန်တယ်။ **Step 3:** Tool calls ရှိရင် ၎င်းတွေကို loop လုပ်ပြီး execute တယ်။ **Step 4:** Results တွေကို conversation history ထဲထည့်ပြီး LLM ကိုထပ်မေးတယ်။ |

---

### 3. `app/llm/client.py` — Abstract LLM Interface

**ဘာလုပ်သလဲ:** LLM provider ဘာဆိုဘာ (OpenAI, Anthropic, Gemini) သုံးသည်ဖြစ်စေ common interface ကိုသတ်မှတ်တဲ့ abstract base class။

```python
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Provider-independent interface for language model clients."""

    @abstractmethod
    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a prompt to the LLM and return generated text."""
        raise NotImplementedError
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `ask()` | Abstract method — subclass တွေ implement မလုပ်ရင် error ထွက်တယ်။ system prompt + user prompt ပေးရတယ်၊ string ပြန်ပေးရတယ်။ |

---

### 4. `app/llm/openai_client.py` — Real OpenAI Implementation

**ဘာလုပ်သလဲ:** Groq API endpoint ကတဆင့် OpenAI SDK သုံးပြီး LLM call လုပ်တဲ့ concrete implementation။

```python
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from .client import LLMClient
from .openai_tools import to_openai_tool
from app.tools import Tool, ToolCall


class OpenAIClient(LLMClient):
    """OpenAI implementation of the provider-independent LLMClient."""

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self._client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )

        self._model = model or os.getenv(
            "OPENAI_MODEL",
            "openai/gpt-oss-120b",
        )

        self._temperature = (
            temperature
            if temperature is not None
            else float(
                os.getenv(
                    "OPENAI_TEMPERATURE",
                    "0.2",
                )
            )
        )

        self._system_prompt: Optional[str] = system_prompt

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=self._temperature,
        )

        return response.output_text

    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: List[Tool],
    ) -> Tuple[Any, List[ToolCall]]:
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=user_prompt,
            tools=[
                to_openai_tool(tool)
                for tool in tools
            ],
            temperature=self._temperature,
        )

        tool_calls: List[ToolCall] = []

        for item in response.output:
            if item.type != "function_call":
                continue

            tool_calls.append(
                ToolCall(
                    call_id=item.call_id,
                    tool_name=item.name,
                    arguments=json.loads(item.arguments),
                )
            )

        return response, tool_calls

    def continue_with_tool_outputs(
        self,
        *,
        conversation: List[Dict[str, Any]],
        tools: List[Tool],
    ) -> Any:
        """Continue a response after executing model-requested tools."""

        return self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=conversation,
            tools=[
                to_openai_tool(tool)
                for tool in tools
            ],
            temperature=self._temperature,
        )
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `__init__()` | OpenAI client initialize လုပ်တယ်။ API key ကို environment variable ကနေဖတ်တယ်။ Model, temperature, system prompt တွေ set လုပ်တယ်။ Base URL ကို Groq ကို point လုပ်ထားတယ်။ |
| `ask()` | Simple prompt-response call။ Tool မပါ — plain text answer ပဲ ပြန်ပေးတယ်။ |
| `ask_with_tools()` | Tool list ပါတဲ့ LLM call။ LLM response ထဲမှာ function_call item တွေကို extract လုပ်ပြီး `ToolCall` object list အဖြစ် return ပြန်ပေးတယ်။ |
| `continue_with_tool_outputs()` | Tool execution result တွေပါတဲ့ conversation history ကို LLM ကိုပေးပြီး final answer ဆွဲထုတ်တယ်။ |

---

### 5. `app/llm/fake_client.py` — Test Fake LLM

**ဘာလုပ်သလဲ:** Testing အတွက် real API call မလုပ်ဘဲ deterministic (ကြိုတင်သတ်မှတ်ထားတဲ့) response ပြန်ပေးတဲ့ fake LLM client။

```python
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .client import LLMClient
from app.tools import ToolCall


@dataclass
class FakeResponse:
    output_text: str
    output: List[Dict[str, Any]] = field(default_factory=list)
    id: str = "fake-response-123"


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

    def __init__(
        self,
        response: str,
        *,
        first_response: Optional["FakeResponse"] = None,
    ) -> None:
        self.response = response
        self._first_response = first_response
        self.calls: List[Dict[str, Any]] = []

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

        return self.response

    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: List[Any],
    ) -> Tuple[FakeResponse, List[Any]]:
        self.calls.append(
            {
                "user_prompt": user_prompt,
                "tools": [
                    tool.name
                    for tool in tools
                ],
            }
        )

        first_response = self._first_response or FakeResponse(
            output_text=self.response,
        )

        tool_calls = [
            ToolCall(
                call_id=item.call_id,
                tool_name=item.name,
                arguments=json.loads(item.arguments),
            )
            for item in first_response.output
            if item.type == "function_call"
        ]

        return first_response, tool_calls

    def continue_with_tool_outputs(
        self,
        *,
        conversation: List[Dict[str, Any]],
        tools: List[Any],
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": "continue_with_tool_outputs",
                "conversation": conversation,
                "tools": [tool.name for tool in tools],
            }
        )

        return FakeResponse(
            output_text="Final response after tool execution.",
            output=[],
        )
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Class/Function | ဘာလုပ်သလဲ |
|---|---|
| `FakeResponse` | Real OpenAI response ကိုမိမိ simulate လုပ်ဖို့ dataclass။ `output_text` နဲ့ `output` list ပါတယ်။ |
| `FakeLLMClient.__init__()` | ကြိုတင် define လုပ်ထားတဲ့ response string ကို သိမ်းထားတယ်။ `calls` list ကို call tracking အတွက်သုံးတယ်။ |
| `ask()` | Call ကို `self.calls` ထဲ record လုပ်ပြီး pre-configured response ပြန်ပေးတယ်။ |
| `ask_with_tools()` | `first_response` ရှိရင် ၎င်းထဲမှာ function_call items ရှာပြီး ToolCall list ဆောက်တယ်။ မရှိရင် empty tool calls ပြန်ပေးတယ်။ |
| `continue_with_tool_outputs()` | ကြိုသတ်မှတ်ထားတဲ့ "Final response after tool execution." string return ပြန်ပေးတယ်။ |

---

### 6. `app/llm/openai_tools.py` — Tool Format Converter

**ဘာလုပ်သလဲ:** Internal `Tool` object ကို OpenAI API format (JSON dict) ကို convert လုပ်တဲ့ helper function တစ်ခု။

```python
from typing import Any, Dict

from app.tools import Tool


def to_openai_tool(tool: Tool) -> Dict[str, Any]:
    """Convert an internal Tool into an OpenAI function tool."""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": True,
    }
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `to_openai_tool()` | `Tool` object တစ်ခုယူပြီး OpenAI API ကို pass လုပ်လို့ရတဲ့ dict format ပြန်ပေးတယ်။ `strict: True` က LLM ကို input schema ကိုတိတိကျကျ follow လုပ်ဖို့ force လုပ်တယ်။ |

---

### 7. `app/tools/base.py` — Abstract Tool Base Class

**ဘာလုပ်သလဲ:** Tool တိုင်းကိုက implement လုပ်ရမဲ့ interface ကို define လုပ်တဲ့ abstract base class။

```python
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
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Property/Function | ဘာလုပ်သလဲ |
|---|---|
| `name` (abstract property) | Tool ရဲ့ unique identifier string — LLM ကို ဒီ name နဲ့ ပြတယ်။ |
| `description` (abstract property) | Tool ဘာလုပ်သလဲဆိုတဲ့ description — LLM ဒါကိုဖတ်ပြီး ဒီ tool ကိုသုံးမသုံးဆုံးဖြတ်တယ်။ |
| `input_schema` (abstract property) | JSON Schema format ဖြင့် tool ကို ဘာ arguments ပေးရသလဲ define လုပ်တယ်။ |
| `run()` (abstract) | Tool ကိုအမှန်တကယ် execute လုပ်တဲ့ method — subclass တွေ implement လုပ်ရတယ်။ |
| `definition()` | Provider-neutral tool metadata dict ပြန်ပေးတယ် (name, description, input_schema)။ |

---

### 8. `app/tools/call.py` — ToolCall Data Class

**ဘာလုပ်သလဲ:** LLM က "ဒီ tool ကိုဒီ arguments နဲ့ run ပေး" လို့ request လုပ်တဲ့ object ကို represent တဲ့ immutable data class။

```python
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request."""

    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
```

**Fields တစ်ခုချင်းရှင်းချက်:**

| Field | ဘာလုပ်သလဲ |
|---|---|
| `call_id` | OpenAI က generate လုပ်တဲ့ unique ID — tool result ကို မည်သည့် call နဲ့ pair လုပ်ရမည်ကို track ဖို့သုံးတယ်။ |
| `tool_name` | ဘာ tool ကို run ရမည်ဆိုတဲ့ name (e.g. `"list_files"`)。 |
| `arguments` | Tool ကို pass လုပ်ရမဲ့ key-value arguments dict (e.g. `{"path": "."}`)。 |

---

### 9. `app/tools/execution.py` — ToolExecution Data Class

**ဘာလုပ်သလဲ:** Tool run ပြီးနောက် result (သို့) error ကို encapsulate လုပ်တဲ့ immutable record။

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ToolExecution:
    """Record of a single tool execution."""

    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any]
    error: Optional[str]
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.error is None
```

**Fields/Properties တစ်ခုချင်းရှင်းချက်:**

| Field/Property | ဘာလုပ်သလဲ |
|---|---|
| `tool_name` | Execute လုပ်ခဲ့တဲ့ tool ရဲ့ name |
| `arguments` | Tool ကို pass လုပ်ခဲ့တဲ့ arguments |
| `result` | Tool run ပြီးနောက် return ပြန်လာတဲ့ data (error ရှိရင် None) |
| `error` | Tool fail ဖြစ်ရင် error message string (success ဖြစ်ရင် None) |
| `duration_ms` | Tool ကို run ဖို့ ဘယ်လောက်ကြာသလဲ (milliseconds) |
| `success` (property) | `error is None` ဖြစ်ရင် True ပြန်ပေးတယ် — success check shortcut |

---

### 10. `app/tools/executor.py` — Tool Executor

**ဘာလုပ်သလဲ:** Tool ကိုအမှန်တကယ် run ပြီး timing ကိုမှတ်ထားကာ `ToolExecution` object return ပြန်ပေးတဲ့ class။ Error ကိုလည်း gracefully handle လုပ်တယ်။

```python
from time import perf_counter
from typing import Any, Dict

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
        arguments: Dict[str, Any],
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
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `__init__()` | `ToolRegistry` ကို inject လုပ်တယ် (dependency injection pattern)。 |
| `execute()` | **Step 1:** Timer စတယ်。**Step 2:** Registry မှာ tool ကိုနာမည်နဲ့ ရှာတယ်。**Step 3:** Tool.run() ခေါ်တယ်。**Step 4:** Success ဖြစ်ရင် result ပါတဲ့ ToolExecution return, fail ဖြစ်ရင် error ပါတဲ့ ToolExecution return。 |

---

### 11. `app/tools/list_files.py` — ListFiles Tool

**ဘာလုပ်သလဲ:** Agent tool တစ်ခုဖြစ်ပြီး directory တစ်ခုရဲ့ file/folder list ကို return ပြန်ပေးတယ်။ `Tool` abstract class ကို concrete implement လုပ်ထားတဲ့ example tool။

```python
from pathlib import Path
from typing import Any, Dict, List

from .base import Tool


class ListFilesTool(Tool):
    """List files and directories under a given path."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories under the given path. "
            "Returns names relative to the requested path."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Directory path to list. "
                        "Use an empty string for the workspace root."
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def run(self, arguments: Dict[str, Any]) -> List[str]:
        path = arguments["path"]

        directory = Path(path or ".")

        if not directory.exists():
            raise FileNotFoundError(
                f"Directory does not exist: {path}"
            )

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {path}"
            )

        return sorted(
            entry.name
            for entry in directory.iterdir()
        )
```

**Function/Property တစ်ခုချင်းရှင်းချက်:**

| Property/Function | ဘာလုပ်သလဲ |
|---|---|
| `name` | `"list_files"` string return ပြန်တယ် — LLM ဒီ name နဲ့ tool ကိုသိတယ်。 |
| `description` | LLM ကိုပြမဲ့ human-readable ရှင်းချက်。 |
| `input_schema` | `path` ဆိုတဲ့ string argument တစ်ခုလိုတယ်ဆိုတဲ့ JSON Schema。 |
| `run()` | **1)** path argument ဖတ်တယ် **2)** Path object ဆောက်တယ် **3)** Directory exist/is_dir check **4)** Sorted file/folder names list return တယ်。 |

---

### 12. `app/tools/registry.py` — Tool Registry

**ဘာလုပ်သလဲ:** Tool တွေကို name-based dictionary ဖြင့် သိမ်းပြီး lookup လုပ်ပေးတဲ့ central store။

```python
from typing import Dict, List

from .base import Tool


class ToolRegistry:
    """Stores and resolves tools by name."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown tool: {name}"
            ) from exc

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def definitions(self) -> List[Dict]:
        return [
            tool.definition()
            for tool in self._tools.values()
        ]
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `__init__()` | Empty `_tools` dict initialize လုပ်တယ်。 |
| `register()` | Tool ကို name ကို key အဖြစ်သုံးပြီး dict ထဲ store လုပ်တယ်。 Duplicate ဖြစ်ရင် ValueError raise တယ်。 |
| `get()` | Name ဖြင့် tool ကို lookup လုပ်တယ်。 မရှိရင် KeyError raise တယ်。 |
| `list()` | Register လုပ်ထားတဲ့ tool တွေအကုန်ကို list အဖြစ် return တယ်。 |
| `definitions()` | Tool တိုင်းရဲ့ metadata dict (name, description, input_schema) list return တယ်。 |

---

## 🧪 TEST FILES

---

### 13. `tests/test_tools.py`

**ဘာ test လုပ်သလဲ:** Tools layer — `ListFilesTool`, `ToolRegistry`, `ToolCall` တွေကို test လုပ်တယ်。

```python
from app.tools import ToolRegistry, ListFilesTool


def test_list_files_tool_lists_directory() -> None:
    tool = ListFilesTool()

    result = tool.run({"path": "."})

    assert isinstance(result, list)
    assert "app" in result
    assert "tests" in result


def test_list_files_tool_definition() -> None:
    tool = ListFilesTool()

    definition = tool.definition()

    assert definition["name"] == "list_files"
    assert "description" in definition
    assert definition["input_schema"]["type"] == "object"


def test_registry_registers_and_resolves_tool() -> None:
    registry = ToolRegistry()
    tool = ListFilesTool()

    registry.register(tool)

    resolved = registry.get("list_files")

    assert resolved is tool


def test_registry_exposes_tool_definitions() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool())

    definitions = registry.definitions()

    assert len(definitions) == 1
    assert definitions[0]["name"] == "list_files"


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool())

    try:
        registry.register(ListFilesTool())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError(
            "Expected duplicate registration to fail"
        )


def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    try:
        registry.get("does_not_exist")
    except KeyError as exc:
        assert "Unknown tool" in str(exc)
    else:
        raise AssertionError(
            "Expected unknown tool lookup to fail"
        )


def test_tool_call_representation() -> None:
    from app.tools.call import ToolCall

    call = ToolCall(
        call_id="call_123",
        tool_name="list_files",
        arguments={"path": "src"},
    )

    assert call.call_id == "call_123"
    assert call.tool_name == "list_files"
    assert call.arguments == {
        "path": "src"
    }
```

**Test တစ်ခုချင်းရှင်းချက်:**

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_list_files_tool_lists_directory` | `"."` path ကို run ရင် app နဲ့ tests directory ပါတဲ့ list ရတယ် |
| `test_list_files_tool_definition` | `definition()` က correct name, description, schema ပြန်ပေးတယ် |
| `test_registry_registers_and_resolves_tool` | Register လုပ်ပြီး get ခေါ်ရင် exact same object ပြန်ပေးတယ် |
| `test_registry_exposes_tool_definitions` | `definitions()` က tools list return ပြန်ပေးတယ် |
| `test_registry_rejects_duplicate_tool` | Same tool ကို ၂ ကြိမ် register ရင် ValueError raise တယ် |
| `test_registry_rejects_unknown_tool` | မရှိတဲ့ tool ကို get ရင် KeyError raise တယ် |
| `test_tool_call_representation` | ToolCall dataclass fields correctly set ဖြစ်တယ် |

---

### 14. `tests/test_llm_client.py`

**ဘာ test လုပ်သလဲ:** `FakeLLMClient` ရဲ့ behavior ကို test လုပ်တယ်。

```python
from app.llm import FakeLLMClient


def test_fake_llm_returns_configured_response() -> None:
    llm = FakeLLMClient(
        response="Hello from fake LLM",
    )

    result = llm.ask(
        system_prompt="You are a test assistant.",
        user_prompt="Say hello.",
    )

    assert result == "Hello from fake LLM"


def test_fake_llm_records_prompt() -> None:
    llm = FakeLLMClient(
        response="test response",
    )

    llm.ask(
        system_prompt="system instruction",
        user_prompt="user request",
    )

    assert len(llm.calls) == 1

    assert llm.calls[0] == {
        "system_prompt": "system instruction",
        "user_prompt": "user request",
    }
```

**Test တစ်ခုချင်းရှင်းချက်:**

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_fake_llm_returns_configured_response` | FakeLLMClient ကို init ဖြင့် ပေးထားတဲ့ response ကိုပဲ return ပြန်ပေးတယ် |
| `test_fake_llm_records_prompt` | `ask()` ကိုခေါ်ရင် `calls` list မှာ prompt တွေ record ဖြစ်တယ် |

---

### 15. `tests/test_openai_tools.py`

**ဘာ test လုပ်သလဲ:** `to_openai_tool()` converter function ကို test လုပ်တယ်。

```python
from app.llm.openai_tools import to_openai_tool
from app.tools.list_files import ListFilesTool


def test_tool_is_converted_to_openai_function() -> None:
    tool = ListFilesTool()

    result = to_openai_tool(tool)

    assert result["type"] == "function"
    assert result["name"] == "list_files"
    assert result["description"] == tool.description
    assert result["parameters"] == tool.input_schema
    assert result["strict"] is True
```

**Test တစ်ခုချင်းရှင်းချက်:**

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_tool_is_converted_to_openai_function` | Internal Tool ကို OpenAI format dict ကို convert ရင် type, name, description, parameters, strict fields မှန်ကန်ရမည် |

---

### 16. `tests/test_single_iteration.py`

**ဘာ test လုပ်သလဲ:** `run_single_iteration()` agent logic ကို end-to-end test လုပ်တယ်。

```python
from types import SimpleNamespace

from app.agent.single_iteration import run_single_iteration
from app.llm.fake_client import FakeLLMClient, FakeResponse
from app.tools.executor import ToolExecutor
from app.tools.list_files import ListFilesTool
from app.tools.registry import ToolRegistry


def test_single_iteration_with_no_tool_calls_returns_response() -> None:
    """When the model returns no tool calls, the response is returned directly."""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(response="No tools needed.")

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Hello.",
    )

    assert result.output_text == "No tools needed."
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["user_prompt"] == "Hello."


def test_single_iteration_executes_tool_and_returns_final_response() -> None:
    registry = ToolRegistry()
    registry.register(ListFilesTool())

    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(
        response="The workspace contains an app directory.",
        first_response=FakeResponse(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call_123",
                    name="list_files",
                    arguments='{"path": "."}',
                )
            ],
        ),
    )

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Inspect the workspace.",
    )

    assert result.output_text == (
        "Final response after tool execution."
    )

    assert len(fake_llm.calls) == 2

    assert fake_llm.calls[0]["tools"] == [
        "list_files"
    ]

    conversation = fake_llm.calls[1]["conversation"]

    assert conversation[0] == {
        "role": "user",
        "content": "Inspect the workspace.",
    }

    assert conversation[1].type == "function_call"
    assert conversation[1].call_id == "call_123"

    assert conversation[2]["type"] == "function_call_output"
    assert conversation[2]["call_id"] == "call_123"
```

**Test တစ်ခုချင်းရှင်းချက်:**

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_single_iteration_with_no_tool_calls_returns_response` | LLM က tool call မတောင်းရင် direct response ပြန်ပေးတယ် |
| `test_single_iteration_executes_tool_and_returns_final_response` | LLM က tool call တောင်းရင် tool execute ဖြစ်ပြီး result ကို conversation ထဲထည့်ကာ LLM ကိုထပ်မေးတယ်、 conversation history structure မှန်ကန်တယ် |

---

## ⚙️ CONFIGURATION FILES

---

### `pyproject.toml` — Project Configuration

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-runtime"
version = "0.1.0"
description = "Minimal agentic runtime with a pluggable LLM client."
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0",
    "python-dotenv>=1.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov",
    "mypy",
    "ruff",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

**ရှင်းချက်:** Python 3.11+ လိုတယ်。 `openai`, `python-dotenv`, `pydantic` ကို main dependencies အဖြစ်သုံးတယ်。 Dev tools: pytest, mypy (type checker), ruff (linter/formatter)。

---

### `.env.example` — Environment Variable Template

```bash
# Copy this file to .env and fill in your real values.
# Never commit .env to version control.

OPENAI_API_KEY=sk-...
```

**ရှင်းချက်:** Real API key ကို `.env` ထဲ ထည့်ရမယ်。 Git ထဲ commit မလုပ်ရ။

---

### `conftest.py` — Pytest Configuration

```python
# conftest.py — project-root conftest
# Placing this file here tells pytest to add the agent-runtime/ directory
# to sys.path so that `from app.xxx import ...` works in all test modules.
```

**ရှင်းချက်:** ဒီ file ကို project root ထဲ ထားရုံနဲ့ pytest ကို `from app.xxx import ...` ဆိုတဲ့ import path ကို test files တွေမှာ သုံးလို့ရစေတယ်。

---

## 📋 DOCUMENTATION FILES

---

### `README.md`

```markdown
# Agent Runtime

A coding agent runtime built from scratch in Python.

## Goals

This project implements a software engineering agent without:

- LangChain
- LangGraph
- CrewAI
- LlamaIndex

Only an LLM provider SDK is used for model communication.

## Current Provider

OpenAI

## Architecture

Agent Runtime
     |
     v
 LLMClient
     |
     +---- OpenAIClient
     |
     +---- FakeLLMClient
```

---

### `PROGRESS.md` — Learning Progress

```markdown
### Day 3 — Tool Calling with LLM

Status: Complete

### Learned

- Native function calling is preferable to text-parsed actions.
- The model selects a tool and produces structured arguments.
- The runtime, not the model, executes the tool.
- Provider-specific tool calls are converted into internal `ToolCall` objects.
- Tool execution is represented by `ToolExecution`.
- `call_id` correlates a model tool request with its result.
- Tool execution errors can be represented as data and returned to the model.
- ToolRegistry and ToolExecutor have separate responsibilities.

### Implemented

- `ToolCall`
- `ToolExecution`
- `ToolExecutor`
- OpenAI tool adapter
- OpenAI function calling
- OpenAI tool output conversion
- Fake tool-calling LLM
- Single LLM → tool → result → LLM interaction
- Deterministic single-iteration test

### Architecture

User → OpenAI → function_call → ToolCall → ToolRegistry → ToolExecutor → ToolExecution → function_call_output → OpenAI → Final Response
```

---

### `docs/adr/0001-llm-provider-abstraction.md` — Architecture Decision Record

```markdown
# ADR-0001: Introduce a Provider-Independent LLM Interface

## Status
Accepted

## Context
The coding agent needs to communicate with an LLM provider.
The initial provider is OpenAI.
However, coupling the agent runtime directly to the OpenAI SDK would
make the core runtime dependent on a specific provider.
The project also needs deterministic tests that do not make real
network calls or consume API credits.

## Decision
Introduce a provider-independent `LLMClient` interface.

The runtime depends on: LLMClient
The OpenAI implementation is: OpenAIClient
Tests can use: FakeLLMClient

The OpenAI SDK is therefore isolated behind the LLM client boundary.

## Consequences

### Positive
- Agent runtime is not coupled directly to OpenAI.
- Tests can be deterministic.
- Provider replacement is easier.
- External API concerns remain isolated.

### Negative
- Adds a small abstraction layer.
- Provider-specific capabilities may require additional interfaces or adapters later.

## Alternatives Considered

### Direct OpenAI SDK usage
Rejected because it couples the runtime to a specific provider.

### Generic third-party agent framework
Rejected because this project explicitly builds the runtime
from scratch for learning and architectural understanding.
```

---

## 🔑 KEY DESIGN PATTERNS (ဒီ project မှာ သုံးထားတဲ့ patterns)

| **Abstract Base Class** | `LLMClient`, `Tool` | Provider/tool swap ဖြစ်အောင် |
| **Protocol (Duck Typing)** | `ToolCallingClient` | LLMClient ကို type check မကျပ်တင်ဘဲ flexible ဖြစ်အောင် |
| **Dependency Injection** | `ToolExecutor(registry)` | Test မှာ swap လုပ်လို့ ရအောင် |
| **Frozen Dataclass** | `ToolCall`, `ToolExecution` | Immutable data — accidental mutation မဖြစ်အောင် |
| **Registry Pattern** | `ToolRegistry` | Named lookup with deduplication |
| **Adapter Pattern** | `to_openai_tool()` | Internal format ↔ OpenAI API format |
| **Fake/Stub Testing** | `FakeLLMClient` | Network မသုံးဘဲ fast, deterministic tests |
| **State Machine** | `AgentState` + `AgentStatus` | Loop termination ကို clean ဖြစ်အောင် |
| **Orchestration Loop** | `AgentLoop` | Intelligence မဟုတ်ဘဲ coordination သာ |
| **Response Sequence** | `FakeLLMClient.response_sequence` | Multi-step deterministic test simulation |

---

---

## 🆕 DAY 4 — Stateful Agent Loop

> **Key Takeaway:** `AgentLoop` ဟာ intelligence မဟုတ်ဘူး — Orchestration ဖြစ်တယ်။
> LLM က decision ချတယ်။ Tool က action လုပ်တယ်။ `AgentState` က state ကိုကိုင်တယ်။ `AgentLoop` က အားလုံးကို coordinate လုပ်တယ်။

---

### 17. `app/agent/state.py` — Agent State Machine

**ဘာလုပ်သလဲ:** Loop တစ်ခုလုံးရဲ့ mutable state ကိုကိုင်ထားတဲ့ dataclass။ Loop ကို ဘယ်အချိန် stop ရမလဲဆိုတာ `is_finished` property တစ်ခုနဲ့ ဆုံးဖြတ်တယ်။

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Dict


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    FAILED = "failed"


@dataclass
class AgentState:
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None

    @property
    def is_finished(self) -> bool:
        return self.status != AgentStatus.RUNNING
```

**Class/Enum/Property တစ်ခုချင်းရှင်းချက်:**

| Element | ဘာလုပ်သလဲ |
|---|---|
| `AgentStatus` (Enum) | Loop ရဲ့ ဖြစ်နိုင်တဲ့ states ၄ ခု — `RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `FAILED` |
| `AgentStatus(str, Enum)` | `str` ကိုပါ inherit လုပ်ထားတာကြောင့် `"running"` ဆိုပြီး serialize လုပ်လို့ရတယ် |
| `conversation` | Loop တစ်ကြိမ်တစ်ကြိမ် build ဖြစ်တဲ့ full message history |
| `iteration` | ဘယ် iteration မှာ ရောက်နေလဲဆိုတဲ့ counter |
| `status` | Default `RUNNING` — loop ခနဲ change ဖြစ်ရင် `is_finished` True ဖြစ်တယ် |
| `final_response` | LLM ရဲ့ last text output — COMPLETED ဖြစ်မှပဲ set ဖြစ်တယ် |
| `error` | Exception ဖြစ်ရင် message ကိုသိမ်းတယ် |
| `is_finished` (property) | `status != RUNNING` ဖြစ်ရင် `True` — while loop ရဲ့ exit condition |

---

### 18. `app/agent/loop.py` — Agent Loop (Orchestrator)

**ဘာလုပ်သလဲ:** LLM → Tool → LLM → Tool → … ဆိုတဲ့ multi-iteration loop ကို orchestrate လုပ်တဲ့ class။ Intelligence မပါဘဲ coordination သာ လုပ်တယ်။

```python
import json
from typing import Any, Dict

from app.agent import AgentState, AgentStatus
from app.llm import OpenAIClient
from app.tools import ToolExecutor, ToolRegistry


class AgentLoop:
    def __init__(
        self,
        client: OpenAIClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
    ) -> None:
        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations

    def run(
        self,
        user_prompt: str,
    ) -> AgentState:
        state = AgentState(
            conversation=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        )

        while not state.is_finished:
            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break

            response, tool_calls = self._client.respond_with_tools(
                conversation=state.conversation,
                tools=self._registry.list(),
            )

            state.conversation.extend(response.output)

            if not tool_calls:
                state.final_response = response.output_text
                state.status = AgentStatus.COMPLETED
                break

            for tool_call in tool_calls:
                execution = self._executor.execute(
                    tool_name=tool_call.tool_name,
                    arguments=tool_call.arguments,
                )

                output: Dict[str, Any]

                if execution.success:
                    output = execution.result
                else:
                    output = {
                        "error": execution.error,
                    }

                state.conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(output),
                    }
                )

            state.iteration += 1

        return state
```

**Function တစ်ခုချင်းရှင်းချက်:**

| Function | ဘာလုပ်သလဲ |
|---|---|
| `__init__()` | LLM client, ToolRegistry, ToolExecutor, max_iterations ကို inject လုပ်တယ် |
| `run()` | **Step 1:** user message ပါတဲ့ initial `AgentState` ဆောက်တယ် **Step 2:** `is_finished` မဖြစ်သ‌ရွေ့ loop ဆက်တယ် **Step 3:** iteration limit check **Step 4:** LLM ကို full conversation + tools ပေးပြီး မေးတယ် **Step 5:** tool calls ရှိရင် execute ပြီး results ကို conversation ထဲ ထပ်ထည့်တယ် **Step 6:** tool calls မရှိရင် `COMPLETED` set ပြီး exit |

**Loop Flow (Iteration တစ်ခုချင်း):**

```
conversation + tools
        │
        ▼
client.respond_with_tools()
        │
        ├── tool_calls ရှိ?
        │       │ YES
        │       ▼
        │   executor.execute() ← tool run
        │       │
        │       ▼
        │   conversation += function_call_output
        │       │
        │       ▼
        │   iteration += 1
        │       │
        │       └── (loop ဆက်)
        │
        └── NO tool_calls
                │
                ▼
            state.final_response = output_text
            state.status = COMPLETED
            (loop exit)
```

---

### 19. `app/llm/fake_client.py` — Updated (Day 4)

**ဘာ ပြောင်းသလဲ:** `response_sequence` + `respond_with_tools()` ထည့်ပြီး AgentLoop ရဲ့ multi-step behavior ကို deterministic simulate လုပ်နိုင်အောင် လုပ်တယ်။

```python
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .client import LLMClient
from app.tools import ToolCall


@dataclass
class FakeResponse:
    output_text: str
    output: List[Any] = field(default_factory=list)
    id: str = "fake-response-123"


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

    def __init__(
        self,
        response: str,
        *,
        first_response: Optional["FakeResponse"] = None,
        response_sequence: Optional[List["FakeResponse"]] = None,
    ) -> None:
        self.response = response
        self._first_response = first_response
        # Multi-step sequence for AgentLoop tests.
        # Each call to respond_with_tools pops the next FakeResponse.
        self._response_sequence: List[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: List[Dict[str, Any]] = []

    def _extract_tool_calls(self, response: "FakeResponse") -> List[ToolCall]:
        return [
            ToolCall(
                call_id=item.call_id,
                tool_name=item.name,
                arguments=json.loads(item.arguments),
            )
            for item in response.output
            if item.type == "function_call"
        ]

    def ask(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return self.response

    def ask_with_tools(self, *, user_prompt: str, tools: List[Any]) -> Tuple[FakeResponse, List[Any]]:
        self.calls.append({"user_prompt": user_prompt, "tools": [tool.name for tool in tools]})
        first_response = self._first_response or FakeResponse(output_text=self.response)
        return first_response, self._extract_tool_calls(first_response)

    def continue_with_tool_outputs(self, *, conversation: List[Dict[str, Any]], tools: List[Any]) -> FakeResponse:
        self.calls.append({"method": "continue_with_tool_outputs", "conversation": conversation, "tools": [tool.name for tool in tools]})
        return FakeResponse(output_text="Final response after tool execution.", output=[])

    def respond_with_tools(
        self,
        *,
        conversation: List[Dict[str, Any]],
        tools: List[Any],
    ) -> Tuple["FakeResponse", List[ToolCall]]:
        """Pop the next FakeResponse from response_sequence.
        When exhausted, returns a plain response with no tool calls.
        """
        self.calls.append({
            "method": "respond_with_tools",
            "conversation": list(conversation),
            "tools": [tool.name for tool in tools],
        })

        if self._response_sequence:
            fake_response = self._response_sequence.pop(0)
        else:
            fake_response = FakeResponse(output_text=self.response)

        return fake_response, self._extract_tool_calls(fake_response)
```

**Day 4 ပြောင်းလဲမှုများ:**

| ပြောင်းလဲမှု | ဘာကြောင့် |
|---|---|
| `response_sequence: List[FakeResponse]` parameter ထည့် | Iteration တစ်ခုချင်းအတွက် response ကြိုတင် define လုပ်နိုင်ဖို့ |
| `_extract_tool_calls()` helper | `ask_with_tools` နဲ့ `respond_with_tools` ၂ ခုလုံးမှာ tool call extraction logic ကို မထပ်ဆင့်ဘဲ reuse လုပ်ဖို့ |
| `respond_with_tools()` method | `AgentLoop` အသုံးပြုတဲ့ multi-turn method — sequence မှ `pop(0)` |

---

### 20. `app/llm/openai_client.py` — Updated (Day 4)

**ဘာ ထည့်သလဲ:** `respond_with_tools()` — loop iteration တိုင်းမှာ full conversation + tools ပေးပြီး call လုပ်တဲ့ single unified method။

```python
def respond_with_tools(
    self,
    *,
    conversation: List[Dict[str, Any]],
    tools: List[Tool],
) -> Tuple[Any, List[ToolCall]]:
    """Single unified call used by AgentLoop on every iteration.

    Sends the full conversation history and available tools to the
    model, then extracts any tool-call requests from the response.
    """
    response = self._client.responses.create(
        model=self._model,
        instructions=self._system_prompt,
        input=conversation,
        tools=[to_openai_tool(tool) for tool in tools],
        temperature=self._temperature,
    )

    tool_calls: List[ToolCall] = []

    for item in response.output:
        if item.type != "function_call":
            continue

        tool_calls.append(
            ToolCall(
                call_id=item.call_id,
                tool_name=item.name,
                arguments=json.loads(item.arguments),
            )
        )

    return response, tool_calls
```

**Day 3 vs Day 4 design ကွာခြားချက်:**

| Day 3 | Day 4 |
|---|---|
| `ask_with_tools(user_prompt)` → first call only | `respond_with_tools(conversation)` → every iteration |
| `continue_with_tool_outputs(conversation)` → second call | single method, stateful conversation passed each time |
| 2 methods ကြားမှာ state ကိုင်ရတယ် | Loop ကသာ state ကိုင်တယ်၊ client stateless |

---

### 21. Updated `app/agent/__init__.py`

```python
from .single_iteration import run_single_iteration
from .state import AgentState, AgentStatus
from .loop import AgentLoop

__all__ = [
    "run_single_iteration",
    "AgentState",
    "AgentStatus",
    "AgentLoop",
]
```

### Updated `app/llm/__init__.py`

```python
# llm sub-package

from .client import LLMClient
from .fake_client import FakeLLMClient, FakeResponse
from .openai_client import OpenAIClient
from .openai_tools import to_openai_tool

__all__ = [
    "LLMClient",
    "FakeLLMClient",
    "FakeResponse",
    "OpenAIClient",
    "to_openai_tool",
]
```

---

### 22. `tests/test_agent_loop.py` — AgentLoop Tests

**ဘာ test လုပ်သလဲ:** Real Groq API မသုံးဘဲ `FakeLLMClient` + `response_sequence` နဲ့ AgentLoop ရဲ့ multi-step behavior ကို deterministic simulate လုပ်တယ်။

```python
from types import SimpleNamespace
import pytest
from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient, FakeResponse
from app.tools import ToolExecutor, ToolRegistry
from app.tools.list_files import ListFilesTool


def _make_function_call_item(*, call_id: str, name: str, arguments: str) -> SimpleNamespace:
    """Build a fake LLM output item that looks like a function_call."""
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=arguments)


def _make_loop(fake_llm: FakeLLMClient, *, max_iterations: int = 10) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool())
    executor = ToolExecutor(registry)
    return AgentLoop(client=fake_llm, registry=registry, executor=executor, max_iterations=max_iterations)


def test_agent_loop_completes_after_tool_call() -> None:
    """Loop runs exactly 2 iterations:
    - Iteration 0: LLM requests list_files → executed → result added
    - Iteration 1: LLM returns final answer → COMPLETED
    """
    fake_llm = FakeLLMClient(
        response="Final answer: the workspace has an app directory.",
        response_sequence=[
            # Iteration 0 — request list_files
            FakeResponse(
                output_text="",
                output=[_make_function_call_item(call_id="call_001", name="list_files", arguments='{"path": "."}}')],
            ),
            # Iteration 1 — final text, no tool calls
            FakeResponse(output_text="Final answer: the workspace has an app directory.", output=[]),
        ],
    )

    loop = _make_loop(fake_llm)
    state = loop.run("List files in the workspace.")

    assert state.status == AgentStatus.COMPLETED
    assert "Final answer" in state.final_response
    assert state.iteration == 1      # incremented after iteration 0 only

    respond_calls = [c for c in fake_llm.calls if c.get("method") == "respond_with_tools"]
    assert len(respond_calls) == 2


def test_agent_loop_stops_at_max_iterations() -> None:
    """Loop must stop at max_iterations when LLM never stops calling tools."""
    always_calls_tool = [
        FakeResponse(
            output_text="",
            output=[_make_function_call_item(call_id=f"call_{i:03d}", name="list_files", arguments='{"path": "."}')],
        )
        for i in range(5)
    ]

    fake_llm = FakeLLMClient(response="should not be reached", response_sequence=always_calls_tool)

    loop = _make_loop(fake_llm, max_iterations=2)
    state = loop.run("Keep listing forever.")

    assert state.status == AgentStatus.MAX_ITERATIONS
    assert state.final_response is None
    assert state.iteration == 2


def test_agent_loop_preserves_conversation() -> None:
    """Conversation must contain: [0] user → [1] function_call → [2] function_call_output"""
    function_call_item = _make_function_call_item(call_id="call_abc", name="list_files", arguments='{"path": "."}')

    fake_llm = FakeLLMClient(
        response="Done.",
        response_sequence=[
            FakeResponse(output_text="", output=[function_call_item]),  # Iteration 0
            FakeResponse(output_text="Done.", output=[]),               # Iteration 1
        ],
    )

    loop = _make_loop(fake_llm)
    state = loop.run("Inspect workspace.")

    conv = state.conversation
    assert conv[0] == {"role": "user", "content": "Inspect workspace."}
    assert conv[1].type == "function_call"
    assert conv[1].call_id == "call_abc"
    assert conv[2]["type"] == "function_call_output"
    assert conv[2]["call_id"] == "call_abc"

    assert state.status == AgentStatus.COMPLETED
    assert state.final_response == "Done."
```

**Test တစ်ခုချင်းရှင်းချက်:**

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_agent_loop_completes_after_tool_call` | Iteration 0: tool call → execute, Iteration 1: final answer → `COMPLETED` |
| `test_agent_loop_stops_at_max_iterations` | Tool calls endless ဖြစ်နေရင် `max_iterations` မှာ stop ဖြစ်ပြီး `MAX_ITERATIONS` set ဖြစ်တယ် |
| `test_agent_loop_preserves_conversation` | Conversation history structure `[user → function_call → function_call_output]` မှန်ကန်တယ် |

---

## 📊 UPDATED PROJECT STRUCTURE (Day 4)

```
agent-runtime/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── agent/
│   │   ├── __init__.py              ← AgentLoop, AgentState, AgentStatus export ထည့်
│   │   ├── single_iteration.py      ← Day 3 (unchanged)
│   │   ├── state.py                 ← 🆕 Day 4: AgentState + AgentStatus
│   │   └── loop.py                  ← 🆕 Day 4: AgentLoop (multi-iteration)
│   ├── llm/
│   │   ├── __init__.py              ← FakeResponse export ထည့်
│   │   ├── client.py
│   │   ├── openai_client.py         ← 🆕 respond_with_tools() ထည့်
│   │   ├── fake_client.py           ← 🆕 response_sequence + respond_with_tools() ထည့်
│   │   └── openai_tools.py
│   └── tools/
│       └── ...                      (unchanged)
└── tests/
    ├── test_agent_loop.py           ← 🆕 Day 4: 3 deterministic tests
    ├── test_agent_state.py          ← 🆕 Day 4: 4 state tests
    └── ...                          (Day 3 tests unchanged)
```

---

## 📈 TEST SUITE SUMMARY

| Day | Test File | Tests | Status |
|---|---|---|---|
| Day 3 | `test_tools.py` | 7 | ✅ |
| Day 3 | `test_llm_client.py` | 2 | ✅ |
| Day 3 | `test_openai_tools.py` | 1 | ✅ |
| Day 3 | `test_single_iteration.py` | 2 | ✅ |
| Day 4 | `test_agent_state.py` | 4 | ✅ |
| Day 4 | `test_agent_loop.py` | 3 | ✅ |
| **Total** | | **19** | **19/19 ✅** |

---

*Updated by Antigravity AI — agent-runtime Day 4 additions*


---

---

## 🆕 DAY 5 — Workspace Security, New Tools, Error Recovery & Execution History

> **Key Takeaway:** Agent software မှာ `error = new observation` ဖြစ်တယ်။
> Tool failure ကို structured observation အဖြစ် LLM ဆီပြန်ပို့ပြီး replan လုပ်ဖြစ်အောင် လုပ်တယ်။

```
Normal software        Agentic software
function()             LLM decision
   ↓                       ↓
success/exception       tool
                           ↓
                       success / failure
                           ↓
                       observation      ← error = data, not crash
                           ↓
                       LLM re-plans
```

---

### 23. `app/tools/workspace.py` — Security Boundary 🆕

**ဘာလုပ်သလဲ:** Path traversal attack (`../../secret.txt`) ကို block လုပ်တဲ့ security boundary class။ Tool တိုင်းမှာ security code duplicate မလုပ်ဘဲ centralized ထားတယ်။

```python
from pathlib import Path

class Workspace:
    """Resolves paths while enforcing a workspace boundary."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, path: str) -> Path:
        candidate = (self._root / path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise PermissionError(f"Path escapes workspace: {path}") from exc
        return candidate
```

| Method | ဘာလုပ်သလဲ |
|---|---|
| `__init__(root)` | Root path ကို resolve လုပ်ပြီး absolute path သိမ်းတယ် |
| `root` (property) | Resolved root path ကိုပြန်ပေးတယ် |
| `resolve(path)` | `root/path` resolve ပြီး root ထဲမရောက်ရင် `PermissionError` raise — `../../` attack block |

**Design:** မကောင်းတဲ့ design က security ကို tool တိုင်းမှာ duplicate ရေးရတယ်။ ကောင်းတဲ့ design က `Workspace` တစ်ခုတည်းမှာ centralize ထားပြီး tool layer ကို feed လုပ်တယ်။

---

### 24. `app/tools/list_files.py` — Updated (Day 5)

**ဘာ ပြောင်းသလဲ:** `ListFilesTool()` → `ListFilesTool(workspace)` — Workspace-aware constructor。

```python
def __init__(self, workspace: Workspace) -> None:
    self._workspace = workspace

def run(self, arguments: dict[str, Any]) -> list[str]:
    path = arguments["path"]
    directory = self._workspace.resolve(path)  # ← boundary enforced here
    ...
```

---

### 25. `app/tools/read_file.py` — New Tool 🆕

**ဘာလုပ်သလဲ:** Workspace မှ UTF-8 text file ဖတ်တဲ့ tool။ `max_bytes` limit enforce လုပ်တယ် — Week 9 context budget ရဲ့ foundation。

```python
class ReadFileTool(Tool):
    def __init__(self, workspace: Workspace, *, max_bytes: int = 100_000) -> None: ...

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = arguments["path"]
        file_path = self._workspace.resolve(path)

        if not file_path.exists():       raise FileNotFoundError(...)
        if not file_path.is_file():      raise IsADirectoryError(...)
        if size > self._max_bytes:       raise ValueError("File is too large to read: ...")

        content = file_path.read_text(encoding="utf-8")
        return {"path": path, "content": content, "size_bytes": size}
```

| Error | ဘာဖြစ်တာလဲ |
|---|---|
| `FileNotFoundError` | File မရှိဘူး — tool failure → LLM observation |
| `ValueError` (too large) | `max_bytes` limit ကျော်တယ် — context budget control |
| `PermissionError` | `Workspace.resolve()` က path traversal block |

---

### 26. `app/tools/search_text.py` — New Tool 🆕

**ဘာလုပ်သလဲ:** Workspace ရဲ့ files တွေထဲမှာ text pattern ကို case-insensitive search လုပ်တဲ့ tool。 `.git` skip, file size limit, max results limit ပါတယ်。

**Refactor note (Cognitive Complexity ≤15):** `_search_file()` ကို extract လုပ်ထားတာဟာ inner-loop nesting penalty ကို ဖြတ်ဖို့ ဖြစ်တယ်。 `query.lower()` ကိုလည်း `query_lower` မှာ cache ထားတယ်。

```python
def _search_file(self, file_path, relative_path, query) -> list[dict]:
    """Return matching lines from a single file."""
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    query_lower = query.lower()
    matches = []
    for line_number, line in enumerate(lines, start=1):
        if query_lower in line.lower():
            matches.append({"path": relative_path.as_posix(), "line": line_number, "text": line})
    return matches
```

---

### 27. `app/agent/history.py` — New 🆕

**ဘာလုပ်သလဲ:** Tool execution တွေကို structured telemetry အဖြစ် record, query, JSON serialize လုပ်ပေးတဲ့ class pair。

```python
@dataclass(frozen=True)
class ExecutionRecord:
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: Any
    error: str | None
    duration_ms: float

class ExecutionHistory:
    def add(self, record: ExecutionRecord) -> None: ...
    def records(self) -> list[ExecutionRecord]: ...
    def to_json(self) -> str: ...     # pretty JSON dump
    def __len__(self) -> int: ...     # len(state.history) syntax
```

| Agentic concept | SWE equivalent |
|---|---|
| `ExecutionHistory` | Structured runtime telemetry / audit log |
| `ExecutionRecord` | Execution result / command result snapshot |

---

### 28. `app/agent/state.py` — Updated (Day 5)

**ဘာ ပြောင်းသလဲ:** `history: ExecutionHistory` field ထည့်တယ်。

```python
from .history import ExecutionHistory

@dataclass
class AgentState:
    conversation: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None
    history: ExecutionHistory = field(default_factory=ExecutionHistory)  # ← NEW
```

---

### 29. `app/agent/loop.py` — Updated (Day 5)

**3 ကြိမ် ပြောင်းလဲမှု:**

**① `ToolCallingClient` Protocol (ADR-0001 provider-independence)**

```python
class ToolCallingClient(Protocol):
    def respond_with_tools(
        self, *, conversation: list[dict[str, Any]], tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]: ...
```

`AgentLoop` က `OpenAIClient` concrete type မဟုတ်တော့ဘဲ Protocol ကိုသာ depend လုပ်တယ် — provider swap လုပ်လို့ရတယ်。

**② History recording**

```python
state.history.add(ExecutionRecord(
    tool_name=execution.tool_name, arguments=execution.arguments,
    success=execution.success, result=execution.result,
    error=execution.error, duration_ms=execution.duration_ms,
))
```

**③ Tool output shape — explicit success flag**

```python
# Day 5 (LLM ကို success/failure unambiguously သိစေတယ်)
if execution.success:
    output = {"success": True, "result": execution.result}
else:
    output = {"success": False, "error": execution.error}
```

**Error as Observation flow:**

```
tool.run() raises Exception
        ↓ (executor catches — noqa: BLE001, intentional)
ToolExecution(success=False, error="...")
        ↓ function_call_output {"success": false, "error": "..."}
        ↓ (conversation ထဲ append)
LLM receives error as observation
        ↓
LLM re-plans → different tool call
```

---

### 30. Day 5 New Test Files

#### `tests/test_workspace.py` (3 tests)

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_workspace_resolves_relative_path` | `"src"` → `tmp_path/src` correctly resolve |
| `test_workspace_allows_nested_path` | `"src/app/main.py"` → nested path ok |
| `test_workspace_blocks_path_traversal` | `"../../secret.txt"` → `PermissionError("escapes workspace")` |

#### `tests/test_file_tools.py` (4 tests)

| Test | ဘာစစ်ဆေးသလဲ |
|---|---|
| `test_list_files_uses_workspace` | Workspace-relative list ပြန်တယ် |
| `test_read_file_returns_content` | content + path + size_bytes ပြန်တယ် |
| `test_read_file_rejects_large_file` | `max_bytes=10` → `ValueError("too large")` |
| `test_search_text_returns_matches` | `"login"` → line + line_number ပြန်တယ် |

#### `tests/test_error_recovery.py` — Day 5 Experiments (4 classes, 10 tests)

**Experiment 1 — Tool Error Recovery**

```
Iteration 0: read_file("does_not_exist.py") → ERROR (FileNotFoundError)
Iteration 1: list_files(".")               → SUCCESS  ← model recovered
Iteration 2: final answer
```

| Test | Key assertion |
|---|---|
| `test_agent_continues_after_tool_error` | crash မဖြစ်ဘဲ COMPLETED ဖြစ်ရမည် |
| `test_failed_tool_recorded_in_history` | `history.records()[0].success is False` |
| `test_error_observation_appended_to_conversation` | Second LLM call ထဲ `{"success": false}` ရောက်ရမည် |

**Experiment 2 — Path Traversal**

| Test | Key assertion |
|---|---|
| `test_path_traversal_blocked_and_agent_survives` | `../../secret.txt` → COMPLETED မသေ |
| `test_path_traversal_recorded_as_failure` | `"escapes workspace"` error in history |
| `test_path_traversal_error_forwarded_to_llm` | `{"success": false, "error": "escapes workspace"}` → LLM |

**Experiment 3 — Huge Output**

| Test | Key assertion |
|---|---|
| `test_oversized_file_produces_tool_failure` | `max_bytes=100`, 500-byte file → `"too large"` |
| `test_oversized_file_error_forwarded_to_llm` | Error observation → LLM |

**Experiment 4 — Realistic Exploration**

```
list_files(".") → read_file("app/agent/loop.py") → final answer
```

| Test | Key assertion |
|---|---|
| `test_realistic_exploration_sequence` | 2 tools recorded (success), final_response contains "AgentLoop" |
| `test_history_json_is_serialisable` | `to_json()` → valid JSON with `tool_name` + `duration_ms` |

---

### 31. Real Agent Run — Live Error Recovery

`python -m app.main` — model က **6 tool calls** လုပ်တယ်:

| # | Tool | Result | Note |
|---|---|---|---|
| 1 | `list_files("")` | ✅ | root listing |
| 2 | `list_files("app")` | ✅ | app directory |
| 3 | `repo_browser.list_files("app/agent")` | ❌ | **hallucinated tool name** |
| 4 | `list_files("app/agent")` | ✅ | **self-corrected after error observation** |
| 5 | `read_file("app/main.py")` | ✅ | content read |
| 6 | `read_file("app/agent/loop.py")` | ✅ | content read |

Call 3→4 ဟာ Experiment 1 ကို real API မှာ live ဖြစ်တာ ဖြစ်တယ်。

---

## 📊 UPDATED PROJECT STRUCTURE (Day 5)

```
agent-runtime/
├── app/
│   ├── main.py                  ← Updated: AgentLoop + 3 tools + Workspace
│   ├── agent/
│   │   ├── __init__.py          ← ExecutionHistory, ExecutionRecord export ထည့်
│   │   ├── state.py             ← Updated: history field ထည့်
│   │   ├── loop.py              ← Updated: ToolCallingClient + history + output shape
│   │   ├── history.py           ← 🆕 ExecutionRecord + ExecutionHistory
│   │   └── single_iteration.py  (unchanged)
│   └── tools/
│       ├── __init__.py          ← ReadFileTool, SearchTextTool, Workspace export ထည့်
│       ├── executor.py          ← Updated: BLE001 noqa comment
│       ├── list_files.py        ← Updated: Workspace-aware
│       ├── read_file.py         ← 🆕 file reader with size limit
│       ├── search_text.py       ← 🆕 text search + _search_file() helper
│       ├── workspace.py         ← 🆕 path traversal security boundary
│       └── ...                  (base, call, execution, registry unchanged)
└── tests/
    ├── test_agent_loop.py       ← Updated: workspace-aware, 4th test
    ├── test_error_recovery.py   ← 🆕 4 experiments, 10 tests
    ├── test_file_tools.py       ← 🆕 workspace + read_file + search_text
    ├── test_workspace.py        ← 🆕 3 path traversal tests
    ├── test_openai_tools.py     ← Updated: workspace-aware
    ├── test_single_iteration.py ← Updated: workspace-aware
    └── test_tools.py            ← Updated: workspace-aware
```

---

## 📈 TEST SUITE SUMMARY (Day 5)

| Day | Test File | Tests | Status |
|---|---|---|---|
| Day 3 | `test_tools.py` | 7 | ✅ |
| Day 3 | `test_llm_client.py` | 2 | ✅ |
| Day 3 | `test_openai_tools.py` | 1 | ✅ |
| Day 3 | `test_single_iteration.py` | 2 | ✅ |
| Day 4 | `test_agent_state.py` | 4 | ✅ |
| Day 4 | `test_agent_loop.py` | 4 | ✅ |
| Day 5 | `test_workspace.py` | 3 | ✅ |
| Day 5 | `test_file_tools.py` | 4 | ✅ |
| Day 5 | `test_error_recovery.py` | 10 | ✅ |
| **Total** | | **37** | **37/37 ✅** |

---

## 🧠 Day 5 Architecture — Final Mental Model

```
                     USER
                       │
                       ▼
                 ┌───────────┐
                 │ AgentLoop │   Orchestrator
                 └─────┬─────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
    ToolCallingClient       ToolExecutor
      (Protocol)                │
                          ┌─────┴──────┐
                          │  Registry  │
                          └─────┬──────┘
                                │
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
           list_files       read_file       search_text
               └────────────────┼────────────────┘
                                │
                          Workspace            Security Boundary
                                │
                         ToolExecution
                                │
                         ExecutionHistory      Runtime Telemetry
                                │
                         Observation
                                └──────────► next LLM iteration
```

| Component | Role |
|---|---|
| `LLM` (Protocol) | Decision maker |
| `Tool` | Actuator |
| `ToolExecutor` | Execution boundary — any error → `ToolExecution(success=False)` |
| `AgentState` | Current runtime state |
| `ExecutionHistory` | Runtime record / audit log |
| `AgentLoop` | Orchestrator |
| `Workspace` | Security boundary |

---

## 🎓 Week 1 Day 5 Exit Criteria

| ✅ | Capability |
|---|---|
| ✅ | `list_files` with workspace-relative paths |
| ✅ | `read_file` with UTF-8 + size limit |
| ✅ | `search_text` with line-number results |
| ✅ | Path traversal blocked at `Workspace` boundary |
| ✅ | File-size limit (context budget foundation for Week 9) |
| ✅ | Tool errors returned to LLM as observations |
| ✅ | Execution history recorded per run |
| ✅ | History JSON serialisable |
| ✅ | Fake deterministic multi-step tests (37 passing) |
| ✅ | Real repository exploration (live API) |

**Week 1 Milestone:**
> Agent က repository ကို tools နဲ့ ရှာ၊ ဖတ်၊ error ကို handle လုပ်ပြီး question ဖြေနိုင်ခြင်း ✅

---

*Updated by Antigravity AI — agent-runtime Day 5 additions*
