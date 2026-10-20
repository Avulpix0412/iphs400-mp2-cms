"""#42: production configuration. Each test is named after the acceptance step
it checks. The configuration checks take the environment as a dict, so most
tests never touch the real environment."""
from __future__ import annotations

import re
import secrets

import pytest

from app import settings

# What a correct production environment looks like; each test spoils one value.
PRODUCTION = {
    "CMS_ENV": "production",
    "CMS_SECRET_KEY": secrets.token_urlsafe(32),
    "CMS_ADMIN_EMAIL": "first-admin@example.test",
    "CMS_ADMIN_PASSWORD": secrets.token_urlsafe(16),
}


def refusal(env: dict[str, str]) -> str:
    with pytest.raises(settings.BadConfiguration) as refused:
        settings.check_configuration(env)
    return str(refused.value)


def test_step1_production_refuses_an_unset_secret_key():
    env = {k: v for k, v in PRODUCTION.items() if k != "CMS_SECRET_KEY"}
    assert "CMS_SECRET_KEY" in refusal(env)


@pytest.mark.parametrize("env", [{}, {"CMS_ENV": ""}, {"CMS_ENV": "development"}])
def test_step1_development_starts_with_nothing_set(env):
    settings.check_configuration(env)


@pytest.mark.parametrize("value", [settings.DEV_SECRET_KEY,
                                   "change-me-to-a-long-random-string"])
def test_step1_production_refuses_a_known_secret_key(value):
    assert "CMS_SECRET_KEY" in refusal(PRODUCTION | {"CMS_SECRET_KEY": value})


@pytest.mark.parametrize("missing", ["CMS_ADMIN_EMAIL", "CMS_ADMIN_PASSWORD"])
def test_step2_production_refuses_an_unset_admin_login(missing):
    env = {k: v for k, v in PRODUCTION.items() if k != missing}
    assert missing in refusal(env)


def test_step2_production_refuses_the_example_admin_password():
    assert "CMS_ADMIN_PASSWORD" in refusal(
        PRODUCTION | {"CMS_ADMIN_PASSWORD": "change-me-admin"})


def test_step2_a_correct_production_environment_is_accepted():
    settings.check_configuration(PRODUCTION)


def test_step2_every_problem_is_named_at_once():
    message = refusal({"CMS_ENV": "production"})
    for var in ("CMS_SECRET_KEY", "CMS_ADMIN_EMAIL", "CMS_ADMIN_PASSWORD"):
        assert var in message


@pytest.mark.parametrize("value", ["prod", "Production", "staging"])
def test_step1_an_unknown_cms_env_is_refused(value):
    assert "CMS_ENV" in refusal(PRODUCTION | {"CMS_ENV": value})


def test_step1_cms_serve_stops_before_serving_and_names_the_variable(
        tmp_path, monkeypatch, capsys):
    from app import cli

    monkeypatch.chdir(tmp_path)  # no .env here
    for key, value in PRODUCTION.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CMS_SECRET_KEY")
    served = []
    monkeypatch.setattr("uvicorn.run", lambda target, **_: served.append(target))

    assert cli.main(["serve"]) == 1
    assert served == []
    assert "CMS_SECRET_KEY" in capsys.readouterr().err


def test_step1_create_app_refuses_a_bad_production_environment(monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("CMS_ENV", "production")
    monkeypatch.setenv("CMS_SECRET_KEY", "")
    monkeypatch.delenv("CMS_SECRET_KEY")
    with pytest.raises(settings.BadConfiguration, match="CMS_SECRET_KEY"):
        create_app()


@pytest.mark.parametrize("mode", ["production", "prod"])
def test_step3_the_seed_script_refuses_outside_development_and_creates_nothing(
        tmp_path, mode):
    from test_t01_seed import run_seed

    seeded_db = tmp_path / "seeded.db"
    result = run_seed(PRODUCTION | {"CMS_ENV": mode,
                                    "CMS_DATABASE": str(seeded_db),
                                    "CMS_EDITOR_PASSWORD": secrets.token_urlsafe(16)})
    assert result.returncode != 0
    assert "CMS_ENV" in result.stdout + result.stderr
    assert not seeded_db.exists()


def start_app(monkeypatch, database, env=PRODUCTION):
    """Start the app on `database` with `env` (production unless it says
    otherwise)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("CMS_DATABASE", str(database))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def test_step4_an_empty_database_gets_one_admin_who_starts_with_setup(
        tmp_path, monkeypatch):
    from conftest import DEMO_USERS, csrf_token, login

    c = start_app(monkeypatch, tmp_path / "prod.db")
    response = login(c, PRODUCTION["CMS_ADMIN_EMAIL"],
                     PRODUCTION["CMS_ADMIN_PASSWORD"])
    assert response.headers["location"] == "/admin/setup"

    new_password = secrets.token_urlsafe(16)
    token = csrf_token(c.get("/admin/setup").text)
    response = c.post("/admin/setup", follow_redirects=False, data={
        "display_name": "站长", "password": new_password,
        "password_confirm": new_password, "csrf_token": token})
    assert response.headers["location"] == "/admin/dashboard"
    assert "站长" in c.get("/admin/dashboard").text
    assert c.get("/admin/users").status_code == 200  # an Admin, not an Editor

    for user in DEMO_USERS.values():
        assert login(c, user["email"], user["password"]).status_code == 401


def test_step4_a_later_start_adds_no_second_admin(tmp_path, monkeypatch):
    from conftest import login

    start_app(monkeypatch, tmp_path / "prod.db")
    later = PRODUCTION | {"CMS_ADMIN_EMAIL": "someone-else@example.test"}
    c = start_app(monkeypatch, tmp_path / "prod.db", later)
    assert login(c, later["CMS_ADMIN_EMAIL"],
                 later["CMS_ADMIN_PASSWORD"]).status_code == 401
    assert login(c, PRODUCTION["CMS_ADMIN_EMAIL"],
                 PRODUCTION["CMS_ADMIN_PASSWORD"]).status_code == 303


def test_step4_development_creates_no_admin_from_the_environment(
        tmp_path, monkeypatch):
    from conftest import login

    c = start_app(monkeypatch, tmp_path / "dev.db",
                            PRODUCTION | {"CMS_ENV": "development"})
    assert login(c, PRODUCTION["CMS_ADMIN_EMAIL"],
                 PRODUCTION["CMS_ADMIN_PASSWORD"]).status_code == 401


def test_step4_an_admin_email_that_belongs_to_an_editor_stops_startup(
        tmp_path, monkeypatch):
    from conftest import add_user

    monkeypatch.setenv("CMS_DATABASE", str(tmp_path / "prod.db"))
    add_user(email=PRODUCTION["CMS_ADMIN_EMAIL"], password=secrets.token_urlsafe(16),
             role="editor", display_name="编辑甲")
    with pytest.raises(settings.BadConfiguration, match="CMS_ADMIN_EMAIL"):
        start_app(monkeypatch, tmp_path / "prod.db")


def example_value(key: str) -> str:
    """`key`'s value in the committed .env.example."""
    text = (settings.ROOT / ".env.example").read_text(encoding="utf-8")
    match = re.search(rf"^{key}=(.*)$", text, re.MULTILINE)
    assert match, f"{key} is not in .env.example"
    return match.group(1)


def test_step1_production_refuses_the_secret_key_in_dot_env_example():
    key = example_value("CMS_SECRET_KEY")
    assert "CMS_SECRET_KEY" in refusal(PRODUCTION | {"CMS_SECRET_KEY": key})


def test_step2_production_refuses_the_admin_password_in_dot_env_example():
    password = example_value("CMS_ADMIN_PASSWORD")
    assert "CMS_ADMIN_PASSWORD" in refusal(
        PRODUCTION | {"CMS_ADMIN_PASSWORD": password})


@pytest.mark.parametrize("var", ["CMS_SECRET_KEY", "CMS_ADMIN_EMAIL",
                                 "CMS_ADMIN_PASSWORD"])
def test_step2_a_blank_value_counts_as_unset(var):
    assert var in refusal(PRODUCTION | {var: "   "})


def test_step4_cms_serve_refuses_an_admin_email_that_belongs_to_an_editor(
        tmp_path, monkeypatch, capsys):
    from app import cli
    from conftest import add_user

    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("CMS_DATABASE", str(tmp_path / "prod.db"))
    add_user(email=PRODUCTION["CMS_ADMIN_EMAIL"], password=secrets.token_urlsafe(16),
             role="editor", display_name="编辑甲")
    for key, value in PRODUCTION.items():
        monkeypatch.setenv(key, value)
    served = []
    monkeypatch.setattr("uvicorn.run", lambda target, **_: served.append(target))

    assert cli.main(["serve"]) == 1
    assert served == []
    assert "CMS_ADMIN_EMAIL" in capsys.readouterr().err


def test_step4_the_seed_cannot_add_the_demo_logins_to_a_production_database(
        tmp_path, monkeypatch):
    from conftest import DEMO_USERS, login
    from test_t01_seed import run_seed

    prod_db = tmp_path / "prod.db"
    c = start_app(monkeypatch, prod_db)
    seed_env = PRODUCTION | {"CMS_DATABASE": str(prod_db),
                             "CMS_EDITOR_PASSWORD": secrets.token_urlsafe(16)}
    run_seed(seed_env)
    # The passwords the seed would have given the demo accounts.
    for role, var in (("admin", "CMS_ADMIN_PASSWORD"),
                      ("editor", "CMS_EDITOR_PASSWORD")):
        assert login(c, DEMO_USERS[role]["email"],
                     seed_env[var]).status_code == 401
