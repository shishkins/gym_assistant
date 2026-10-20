"""Reading a progress photo into a body-fat band.

One question, one structured answer - no conversation, no tools. Kept apart
from :mod:`ai.client` for the same reason the food reader was: what has to
stay fixed here is the bias, and a bias only stays fixed under one pinned
model and one versioned prompt. Both are stored with every estimate, and an
estimate is only ever compared with another read under the same pair.

What the model is told and what it is not:

* It gets the photo and the person's sex. Sex changes where the healthy
  range sits; leaving it out makes the model guess it from the photo.
* It does NOT get weight or height. Given those it starts estimating from
  BMI - a number that cannot tell a lifter from someone heavy - and the photo
  stops mattering. Kilograms are worked out afterwards, in
  :mod:`domain.body`, from the band and the last weigh-in.

Unlike the old food reader, every call goes through :class:`UsageService`:
the month's budget is checked before the request and the cost is written
after it. The food reader skipped both, so its spend was invisible to
``/ai_costs`` and to the limit.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

import anthropic
import structlog

from gym_assistant.ai.client import AiOverloadedError, AiUnavailableError, BudgetExceededError
from gym_assistant.ai.usage import Tokens, UsageService
from gym_assistant.config import Settings
from gym_assistant.domain.body import Band
from gym_assistant.domain.models import Sex

log = structlog.get_logger(__name__)

# Bumping this is a decision, not a tidy-up: estimates read under different
# versions are not compared with each other, so a bump starts a new series.
PROMPT_VERSION = "body-v1"

# The answer is a few numbers and a few short lines, but the model thinks
# first, and the food reader once ran out of room before writing anything.
MAX_TOKENS = 4000
MAX_OBSERVATIONS = 5
EFFORT = "medium"

PROMPT = """Ты смотришь на фото прогресса из дневника тренировок. Человек сам
попросил оценить по нему процент жира в теле.

Сначала скажи, что на фото:
- body  - человек, снятый так, что видно тело: торс, живот, руки
- other - всё остальное: еда, лицо крупным планом, одетый человек, где форму
  тела не видно, предметы

Если на фото тело, оцени процент жира ВИЛКОЙ:
- bf_low, bf_likely, bf_high - нижняя граница, самое вероятное, верхняя
- usable - false, если тело видно плохо: одежда, темнота, неудачный ракурс,
  видна только часть. Тогда всё равно дай вилку, но широкую.
- observations - 2-5 коротких наблюдений, на которых держится оценка:
  видны ли мышцы пресса, линии между мышцами, вены, складки на талии и боках,
  форма живота. Только то, что видно. Без оценок внешности.
- limits - одной строкой, что мешает оценке точнее: свет, поза, одежда,
  ракурс. Пусто, если ничего.

ПРО ШИРИНУ ВИЛКИ. Оценка жира по фото ошибается на 3-5 процентных пунктов
даже у моделей, обученных только этому. Ты не точнее их. Вилка уже 4 пунктов
- это притворство. При хорошем свете и видном торсе честная вилка 5-7
пунктов; при плохом - 8-12.

Ориентиры для мужчин: 6-9% - резкий рельеф пресса и вены на животе;
10-14% - пресс виден, бока сухие; 15-19% - пресс угадывается, небольшие
бока; 20-25% - пресса не видно, мягкая талия; 25%+ - живот выступает.
Для женщин те же картины примерно на 8-10 пунктов выше.

Не льсти и не пугай. Оценка нужна для того, чтобы следить за динамикой,
а не для приговора.

Отвечай только структурой.
"""

SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "usable", "bf_low", "bf_likely", "bf_high", "observations", "limits"],
    "properties": {
        "kind": {"type": "string", "enum": ["body", "other"]},
        "usable": {"type": "boolean"},
        "bf_low": {"type": "number"},
        "bf_likely": {"type": "number"},
        "bf_high": {"type": "number"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "limits": {"type": "string"},
    },
}

SEX_LINE = {
    Sex.MALE: "Пол: мужской.",
    Sex.FEMALE: "Пол: женский.",
}
SEX_UNKNOWN = "Пол не указан - определи по фото и выбери ориентиры по нему."

Kind = Literal["body", "other"]


class BodyRefusedError(AiUnavailableError):
    """The model declined to read the photo.

    A refusal is billed like any answer and is not a fault of ours or of the
    API, so it gets its own message rather than "try again later".
    """


@dataclass(frozen=True, slots=True)
class BodyReading:
    kind: Kind
    usable: bool
    band: Band | None
    observations: tuple[str, ...]
    limits: str | None
    model: str
    prompt_version: str
    cost_usd: Decimal

    @property
    def is_estimate(self) -> bool:
        """Whether there is anything worth keeping and showing."""
        return self.kind == "body" and self.band is not None and self.band.plausible


class BodyVision:
    """One photo in, one band out, the bill recorded either way."""

    def __init__(self, settings: Settings, usage: UsageService) -> None:
        self._settings = settings
        self._usage = usage
        self._model = settings.ai_model_vision
        key = settings.anthropic_api_key
        self._client = (
            anthropic.AsyncAnthropic(api_key=key.get_secret_value(), max_retries=3) if key else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model(self) -> str:
        return self._model

    async def look(
        self,
        image: bytes,
        *,
        user_id: int,
        sex: Sex | None,
        media_type: str = "image/jpeg",
    ) -> BodyReading:
        if self._client is None:
            raise AiUnavailableError("ANTHROPIC_API_KEY is not set")

        left = await self._usage.budget_left(self._settings.ai_monthly_limit_usd)
        if left <= 0:
            raise BudgetExceededError(str(left))

        payload = base64.standard_b64encode(image).decode()
        # The sex line goes after the frozen prompt, never into it: two
        # estimates under the same PROMPT_VERSION were read by the same
        # instructions, whoever they were for.
        details = SEX_LINE.get(sex, SEX_UNKNOWN) if sex is not None else SEX_UNKNOWN
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                output_config=cast(
                    "Any",
                    {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
                ),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": cast("Any", media_type),
                                    "data": payload,
                                },
                            },
                            {"type": "text", "text": f"{PROMPT}\n{details}"},
                        ],
                    }
                ],
            )
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 529):
                raise AiOverloadedError(str(exc)) from exc
            log.warning("body_vision_failed", status=exc.status_code, error=str(exc))
            raise AiUnavailableError(str(exc)) from exc
        except anthropic.APIError as exc:
            log.warning("body_vision_failed", error=str(exc))
            raise AiUnavailableError(str(exc)) from exc

        # Paid for the moment it arrived - recorded before anything below can
        # throw it away.
        cost = await self._usage.record(
            user_id=user_id,
            session_id=None,
            model=response.model,
            tokens=Tokens.of(response.usage),
        )

        if response.stop_reason == "refusal":
            log.info("body_vision_refused", user_id=user_id)
            raise BodyRefusedError("refusal")

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            log.warning(
                "body_vision_empty_answer",
                stop_reason=response.stop_reason,
                output_tokens=response.usage.output_tokens,
            )
            raise AiUnavailableError(f"empty answer, stop_reason={response.stop_reason}")
        return parse(text, model=self._model, cost_usd=cost)


def parse(text: str, *, model: str, cost_usd: Decimal = Decimal(0)) -> BodyReading:
    """The structured answer as a reading.

    Public so the parsing - the part that decides what counts as an
    estimate - is tested without an API call.
    """
    try:
        raw: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - the schema forbids it
        raise AiUnavailableError(f"unparsable answer: {exc}") from exc

    kind: Kind = "body" if raw.get("kind") == "body" else "other"
    band: Band | None = None
    if kind == "body":
        try:
            band = Band.ordered(_pp(raw["bf_low"]), _pp(raw["bf_likely"]), _pp(raw["bf_high"]))
        except (KeyError, TypeError, ArithmeticError, InvalidOperation):
            band = None

    observations = tuple(
        line for entry in raw.get("observations") or [] if (line := str(entry).strip())
    )[:MAX_OBSERVATIONS]
    limits = str(raw.get("limits") or "").strip()[:300] or None

    return BodyReading(
        kind=kind,
        usable=bool(raw.get("usable")),
        band=band,
        observations=tuple(line[:200] for line in observations),
        limits=limits,
        model=model,
        prompt_version=PROMPT_VERSION,
        cost_usd=cost_usd,
    )


def _pp(value: Any) -> Decimal:
    """A percentage to one decimal, via str so a float does not leak digits."""
    return Decimal(str(value)).quantize(Decimal("0.1"))
