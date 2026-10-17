"""T02: the seed script adds demo Heroes and Patches (Seam 2: the seed script,
checked through the console)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import DEMO_USERS, login
from test_t01_seed import run_seed

ENV = {"CMS_ADMIN_PASSWORD": "from-env-admin",
       "CMS_EDITOR_PASSWORD": "from-env-editor"}


def seeded_admin(tmp_path, monkeypatch, times: int = 1) -> TestClient:
    seeded_db = tmp_path / "seeded.db"
    for _ in range(times):
        result = run_seed({"CMS_DATABASE": str(seeded_db), **ENV})
        assert result.returncode == 0, result.stdout + result.stderr
    monkeypatch.setenv("CMS_DATABASE", str(seeded_db))
    admin = TestClient(create_app())
    login(admin, DEMO_USERS["admin"]["email"], "from-env-admin")
    return admin


def test_seed_creates_demo_heroes_and_patches_with_the_newest_current(
        tmp_path, monkeypatch):
    admin = seeded_admin(tmp_path, monkeypatch)

    heroes = admin.get("/admin/heroes").text
    assert "<td>瓦妮莎</td><td>Vanessa</td><td><code>vanessa</code></td>" in heroes
    assert heroes.count("/edit\"") >= 3
    patches = admin.get("/admin/patches").text
    assert "<td>6.7（当前版本）</td>" in patches
    assert "<td>6.6</td>" in patches and "<td>6.5</td>" in patches


def test_seeding_twice_adds_no_duplicate_heroes_or_patches(tmp_path, monkeypatch):
    admin = seeded_admin(tmp_path, monkeypatch, times=2)
    assert admin.get("/admin/heroes").text.count("<td>Vanessa</td>") == 1
    patches = admin.get("/admin/patches").text
    assert patches.count("<td>6.5") == 1
    assert "<td>6.7（当前版本）</td>" in patches
