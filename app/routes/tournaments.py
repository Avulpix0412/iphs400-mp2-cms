"""Tournament announcements (预告) and recaps (回顾) in the console, managed
by Admins only.

The router itself requires an Admin, so no route here can forget to. Every
change goes through app/content.py; these routes only turn its answers into
pages.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app import content, db, game, publish
from app.accounts import User
from app.content import TournamentFields, TournamentItem
from app.routes.pages import page_manager, preview_page, status_for
from app.web import flash, form_text, id_or_none, redirect, templates

router = APIRouter(dependencies=[Depends(page_manager)])


async def tournament_fields(request: Request) -> TournamentFields:
    form = await request.form()
    texts = {name: form_text(form, name) for name in
             ("kind", "title_zh", "body_zh", "title_en", "body_en", "tournament_date")}
    return TournamentFields(**texts,
                            patch_id=id_or_none(form_text(form, "patch_id")),
                            announcement_id=id_or_none(form_text(form, "announcement_id")))


async def sent_tournament_fields(request: Request) -> TournamentFields | None:
    """The editor form's fields when a button inside it sent them along, or
    None for a bare post of the button alone."""
    form = await request.form()
    return await tournament_fields(request) if "kind" in form else None


def existing_item(item_id: int,
                  user: Annotated[User, Depends(page_manager)]) -> TournamentItem:
    try:
        with db.connect() as conn:
            return content.tournament_item(conn, user, item_id)
    except content.NotFound:
        raise HTTPException(status_code=404) from None


def editor_page(request: Request, user: User, item: TournamentItem | None,
                fields: TournamentFields, *, error: str | None = None,
                status_code: int = 200):
    with db.connect() as conn:
        patches = game.patches(conn)
        if fields.patch_id is None and patches:  # a new item: the Current Patch
            fields = replace(fields, patch_id=patches[0].id)
        announcements = [other for other in content.tournament_items(conn, user)
                         if other.kind == "announcement"
                         and (item is None or other.id != item.id)]
    title = (f"编辑锦标赛{item.kind_label}：{item.title_zh or '（无标题）'}" if item
             else "新建锦标赛内容")
    return templates.TemplateResponse(
        request, "admin/tournament_edit.html",
        {"title": title, "user": user, "item": item, "fields": fields,
         "kinds": content.KIND_LABELS, "patches": patches,
         "announcements": announcements, "error": error},
        status_code=status_code)


@router.get("/admin/tournaments")
def tournament_list(request: Request, user: Annotated[User, Depends(page_manager)]):
    with db.connect() as conn:
        listed = content.tournament_items(conn, user)
    return templates.TemplateResponse(
        request, "admin/tournaments.html",
        {"title": "锦标赛", "user": user, "items": listed})


@router.get("/admin/tournaments/new")
def new_item_form(request: Request, user: Annotated[User, Depends(page_manager)]):
    return editor_page(request, user, None, TournamentFields())


@router.post("/admin/tournaments")
def create_item(request: Request, user: Annotated[User, Depends(page_manager)],
                fields: Annotated[TournamentFields, Depends(tournament_fields)]):
    try:
        with db.connect() as conn:
            item = content.create_tournament_item(conn, user, fields)
    except content.Refused as refused:
        return editor_page(request, user, None, fields, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "草稿已保存。")
    return redirect(f"/{item.console_path}/edit")


@router.get("/admin/tournaments/{item_id}/edit")
def edit_item_form(request: Request, user: Annotated[User, Depends(page_manager)],
                   item: Annotated[TournamentItem, Depends(existing_item)]):
    return editor_page(request, user, item, TournamentFields.of(item))


@router.post("/admin/tournaments/{item_id}")
def save_item(request: Request, user: Annotated[User, Depends(page_manager)],
              item: Annotated[TournamentItem, Depends(existing_item)],
              fields: Annotated[TournamentFields, Depends(tournament_fields)]):
    try:
        with db.connect() as conn:
            content.save_tournament_item(conn, user, item.id, fields)
    except content.Refused as refused:
        return editor_page(request, user, item, fields, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "已保存。" if item.status == "draft"
          else "已保存。点击“更新网站”后，读者才会看到改动。")
    return redirect(f"/{item.console_path}/edit")


@router.post("/admin/tournaments/{item_id}/publish")
def publish_item(request: Request, user: Annotated[User, Depends(page_manager)],
                 item: Annotated[TournamentItem, Depends(existing_item)],
                 fields: Annotated[TournamentFields | None,
                                   Depends(sent_tournament_fields)]):
    """Publish, saving the editor's fields first when they came along; if
    either is refused, neither is saved."""
    try:
        with db.connect() as conn:
            if fields:
                content.save_tournament_item(conn, user, item.id, fields)
            content.publish_tournament_item(conn, user, item.id)
    except content.Refused as refused:
        return editor_page(request, user, item, fields or TournamentFields.of(item),
                           error=refused.message, status_code=status_for(refused))
    flash(request, "已发布。点击“更新网站”后，它会出现在公开网站的锦标赛栏目里。")
    return redirect(f"/{item.console_path}/edit")


@router.post("/admin/tournaments/{item_id}/unpublish")
def unpublish_item(request: Request, user: Annotated[User, Depends(page_manager)],
                   item: Annotated[TournamentItem, Depends(existing_item)]):
    try:
        with db.connect() as conn:
            content.unpublish_tournament_item(conn, user, item.id)
    except content.Refused as refused:
        return editor_page(request, user, item, TournamentFields.of(item),
                           error=refused.message, status_code=status_for(refused))
    flash(request, "已撤下，回到了草稿。点击“更新网站”后，它才会从公开网站上消失。")
    return redirect(f"/{item.console_path}/edit")


@router.get("/admin/tournaments/{item_id}/preview")
def preview_item(request: Request, user: Annotated[User, Depends(page_manager)],
                 item: Annotated[TournamentItem, Depends(existing_item)]):
    meta = {lang: f"{t[item.kind]} · {t['tournament_date']} {item.tournament_date}"
                  f" · {item.patch_name}" for lang, t in publish.LABELS.items()}
    return preview_page(request, user, item, kind=f"锦标赛{item.kind_label}", meta=meta)


@router.get("/admin/tournaments/{item_id}/delete")
def confirm_delete_item(request: Request, user: Annotated[User, Depends(page_manager)],
                        item: Annotated[TournamentItem, Depends(existing_item)]):
    consequences = ["彻底删除后无法恢复。"]
    if item.kind == "announcement":
        consequences.append("关联到这条预告的回顾会保留，只是不再链接到它。")
    if item.status == "published":
        consequences.append("下次“更新网站”后，它会从公开网站上消失。")
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": f"删除锦标赛{item.kind_label}", "user": user,
         "question": f"确定要彻底删除锦标赛{item.kind_label}《{item.title_zh or '（无标题）'}》吗？",
         "consequences": consequences, "button": "彻底删除",
         "action": f"{item.console_path}/delete",
         "cancel": f"{item.console_path}/edit"})


@router.post("/admin/tournaments/{item_id}/delete")
def delete_item(request: Request, user: Annotated[User, Depends(page_manager)],
                item: Annotated[TournamentItem, Depends(existing_item)]):
    try:
        with db.connect() as conn:
            content.delete_tournament_item(conn, user, item.id)
    except content.NotFound:  # deleted in another tab just now
        raise HTTPException(status_code=404) from None
    flash(request, f"锦标赛{item.kind_label}已彻底删除。")
    return redirect("/admin/tournaments")
