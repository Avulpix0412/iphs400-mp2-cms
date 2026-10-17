"""The console dashboard. /admin itself stays the T00 hello page."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.accounts import User
from app.web import signed_in_user, templates

router = APIRouter()


@router.get("/admin/dashboard")
def dashboard(request: Request, user: Annotated[User, Depends(signed_in_user)]):
    return templates.TemplateResponse(request, "admin/dashboard.html",
                                      {"title": "控制台", "user": user})
