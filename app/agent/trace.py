import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TextIO


@dataclass(frozen=True)
class TraceEvent:
    """One immutable, JSON-serializable trace record."""

    run_id: str
    seq: int
    ts: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type,
            **self.data,
        }


class TraceSink(Protocol):
    def write(self, event: TraceEvent) -> None: ...


class InMemorySink:
    """Collects events in a list. For tests and ad-hoc inspection."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def write(self, event: TraceEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


class JsonlFileSink:
    """Appends one JSON object per line; flushes every event so a crash
    keeps everything written so far."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: TraceEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TraceRecorder:
    """Per-run emitter. Owns run_id and the sequence counter.

    A sink failure must never break the run: observability is not
    business logic. Failures go to stderr once per event.
    """

    def __init__(
        self,
        sink: TraceSink,
        *,
        run_id: str | None = None,
        now: Callable[[], str] = _utc_now_iso,
        err: TextIO | None = None,
    ) -> None:
        self._sink = sink
        self.run_id = run_id or uuid.uuid4().hex
        self._now = now
        self._seq = 0
        self._err = err or sys.stderr

    def emit(self, type_: str, **data: Any) -> None:
        self._seq += 1
        event = TraceEvent(
            run_id=self.run_id,
            seq=self._seq,
            ts=self._now(),
            type=type_,
            data=data,
        )
        try:
            self._sink.write(event)
        except Exception as exc:
            print(f"trace sink failed: {exc!r}", file=self._err)
