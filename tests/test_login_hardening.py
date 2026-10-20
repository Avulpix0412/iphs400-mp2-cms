"""Login hardening: a refused login never tells whether the email has an
account (Seam 1: the console over HTTP)."""
from __future__ import annotations

import re

import pytest

from conftest import DEMO_USERS, add_user, csrf_token, login

UNKNOWN_EMAIL = "nobody@example.test"


def alert(page_html: str) -> str:
    """The error message the login page shows."""
    match = re.search(r'role="alert">([^<]*)<', page_html)
    assert match, "page shows no error"
    return match.group(1)


def deactivated_editor() -> str:
    add_user(email="gone@example.test", password="gone-pw-123", role="editor",
             display_name="离开的编辑", state="deactivated")
    return "gone@example.test"


@pytest.mark.parametrize("known_email", [
    lambda: DEMO_USERS["admin"]["email"],
    lambda: DEMO_USERS["editor"]["email"],
    deactivated_editor,
], ids=["admin", "editor", "deactivated"])
def test_wrong_password_and_unknown_email_get_the_same_status_and_message(
        client, known_email):
    wrong_password = login(client, known_email(), "not-the-password")
    unknown_email = login(client, UNKNOWN_EMAIL, "not-the-password")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert alert(wrong_password.text) == alert(unknown_email.text) == "邮箱或密码错误。"


# Rate-limiting, keyed on the email: five failures within 15 minutes and that
# email is refused, whatever the password, until the window has passed.

LOCKED_OUT = "登录失败次数过多，请 15 分钟后再试。"
EDITOR = DEMO_USERS["editor"]


def fail_five_times(client, email: str) -> None:
    for _ in range(5):
        assert login(client, email, "not-the-password").status_code == 401


def test_a_sixth_attempt_is_refused_even_with_the_right_password(client):
    fail_five_times(client, EDITOR["email"])

    sixth = login(client, EDITOR["email"], EDITOR["password"])

    assert sixth.status_code == 429
    assert alert(sixth.text) == LOCKED_OUT


def test_the_right_password_works_again_once_15_minutes_have_passed(
        client, login_clock):
    fail_five_times(client, EDITOR["email"])

    login_clock.advance(15 * 60 - 1)
    assert login(client, EDITOR["email"], EDITOR["password"]).status_code == 429
    login_clock.advance(1)
    assert login(client, EDITOR["email"], EDITOR["password"]).status_code == 303


def test_a_locked_out_email_does_not_stop_another_from_logging_in(client):
    admin = DEMO_USERS["admin"]
    fail_five_times(client, EDITOR["email"])

    assert login(client, admin["email"], admin["password"]).status_code == 303


def test_a_successful_login_clears_the_failures_before_it(client):
    for _ in range(4):
        login(client, EDITOR["email"], "not-the-password")
    assert login(client, EDITOR["email"], EDITOR["password"]).status_code == 303
    login(client, EDITOR["email"], "not-the-password")

    assert login(client, EDITOR["email"], EDITOR["password"]).status_code == 303


def test_guesses_sent_all_at_once_still_get_only_five_tries():
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.main import create_app

    clients = [TestClient(create_app()) for _ in range(10)]
    tokens = [csrf_token(c.get("/login").text) for c in clients]

    def guess(i: int) -> int:
        return clients[i].post("/login", data={
            "email": EDITOR["email"], "password": f"guess-{i}",
            "csrf_token": tokens[i]}, follow_redirects=False).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = sorted(pool.map(guess, range(10)))

    assert statuses == [401] * 5 + [429] * 5
