"""Shared test fixtures.

`client` gives you the app. `client_as(role)` gives you a client that is logged
in as a seeded user of that role, so access-control tests stay one line:

    def test_editor_cannot_manage_users(client_as):
        assert client_as("editor").get("/admin/users").status_code in (302, 403)

Every test gets its own empty SQLite database (through `CMS_DATABASE`) holding
only the DEMO_USERS below. The Site build writes into a temporary folder, and
its deploy step is replaced, so no test ever pushes to gh-pages.
"""
from __future__ import annotations

import os

# A CMS_ENV exported in the shell must not change how the app imports.
os.environ.pop("CMS_ENV", None)

import re

import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

# Matches scripts/seed_demo.py. Passwords come from the environment there; in
# tests they are fixed and meaningless.
DEMO_USERS = {
    "admin": {"email": "admin@example.test", "password": "test-admin-pw",
              "display_name": "演示管理员"},
    "editor": {"email": "editor@example.test", "password": "test-editor-pw",
               "display_name": "演示编辑"},
}


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """A fresh database per test, seeded with DEMO_USERS."""
    from app import accounts, db

    monkeypatch.setenv("CMS_DATABASE", str(tmp_path / "cms.db"))
    with db.connect() as conn:
        for role, user in DEMO_USERS.items():
            accounts.create_user(conn, email=user["email"],
                                 password=user["password"], role=role,
                                 display_name=user["display_name"])
    return tmp_path / "cms.db"


@pytest.fixture(autouse=True)
def deploys(tmp_path, monkeypatch) -> list[Path]:
    """The folders the Site build deployed, in order. A test can replace
    `app.publish.deploy` again to make the push fail."""
    from app import publish, settings

    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    pushed: list[Path] = []
    monkeypatch.setattr(publish, "deploy", lambda out, *_: pushed.append(out))
    return pushed


class FakeClock:
    """A clock that stands still until the test moves it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def login_clock(monkeypatch) -> FakeClock:
    """Every test starts with no failed logins counted, on a clock it can
    move with `login_clock.advance(seconds)`."""
    from app import accounts

    clock = FakeClock()
    monkeypatch.setattr(accounts, "login_limiter",
                        accounts.LoginLimiter(clock=clock))
    return clock


def add_user(**fields) -> None:
    """Arrange an extra account directly, in any state, with its setup done
    (quicker than making it on the Users page, which T09's tests do)."""
    from app import accounts, db

    with db.connect() as conn:
        accounts.create_user(conn, **fields)


def csrf_token(page_html: str) -> str:
    """Pull the CSRF token out of a rendered console form."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', page_html)
    assert match, "page has no CSRF token"
    return match.group(1)


def login(c: TestClient, email: str, password: str):
    """Submit the login form the way a browser does, token included."""
    token = csrf_token(c.get("/login").text)
    return c.post("/login", data={"email": email, "password": password,
                                  "csrf_token": token},
                  follow_redirects=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def client_as():
    """Return a factory: client_as("editor") -> a logged-in TestClient."""

    def _login(role: str) -> TestClient:
        user = DEMO_USERS[role]
        c = TestClient(create_app())
        if c.get("/login").status_code == 404:
            pytest.skip("No /login route yet — build the login ticket first.")
        response = login(c, user["email"], user["password"])
        assert response.status_code in (200, 302, 303), (
            f"Login as {role} failed with {response.status_code}")
        return c

    return _login
