"""Exporting a user's own data as CSV.

Written for the spreadsheet that will actually open it: semicolon separator
and a BOM, because Excel in a Russian locale reads a comma-separated UTF-8
file as one column of mojibake and gives no hint why.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from gym_assistant.domain.models import BodyMeasurement, WorkoutSet

BOM = "﻿"
DELIMITER = ";"

SET_COLUMNS = (
    "дата",
    "время",
    "упражнение",
    "группа_мышц",
    "подход",
    "вес_кг",
    "повторы",
    "время_сек",
    "дистанция_м",
    "rpe",
    "разминка",
)

MEASUREMENT_COLUMNS = (
    "дата",
    "вес_кг",
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


def sets_to_csv(sets: Sequence[WorkoutSet]) -> bytes:
    rows = [
        (
            item.performed_at.date().isoformat(),
            item.performed_at.strftime("%H:%M"),
            item.exercise.name_ru if item.exercise else "",
            item.exercise.primary_muscle_group.name_ru if item.exercise else "",
            item.set_index,
            item.weight_kg,
            item.reps,
            item.duration_sec,
            item.distance_m,
            item.rpe,
            "да" if item.is_warmup else "",
        )
        for item in sets
    ]
    return _write(SET_COLUMNS, rows)


def measurements_to_csv(measurements: Sequence[BodyMeasurement]) -> bytes:
    rows = [
        (
            item.measured_at.date().isoformat(),
            item.weight_kg,
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
    return _write(MEASUREMENT_COLUMNS, rows)
