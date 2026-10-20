"""Login, logout, and first-login setup."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request

from app import accounts, db
from app.accounts import User
from app.web import (flash, home_for, redirect, signed_in_user_mid_setup,
                     start_session, templates)

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "admin/login.html",
                                      {"title": "登录", "email": ""})


@router.post("/login")
def login(request: Request, email: Annotated[str, Form()],
          password: Annotated[str, Form()]):
    try:
        with db.connect() as conn:
            session_id, user = accounts.log_in(conn, email, password)
    except accounts.Refused as refused:
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"title": "登录", "email": email, "error": refused.message},
            status_code=_status_for(refused))
    start_session(request, session_id)
    return redirect(home_for(user))


def _status_for(refused: accounts.Refused) -> int:
    if isinstance(refused, accounts.LockedOut):
        return 429
    if isinstance(refused, accounts.AccountDeactivated):
        return 403
    return 401


@router.post("/logout")
def logout(request: Request):
    with db.connect() as conn:
        accounts.log_out(conn, request.session.get("sid"))
    request.session.clear()
    flash(request, "已退出登录。")
    return redirect("/login")


@router.get("/admin/setup")
def setup_form(request: Request,
               user: Annotated[User, Depends(signed_in_user_mid_setup)]):
    if not user.needs_setup:
        return redirect(home_for(user))
    return templates.TemplateResponse(
        request, "admin/setup.html",
        {"title": "首次登录设置", "user": user,
         "display_name": user.display_name or ""})


@router.post("/admin/setup")
def setup(request: Request,
          user: Annotated[User, Depends(signed_in_user_mid_setup)],
          display_name: Annotated[str, Form()], password: Annotated[str, Form()],
          password_confirm: Annotated[str, Form()]):
    if not user.needs_setup:
        return redirect(home_for(user))
    try:
        with db.connect() as conn:
            accounts.complete_setup(conn, user, display_name=display_name,
                                    password=password,
                                    password_confirm=password_confirm)
    except accounts.Refused as refused:
        return templates.TemplateResponse(
            request, "admin/setup.html",
            {"title": "首次登录设置", "user": user, "display_name": display_name,
             "error": refused.message},
            status_code=400)
    flash(request, "设置完成，欢迎加入！")
    return redirect("/admin/dashboard")
