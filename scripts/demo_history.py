"""Fill the development database with a plausible training history.

Charts need weeks of data to say anything, and waiting six weeks to find out
whether a chart is readable is not a testing strategy. This writes a history
that looks like real training - progression, warm-ups, rest days, an
occasional missed week - so the reports can be judged today.

    uv run python scripts/demo_history.py            # 12 weeks
    uv run python scripts/demo_history.py --weeks 24
    uv run python scripts/demo_history.py --wipe     # remove it again

Demo data is tagged in the workout note, so --wipe removes exactly what this
script created and leaves real sessions alone.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from gym_assistant.config import get_settings
from gym_assistant.db import create_engine, create_session_factory
from gym_assistant.domain.models import BodyMeasurement, Workout, WorkoutSet, WorkoutStatus
from gym_assistant.domain.services import ExerciseService, MeasurementService, ProfileService

DEMO_NOTE = "demo-history"

# A plain upper/lower split: enough variety for the volume chart to have
# something to say, without pretending to be a real programme.
PLAN = (
    (("бенч", 70, 8), ("тяга штанги", 60, 8), ("жим стоя", 40, 8), ("бицепс", 25, 10)),
    (("присед", 100, 6), ("румынка", 80, 8), ("жим ногами", 150, 10), ("икры", 60, 15)),
)


async def _seed(telegram_id: int, weeks: int) -> None:
    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)
    random.seed(20260902)

    async with factory() as session:
        user = await ProfileService(session).get_or_create_user(telegram_id)
        exercises = ExerciseService(session)

        resolved = []
        for day in PLAN:
            entries = []
            for query, base, reps in day:
                found = await exercises.search(query, user_id=user.id, limit=1)
                if not found:
                    print(f"  пропускаю «{query}» — не нашёл в справочнике")
                    continue
                entries.append((found[0], base, reps))
            resolved.append(entries)

        start = datetime.now(UTC) - timedelta(weeks=weeks)
        created = 0

        for week in range(weeks):
            # One week in six is missed: a chart with no gaps in it is not a
            # chart of anyone's actual training.
            if random.random() < 0.15:
                continue

            for index, entries in enumerate(resolved):
                when = start + timedelta(weeks=week, days=index * 3, hours=random.randint(9, 19))
                workout = Workout(
                    user_id=user.id,
                    started_at=when,
                    finished_at=when + timedelta(minutes=random.randint(45, 80)),
                    status=WorkoutStatus.COMPLETED.value,
                    note=DEMO_NOTE,
                )
                session.add(workout)
                await session.flush()

                for order, (exercise, base, reps) in enumerate(entries):
                    progression = Decimal(base) + Decimal(week) * Decimal("1.25")
                    noise = Decimal(random.choice((-2.5, 0, 0, 0, 2.5)))
                    weight = (progression + noise).quantize(Decimal("0.1"))

                    session.add(
                        WorkoutSet(
                            workout_id=workout.id,
                            exercise_id=exercise.id,
                            order_index=order,
                            set_index=1,
                            weight_kg=(weight * Decimal("0.5")).quantize(Decimal("0.1")),
                            reps=reps + 4,
                            is_warmup=True,
                            performed_at=when,
                        )
                    )
                    for number in range(3):
                        session.add(
                            WorkoutSet(
                                workout_id=workout.id,
                                exercise_id=exercise.id,
                                order_index=order,
                                set_index=number + 2,
                                weight_kg=weight,
                                reps=max(1, reps - random.randint(0, 2)),
                                performed_at=when + timedelta(minutes=5 * order + number),
                            )
                        )
                        created += 1

        body = Decimal("84.0")
        for day in range(0, weeks * 7, 3):
            body += Decimal(str(round(random.uniform(-0.5, 0.35), 1)))
            await MeasurementService(session).record(
                user.id,
                weight_kg=body,
                measured_at=start + timedelta(days=day),
                note=DEMO_NOTE,
            )

        await session.commit()
        print(f"Готово: {created} рабочих подходов за {weeks} недель, плюс замеры веса.")

    await engine.dispose()


async def _wipe(telegram_id: int) -> None:
    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)

    async with factory() as session:
        user = await ProfileService(session).get_or_create_user(telegram_id)
        ids = list(
            await session.scalars(
                select(Workout.id).where(Workout.user_id == user.id, Workout.note == DEMO_NOTE)
            )
        )
        if ids:
            await session.execute(delete(Workout).where(Workout.id.in_(ids)))
        measurements = await session.execute(
            delete(BodyMeasurement).where(
                BodyMeasurement.user_id == user.id, BodyMeasurement.note == DEMO_NOTE
            )
        )
        await session.commit()
        print(f"Удалено: {len(ids)} тренировок и {measurements.rowcount} замеров.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-id", type=int, default=402666721)
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--wipe", action="store_true", help="удалить демо-историю")
    args = parser.parse_args()

    asyncio.run(_wipe(args.telegram_id) if args.wipe else _seed(args.telegram_id, args.weeks))


if __name__ == "__main__":
    main()
