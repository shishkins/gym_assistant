"""Reading a photo of food into numbers.

Separate from :mod:`ai.client` on purpose. That one is a conversation: many
turns, tools, a running history. This is one question with one structured
answer, and it must stay that way - extraction is the part whose bias has to
stay put, because the adaptive TDEE built on top of it can absorb a steady
error and cannot absorb a moving one.

**The model here is pinned and the prompt is versioned.** Both are written
into every meal. Changing either shifts the bias, which is the one thing that
breaks the whole design, so the seam has to be visible in the history.

What was measured before any of this was written, on nine photos of the food
this user actually eats, three runs each:

* Sonnet's run-to-run swing was 9% median against Haiku's 25%, and Haiku
  misread a legible drink label as "water, 0 kcal". Extraction stays on
  Sonnet despite costing four times more.
* Asking for a band rather than one number cut the worst case from 52% to
  30%. The band's WIDTH is honest - wide where the model wobbles - while its
  centre drifts, so the centre is what gets shown and the width is what
  decides whether to ask.
* Naming is the unstable part that no prompt fixes: the same croissant came
  back under three names. The fix is not a closed catalogue - food is an open
  set - but an anchor to what this person has eaten before.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast

import anthropic
import structlog

from gym_assistant.config import Settings

log = structlog.get_logger(__name__)

# Bumping this is a decision, not a tidy-up: every meal already recorded keeps
# the version it was read with, and the two cannot be compared as one series.
PROMPT_VERSION = "food-v3"

MAX_TOKENS = 2500
MAX_ITEMS = 12

PROMPT = """Ты разбираешь фотографию для дневника питания.

Сначала скажи, что на фото:
- food  - еда, блюдо, тарелка, упаковка продукта
- body  - человек, снятый для отслеживания формы тела
- other - всё остальное

Если на фото еда, перечисли позиции.

ГЛАВНОЕ ПРАВИЛО: одна еда — одна позиция. Составное блюдо, у которого есть
своё название — фо бо, борщ, плов, бургер, сэндвич — это ОДНА позиция
целиком, с составом на 100 г готового блюда. Не разбивай его на ингредиенты
и не добавляй их отдельными позициями: вес и калории посчитаются дважды.

Отдельные позиции — это то, что лежит раздельно и съедается само по себе:
лепёшка рядом с мясом, салат, соус в отдельной плошке, гарнир, напиток.

Напитки считай тоже. Сок, смузи, кола, пиво — это калории, и их легко
не заметить. Воду и несладкий чай перечисли, но с нулевой калорийностью.

Для КАЖДОЙ позиции укажи:
- name: название по-русски, как назвал бы его человек
- grams_low, grams_likely, grams_high: вес съедобной части в граммах
- kcal_100g, protein_100g, fat_100g, carb_100g: состав на 100 грамм
- basis: по чему ты судил о размере — тарелка, приборы, упаковка, рука,
  ничего
- needs_scale: true, если рядом нет НИЧЕГО известного размера и предмет для
  масштаба (вилка, ладонь, телефон) сильно помог бы

ПРО ВИЛКУ ВЕСА. Это самое важное здесь.

grams_low и grams_high — не украшение и не вежливость. Это честная граница
того, что ты можешь утверждать по этой фотографии.

Если видна тарелка, приборы или упаковка — ты знаешь масштаб, и вилка должна
быть УЗКОЙ: 380-400-420.

Если масштаб непонятен, еда снята сверху без ориентиров, часть порции скрыта
или блюдо может быть любого размера — вилка должна быть ШИРОКОЙ: 300-450-700.
Не притворяйся уверенным. Широкая вилка — это правильный ответ, а не плохой.

Проверь себя: если бы тебе показали это же фото завтра, попало бы твоё
завтрашнее число внутрь сегодняшней вилки? Если нет — расширь её.

Ориентиры размера: обеденная тарелка 26-28 см, пиала для супа 500-700 мл,
вилка 19 см, палочки 24 см, банка 330 мл, ладонь 18 см.

Не занижай большие порции. Известно, что модели систематически уменьшают
крупные порции; если порция выглядит большой, доверяй тому, что видишь.

Если чего-то не разобрать — не выдумывай. Задай ОДИН уточняющий вопрос в
поле question: короткий, с вариантами, на который человек ответит одним
словом. Если всё понятно — question пусто.

Отвечай только структурой.
"""

SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "items", "question"],
    "properties": {
        "kind": {"type": "string", "enum": ["food", "body", "other"]},
        "question": {"type": ["string", "null"]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "grams_low",
                    "grams_likely",
                    "grams_high",
                    "kcal_100g",
                    "protein_100g",
                    "fat_100g",
                    "carb_100g",
                    "basis",
                    "needs_scale",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "grams_low": {"type": "number"},
                    "grams_likely": {"type": "number"},
                    "grams_high": {"type": "number"},
                    "kcal_100g": {"type": "number"},
                    "protein_100g": {"type": "number"},
                    "fat_100g": {"type": "number"},
                    "carb_100g": {"type": "number"},
                    "basis": {"type": "string"},
                    "needs_scale": {"type": "boolean"},
                },
            },
        },
    },
}

Kind = Literal["food", "body", "other"]


class VisionUnavailableError(RuntimeError):
    """No key, or the API would not answer."""


@dataclass(frozen=True, slots=True)
class SeenItem:
    """One thing the model says is on the plate, in its own units."""

    name: str
    grams: Decimal
    grams_low: Decimal
    grams_high: Decimal
    kcal_100g: Decimal
    protein_100g: Decimal
    fat_100g: Decimal
    carb_100g: Decimal
    basis: str
    needs_scale: bool

    @property
    def kcal(self) -> Decimal:
        return self.grams * self.kcal_100g / 100

    @property
    def protein_g(self) -> Decimal:
        return self.grams * self.protein_100g / 100

    @property
    def fat_g(self) -> Decimal:
        return self.grams * self.fat_100g / 100

    @property
    def carb_g(self) -> Decimal:
        return self.grams * self.carb_100g / 100

    @property
    def band_width_pct(self) -> Decimal:
        """How unsure the model is about this portion, in percent of it.

        Measured at 32-46% on real photos. Above roughly half, the number is a
        guess dressed as a measurement and is worth asking about.
        """
        if not self.grams:
            return Decimal(0)
        return (self.grams_high - self.grams_low) / self.grams * 100


@dataclass(frozen=True, slots=True)
class Seen:
    """What one photo turned out to be."""

    kind: Kind
    items: tuple[SeenItem, ...]
    question: str | None
    model: str
    prompt_version: str

    @property
    def kcal(self) -> Decimal:
        return sum((item.kcal for item in self.items), Decimal(0))

    @property
    def protein_g(self) -> Decimal:
        return sum((item.protein_g for item in self.items), Decimal(0))

    @property
    def fat_g(self) -> Decimal:
        return sum((item.fat_g for item in self.items), Decimal(0))

    @property
    def carb_g(self) -> Decimal:
        return sum((item.carb_g for item in self.items), Decimal(0))


def atwater_gap_pct(item: SeenItem) -> Decimal:
    """How far the stated calories are from the macros that should make them.

    4 kcal a gram of protein and of carbohydrate, 9 of fat. The model holds
    this by itself about four times in five, so a wide gap means the numbers
    were produced separately rather than as one estimate - a sign to distrust
    that row rather than the whole meal.
    """
    computed = 4 * item.protein_100g + 4 * item.carb_100g + 9 * item.fat_100g
    if item.kcal_100g <= 0:
        return Decimal(100)
    return abs(item.kcal_100g - computed) / item.kcal_100g * 100


class FoodVision:
    """One photo in, one structured reading out."""

    def __init__(self, settings: Settings) -> None:
        key = settings.anthropic_api_key
        self._model = settings.ai_model_vision
        self._client = (
            anthropic.AsyncAnthropic(api_key=key.get_secret_value(), max_retries=3) if key else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    async def look(
        self,
        image: bytes,
        *,
        media_type: str = "image/jpeg",
        hint: list[str] | None = None,
        note: str | None = None,
        extra: bytes | None = None,
        previous: list[SeenItem] | None = None,
    ) -> Seen:
        """One photo, plus whatever the person chose to add.

        Everything past ``image`` is data appended after the frozen prompt,
        never a change to it - the same arrangement as the chat assistant's
        per-user line. That is what keeps ``PROMPT_VERSION`` meaning something:
        two meals read under the same version were read by the same
        instructions, whatever hints happened to travel with them.
        """
        if self._client is None:
            raise VisionUnavailableError("ANTHROPIC_API_KEY is not set")

        payload = base64.standard_b64encode(image).decode()
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                output_config=cast("Any", {"format": {"type": "json_schema", "schema": SCHEMA}}),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            *cast("Any", _images(payload, extra, media_type)),
                            {"type": "text", "text": PROMPT + _context(hint, note, previous)},
                        ],
                    }
                ],
            )
        except anthropic.APIError as exc:
            log.warning("vision_failed", error=str(exc))
            raise VisionUnavailableError(str(exc)) from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return self._parse(text)

    def _parse(self, text: str) -> Seen:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - schema forbids it
            raise VisionUnavailableError(f"unparsable answer: {exc}") from exc

        items = tuple(
            parsed
            for entry in raw.get("items", [])[:MAX_ITEMS]
            if (parsed := _item(entry)) is not None
        )
        question = (raw.get("question") or "").strip() or None
        return Seen(
            kind=cast("Kind", raw.get("kind", "other")),
            items=items,
            question=question,
            model=self._model,
            prompt_version=PROMPT_VERSION,
        )


def _item(entry: dict[str, Any]) -> SeenItem | None:
    """One row, or nothing.

    A row is dropped rather than repaired when its numbers are impossible.
    Repairing means inventing, and a plate that is missing its sauce is easier
    to notice and fix than one carrying a figure nobody produced.
    """
    try:
        low = _money(entry["grams_low"])
        grams = _money(entry["grams_likely"])
        high = _money(entry["grams_high"])
        kcal_100g = _money(entry["kcal_100g"])
    except (KeyError, TypeError, ArithmeticError):
        return None

    if not 0 < grams <= 5000 or not 0 <= kcal_100g <= 900:
        log.info("vision_item_dropped", name=entry.get("name"), grams=str(grams))
        return None

    # The model occasionally hands back a band that does not contain its own
    # centre. Ordering them is cheaper than refusing the row.
    low, high = min(low, grams), max(high, grams)

    return SeenItem(
        name=str(entry.get("name") or "Без названия").strip()[:200],
        grams=grams,
        grams_low=low,
        grams_high=high,
        kcal_100g=kcal_100g,
        protein_100g=_money(entry.get("protein_100g", 0)),
        fat_100g=_money(entry.get("fat_100g", 0)),
        carb_100g=_money(entry.get("carb_100g", 0)),
        basis=str(entry.get("basis") or "").strip()[:200],
        needs_scale=bool(entry.get("needs_scale")),
    )


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.1"))


def _images(payload: str, extra: bytes | None, media_type: str) -> list[dict[str, Any]]:
    """The plate first, the hint photo second, in that order.

    The second one is usually a menu or a delivery app - a picture of text.
    It carries the name and often the weight outright, which beats any
    estimate made by looking at the food itself.
    """
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": payload},
        }
    ]
    if extra is not None:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(extra).decode(),
                },
            }
        )
    return blocks


def _context(hint: list[str] | None, note: str | None, previous: list[SeenItem] | None) -> str:
    """Per-request data, appended after the frozen prompt and never inside it."""
    parts: list[str] = []

    if hint:
        # The anchor that stops the same croissant coming back under a new
        # name every morning. A suggestion, not a menu: food is an open set,
        # and a closed list would wall off the first unfamiliar dish.
        listed = "\n".join(f"- {name}" for name in hint)
        parts.append(
            "\n\nЧеловек недавно ел вот это. Если на фото что-то из списка — "
            "назови ТОЧНО так же, слово в слово. Если нет — назови свободно, "
            "список не ограничивает:\n" + listed
        )

    if previous:
        was = "\n".join(f"- {item.name}: {item.grams:.0f} г" for item in previous)
        parts.append(
            "\n\nТы уже разбирал это фото и получил вот что. Исправь то, "
            "что расходится с подсказкой ниже, остальное оставь как было:\n" + was
        )

    if note:
        # Last, so it outranks everything above it: it is the only line here
        # that came from someone who saw the actual plate.
        parts.append(
            "\n\nПОДСКАЗКА ОТ ЧЕЛОВЕКА, она важнее твоей оценки по фото:\n" + note.strip()[:500]
        )

    return "".join(parts)
