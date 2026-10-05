from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.llm.types import Usage


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1M tokens. Supplied via config, never hardcoded."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float

    def __post_init__(self) -> None:
        if self.input_usd_per_mtok < 0 or self.output_usd_per_mtok < 0:
            raise ValueError("pricing must be >= 0")

    def cost_usd(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_usd_per_mtok
            + usage.output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class TokenBudget:
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be >= 1")
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be > 0")


@dataclass(frozen=True)
class UsageRecord:
    call_index: int  # 1-based
    usage: Usage | None  # None = provider did not report


class UsageTracker:
    """Accumulates per-call usage for a single agent run."""

    def __init__(self, pricing: ModelPricing | None = None) -> None:
        self._pricing = pricing
        self._records: list[UsageRecord] = []

    def record(self, usage: Usage | None) -> None:
        self._records.append(
            UsageRecord(call_index=len(self._records) + 1, usage=usage)
        )

    @property
    def calls(self) -> int:
        return len(self._records)

    @property
    def unreported_calls(self) -> int:
        return sum(1 for r in self._records if r.usage is None)

    @property
    def total(self) -> Usage:
        total = Usage()
        for record in self._records:
            if record.usage is not None:
                total = total + record.usage
        return total

    def cost_usd(self) -> float | None:
        if self._pricing is None:
            return None
        return self._pricing.cost_usd(self.total)

    def exceeded(self, budget: TokenBudget) -> str | None:
        """Return the reason the budget is exhausted, or None."""
        if self.unreported_calls:
            return "usage_unreported"  # fail closed

        if (
            budget.max_total_tokens is not None
            and self.total.total_tokens >= budget.max_total_tokens
        ):
            return "max_total_tokens"

        cost = self.cost_usd()
        if (
            budget.max_cost_usd is not None
            and cost is not None
            and cost >= budget.max_cost_usd
        ):
            return "max_cost_usd"

        return None

    def report(self) -> dict[str, Any]:
        cumulative = 0
        per_call: list[dict[str, Any]] = []

        for record in self._records:
            if record.usage is None:
                per_call.append(
                    {"call": record.call_index, "input_tokens": None,
                     "output_tokens": None, "cumulative_total": cumulative}
                )
                continue
            cumulative += record.usage.total_tokens
            per_call.append(
                {
                    "call": record.call_index,
                    "input_tokens": record.usage.input_tokens,
                    "output_tokens": record.usage.output_tokens,
                    "cumulative_total": cumulative,
                }
            )

        total = self.total
        cost = self.cost_usd()

        return {
            "calls": self.calls,
            "unreported_calls": self.unreported_calls,
            "input_tokens": total.input_tokens,
            "output_tokens": total.output_tokens,
            "total_tokens": total.total_tokens,
            "cost_usd": round(cost, 6) if cost is not None else None,
            "per_call": per_call,
        }
