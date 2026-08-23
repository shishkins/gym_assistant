# Gym Assistant

Телеграм-бот для дневника силовых тренировок с AI-ассистентом, который помнит
всю историю занятий и умеет её анализировать.

> **Статус:** итерация 0 — каркас проекта. Бот запускается, отвечает на команды,
> инфраструктура и CI/CD работают. Функциональность в разработке.

## Возможности

| Итерация | Что появляется | Статус |
|----------|----------------|--------|
| 0 | Каркас, БД, Redis, миграции, CI/CD | ✅ готово |
| 1 | Профиль, вес, замеры тела, фото прогресса | 🔜 |
| 2 | Справочник упражнений, справка по технике | 🔜 |
| 3 | Логирование тренировок и подходов | 🔜 |
| 4 | Статистика и графики | 🔜 |
| 5 | AI-ассистент поверх истории тренировок | 🔜 |
| 6 | Голосовой ввод | 🔜 |

## Стек

Python 3.12 · aiogram 3 · PostgreSQL 16 · Redis 7 · SQLAlchemy 2 · Alembic ·
Anthropic Claude · faster-whisper · Docker Compose · GitHub Actions

## Архитектура

```
bot/        хендлеры, клавиатуры, FSM, middleware  — только ввод-вывод
domain/     бизнес-логика, модели, репозитории     — не знает про aiogram и AI
analytics/  метрики и графики                      — чистые функции
ai/         инструменты Claude поверх domain
stt/        клиент сервиса распознавания речи
```

Главное правило: **`domain/` не импортирует `aiogram` и `anthropic`.**
Хендлеры бота, AI-инструменты и будущий Mini App вызывают одни и те же сервисы.

## Быстрый старт

Нужны [uv](https://docs.astral.sh/uv/) и Docker.

```bash
git clone https://github.com/<user>/gym_assistant.git
cd gym_assistant

cp .env.example .env
# заполните BOT_TOKEN (токен dev-бота из @BotFather)
# и ALLOWED_TELEGRAM_IDS (ваш Telegram ID)

uv sync

# для локального запуска БД доступна на localhost
docker compose -f compose.yaml -f compose.dev.yaml up -d postgres redis

POSTGRES_HOST=localhost uv run alembic upgrade head
POSTGRES_HOST=localhost uv run python -m gym_assistant
```

Не знаете свой Telegram ID — просто напишите боту `/start`: он ответит отказом
и покажет ваш ID. Впишите его в `.env` и перезапустите.

## Разработка

```bash
uv run ruff check .          # линтер
uv run ruff format .         # форматирование
uv run mypy src/gym_assistant
uv run pytest                # тесты
```

Новая миграция:

```bash
POSTGRES_HOST=localhost uv run alembic revision --autogenerate -m "add workouts"
POSTGRES_HOST=localhost uv run alembic upgrade head
```

## Деплой

Пуш в `main` с зелёным CI собирает образ, публикует его в GHCR и разворачивает
на сервере. Включается репозиторной переменной `DEPLOY_ENABLED=true`.

Нужные секреты: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` (и `SSH_PORT`, если не 22).

Наружу не публикуется ни один порт — бот работает на исходящем long polling,
белый IP и домен не нужны.

## Безопасность

- `.env` никогда не попадает в репозиторий
- Доступ к боту — по белому списку Telegram ID
- AI-инструменты получают `user_id` из контекста сессии, а не из аргументов
  модели, поэтому ассистент не может прочитать чужие данные

## Лицензия

MIT
