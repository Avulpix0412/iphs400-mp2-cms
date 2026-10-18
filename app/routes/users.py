"""The Users page (用户): Admins manage every account through app/accounts.py,
which decides what may change; Editors are refused on every route here."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app import accounts, db, guides
from app.accounts import User
from app.web import flash, redirect, requires, templates

router = APIRouter()
user_manager = requires("manage_users")


def users_page(request: Request, user: User, *, error: str | None = None,
               status_code: int = 200, new_account: dict[str, str] | None = None):
    with db.connect() as conn:
        listed = accounts.users(conn, user)
        counts = guides.counts_by_author(conn, user)
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"title": "用户", "user": user, "users": listed, "counts": counts,
         "no_guides": guides.AuthorCounts(), "roles": accounts.ROLE_LABELS,
         "states": accounts.STATE_LABELS, "error": error,
         "new_account": new_account or {"email": "", "role": "editor"}},
        status_code=status_code)


@router.get("/admin/users")
def users(request: Request, user: Annotated[User, Depends(user_manager)]):
    return users_page(request, user)


@router.post("/admin/users")
def create_account(request: Request, user: Annotated[User, Depends(user_manager)],
                   email: Annotated[str, Form()] = "", role: Annotated[str, Form()] = "",
                   temporary_password: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            created = accounts.create_account(conn, user, email=email, role=role,
                                              temporary_password=temporary_password)
    except accounts.Refused as refused:
        return users_page(request, user, error=refused.message, status_code=400,
                          new_account={"email": email, "role": role})
    flash(request, f"已创建账号 {created.email}。请把临时密码告诉对方，"
                   "对方首次登录时会设置自己的密码和昵称。")
    return redirect("/admin/users")


def shown_account(conn: sqlite3.Connection, user: User, user_id: int) -> User:
    try:
        return accounts.account(conn, user, user_id)
    except accounts.AccountNotFound:
        raise HTTPException(status_code=404) from None


def account_page(request: Request, user: User, user_id: int, *,
                 error: str | None = None, status_code: int = 200):
    with db.connect() as conn:
        shown = shown_account(conn, user, user_id)
        guide_counts = guides.counts_by_author(conn, user).get(
            user_id, guides.AuthorCounts())
    return templates.TemplateResponse(
        request, "admin/user.html",
        {"title": f"管理账号：{shown.display_name or shown.email}", "user": user,
         "account": shown, "guide_counts": guide_counts,
         "roles": accounts.ROLE_LABELS, "states": accounts.STATE_LABELS,
         "error": error},
        status_code=status_code)


def status_for(refused: accounts.Refused) -> int:
    return 403 if isinstance(refused, accounts.NotAllowed) else 400


@router.get("/admin/users/{user_id}")
def account(request: Request, user_id: int,
            user: Annotated[User, Depends(user_manager)]):
    return account_page(request, user, user_id)


def change(request: Request, user: User, user_id: int,
           action: Callable[[sqlite3.Connection], None], done: str):
    """Make one change to an account, then show its page again: with `done`
    as a flash, or with the reason it was refused."""
    try:
        with db.connect() as conn:
            action(conn)
    except accounts.Refused as refused:
        if isinstance(refused, accounts.AccountNotFound):
            raise HTTPException(status_code=404) from None
        return account_page(request, user, user_id, error=refused.message,
                            status_code=status_for(refused))
    flash(request, done)
    return redirect(f"/admin/users/{user_id}")


@router.post("/admin/users/{user_id}/role")
def change_role(request: Request, user_id: int,
                user: Annotated[User, Depends(user_manager)],
                role: Annotated[str, Form()] = ""):
    return change(request, user, user_id,
                  lambda conn: accounts.change_role(conn, user, user_id, role),
                  f"角色已改为{accounts.ROLE_LABELS.get(role, role)}，"
                  "对方下一次打开页面时生效。")


@router.post("/admin/users/{user_id}/ban")
def ban(request: Request, user_id: int, user: Annotated[User, Depends(user_manager)]):
    return change(request, user, user_id,
                  lambda conn: accounts.ban_submissions(conn, user, user_id),
                  "已禁止投稿。对方仍可登录和编辑草稿，已发布的攻略留在网站上。")


@router.post("/admin/users/{user_id}/unban")
def unban(request: Request, user_id: int, user: Annotated[User, Depends(user_manager)]):
    return change(request, user, user_id,
                  lambda conn: accounts.lift_submission_ban(conn, user, user_id),
                  "已解除禁止投稿，对方可以重新提交审核。")


@router.get("/admin/users/{user_id}/deactivate")
def confirm_deactivate(request: Request, user_id: int,
                       user: Annotated[User, Depends(user_manager)]):
    with db.connect() as conn:
        shown = shown_account(conn, user, user_id)
    try:
        accounts.check_deactivatable(user, shown)
    except accounts.Refused as refused:
        return account_page(request, user, user_id, error=refused.message,
                            status_code=400)
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "停用账号", "user": user,
         "question": f"确定要停用 {shown.display_name or shown.email} 的账号吗？",
         "consequences": ["停用后对方立刻被退出登录，也无法再登录。",
                          "对方已发布的攻略仍然留在网站上。",
                          "以后可以重新启用；重新启用后账号为正常状态，"
                          "之前的禁止投稿不会保留。"],
         "button": "停用账号", "action": f"admin/users/{user_id}/deactivate",
         "cancel": f"admin/users/{user_id}"})


@router.post("/admin/users/{user_id}/deactivate")
def deactivate(request: Request, user_id: int,
               user: Annotated[User, Depends(user_manager)]):
    return change(request, user, user_id,
                  lambda conn: accounts.deactivate(conn, user, user_id),
                  "账号已停用，对方无法再登录。已发布的攻略留在网站上。")


@router.post("/admin/users/{user_id}/reactivate")
def reactivate(request: Request, user_id: int,
               user: Annotated[User, Depends(user_manager)]):
    return change(request, user, user_id,
                  lambda conn: accounts.reactivate(conn, user, user_id),
                  "账号已重新启用，对方可以登录了。")


@router.post("/admin/users/{user_id}/password")
def reset_password(request: Request, user_id: int,
                   user: Annotated[User, Depends(user_manager)],
                   temporary_password: Annotated[str, Form()] = ""):
    return change(request, user, user_id,
                  lambda conn: accounts.reset_password(conn, user, user_id,
                                                       temporary_password),
                  "密码已重置。请把临时密码告诉对方，对方登录后要重新设置密码。")
