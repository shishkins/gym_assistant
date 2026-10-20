"""The arithmetic and the wording around a body-fat band, without a model."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from gym_assistant.ai.body import MAX_OBSERVATIONS, PROMPT_VERSION, parse
from gym_assistant.bot.texts import render, ru
from gym_assistant.domain import body
from gym_assistant.domain.body import Band, Trend, composition, is_low, trend, weight_is_fresh
from gym_assistant.domain.models import BodyEstimate, Sex
from gym_assistant.domain.services import WeighIn

D = Decimal
NOW = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)


def _band(low: str, likely: str, high: str) -> Band:
    return Band(D(low), D(likely), D(high))


# --- kilograms ------------------------------------------------------------


def test_fat_and_lean_mass_follow_the_band() -> None:
    mass = composition(_band("15", "18", "22"), D("80"), 180)

    assert (mass.fat_kg.low, mass.fat_kg.likely, mass.fat_kg.high) == (
        D("12.0"),
        D("14.4"),
        D("17.6"),
    )
    # The low fat mass goes with the HIGH lean mass, and vice versa.
    assert (mass.lean_kg.low, mass.lean_kg.likely, mass.lean_kg.high) == (
        D("62.4"),
        D("65.6"),
        D("68.0"),
    )


def test_ffmi_is_lean_mass_over_height_squared() -> None:
    mass = composition(_band("15", "18", "22"), D("80"), 180)

    # 65.6 / 1.8^2 = 20.247; at exactly 1.80 m the normalisation adds nothing.
    assert mass.ffmi == D("20.2")
    assert mass.ffmi == mass.ffmi_normalized


def test_ffmi_normalisation_lifts_a_tall_person_and_lowers_a_short_one() -> None:
    """Kouri 1995: + 6.1 per metre below 1.80, - above."""
    tall = composition(_band("15", "15", "15"), D("90"), 195)
    short = composition(_band("15", "15", "15"), D("60"), 165)

    assert tall.ffmi is not None and tall.ffmi_normalized is not None
    assert short.ffmi is not None and short.ffmi_normalized is not None
    assert tall.ffmi_normalized < tall.ffmi
    assert short.ffmi_normalized > short.ffmi
    # 6.1 * 0.15 = 0.915 either way, give or take the rounding.
    assert abs((short.ffmi_normalized - short.ffmi) - D("0.9")) <= D("0.1")


def test_no_height_means_no_ffmi_rather_than_a_guess() -> None:
    mass = composition(_band("15", "18", "22"), D("80"), None)

    assert mass.ffmi is None and mass.ffmi_normalized is None
    assert mass.fat_kg.likely == D("14.4")


# --- the band itself ------------------------------------------------------


def test_a_band_out_of_order_is_sorted_rather_than_refused() -> None:
    band = Band.ordered(D("14"), D("12"), D("18"))

    assert (band.low, band.likely, band.high) == (D("12"), D("14"), D("18"))


def test_a_band_outside_human_range_is_not_plausible() -> None:
    assert _band("12", "15", "19").plausible
    assert not _band("1", "2", "4").plausible
    assert not _band("50", "60", "75").plausible


# --- what may be said about a change --------------------------------------


def test_a_change_smaller_than_the_noise_is_no_change() -> None:
    before = _band("15", "18", "22")

    assert trend(before, _band("14", "16", "20")) is Trend.SAME
    assert trend(before, _band("17", "20", "24")) is Trend.SAME


def test_a_change_at_the_noise_bar_is_reported_in_its_direction() -> None:
    before = _band("15", "18", "22")
    noise = body.NOISE_PP

    assert trend(before, _band("12", str(D(18) - noise), "19")) is Trend.DOWN
    assert trend(before, _band("18", str(D(18) + noise), "25")) is Trend.UP


def test_low_fat_is_judged_per_sex_and_strictly_without_one() -> None:
    lean_man = _band("7", "9", "12")
    lean_woman = _band("14", "16", "19")

    assert is_low(lean_man, Sex.MALE)
    assert is_low(lean_woman, Sex.FEMALE)
    assert not is_low(lean_woman, Sex.MALE)
    # Sex unknown: the higher floor, so "stop cutting" errs towards caution.
    assert is_low(lean_woman, None)


def test_a_weigh_in_two_weeks_from_the_photo_still_counts_and_three_do_not() -> None:
    assert weight_is_fresh(NOW - timedelta(days=14), NOW)
    assert weight_is_fresh(NOW + timedelta(days=2), NOW)
    assert not weight_is_fresh(NOW - timedelta(days=21), NOW)


# --- reading the model's answer -------------------------------------------


def _answer(**overrides: object) -> str:
    payload: dict[str, object] = {
        "kind": "body",
        "usable": True,
        "bf_low": 15,
        "bf_likely": 18.04,
        "bf_high": 22,
        "observations": ["пресс угадывается", "небольшие бока"],
        "limits": "",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_a_body_answer_becomes_an_estimate() -> None:
    reading = parse(_answer(), model="claude-sonnet-5")

    assert reading.is_estimate
    assert reading.band == Band(D("15.0"), D("18.0"), D("22.0"))
    assert reading.prompt_version == PROMPT_VERSION
    assert reading.limits is None, "empty limits are absence, not an empty line"


def test_a_photo_of_something_else_is_not_an_estimate() -> None:
    reading = parse(_answer(kind="other"), model="claude-sonnet-5")

    assert not reading.is_estimate
    assert reading.band is None


def test_an_impossible_band_is_not_an_estimate() -> None:
    reading = parse(_answer(bf_low=1, bf_likely=2, bf_high=3), model="claude-sonnet-5")

    assert not reading.is_estimate


def test_observations_are_trimmed_and_capped() -> None:
    many = ["  видно пресс  ", "", *[f"наблюдение {n}" for n in range(10)]]
    reading = parse(_answer(observations=many), model="claude-sonnet-5")

    assert reading.observations[0] == "видно пресс"
    assert "" not in reading.observations
    assert len(reading.observations) == MAX_OBSERVATIONS


# --- the message ----------------------------------------------------------


def _estimate(likely: str = "18", *, observations: list[str] | None = None) -> BodyEstimate:
    return BodyEstimate(
        user_id=1,
        measured_at=NOW,
        photo_file_id="f",
        bf_low=D(likely) - 3,
        bf_likely=D(likely),
        bf_high=D(likely) + 4,
        observations=observations or [],
        limits=None,
        model="claude-sonnet-5",
        prompt_version=PROMPT_VERSION,
    )


def test_the_message_shows_a_band_and_never_calls_lean_mass_muscle() -> None:
    text = render.render_body_estimate(
        _estimate(),
        weigh_in=WeighIn(D("80"), NOW, fresh=True),
        height_cm=180,
        sex=Sex.MALE,
        previous=None,
    )

    assert "15–22%" in text
    assert "тощая масса" in text
    assert "мышечная масса" not in text.lower()
    assert ru.BODY_ACCURACY in text


def test_the_models_words_are_escaped_before_they_reach_html() -> None:
    text = render.render_body_estimate(
        _estimate(observations=["талия <80 см & сухая"]),
        weigh_in=None,
        height_cm=None,
        sex=Sex.MALE,
        previous=None,
    )

    assert "&lt;80 см &amp; сухая" in text
    assert "<80" not in text


def test_a_stale_weight_is_not_turned_into_kilograms() -> None:
    text = render.render_body_estimate(
        _estimate(),
        weigh_in=WeighIn(D("80"), NOW - timedelta(days=60), fresh=False),
        height_cm=180,
        sex=Sex.MALE,
        previous=None,
    )

    assert "тощая масса —" not in text
    assert "слишком далеко" in text


def test_low_fat_turns_into_advice_to_stop_losing() -> None:
    text = render.render_body_estimate(
        _estimate("8"), weigh_in=None, height_cm=None, sex=Sex.MALE, previous=None
    )

    assert ru.BODY_LOW_FAT in text
