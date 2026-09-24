"""Exporting a user's own data as CSV.

Written for the spreadsheet that will actually open it: semicolon separator
and a BOM, because Excel in a Russian locale reads a comma-separated UTF-8
file as one column of mojibake and gives no hint why.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from decimal import Decimal

from gym_assistant.domain.models import BodyMeasurement, WorkoutSet
from gym_assistant.domain.units import Units, from_kg, label

BOM = "﻿"
DELIMITER = ";"


def set_columns(units: Units = Units.METRIC) -> tuple[str, ...]:
    return (
        "дата",
        "время",
        "упражнение",
        "группа_мышц",
        "подход",
        f"вес_{label(units)}",
        "повторы",
        "время_сек",
        "дистанция_м",
        "rpe",
        "разминка",
    )


def measurement_columns(units: Units = Units.METRIC) -> tuple[str, ...]:
    return (
        "дата",
        f"вес_{label(units)}",
        "жир_процент",
        "грудь_см",
        "талия_см",
        "бёдра_см",
        "бицепс_см",
        "бедро_см",
        "заметка",
    )


def _write(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=DELIMITER, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return (BOM + buffer.getvalue()).encode("utf-8")


def _weight(value: Decimal | None, units: Units) -> Decimal | None:
    return None if value is None else from_kg(value, units)


def sets_to_csv(sets: Sequence[WorkoutSet], units: Units = Units.METRIC) -> bytes:
    rows = [
        (
            item.performed_at.date().isoformat(),
            item.performed_at.strftime("%H:%M"),
            item.exercise.name_ru if item.exercise else "",
            item.exercise.primary_muscle_group.name_ru if item.exercise else "",
            item.set_index,
            _weight(item.weight_kg, units),
            item.reps,
            item.duration_sec,
            item.distance_m,
            item.rpe,
            "да" if item.is_warmup else "",
        )
        for item in sets
    ]
    return _write(set_columns(units), rows)


def measurements_to_csv(
    measurements: Sequence[BodyMeasurement], units: Units = Units.METRIC
) -> bytes:
    rows = [
        (
            item.measured_at.date().isoformat(),
            _weight(item.weight_kg, units),
            item.body_fat_pct,
            item.chest_cm,
            item.waist_cm,
            item.hip_cm,
            item.biceps_cm,
            item.thigh_cm,
            item.note,
        )
        for item in measurements
    ]
    return _write(measurement_columns(units), rows)
