"""The Trash (回收站): deleted Guides, which only Admins see. They restore a
Guide from it or delete it for good, through app/guides.py."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app import db, guides
from app.accounts import User
from app.routes.guides import status_for
from app.web import AdminRequired, flash, redirect, signed_in_user, templates

router = APIRouter()


def trash_manager(user: Annotated[User, Depends(signed_in_user)]) -> User:
    """The signed-in Admin; Editors are refused, even by typed URL."""
    if not user.can("manage_trash"):
        raise AdminRequired
    return user


def trash_page(request: Request, user: User, *, error: str | None = None,
               status_code: int = 200):
    with db.connect() as conn:
        listed = guides.trashed(conn, user)
    return templates.TemplateResponse(
        request, "admin/trash.html",
        {"title": "回收站", "user": user, "guides": listed, "error": error},
        status_code=status_code)


@router.get("/admin/trash")
def trash(request: Request, user: Annotated[User, Depends(trash_manager)]):
    return trash_page(request, user)


@router.post("/admin/trash/{guide_id}/restore")
def restore(request: Request, guide_id: int,
            user: Annotated[User, Depends(trash_manager)]):
    try:
        with db.connect() as conn:
            guides.restore(conn, user, guide_id)
    except guides.Refused as refused:
        return trash_page(request, user, error=refused.message,
                          status_code=status_for(refused))
    flash(request, "已恢复，攻略原样回到了作者手里。")
    return redirect("/admin/trash")



@router.get("/admin/trash/{guide_id}/delete")
def confirm_delete_for_good(request: Request, guide_id: int,
                            user: Annotated[User, Depends(trash_manager)]):
    try:
        with db.connect() as conn:
            guide = guides.in_trash(conn, user, guide_id)
    except guides.GuideNotFound:
        raise HTTPException(status_code=404) from None
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "彻底删除攻略", "user": user,
         "question": f"确定要彻底删除《{guide.title_zh or '（无标题）'}》吗？",
         "consequences": ["彻底删除后无法恢复，攻略的正文、审核意见和修订都会一起删除。"],
         "button": "彻底删除", "action": f"admin/trash/{guide_id}/delete",
         "cancel": "admin/trash"})


@router.post("/admin/trash/{guide_id}/delete")
def delete_for_good(request: Request, guide_id: int,
                    user: Annotated[User, Depends(trash_manager)]):
    try:
        with db.connect() as conn:
            guides.delete_for_good(conn, user, guide_id)
    except guides.Refused as refused:
        return trash_page(request, user, error=refused.message,
                          status_code=status_for(refused))
    flash(request, "已彻底删除。")
    return redirect("/admin/trash")
