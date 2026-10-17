"""Shared test fixtures.

`client` gives you the app. `client_as(role)` gives you a client that is logged
in as a seeded user of that role, so access-control tests stay one line:

    def test_editor_cannot_manage_users(client_as):
        assert client_as("editor").get("/admin/users").status_code in (302, 403)

Every test gets its own empty SQLite database (through `CMS_DATABASE`) holding
only the DEMO_USERS below.
"""
from __future__ import annotations

import re

import pytest
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


def add_user(**fields) -> None:
    """Arrange an extra account (until the Users page exists to make one)."""
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
