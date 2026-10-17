"""Guides in the console: the content list, the editor, and the workflow
buttons. Every change goes through app/guides.py, which decides who may make
it; these routes only turn its answers into pages."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import FormData

from app import db, game, guides
from app.rendering import render_markdown
from app.accounts import User
from app.guides import Guide, GuideFields
from app.web import flash, redirect, signed_in_user, templates

router = APIRouter(dependencies=[Depends(signed_in_user)])


def _id_or_none(value: str) -> int | None:
    return int(value) if value.strip().isdigit() else None


def _fields_from(form: FormData) -> GuideFields:
    """The Guide form's fields. A missing text field counts as blank, so it
    gets our message rather than a 422; the slug stays None unless the form
    has a slug field (only Admins' does)."""
    def text(name: str) -> str:
        value = form.get(name)
        return value if isinstance(value, str) else ""
    slug = form.get("slug")
    return GuideFields(title_zh=text("title_zh"), body_zh=text("body_zh"),
                       title_en=text("title_en"), body_en=text("body_en"),
                       hero_id=_id_or_none(text("hero_id")),
                       patch_id=_id_or_none(text("patch_id")),
                       slug=slug if isinstance(slug, str) else None)


async def guide_fields(request: Request) -> GuideFields:
    return _fields_from(await request.form())


async def sent_guide_fields(request: Request) -> GuideFields | None:
    """The editor form's fields when a workflow button sent them along (it
    sits inside the form), or None for a bare post of the button alone."""
    form = await request.form()
    return _fields_from(form) if "hero_id" in form else None


def status_for(refused: guides.Refused) -> int:
    if isinstance(refused, guides.GuideNotFound):
        return 404
    return 403 if isinstance(refused, guides.NotAllowed) else 400


def editor_page(request: Request, user: User, guide: Guide | None,
                fields: GuideFields, *, error: str | None = None,
                status_code: int = 200):
    with db.connect() as conn:
        heroes = game.heroes(conn)
        patches = guides.patch_choices(conn, guide)
    title = f"编辑攻略：{guide.title_zh or '（无标题）'}" if guide else "写攻略"
    return templates.TemplateResponse(
        request, "admin/guide_edit.html",
        {"title": title, "user": user, "guide": guide, "fields": fields,
         "heroes": heroes, "patches": patches, "error": error,
         "can_submit": guide is not None and guides.can_submit(user, guide),
         "can_publish": guide is not None and guides.can_publish(user, guide)},
        status_code=status_code)


def visible_guide(guide_id: int,
                  user: Annotated[User, Depends(signed_in_user)]) -> Guide:
    """The Guide in the URL, or 404 if it doesn't exist or isn't this user's
    to see."""
    with db.connect() as conn:
        guide = guides.guide(conn, user, guide_id)
    if guide is None:
        raise HTTPException(status_code=404)
    return guide


def refused_page(request: Request, user: User, guide_id: int,
                 fields: GuideFields | None, refused: guides.Refused):
    """Show the editor again with the reason, keeping what was typed."""
    guide = visible_guide(guide_id, user)
    return editor_page(request, user, guide, fields or GuideFields.of(guide),
                       error=refused.message, status_code=status_for(refused))


@router.get("/admin/guides")
def guide_list(request: Request, user: Annotated[User, Depends(signed_in_user)],
               status: str = "", hero: str = "", author: str = "",
               patch: str = "", lang: str = ""):
    filters = guides.GuideFilter(
        status=status if status in guides.STATUS_LABELS else "",
        hero_id=_id_or_none(hero), author_id=_id_or_none(author),
        patch_id=_id_or_none(patch),
        language=lang if lang in guides.LANGUAGE_LABELS else "")
    with db.connect() as conn:
        listed = guides.guides(conn, user, filters)
        heroes, patches = game.heroes(conn), game.patches(conn)
        authors = guides.authors(conn, user)
    return templates.TemplateResponse(
        request, "admin/guides.html",
        {"title": "攻略", "user": user, "guides": listed, "filters": filters,
         "statuses": guides.STATUS_LABELS, "languages": guides.LANGUAGE_LABELS,
         "heroes": heroes, "patches": patches, "authors": authors,
         "filtered": filters != guides.GuideFilter()})


@router.get("/admin/guides/new")
def new_guide_form(request: Request,
                   user: Annotated[User, Depends(signed_in_user)]):
    with db.connect() as conn:
        patches = guides.patch_choices(conn)
    current = patches[0].id if patches else None
    return editor_page(request, user, None, GuideFields(patch_id=current))


@router.post("/admin/guides")
def create_guide(request: Request, user: Annotated[User, Depends(signed_in_user)],
                 fields: Annotated[GuideFields, Depends(guide_fields)]):
    try:
        with db.connect() as conn:
            guide = guides.create(conn, user, fields)
    except guides.Refused as refused:
        return editor_page(request, user, None, fields, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "草稿已保存。")
    return redirect(f"/admin/guides/{guide.id}/edit")


@router.get("/admin/guides/{guide_id}/edit")
def edit_guide_form(request: Request,
                    user: Annotated[User, Depends(signed_in_user)],
                    guide: Annotated[Guide, Depends(visible_guide)]):
    return editor_page(request, user, guide, GuideFields.of(guide))


@router.get("/admin/guides/{guide_id}/preview")
def preview_guide(request: Request, user: Annotated[User, Depends(signed_in_user)],
                  guide: Annotated[Guide, Depends(visible_guide)]):
    return templates.TemplateResponse(
        request, "admin/guide_preview.html",
        {"title": f"预览：{guide.title_zh or '（无标题）'}", "user": user,
         "guide": guide, "body_zh": render_markdown(guide.body_zh),
         "body_en": render_markdown(guide.body_en)})


@router.post("/admin/guides/{guide_id}")
def save_guide(request: Request, guide_id: int,
               user: Annotated[User, Depends(signed_in_user)],
               fields: Annotated[GuideFields, Depends(guide_fields)]):
    try:
        with db.connect() as conn:
            guides.save(conn, user, guide_id, fields)
    except guides.Refused as refused:
        return refused_page(request, user, guide_id, fields, refused)
    flash(request, "已保存。")
    return redirect(f"/admin/guides/{guide_id}/edit")


WorkflowStep = Callable[[sqlite3.Connection, User, int], Guide]


def workflow_step(request: Request, user: User, guide_id: int,
                  fields: GuideFields | None, step: WorkflowStep, done: str):
    """Press a workflow button. When the editor form came along, its edits are
    saved in the same transaction: if the step is refused they are not saved
    either, and the editor shows them again with the reason."""
    try:
        with db.connect() as conn:
            if fields:
                guides.save(conn, user, guide_id, fields)
            step(conn, user, guide_id)
    except guides.Refused as refused:
        return refused_page(request, user, guide_id, fields, refused)
    flash(request, done)
    return redirect(f"/admin/guides/{guide_id}/edit")


@router.post("/admin/guides/{guide_id}/submit")
def submit_guide(request: Request, guide_id: int,
                 user: Annotated[User, Depends(signed_in_user)],
                 fields: Annotated[GuideFields | None, Depends(sent_guide_fields)]):
    return workflow_step(request, user, guide_id, fields, guides.submit,
                         "已提交审核，请等待管理员审核。")


@router.post("/admin/guides/{guide_id}/publish")
def publish_guide(request: Request, guide_id: int,
                  user: Annotated[User, Depends(signed_in_user)],
                  fields: Annotated[GuideFields | None, Depends(sent_guide_fields)]):
    return workflow_step(request, user, guide_id, fields, guides.publish,
                         "已发布。点击“更新网站”后，读者才会在公开网站上看到它。")
