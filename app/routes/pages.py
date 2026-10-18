"""Pages (such as About 关于) in the console, managed by Admins only.

The router itself requires an Admin, so no route here can forget to. Every
change goes through app/content.py; these routes only turn its answers into
pages.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app import content, db, game
from app.accounts import User
from app.content import Page, PageFields, TextBearing
from app.rendering import preview_warnings, render_markdown
from app.web import flash, form_text, redirect, requires, templates

page_manager = requires("manage_pages")
router = APIRouter(dependencies=[Depends(page_manager)])


async def page_fields(request: Request) -> PageFields:
    form = await request.form()
    return PageFields(**{name: form_text(form, name) for name in
                         ("slug", "title_zh", "body_zh", "title_en", "body_en")})


async def sent_page_fields(request: Request) -> PageFields | None:
    """The editor form's fields when a button inside it sent them along, or
    None for a bare post of the button alone."""
    return await page_fields(request) if "slug" in await request.form() else None


def status_for(refused: content.Refused) -> int:
    if isinstance(refused, content.NotFound):
        return 404
    return 403 if isinstance(refused, content.NotAllowed) else 400


def existing_page(page_id: int, user: Annotated[User, Depends(page_manager)]) -> Page:
    try:
        with db.connect() as conn:
            return content.page(conn, user, page_id)
    except content.NotFound:
        raise HTTPException(status_code=404) from None


def editor_page(request: Request, user: User, page: Page | None, fields: PageFields,
                *, error: str | None = None, status_code: int = 200):
    title = f"编辑页面：{page.title_zh or '（无标题）'}" if page else "新建页面"
    return templates.TemplateResponse(
        request, "admin/page_edit.html",
        {"title": title, "user": user, "page": page, "fields": fields,
         "error": error},
        status_code=status_code)


@router.get("/admin/pages")
def page_list(request: Request, user: Annotated[User, Depends(page_manager)]):
    with db.connect() as conn:
        listed = content.pages(conn, user)
    return templates.TemplateResponse(
        request, "admin/pages.html", {"title": "页面", "user": user, "pages": listed})


@router.get("/admin/pages/new")
def new_page_form(request: Request, user: Annotated[User, Depends(page_manager)]):
    return editor_page(request, user, None, PageFields())


@router.post("/admin/pages")
def create_page(request: Request, user: Annotated[User, Depends(page_manager)],
                fields: Annotated[PageFields, Depends(page_fields)]):
    try:
        with db.connect() as conn:
            page = content.create_page(conn, user, fields)
    except content.Refused as refused:
        return editor_page(request, user, None, fields, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "草稿已保存。")
    return redirect(f"/{page.console_path}/edit")


@router.get("/admin/pages/{page_id}/edit")
def edit_page_form(request: Request, user: Annotated[User, Depends(page_manager)],
                   page: Annotated[Page, Depends(existing_page)]):
    return editor_page(request, user, page, PageFields.of(page))


@router.post("/admin/pages/{page_id}")
def save_page(request: Request, user: Annotated[User, Depends(page_manager)],
              page: Annotated[Page, Depends(existing_page)],
              fields: Annotated[PageFields, Depends(page_fields)]):
    try:
        with db.connect() as conn:
            content.save_page(conn, user, page.id, fields)
    except content.Refused as refused:
        return editor_page(request, user, page, fields, error=refused.message,
                           status_code=status_for(refused))
    flash(request, "已保存。" if page.status == "draft"
          else "已保存。点击“更新网站”后，读者才会看到改动。")
    return redirect(f"/{page.console_path}/edit")


@router.post("/admin/pages/{page_id}/publish")
def publish_page(request: Request, user: Annotated[User, Depends(page_manager)],
                 page: Annotated[Page, Depends(existing_page)],
                 fields: Annotated[PageFields | None, Depends(sent_page_fields)]):
    """Publish, saving the editor's fields first when they came along; if
    either is refused, neither is saved."""
    try:
        with db.connect() as conn:
            if fields:
                content.save_page(conn, user, page.id, fields)
            content.publish_page(conn, user, page.id)
    except content.Refused as refused:
        return editor_page(request, user, page, fields or PageFields.of(page),
                           error=refused.message, status_code=status_for(refused))
    flash(request, "已发布。点击“更新网站”后，它会出现在公开网站的导航里。")
    return redirect(f"/{page.console_path}/edit")


@router.post("/admin/pages/{page_id}/unpublish")
def unpublish_page(request: Request, user: Annotated[User, Depends(page_manager)],
                   page: Annotated[Page, Depends(existing_page)]):
    try:
        with db.connect() as conn:
            content.unpublish_page(conn, user, page.id)
    except content.Refused as refused:
        return editor_page(request, user, page, PageFields.of(page),
                           error=refused.message, status_code=status_for(refused))
    flash(request, "已撤下，页面回到了草稿。点击“更新网站”后，它才会从公开网站上消失。")
    return redirect(f"/{page.console_path}/edit")


@router.get("/admin/pages/{page_id}/delete")
def confirm_delete_page(request: Request, user: Annotated[User, Depends(page_manager)],
                        page: Annotated[Page, Depends(existing_page)]):
    consequences = ["彻底删除后无法恢复。"]
    if page.status == "published":
        consequences.append("下次“更新网站”后，它会从公开网站和导航里消失。")
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "删除页面", "user": user,
         "question": f"确定要彻底删除页面《{page.title_zh or '（无标题）'}》吗？",
         "consequences": consequences, "button": "彻底删除",
         "action": f"{page.console_path}/delete",
         "cancel": f"{page.console_path}/edit"})


@router.post("/admin/pages/{page_id}/delete")
def delete_page(request: Request, user: Annotated[User, Depends(page_manager)],
                page: Annotated[Page, Depends(existing_page)]):
    try:
        with db.connect() as conn:
            content.delete_page(conn, user, page.id)
    except content.NotFound:  # deleted in another tab just now
        raise HTTPException(status_code=404) from None
    flash(request, "页面已彻底删除。")
    return redirect("/admin/pages")


def preview_page(request: Request, user: User, item: TextBearing, *, kind: str,
                 meta: dict[str, str] | None = None,
                 images: dict[str, dict[str, tuple[str, str]]] | None = None):
    """A Page or Tournament item as Readers will see it, with warnings about
    its Game Term markers and nicknames. `meta` is the line under each
    language's title, and `images` what its text needs to show its images
    (see media.sources), by language."""
    with db.connect() as conn:
        glossary = game.glossary(conn)
    rendered = {lang: render_markdown(getattr(item, f"body_{lang}"), lang, glossary,
                                      (images or {}).get(lang))
                for lang in ("zh", "en")}
    term_warnings = preview_warnings(item.title_zh, item.title_en, rendered["zh"],
                                     rendered["en"], glossary)
    return templates.TemplateResponse(
        request, "admin/content_preview.html",
        {"title": f"预览：{item.title_zh or '（无标题）'}", "user": user,
         "item": item, "kind": kind, "meta": meta or {},
         "body_zh": rendered["zh"].html, "body_en": rendered["en"].html,
         "term_warnings": term_warnings})


@router.get("/admin/pages/{page_id}/preview")
def preview(request: Request, user: Annotated[User, Depends(page_manager)],
            page: Annotated[Page, Depends(existing_page)]):
    return preview_page(request, user, page, kind="页面")
