"""What a body-fat band means in kilograms, and what may be said about it.

Pure arithmetic over one estimate and one weigh-in. The estimate comes from a
photo and is the weak link - so everything here carries the band through
rather than collapsing it to the middle, and the comparison with an earlier
estimate refuses to call a change that the band cannot see.

Accuracy this rests on, from the research done before writing it (sources in
SPEC section 19, revision of 2026-10-20):

* No peer-reviewed study has tested a general vision model such as this one
  against DEXA. Models trained for exactly this job reach about 3-4.5
  percentage points of error on uncontrolled photos and are worst at the
  extremes. A general model is not expected to do better.
* The US Navy tape method, the usual cheap alternative, is off DEXA by a
  similar 2.5-6 points for men and was found unfit for tracking change over
  eight weeks.

Hence the two rules that shape this module: show a band, never a single
number; and treat any change smaller than :data:`NOISE_PP` as no change.

"Lean mass" here is everything that is not fat - water, bone, organs and
muscle together. It is never called muscle: telling someone they gained
"two kilograms of muscle" off a photo would be inventing a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from gym_assistant.domain.models import Sex

# A change in body fat smaller than this, between two photo estimates, is
# inside what the method cannot tell apart. Three points is the low end of the
# measured error of photo models built for this task; a general model is not
# better, so the bar is not lower.
NOISE_PP = Decimal(3)

# A weigh-in older than this no longer describes the body in the photo. Two
# weeks of a normal cut moves weight by a kilogram or more.
WEIGHT_FRESH_FOR = timedelta(days=14)

# Below these, the safe advice is to stop losing, not to lose more. Essential
# fat is roughly 3-5% for men and 10-13% for women; the margins on top are
# the same as in SPEC 20.2, where the bot's other safety floors live.
LOW_FAT_PP = {Sex.MALE: Decimal(10), Sex.FEMALE: Decimal(18)}

# What the model may answer at all. Anything outside is a misread, not a body.
MIN_PLAUSIBLE_PP = Decimal(3)
MAX_PLAUSIBLE_PP = Decimal(60)

# Kouri et al. 1995: FFMI normalised to a height of 1.80 m, so tall and short
# people can be compared on one scale.
FFMI_REFERENCE_M = Decimal("1.8")
FFMI_HEIGHT_SLOPE = Decimal("6.1")

ONE = Decimal("0.1")


class Trend(StrEnum):
    DOWN = "down"
    UP = "up"
    SAME = "same"


@dataclass(frozen=True, slots=True)
class Band:
    """Low, likely and high body fat, in percent of body weight."""

    low: Decimal
    likely: Decimal
    high: Decimal

    @classmethod
    def ordered(cls, low: Decimal, likely: Decimal, high: Decimal) -> Band:
        """A band that contains its own centre.

        The model now and then returns 14-12-18. Sorting is cheaper than
        refusing the reading, and it changes nothing a careful reader would
        have trusted anyway.
        """
        low, likely, high = sorted((low, likely, high))
        return cls(low=low, likely=likely, high=high)

    @property
    def plausible(self) -> bool:
        return self.low >= MIN_PLAUSIBLE_PP and self.high <= MAX_PLAUSIBLE_PP

    @property
    def width(self) -> Decimal:
        return self.high - self.low


@dataclass(frozen=True, slots=True)
class Composition:
    """One estimate turned into kilograms.

    Every mass is a band too: the low fat mass goes with the high lean mass.
    """

    band: Band
    weight_kg: Decimal
    fat_kg: Band
    lean_kg: Band
    ffmi: Decimal | None
    ffmi_normalized: Decimal | None


def _round(value: Decimal) -> Decimal:
    return value.quantize(ONE, rounding=ROUND_HALF_UP)


def composition(band: Band, weight_kg: Decimal, height_cm: int | None) -> Composition:
    """Fat and lean mass from a fat band and a weight.

    FFMI is lean kilograms over height squared - the same idea as BMI, with
    the fat taken out, which is what makes it mean something for a lifter.
    It is computed from the likely band only: a band of an index of a band
    reads as precision nobody has.
    """
    fat = Band(
        low=_round(weight_kg * band.low / 100),
        likely=_round(weight_kg * band.likely / 100),
        high=_round(weight_kg * band.high / 100),
    )
    lean = Band(
        low=_round(weight_kg - fat.high),
        likely=_round(weight_kg - fat.likely),
        high=_round(weight_kg - fat.low),
    )

    ffmi: Decimal | None = None
    normalized: Decimal | None = None
    if height_cm:
        height_m = Decimal(height_cm) / 100
        raw = lean.likely / (height_m * height_m)
        ffmi = _round(raw)
        normalized = _round(raw + FFMI_HEIGHT_SLOPE * (FFMI_REFERENCE_M - height_m))

    return Composition(
        band=band,
        weight_kg=weight_kg,
        fat_kg=fat,
        lean_kg=lean,
        ffmi=ffmi,
        ffmi_normalized=normalized,
    )


def weight_is_fresh(weighed_at: datetime, photo_at: datetime) -> bool:
    """Whether a weigh-in can stand for the body in a photo.

    Either side of the photo counts: someone who weighs in the morning after
    taking the picture the night before has a perfectly good weight.
    """
    return abs(photo_at - weighed_at) <= WEIGHT_FRESH_FOR


def trend(previous: Band, current: Band) -> Trend:
    """Whether body fat moved, by more than the method can see.

    Compares the likely values against :data:`NOISE_PP`. Two estimates
    a point apart are the same estimate read twice; saying "down by one
    percent" would be reporting the model's mood.
    """
    delta = current.likely - previous.likely
    if delta <= -NOISE_PP:
        return Trend.DOWN
    if delta >= NOISE_PP:
        return Trend.UP
    return Trend.SAME


def is_low(band: Band, sex: Sex | None) -> bool:
    """Lean enough that further loss is the wrong advice.

    Judged on the likely value, not the generous end, and without a known sex
    on the higher, female floor. Both lean the same way on purpose: the cost
    of a wrong "stop cutting" is a pause, the cost of a wrong "keep going" is
    health.
    """
    floor = LOW_FAT_PP[sex] if sex is not None else LOW_FAT_PP[Sex.FEMALE]
    return band.likely < floor
