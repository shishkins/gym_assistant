"""Where one day ends and the next begins.

Every timestamp is stored in UTC and stays that way. What depends on the
zone is grouping: which day a set belongs to, which week, what "today" and
"yesterday" mean. Before this module the ``TIMEZONE`` setting existed and
nothing read it, so in Vietnam a 06:00 Monday session was filed under the
previous week and this morning's sets were shown as "yesterday".

One zone for the whole bot, set once at startup from settings - see the note
on ``Settings.timezone`` for why not per user. It defaults to UTC, which is
what tests run in unless they say otherwise.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

_zone: ZoneInfo = ZoneInfo("UTC")


def configure(name: str) -> None:
    """Sets the zone. An unknown name raises here, at startup, not at 3am."""
    global _zone
    _zone = ZoneInfo(name)


def zone() -> ZoneInfo:
    return _zone


def zone_name() -> str:
    """For SQL: ``timezone(<name>, column)`` cuts days where people live."""
    return _zone.key


def local(moment: datetime) -> datetime:
    """A stored moment in local time. A naive one is taken to be UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_zone)


def local_date(moment: datetime) -> date:
    return local(moment).date()


def now() -> datetime:
    return datetime.now(_zone)


def today() -> date:
    return now().date()
