"""The Moderation queue (评论审核): Comments on Guides, managed by Admins only.

The router itself requires an Admin, so no route here can forget to. Every
change goes through app/comments.py; these routes only turn its answers into
pages.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import comments, db, game
from app.accounts import User
from app.rendering import render_markdown
from app.web import flash, form_text, id_or_none, redirect, requires, templates

comment_moderator = requires("moderate_comments")
router = APIRouter(dependencies=[Depends(comment_moderator)])

QUEUE = "/admin/comments"


def status_for(refused: comments.Refused) -> int:
    if isinstance(refused, comments.NotFound):
        return 404
    return 403 if isinstance(refused, comments.NotAllowed) else 400


def queue_page(request: Request, user: User, *, new: dict[str, str] | None = None,
               error: str | None = None, status_code: int = 200):
    """The queue, with the add form holding `new` (what was sent, when it was
    refused). Each Comment shows as Readers would see it, sanitized like a
    Guide's text."""
    with db.connect() as conn:
        listed = comments.pending(conn, user)
        choices = comments.guide_choices(conn, user)
        glossary = game.glossary(conn)
    rendered = {comment.id: render_markdown(comment.body, comment.lang, glossary).html
                for comment in listed}
    return templates.TemplateResponse(
        request, "admin/comments.html",
        {"title": "评论审核", "user": user, "comments": listed, "rendered": rendered,
         "guides": choices,
         "new": new or {}, "languages": comments.LANGUAGES, "error": error},
        status_code=status_code)


@router.get(QUEUE)
def queue(request: Request, user: Annotated[User, Depends(comment_moderator)]):
    return queue_page(request, user)


@router.post(QUEUE)
async def add_comment(request: Request,
                      user: Annotated[User, Depends(comment_moderator)]):
    form = await request.form()
    new = {name: form_text(form, name)
           for name in ("guide_id", "reader_name", "body", "lang")}
    try:
        with db.connect() as conn:
            comment = comments.add(conn, user, guide_id=id_or_none(new["guide_id"]),
                                   reader_name=new["reader_name"], body=new["body"],
                                   lang=new["lang"])
    except comments.Refused as refused:
        return queue_page(request, user, new=new, error=refused.message,
                          status_code=status_for(refused))
    flash(request, "已添加评论，等待处理。")
    if comment.language_warning:
        flash(request, comment.language_warning, "notice")
    return redirect(QUEUE)


@router.post(QUEUE + "/{comment_id}/approve")
def approve(request: Request, comment_id: int,
           user: Annotated[User, Depends(comment_moderator)]):
    try:
        with db.connect() as conn:
            comments.approve(conn, user, comment_id)
    except comments.Refused as refused:
        return queue_page(request, user, error=refused.message,
                          status_code=status_for(refused))
    flash(request, "已通过，评论会在下次更新网站后出现在攻略下面。")
    return redirect(QUEUE)


@router.post(QUEUE + "/{comment_id}/reject")
def reject(request: Request, comment_id: int,
           user: Annotated[User, Depends(comment_moderator)]):
    try:
        with db.connect() as conn:
            comments.reject(conn, user, comment_id)
    except comments.Refused as refused:
        return queue_page(request, user, error=refused.message,
                          status_code=status_for(refused))
    flash(request, "已拒绝，这条评论不会上网站。")
    return redirect(QUEUE)
