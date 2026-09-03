"""The call to Claude, and the loop around it.

A manual loop rather than the SDK's tool runner. The runner would drive the
turns, but four things have to happen *between* them: log what the call cost,
check the month's budget before spending more, persist the exchange so it
survives a restart, and stop after a fixed number of tool calls. That is the
control flow, so it is written out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

import anthropic
import structlog
from anthropic.types import MessageParam, ToolParam

from gym_assistant.ai import tools
from gym_assistant.ai.prompts import SYSTEM_PROMPT, brief
from gym_assistant.ai.usage import Tokens, UsageService
from gym_assistant.config import Settings

log = structlog.get_logger(__name__)

# A question about training history needs a handful of lookups. Past that the
# model is going in circles, and every extra turn resends the whole exchange.
MAX_TOOL_ROUNDS = 6
MAX_TOKENS = 2048


class BudgetExceededError(RuntimeError):
    """The month's spending limit is used up."""


class AiUnavailableError(RuntimeError):
    """No API key, or the API refused to talk to us."""


@dataclass
class Answer:
    text: str
    tokens: Tokens
    cost_usd: Decimal
    tool_calls: list[str] = field(default_factory=list)
    # Everything the API produced, in API shape, ready to be stored and
    # replayed on the next turn. Text alone would lose the tool blocks.
    turns: list[dict[str, Any]] = field(default_factory=list)


def _tokens_from(usage: Any) -> Tokens:
    return Tokens(
        input=getattr(usage, "input_tokens", 0) or 0,
        output=getattr(usage, "output_tokens", 0) or 0,
        cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


def _add(left: Tokens, right: Tokens) -> Tokens:
    return Tokens(
        input=left.input + right.input,
        output=left.output + right.output,
        cache_read=left.cache_read + right.cache_read,
        cache_write=left.cache_write + right.cache_write,
    )


class AiAssistant:
    def __init__(self, settings: Settings, usage: UsageService) -> None:
        self._settings = settings
        self._usage = usage
        key = settings.anthropic_api_key
        self._client = anthropic.AsyncAnthropic(api_key=key.get_secret_value()) if key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def ask(
        self,
        ctx: tools.ToolContext,
        question: str,
        *,
        history: list[dict[str, Any]] | None = None,
        session_id: int | None = None,
    ) -> Answer:
        """One question, however many tool calls it takes."""
        if self._client is None:
            raise AiUnavailableError("ANTHROPIC_API_KEY is not set")

        left = await self._usage.budget_left(self._settings.ai_monthly_limit_usd)
        if left <= 0:
            raise BudgetExceededError(str(left))

        opening = "\n".join(filter(None, [brief(ctx.user.first_name), question])).strip()
        messages: list[dict[str, Any]] = [
            *(history or []),
            {"role": "user", "content": opening},
        ]

        spent = Tokens()
        cost = Decimal(0)
        called: list[str] = []
        produced: list[dict[str, Any]] = [{"role": "user", "content": opening}]

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._create(messages)

            tokens = _tokens_from(response.usage)
            spent = _add(spent, tokens)
            cost += await self._usage.record(
                user_id=ctx.user.id,
                session_id=session_id,
                model=response.model,
                tokens=tokens,
            )

            blocks = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": blocks})
            produced.append({"role": "assistant", "content": blocks})

            if response.stop_reason != "tool_use":
                return Answer(
                    text=_text_of(response),
                    tokens=spent,
                    cost_usd=cost,
                    tool_calls=called,
                    turns=produced,
                )

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                called.append(block.name)
                results.append(await self._run(ctx, block))

            # Every result goes back in ONE user message. Splitting them
            # teaches the model to stop asking for tools in parallel.
            messages.append({"role": "user", "content": results})
            produced.append({"role": "user", "content": results})

        log.warning("ai_tool_rounds_exhausted", user_id=ctx.user.id, called=called)
        return Answer(
            text=(
                "Не смог собрать ответ — слишком много обращений к данным. "
                "Попробуй спросить конкретнее."
            ),
            tokens=spent,
            cost_usd=cost,
            tool_calls=called,
            turns=produced,
        )

    async def _create(self, messages: list[dict[str, Any]]) -> Any:
        assert self._client is not None
        try:
            return await self._client.messages.create(
                model=self._settings.ai_model_main,
                max_tokens=MAX_TOKENS,
                # Cached by exact bytes, so the prefix is frozen: system
                # prompt then tools, nothing per-user in either.
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=cast("list[ToolParam]", tools.TOOL_DEFINITIONS),
                messages=cast("list[MessageParam]", messages),
            )
        except anthropic.APIStatusError as exc:
            log.warning("ai_api_error", status=exc.status_code, message=exc.message)
            raise AiUnavailableError(str(exc.status_code)) from exc
        except anthropic.APIConnectionError as exc:
            log.warning("ai_api_unreachable")
            raise AiUnavailableError("connection") from exc

    async def _run(self, ctx: tools.ToolContext, block: Any) -> dict[str, Any]:
        """Executes one tool call, turning any failure into a result.

        A raised exception would abandon the turn; an error handed back lets
        the model say what went wrong, or try a different tool.
        """
        try:
            payload: Any = await tools.run_tool(ctx, block.name, dict(block.input or {}))
        except tools.UnknownToolError:
            payload = {"error": "unknown_tool", "name": block.name}
        except Exception:
            log.exception("ai_tool_failed", tool=block.name)
            payload = {"error": "tool_failed", "name": block.name}

        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(payload, ensure_ascii=False),
            "is_error": bool(isinstance(payload, dict) and payload.get("error")),
        }


def _text_of(response: Any) -> str:
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n\n".join(part.strip() for part in parts if part.strip())
