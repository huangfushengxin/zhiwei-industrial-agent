"""Budget mandatory instructions/facts first, then retain whole recent turns."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence


class ContextBudgetError(ValueError):
    pass


@dataclass(frozen=True)
class Context:
    messages: list[dict[str, str]]
    estimated_input_tokens: int
    dropped_turns: int


def estimate_tokens(messages: Sequence[dict[str, str]]) -> int:
    # UTF-8 bytes deliberately overestimate typical text tokenization, including
    # Chinese. This is a heuristic, not the provider's tokenizer or billing count.
    return len(json.dumps(list(messages), ensure_ascii=False).encode("utf-8")) + 128


def fit_context(system: str, task: str, history: Sequence[dict[str, str]] = (), *,
                window: int = 8192, output_tokens: int = 1024,
                safety_tokens: int = 512) -> Context:
    if min(window, output_tokens) <= 0 or safety_tokens < 0:
        raise ValueError("Context and output budgets must be positive")
    turns = [dict(message) for message in history]
    if len(turns) % 2 or any(
        m.get("role") != ("user" if i % 2 == 0 else "assistant")
        or not isinstance(m.get("content"), str)
        for i, m in enumerate(turns)
    ):
        raise ValueError("History must contain complete user/assistant pairs")
    first = {"role": "system", "content": system}
    last = {"role": "user", "content": task}
    budget = window - output_tokens - safety_tokens
    if estimate_tokens([first, last]) > budget:
        raise ContextBudgetError("Instructions and tool facts exceed the input budget")
    dropped = 0
    while estimate_tokens([first, *turns, last]) > budget:
        turns = turns[2:]
        dropped += 1
    messages = [first, *turns, last]
    return Context(messages, estimate_tokens(messages), dropped)
