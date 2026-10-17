"""The console dashboard. /admin itself stays the T00 hello page."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import db, guides, publish
from app.accounts import User
from app.web import signed_in_user, templates

router = APIRouter()


@router.get("/admin/dashboard")
def dashboard(request: Request, user: Annotated[User, Depends(signed_in_user)]):
    with db.connect() as conn:
        counts = guides.counts(conn, user)
        not_on_site = (publish.changes_not_on_site(conn)
                       if user.can("build_site") else None)
    return templates.TemplateResponse(
        request, "admin/dashboard.html",
        {"title": "控制台", "user": user, "counts": counts,
         "statuses": guides.STATUS_LABELS, "not_on_site": not_on_site})
