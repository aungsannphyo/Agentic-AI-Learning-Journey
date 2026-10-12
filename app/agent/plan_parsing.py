"""Defensive parser for free-text plans. Model output is untrusted:
never raises, returns [] when nothing numbered is found."""

import re

_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")


def parse_numbered_steps(text: str) -> list[str]:
    steps: list[str] = []
    for line in text.splitlines():
        match = _STEP.match(line)
        if match:
            steps.append(match.group(1))
    return steps
