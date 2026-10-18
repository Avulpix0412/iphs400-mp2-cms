"""Guides in the console: the content list, the editor, and the workflow
buttons. Every change goes through app/guides.py, which decides who may make
it; these routes only turn its answers into pages."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from itertools import zip_longest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import FormData

from app import db, game, guides
from app.rendering import highlight, render_markdown
from app.accounts import User
from app.guides import Guide, GuideFields, ReviewNote, Revision
from app.web import AdminRequired, flash, redirect, signed_in_user, templates

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
        rounds = guides.review_rounds(conn, user, guide.id) if guide else []
    title = f"编辑攻略：{guide.title_zh or '（无标题）'}" if guide else "写攻略"
    return templates.TemplateResponse(
        request, "admin/guide_edit.html",
        {"title": title, "user": user, "guide": guide, "fields": fields,
         "heroes": heroes, "patches": patches, "error": error,
         "review_rounds": rounds, "statuses": guides.STATUS_LABELS,
         "can_submit": guide is not None and guides.can_submit(user, guide),
         "can_publish": guide is not None and guides.can_publish(user, guide),
         "can_review": guide is not None and guides.can_review(user, guide),
         "can_open_revision": (guide is not None
                               and guides.can_open_revision(user, guide)),
         "can_edit": guide is None or guides.can_edit(user, guide)},
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


def preview_page(request: Request, user: User, item: Guide | Revision):
    """The Guide (or Revision) as Readers will see it, with the passages its
    Review notes quote highlighted, the latest round's set apart from earlier
    rounds' (here only: the Site build never highlights)."""
    with db.connect() as conn:
        latest, earlier = guides.quotes_to_highlight(conn, user, item)
    body_zh, found_zh = highlight(render_markdown(item.body_zh), latest, earlier)
    body_en, found_en = highlight(render_markdown(item.body_en), latest, earlier)
    return templates.TemplateResponse(
        request, "admin/guide_preview.html",
        {"title": f"预览：{item.title_zh or '（无标题）'}", "user": user,
         "guide": item, "body_zh": body_zh, "body_en": body_en,
         "quotes": latest + earlier, "earlier": earlier,
         "found": found_zh | found_en})


@router.get("/admin/guides/{guide_id}/preview")
def preview_guide(request: Request, user: Annotated[User, Depends(signed_in_user)],
                  guide: Annotated[Guide, Depends(visible_guide)]):
    return preview_page(request, user, guide)


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


WorkflowStep = Callable[[sqlite3.Connection, User, int], Guide | Revision]


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


async def sent_review_notes(request: Request) -> list[ReviewNote]:
    """The Review note builder's rows, in order. Rows left wholly blank are
    dropped; a half-filled row is kept, for app/guides.py to refuse."""
    form = await request.form()
    def texts(name: str) -> list[str]:  # anything but text (a file) is blank
        return [value if isinstance(value, str) else "" for value in form.getlist(name)]
    rows = zip_longest(texts("quote"), texts("advice"), fillvalue="")
    return [ReviewNote(quote, advice) for quote, advice in rows
            if quote.strip() or advice.strip()]


BLANK_NOTE_ROWS = 3


def review_page(request: Request, user: User, guide: Guide | Revision,
                notes: list[ReviewNote], *, error: str | None = None,
                status_code: int = 200):
    rows = notes + [ReviewNote("", "")] * max(BLANK_NOTE_ROWS - len(notes), 1)
    kind = "修订" if guide.is_revision else ""
    return templates.TemplateResponse(
        request, "admin/guide_review.html",
        {"title": f"审核{kind}：{guide.title_zh or '（无标题）'}", "user": user,
         "guide": guide, "notes": rows, "error": error,
         "body_zh": render_markdown(guide.body_zh),
         "body_en": render_markdown(guide.body_en)},
        status_code=status_code)


@router.get("/admin/guides/{guide_id}/review")
def review_guide(request: Request, user: Annotated[User, Depends(signed_in_user)],
                 guide: Annotated[Guide, Depends(visible_guide)]):
    if not user.can("publish_guides"):
        raise AdminRequired(user)
    return review_page(request, user, guide, [])


ReviewStep = Callable[[sqlite3.Connection, User, int, list[ReviewNote]],
                     Guide | Revision]


def review_step(request: Request, user: User, guide_id: int,
                notes: list[ReviewNote], step: ReviewStep, done: str):
    """Send a Guide back with the Review notes from the review screen. If
    that is refused, the screen shows the reason and keeps what was typed."""
    try:
        with db.connect() as conn:
            step(conn, user, guide_id, notes)
    except guides.Refused as refused:
        if not user.can("publish_guides"):
            return refused_page(request, user, guide_id, None, refused)
        return review_page(request, user, visible_guide(guide_id, user), notes,
                           error=refused.message, status_code=status_for(refused))
    flash(request, done)
    return redirect(f"/admin/guides/{guide_id}/edit")


@router.post("/admin/guides/{guide_id}/return")
def return_guide(request: Request, guide_id: int,
                 user: Annotated[User, Depends(signed_in_user)],
                 notes: Annotated[list[ReviewNote], Depends(sent_review_notes)]):
    return review_step(request, user, guide_id, notes, guides.return_guide,
                       "已退回给作者，作者会在草稿顶部看到审核意见。")


@router.post("/admin/guides/{guide_id}/unpublish")
def unpublish_guide(request: Request, guide_id: int,
                    user: Annotated[User, Depends(signed_in_user)],
                    notes: Annotated[list[ReviewNote], Depends(sent_review_notes)]):
    return review_step(request, user, guide_id, notes, guides.unpublish,
                       "已撤下，攻略作为草稿回到作者手里。点击“更新网站”后，"
                       "它才会从公开网站上消失。")


def revision_editor_page(request: Request, user: User, revision: Revision,
                         fields: GuideFields, *, error: str | None = None,
                         status_code: int = 200):
    with db.connect() as conn:
        heroes = game.heroes(conn)
        patches = guides.patch_choices(conn, revision)
        rounds = guides.revision_rounds(conn, user, revision.id)
    return templates.TemplateResponse(
        request, "admin/revision_edit.html",
        {"title": f"修订：{revision.guide.title_zh or '（无标题）'}", "user": user,
         "revision": revision, "fields": fields, "heroes": heroes,
         "patches": patches, "error": error, "review_rounds": rounds,
         "can_submit": guides.can_submit_revision(user, revision),
         "can_publish": guides.can_publish_revision(user, revision),
         "can_review": guides.can_publish_revision(user, revision),
         "can_discard": guides.can_discard_revision(user, revision)},
        status_code=status_code)


def open_revision_of(guide_id: int,
                     user: Annotated[User, Depends(signed_in_user)]) -> Revision:
    """The open Revision of the Guide in the URL, or 404."""
    with db.connect() as conn:
        revision = guides.revision(conn, user, guide_id)
    if revision is None:
        raise HTTPException(status_code=404)
    return revision


def revision_refused_page(request: Request, user: User, guide_id: int,
                          fields: GuideFields | None, refused: guides.Refused):
    """Show the Revision's editor again with the reason, keeping what was
    typed; or the Guide's editor, if the Revision is gone."""
    with db.connect() as conn:
        revision = guides.revision(conn, user, guide_id)
    if revision is None:
        return refused_page(request, user, guide_id, None, refused)
    return revision_editor_page(request, user, revision,
                                fields or GuideFields.of(revision),
                                error=refused.message, status_code=status_for(refused))


@router.post("/admin/guides/{guide_id}/revisions")
def open_revision(request: Request, guide_id: int,
                  user: Annotated[User, Depends(signed_in_user)]):
    try:
        with db.connect() as conn:
            guides.open_revision(conn, user, guide_id)
    except guides.Refused as refused:
        return refused_page(request, user, guide_id, None, refused)
    flash(request, "修订已打开。审核通过前，网站上仍显示原来的版本。")
    return redirect(f"/admin/guides/{guide_id}/revision/edit")


@router.get("/admin/guides/{guide_id}/revision/edit")
def edit_revision_form(request: Request,
                       user: Annotated[User, Depends(signed_in_user)],
                       revision: Annotated[Revision, Depends(open_revision_of)]):
    return revision_editor_page(request, user, revision, GuideFields.of(revision))


@router.post("/admin/guides/{guide_id}/revision")
def save_revision(request: Request, guide_id: int,
                  user: Annotated[User, Depends(signed_in_user)],
                  fields: Annotated[GuideFields, Depends(guide_fields)]):
    try:
        with db.connect() as conn:
            guides.save_revision(conn, user, guide_id, fields)
    except guides.Refused as refused:
        return revision_refused_page(request, user, guide_id, fields, refused)
    flash(request, "修订已保存。")
    return redirect(f"/admin/guides/{guide_id}/revision/edit")


def revision_step(request: Request, user: User, guide_id: int,
                  fields: GuideFields | None, step: WorkflowStep, done: str,
                  then: str = "revision/edit"):
    """Press a workflow button on a Revision, as `workflow_step` does on a
    Guide; afterwards show the Guide's page `then`."""
    try:
        with db.connect() as conn:
            if fields:
                guides.save_revision(conn, user, guide_id, fields)
            step(conn, user, guide_id)
    except guides.Refused as refused:
        return revision_refused_page(request, user, guide_id, fields, refused)
    flash(request, done)
    return redirect(f"/admin/guides/{guide_id}/{then}")


@router.post("/admin/guides/{guide_id}/revision/submit")
def submit_revision(request: Request, guide_id: int,
                    user: Annotated[User, Depends(signed_in_user)],
                    fields: Annotated[GuideFields | None, Depends(sent_guide_fields)]):
    return revision_step(request, user, guide_id, fields, guides.submit_revision,
                         "修订已提交审核。审核通过前，网站上仍显示原来的版本。")


@router.post("/admin/guides/{guide_id}/revision/publish")
def publish_revision(request: Request, guide_id: int,
                     user: Annotated[User, Depends(signed_in_user)],
                     fields: Annotated[GuideFields | None, Depends(sent_guide_fields)]):
    return revision_step(request, user, guide_id, fields, guides.publish_revision,
                         "修订已发布，替换了原来的内容。点击“更新网站”后，"
                         "读者才会在公开网站上看到它。", then="edit")


@router.get("/admin/guides/{guide_id}/revision/preview")
def preview_revision(request: Request, user: Annotated[User, Depends(signed_in_user)],
                     revision: Annotated[Revision, Depends(open_revision_of)]):
    return preview_page(request, user, revision)


@router.get("/admin/guides/{guide_id}/revision/review")
def review_revision(request: Request, user: Annotated[User, Depends(signed_in_user)],
                    revision: Annotated[Revision, Depends(open_revision_of)]):
    if not user.can("publish_guides"):
        raise AdminRequired(user)
    return review_page(request, user, revision, [])


@router.post("/admin/guides/{guide_id}/revision/return")
def return_revision(request: Request, guide_id: int,
                    user: Annotated[User, Depends(signed_in_user)],
                    notes: Annotated[list[ReviewNote], Depends(sent_review_notes)]):
    try:
        with db.connect() as conn:
            guides.return_revision(conn, user, guide_id, notes)
    except guides.Refused as refused:
        revision = None
        if user.can("publish_guides"):
            with db.connect() as conn:
                revision = guides.revision(conn, user, guide_id)
        if revision is None:
            return revision_refused_page(request, user, guide_id, None, refused)
        return review_page(request, user, revision, notes, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "修订已退回给作者，网站上的攻略保持不变。")
    return redirect(f"/admin/guides/{guide_id}/revision/edit")


@router.get("/admin/guides/{guide_id}/delete")
def confirm_delete_guide(request: Request,
                         user: Annotated[User, Depends(signed_in_user)],
                         guide: Annotated[Guide, Depends(visible_guide)]):
    consequences = ["删除后它会进入回收站。只有管理员能看到回收站，并可以把它恢复。"]
    if guide.status == "published":
        consequences.append("下次“更新网站”后，它会从公开网站上消失。")
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "删除攻略", "user": user,
         "question": f"确定要删除《{guide.title_zh or '（无标题）'}》吗？",
         "consequences": consequences, "button": "删除",
         "action": f"{guide.console_path}/delete",
         "cancel": f"{guide.console_path}/edit"})


@router.post("/admin/guides/{guide_id}/delete")
def delete_guide(request: Request, guide_id: int,
                 user: Annotated[User, Depends(signed_in_user)]):
    try:
        with db.connect() as conn:
            guides.delete(conn, user, guide_id)
    except guides.Refused as refused:
        return refused_page(request, user, guide_id, None, refused)
    flash(request, "已删除，攻略已移到回收站。")
    return redirect("/admin/guides")


@router.get("/admin/guides/{guide_id}/revision/delete")
def confirm_discard_revision(request: Request,
                             user: Annotated[User, Depends(signed_in_user)],
                             revision: Annotated[Revision, Depends(open_revision_of)]):
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "放弃修订", "user": user,
         "question": f"确定要放弃《{revision.guide.title_zh or '（无标题）'}》的这份修订吗？",
         "consequences": ["修订里的改动会被丢弃，无法恢复。已发布的攻略保持不变。"],
         "button": "放弃修订", "action": f"{revision.console_path}/delete",
         "cancel": f"{revision.console_path}/edit"})


@router.post("/admin/guides/{guide_id}/revision/delete")
def discard_revision(request: Request, guide_id: int,
                     user: Annotated[User, Depends(signed_in_user)]):
    try:
        with db.connect() as conn:
            guides.discard_revision(conn, user, guide_id)
    except guides.Refused as refused:
        return revision_refused_page(request, user, guide_id, None, refused)
    flash(request, "修订已放弃，已发布的攻略保持不变。")
    return redirect(f"/admin/guides/{guide_id}/edit")
