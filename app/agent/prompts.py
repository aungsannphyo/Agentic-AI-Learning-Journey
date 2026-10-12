"""Prompts as versioned artifacts (name + content hash)."""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:8]

    @property
    def label(self) -> str:
        return f"{self.name}@{self.sha}"


# Byte-identical to the prompt that produced baseline v0.2 / v0.2b.
_BASE = (
    "You are a software engineering agent. "
    "You must ONLY call the tools explicitly provided: list_files, read_file, search_text. "
    "Never use any namespace prefixes or tools not defined. "
    "Only use workspace-relative paths. "
    "Do not invent file contents. If something does not exist, say so."
)

_GROUNDING = (
    " Never state facts about the repository from general knowledge. "
    "Every claim in your answer must come from a tool result you obtained "
    "in this run. If you have not read the relevant file yet, read it "
    "before answering."
)

BASELINE = Prompt("baseline", _BASE)
GROUNDED_V1 = Prompt("grounded-v1", _BASE + _GROUNDING)

PLANNER_V1 = Prompt(
    "planner-v1",
    "Write a short plan for answering the task below. The agent that will "
    "execute it can only use these tools, all on the repository: list_files, "
    "read_file, search_text. Write at most 6 steps, each one short sentence "
    "saying what to look for or read. Do not answer the task itself.",
)

PROMPTS: dict[str, Prompt] = {p.name: p for p in (BASELINE, GROUNDED_V1)}


def get_prompt(name: str) -> Prompt:
    try:
        return PROMPTS[name]
    except KeyError:
        raise KeyError(
            f"unknown prompt '{name}'; available: {sorted(PROMPTS)}"
        ) from None
