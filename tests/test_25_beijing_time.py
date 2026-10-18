"""#25: every console and site time is shown in Beijing time, stored in UTC.

SQLite stamps every time itself, so no console action can store a chosen one.
The day-crossing cases call the one conversion function directly (a seam the
user agreed to for this ticket); the pages are checked at Seams 1 and 2 against
the clock."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app import settings, times
from app.publish import render_site
from test_t03_guides import admin, editor, new_guide, save  # noqa: F401
from test_t04_site_build import followed, page, site  # noqa: F401
from test_t04_site_build import published_guide as published_guide_on_site
from test_t05_review import notes_section, published_guide, review, submitted_guide
from test_t06_revisions_trash import delete, submitted_revision
from test_t08_pages_tournaments import new_page, new_tournament_item
from test_t09_users import ADMIN, account_page, user_row


def test_a_utc_time_is_shown_eight_hours_later_to_the_minute():
    assert times.beijing_time("2026-10-17 13:05:42.123") == "2026-10-17 21:05"


def test_a_time_stored_without_milliseconds_is_shown_the_same_way():
    assert times.beijing_time("2026-10-17 13:05:42") == "2026-10-17 21:05"


def test_a_guide_updated_late_in_the_utc_day_is_dated_the_next_beijing_day():
    assert times.beijing_date("2026-10-17 17:30:00.000") == "2026-10-18"
    assert times.beijing_time("2026-12-31 16:00:00") == "2027-01-01 00:00"


def test_a_time_just_before_beijing_midnight_keeps_its_day():
    assert times.beijing_date("2026-10-17 15:59:59.999") == "2026-10-17"


# What a console page shows: any date and time, with or without seconds.
SHOWN_TIME = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d(?:\.\d+)?)?")


@pytest.fixture
def started() -> datetime:
    """A minute before the test began. Fixtures listed ahead of this one (the
    Admin signing in, say) may already have stamped a time."""
    return datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)


def beijing_minutes_since(start: datetime) -> set[str]:
    """Every minute from `start` until now, as a Beijing wall clock reads it.
    Worked out from the system clock and the UTC+8 offset, not by the app."""
    clock = timezone(timedelta(hours=8))
    minutes, minute = set(), start
    while minute <= datetime.now(UTC):
        minutes.add(minute.astimezone(clock).strftime("%Y-%m-%d %H:%M"))
        minute += timedelta(minutes=1)
    return minutes


def times_on(page: str) -> list[str]:
    shown = SHOWN_TIME.findall(page)
    assert shown, "page shows no time"
    return shown


def assert_beijing_now(page: str, started: datetime) -> None:
    """Every time on `page` is a Beijing time stamped during this test, to the
    minute: not UTC, and with no seconds or milliseconds."""
    allowed = beijing_minutes_since(started)
    for shown in times_on(page):
        assert shown in allowed, f"{shown} is not Beijing time now ({sorted(allowed)})"


def test_the_guide_editor_and_content_list_show_beijing_time(editor, started):
    edit_page = new_guide(editor)
    assert_beijing_now(editor.get(edit_page).text, started)
    assert_beijing_now(editor.get("/admin/guides").text, started)


def test_the_review_queue_on_the_dashboard_shows_beijing_time(editor, admin, started):
    submitted_guide(editor)
    assert_beijing_now(admin.get("/admin/dashboard").text, started)


def test_review_notes_say_when_the_return_happened_in_beijing_time(
        editor, admin, started):
    edit_page = submitted_guide(editor)
    assert review(admin, edit_page, "return", [("先拿船", "写清楚为什么。")]).status_code == 303
    top = notes_section(editor.get(edit_page).text)
    assert "退回" in top
    assert_beijing_now(top, started)


def test_a_revision_and_its_changed_guide_warning_show_beijing_time(
        editor, admin, started):
    edit_page = published_guide(editor, admin)
    revision = submitted_revision(editor, edit_page, title_zh="修订后的标题")
    save(admin, edit_page, title_zh="管理员改过的标题")

    for c, screen in [(editor, revision),
                      (admin, f"{revision.removesuffix('/edit')}/review")]:
        page = c.get(screen).text
        assert "修订打开之后" in page
        assert_beijing_now(page, started)


def test_the_trash_says_when_each_guide_was_deleted_in_beijing_time(
        editor, admin, started):
    delete(editor, new_guide(editor))
    assert_beijing_now(admin.get("/admin/trash").text, started)


def test_the_users_pages_show_the_last_login_in_beijing_time(admin, started):
    assert_beijing_now(user_row(admin, ADMIN), started)
    assert_beijing_now(admin.get(account_page(admin, ADMIN)).text, started)


def test_page_and_tournament_item_screens_show_beijing_time(admin, started):
    edit_page = new_page(admin)
    assert_beijing_now(admin.get(edit_page).text, started)
    assert_beijing_now(admin.get("/admin/pages").text, started)
    assert_beijing_now(admin.get(new_tournament_item(admin)).text, started)


def beijing_dates_since(start: datetime) -> set[str]:
    return {minute[:10] for minute in beijing_minutes_since(start)}


def test_guide_dates_on_the_site_are_beijing_dates_in_both_languages(
        admin, site, started):
    """Only fails on the old code between 00:00 and 08:00 Beijing time, when
    the UTC date is a day behind; the day-crossing tests above cover the rest."""
    slug = published_guide_on_site(admin, title_en="Pirate Vanessa", body_en="Ships first.")
    render_site(site)
    allowed = beijing_dates_since(started)
    for lang in ("zh", "en"):
        for path in ["", "guides/", f"guides/{slug}/", "heroes/vanessa/",
                     followed(site, f"{lang}/guides/{slug}/",
                              r'href="([./]*authors/\d+/)"').removeprefix(f"{lang}/")]:
            shown = re.findall(r"\d{4}-\d\d-\d\d(?: \d\d:\d\d\S*)?", page(site, f"{lang}/{path}"))
            assert shown, f"no date on {lang}/{path}"
            assert set(shown) <= allowed, f"{lang}/{path} shows {shown}, not {allowed}"


@pytest.mark.parametrize("screen", ["/admin/guides", "/admin/trash", "/admin/dashboard"])
def test_wide_console_tables_scroll_sideways_on_a_phone(editor, admin, screen):
    submitted_guide(editor)  # so the dashboard has a review queue
    page = admin.get(screen).text
    assert re.search(r'<div class="scroll">\s*<table>.*?</table>\s*</div>', page, re.DOTALL), \
        f"the table on {screen} is not inside the scrolling container"


def test_no_template_prints_a_stored_time_without_converting_it():
    """Every stored time is a field named `…_at`; printing one raw would show
    UTC with milliseconds. This keeps a new page from doing so by accident."""
    unconverted = [f"{file.relative_to(settings.TEMPLATES)}: {{{{{expression}}}}}"
                   for file in sorted(settings.TEMPLATES.rglob("*.html"))
                   for expression in re.findall(r"\{\{(.*?)\}\}", file.read_text(), re.DOTALL)
                   if re.search(r"\w_at\b", expression)
                   and not re.search(r"\|\s*beijing_(time|date)\b", expression)]
    assert not unconverted, unconverted


def test_a_missing_time_shows_nothing_rather_than_breaking_the_page():
    assert times.beijing_time(None) == "" and times.beijing_date(None) == ""
