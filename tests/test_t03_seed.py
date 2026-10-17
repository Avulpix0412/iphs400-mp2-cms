"""T03: the seed script adds demo Guides in every status (checked through the
console)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from test_t02_seed import seeded_admin
from test_t03_guides import dashboard_counts


def test_seed_creates_demo_guides_in_draft_submitted_and_published(tmp_path,
                                                                   monkeypatch):
    admin = seeded_admin(tmp_path, monkeypatch)
    by_status = dashboard_counts(admin)
    assert set(by_status) == {"草稿", "待审核", "已发布"}
    assert all(n >= 1 for n in by_status.values()), by_status
    assert "演示编辑" in admin.get("/admin/guides?status=submitted").text


def test_seeding_twice_adds_no_duplicate_guides(tmp_path, monkeypatch):
    once_dir, twice_dir = tmp_path / "once", tmp_path / "twice"
    once_dir.mkdir()
    twice_dir.mkdir()
    once: TestClient = seeded_admin(once_dir, monkeypatch)
    assert dashboard_counts(once) == dashboard_counts(
        seeded_admin(twice_dir, monkeypatch, times=2))
