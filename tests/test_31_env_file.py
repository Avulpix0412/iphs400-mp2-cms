"""#31: the seed script and the `cms` command load .env themselves, so the
rubric's `uv run python scripts/seed_demo.py` works without `--env-file`."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import DEMO_USERS, login
from test_t01_seed import run_seed


def test_seed_reads_the_passwords_from_a_dot_env_in_the_working_folder(
        tmp_path, monkeypatch):
    seeded_db = tmp_path / "seeded.db"
    (tmp_path / ".env").write_text(
        f"CMS_DATABASE={seeded_db}\n"
        "CMS_ADMIN_PASSWORD=from-file-admin\n"
        "CMS_EDITOR_PASSWORD=from-file-editor\n")
    monkeypatch.delenv("CMS_DATABASE")  # set by conftest; here only .env names it
    result = run_seed({}, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setenv("CMS_DATABASE", str(seeded_db))
    c = TestClient(create_app())
    response = login(c, DEMO_USERS["admin"]["email"], "from-file-admin")
    assert response.headers["location"] == "/admin/dashboard"


def test_a_variable_set_in_the_environment_beats_the_same_key_in_dot_env(
        tmp_path, monkeypatch):
    from_env_db = tmp_path / "from-env.db"
    (tmp_path / ".env").write_text(
        f"CMS_DATABASE={tmp_path / 'from-file.db'}\n"
        "CMS_ADMIN_PASSWORD=from-file-admin\n"
        "CMS_EDITOR_PASSWORD=from-file-editor\n")
    result = run_seed({"CMS_DATABASE": str(from_env_db),
                       "CMS_ADMIN_PASSWORD": "from-env-admin"}, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "from-file.db").exists()

    monkeypatch.setenv("CMS_DATABASE", str(from_env_db))
    c = TestClient(create_app())
    response = login(c, DEMO_USERS["admin"]["email"], "from-env-admin")
    assert response.headers["location"] == "/admin/dashboard"


def test_without_a_dot_env_the_seed_prints_its_message_and_exits_1(tmp_path):
    result = run_seed({"CMS_DATABASE": str(tmp_path / "seeded.db")}, cwd=tmp_path)
    assert result.returncode == 1
    assert result.stdout.startswith(
        "Set CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD in .env (copy .env.example)")


def unset(monkeypatch, key: str) -> None:
    """Remove `key` from the environment and restore it after the test, even
    when the loader sets it. (delenv alone records nothing for an unset key.)"""
    monkeypatch.setenv(key, "")
    monkeypatch.delenv(key)


def loaded(tmp_path, monkeypatch, text: str, keys: list[str]) -> dict[str, str | None]:
    """Load `text` as a .env file and return what each key became."""
    from app import envfile

    for key in keys:
        unset(monkeypatch, key)
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    envfile.load(tmp_path / ".env")
    return {key: os.environ.get(key) for key in keys}


def test_quoted_values_with_spaces_comments_and_blank_lines_parse(
        tmp_path, monkeypatch):
    text = ('# Copy to .env and change the values.\n'
            'CMS_T31_TITLE="大巴扎 攻略站"\n'
            '\n'
            "CMS_T31_SINGLE='single quoted'\n"
            '   # an indented comment\n'
            'CMS_T31_PLAIN=plain-value\n'
            'CMS_T31_EMPTY=\n')
    assert loaded(tmp_path, monkeypatch, text,
                  ["CMS_T31_TITLE", "CMS_T31_SINGLE", "CMS_T31_PLAIN",
                   "CMS_T31_EMPTY"]) == {
        "CMS_T31_TITLE": "大巴扎 攻略站",
        "CMS_T31_SINGLE": "single quoted",
        "CMS_T31_PLAIN": "plain-value",
        "CMS_T31_EMPTY": "",
    }


def test_an_unquoted_value_with_spaces_is_kept_whole_and_a_line_without_equals_is_skipped(
        tmp_path, monkeypatch, capsys):
    text = ('CMS_T31_TITLE=大巴扎 攻略站\n'
            'CMS_T31_TYPO\n'
            'CMS_T31_PLAIN=still-loaded\n')
    assert loaded(tmp_path, monkeypatch, text,
                  ["CMS_T31_TITLE", "CMS_T31_TYPO", "CMS_T31_PLAIN"]) == {
        "CMS_T31_TITLE": "大巴扎 攻略站",
        "CMS_T31_TYPO": None,
        "CMS_T31_PLAIN": "still-loaded",
    }
    warning = capsys.readouterr().err
    assert "line 2" in warning
    assert "CMS_T31_TYPO" not in warning


def test_cms_serve_loads_dot_env_from_the_working_folder(tmp_path, monkeypatch):
    from app import cli

    unset(monkeypatch, "CMS_SITE_TITLE")
    (tmp_path / ".env").write_text('CMS_SITE_TITLE="来自 env 文件的站名"\n',
                                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    served = []
    monkeypatch.setattr("uvicorn.run", lambda target, **_: served.append(target))

    assert cli.main(["serve"]) == 0
    assert served == ["app.main:app"]
    assert "来自 env 文件的站名" in TestClient(create_app()).get("/").text


def test_inline_comments_export_and_a_byte_order_mark_parse_as_uv_reads_them(
        tmp_path, monkeypatch):
    text = ('﻿CMS_T31_FIRST=after-the-bom\n'
            'CMS_T31_TITLE="大巴扎 攻略站"  # shown in the header\n'
            'CMS_T31_PLAIN=plain-value # a comment\n'
            'CMS_T31_HASH=keeps#this\n'
            'CMS_T31_EMPTY=  # set after deploy\n'
            'export CMS_T31_EXPORTED=exported\n')
    assert loaded(tmp_path, monkeypatch, text,
                  ["CMS_T31_FIRST", "CMS_T31_TITLE", "CMS_T31_PLAIN", "CMS_T31_HASH",
                   "CMS_T31_EMPTY", "CMS_T31_EXPORTED"]) == {
        "CMS_T31_FIRST": "after-the-bom",
        "CMS_T31_TITLE": "大巴扎 攻略站",
        "CMS_T31_PLAIN": "plain-value",
        "CMS_T31_HASH": "keeps#this",
        "CMS_T31_EMPTY": "",
        "CMS_T31_EXPORTED": "exported",
    }
