"""A test rig that drives real updates through the real Dispatcher.

Service-level tests cannot catch wiring mistakes: a handler registered in the
wrong order, a filter that never matches, a state that is never entered. This
harness assembles the dispatcher exactly as ``__main__`` does - same routers,
same middlewares, same order - and feeds it Telegram updates, recording the
API calls the bot would have made.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from aiogram.types import (
    User as TelegramUser,
)
from sqlalchemy.ext.asyncio import AsyncSession

from gym_assistant.bot.handlers import get_routers
from gym_assistant.bot.middlewares import LoggingMiddleware, UserMiddleware, WhitelistMiddleware
from gym_assistant.config import Settings

TOKEN = "42:test-token-not-real"


class RecordingSession(BaseSession):
    """Captures outgoing API calls instead of talking to Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._message_id = 1000

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - aiogram's signature
    ) -> Any:
        self.calls.append(method)
        name = type(method).__name__

        if name in {"SendMessage", "EditMessageText", "SendPhoto"}:
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=datetime.now(UTC),
                chat=Chat(id=CHAT_ID, type="private"),
                text=getattr(method, "text", None) or "",
                reply_markup=getattr(method, "reply_markup", None),
            )
        if name == "SendMediaGroup":
            return []
        if name == "GetMe":  # pragma: no cover - not used by these tests
            return TelegramUser(id=42, is_bot=True, first_name="Test")
        return True

    # -- assertions helpers ------------------------------------------------

    @property
    def texts(self) -> list[str]:
        """Every message the bot sent or edited, in order."""
        return [
            text
            for call in self.calls
            if type(call).__name__ in {"SendMessage", "EditMessageText"}
            and (text := getattr(call, "text", None)) is not None
        ]

    @property
    def last_text(self) -> str:
        return self.texts[-1]

    @property
    def last_markup(self) -> InlineKeyboardMarkup | None:
        for call in reversed(self.calls):
            markup = getattr(call, "reply_markup", None)
            if isinstance(markup, InlineKeyboardMarkup):
                return markup
        return None

    def button_with(self, fragment: str) -> str:
        """Callback data of the first button whose label contains ``fragment``."""
        markup = self.last_markup
        assert markup is not None, "the last message carried no keyboard"
        for row in markup.inline_keyboard:
            for button in row:
                if fragment.lower() in button.text.lower() and button.callback_data:
                    return button.callback_data
        raise AssertionError(
            f"no button matching {fragment!r}; saw "
            f"{[b.text for row in markup.inline_keyboard for b in row]}"
        )

    def clear(self) -> None:
        self.calls.clear()


CHAT_ID = 555
TELEGRAM_USER_ID = 777


class BotHarness:
    def __init__(self, dispatcher: Dispatcher, bot: Bot, session: RecordingSession) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.session = session
        self._update_id = 0
        self._message_id = 1

    def _next_update_id(self) -> int:
        self._update_id += 1
        return self._update_id

    async def send(self, text: str) -> None:
        """Simulates the user typing ``text``."""
        self._message_id += 1
        update = Update(
            update_id=self._next_update_id(),
            message=Message(
                message_id=self._message_id,
                date=datetime.now(UTC),
                chat=Chat(id=CHAT_ID, type="private"),
                from_user=TelegramUser(
                    id=TELEGRAM_USER_ID, is_bot=False, first_name="Тестер", username="tester"
                ),
                text=text,
                entities=_command_entities(text),
            ),
        )
        await self.dispatcher.feed_update(self.bot, update)

    async def tap(self, callback_data: str) -> None:
        """Simulates the user pressing an inline button."""
        self._message_id += 1
        update = Update(
            update_id=self._next_update_id(),
            callback_query=CallbackQuery(
                id=str(self._next_update_id()),
                from_user=TelegramUser(
                    id=TELEGRAM_USER_ID, is_bot=False, first_name="Тестер", username="tester"
                ),
                chat_instance="test",
                data=callback_data,
                message=Message(
                    message_id=self._message_id,
                    date=datetime.now(UTC),
                    chat=Chat(id=CHAT_ID, type="private"),
                    text="…",
                ),
            ),
        )
        await self.dispatcher.feed_update(self.bot, update)

    async def tap_button(self, fragment: str) -> None:
        await self.tap(self.session.button_with(fragment))


def _command_entities(text: str) -> list[Any] | None:
    """aiogram's Command filter needs the entity Telegram would have attached."""
    if not text.startswith("/"):
        return None
    from aiogram.types import MessageEntity

    length = len(text.split(maxsplit=1)[0])
    return [MessageEntity(type="bot_command", offset=0, length=length)]


class _SessionHolder:
    """Lets one long-lived dispatcher serve a different session each test."""

    session: AsyncSession | None = None


class _HolderSessionMiddleware:
    """Injects the test's session and never commits: the fixture rolls back."""

    def __init__(self, holder: _SessionHolder) -> None:
        self._holder = holder

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        assert self._holder.session is not None, "no session bound to the harness"
        data["session"] = self._holder.session
        return await handler(event, data)


# Routers are module-level singletons and a Router can belong to exactly one
# Dispatcher, so the dispatcher is built once and reused across tests. What
# varies per test - the database session and the FSM state - is swapped out.
_HOLDER = _SessionHolder()
_STORAGE = MemoryStorage()
_DISPATCHER: Dispatcher | None = None


def _dispatcher(settings: Settings) -> Dispatcher:
    global _DISPATCHER
    if _DISPATCHER is not None:
        return _DISPATCHER

    dispatcher = Dispatcher(storage=_STORAGE)
    dispatcher["settings"] = settings

    # Same order as __main__.
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(WhitelistMiddleware(frozenset({TELEGRAM_USER_ID})))
    dispatcher.update.outer_middleware(_HolderSessionMiddleware(_HOLDER))
    dispatcher.update.outer_middleware(UserMiddleware())
    dispatcher.include_routers(*get_routers())

    _DISPATCHER = dispatcher
    return dispatcher


def build_harness(db_session: AsyncSession, settings: Settings) -> BotHarness:
    _HOLDER.session = db_session
    # Every test starts with no conversation in progress.
    _STORAGE.storage.clear()

    recording = RecordingSession()
    bot = Bot(
        token=TOKEN,
        session=recording,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    return BotHarness(_dispatcher(settings), bot, recording)
