"""Thin wrapper around the Anthropic SDK: key check, timeout, per-process call budget."""

from __future__ import annotations

import os
from typing import Any, Protocol

import anthropic

MODEL = "claude-sonnet-5"
MAX_TOKENS = 8192
TIMEOUT_S = 20.0
MAX_RETRIES = 0  # a slow call falls through to templates rather than doubling the wait on stage
API_KEY_ENV = "ANTHROPIC_API_KEY"
MAX_CALLS_PER_PROCESS = 60


class MissingAPIKeyError(RuntimeError):
    """Raised when the API key environment variable is not set."""


class BudgetExceededError(RuntimeError):
    """Raised when the per-process live-call budget is exhausted."""


class MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class LLMClient(Protocol):
    """The subset of `anthropic.Anthropic` this package uses; tests inject a fake."""

    @property
    def messages(self) -> MessagesAPI: ...


def get_client() -> anthropic.Anthropic:
    if not os.environ.get(API_KEY_ENV):
        raise MissingAPIKeyError(f"{API_KEY_ENV} is not set in the environment")
    # The SDK reads the key from the environment itself; it is never passed around here.
    return anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=MAX_RETRIES)


_calls_made = 0


def calls_made() -> int:
    return _calls_made


def reset_budget() -> None:
    global _calls_made
    _calls_made = 0


def charge_budget(limit: int = MAX_CALLS_PER_PROCESS) -> None:
    """Count one paid call; raise before the (limit + 1)th so a bug cannot loop on the API."""
    global _calls_made
    if _calls_made >= limit:
        raise BudgetExceededError(f"live-call budget of {limit} per process exhausted")
    _calls_made += 1


def create_message(client: LLMClient, **kwargs: Any) -> Any:
    """One budgeted `messages.create` with the project model and token cap."""
    charge_budget()
    return client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, **kwargs)


def tool_input(message: Any, tool_name: str) -> dict[str, Any] | None:
    """The `input` of the first `tool_use` block named `tool_name`, or None."""
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            payload = getattr(block, "input", None)
            return payload if isinstance(payload, dict) else None
    return None
