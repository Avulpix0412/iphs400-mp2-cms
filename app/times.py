"""Showing stored times in Beijing time.

Every time is stored in UTC, as SQLite writes it ("2026-10-17 13:05:42.123",
or without the milliseconds for CURRENT_TIMESTAMP columns), and compared as
stored: the dashboard's "changes not yet on the site" count depends on that.
Only what the console and the site show is converted, by these two functions,
which both template environments register as filters (`|beijing_time`,
`|beijing_date`), so no page prints a stored time as it is.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

# Asia/Shanghai. China has kept UTC+8 all year since 1991, so a fixed offset
# gives the same times without needing the tz database (absent on Windows).
BEIJING = timezone(timedelta(hours=8), "北京时间")


def _in_beijing(stored: str | None, layout: str) -> str:
    """`stored` in Beijing time, laid out by strftime `layout`. A time never
    set (NULL) shows as nothing rather than breaking the page."""
    if not stored:
        return ""
    return (datetime.fromisoformat(stored).replace(tzinfo=UTC)
            .astimezone(BEIJING).strftime(layout))


def beijing_time(stored: str | None) -> str:
    """A stored UTC time as Beijing time to the minute: "2026-10-17 21:05"."""
    return _in_beijing(stored, "%Y-%m-%d %H:%M")


def beijing_date(stored: str | None) -> str:
    """The Beijing date of a stored UTC time: "2026-10-18" for 17:30 UTC on
    the 17th."""
    return _in_beijing(stored, "%Y-%m-%d")


FILTERS = {"beijing_time": beijing_time, "beijing_date": beijing_date}
