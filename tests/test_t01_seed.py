"""T01: the seed script creates one Admin and one Editor from the environment."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import DEMO_USERS, login

ROOT = Path(__file__).resolve().parents[1]


def run_seed(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items()
             if k not in ("CMS_ADMIN_PASSWORD", "CMS_EDITOR_PASSWORD")}
    return subprocess.run([sys.executable, "scripts/seed_demo.py"], cwd=ROOT,
                          env=clean | env, capture_output=True, text=True)


def test_seed_refuses_to_run_without_both_passwords(tmp_path, monkeypatch):
    seeded_db = tmp_path / "seeded.db"
    result = run_seed({"CMS_DATABASE": str(seeded_db),
                       "CMS_ADMIN_PASSWORD": "only-the-admin-pw"})
    assert result.returncode != 0
    assert "CMS_EDITOR_PASSWORD" in result.stdout + result.stderr

    monkeypatch.setenv("CMS_DATABASE", str(seeded_db))
    c = TestClient(create_app())
    assert login(c, DEMO_USERS["admin"]["email"], "only-the-admin-pw").status_code == 401


def test_seeded_admin_and_editor_log_in_with_the_passwords_from_the_environment(
        tmp_path, monkeypatch):
    seeded_db = tmp_path / "seeded.db"
    result = run_seed({"CMS_DATABASE": str(seeded_db),
                       "CMS_ADMIN_PASSWORD": "from-env-admin",
                       "CMS_EDITOR_PASSWORD": "from-env-editor"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "from-env" not in result.stdout + result.stderr

    monkeypatch.setenv("CMS_DATABASE", str(seeded_db))
    for role, password in [("admin", "from-env-admin"), ("editor", "from-env-editor")]:
        c = TestClient(create_app())
        response = login(c, DEMO_USERS[role]["email"], password)
        assert response.headers["location"] == "/admin/dashboard"
        assert DEMO_USERS[role]["display_name"] in c.get("/admin/dashboard").text


def test_seeding_twice_is_harmless(tmp_path):
    env = {"CMS_DATABASE": str(tmp_path / "seeded.db"),
           "CMS_ADMIN_PASSWORD": "from-env-admin",
           "CMS_EDITOR_PASSWORD": "from-env-editor"}
    assert run_seed(env).returncode == 0
    assert run_seed(env).returncode == 0
