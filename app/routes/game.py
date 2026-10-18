"""Game Terms (Heroes on their own page) and Patches, managed by Admins only.

The router itself requires an Admin, so no route here can forget to; each
route's own `admin_user` is the same (cached) check, there to get the user.
"""
from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app import db, game
from app.accounts import User
from app.web import admin_user, flash, redirect, templates

router = APIRouter(dependencies=[Depends(admin_user)])


def hero_list_page(request: Request, user: User, *, name_zh: str = "",
                   name_en: str = "", nicknames: str = "",
                   error: str | None = None):
    with db.connect() as conn:
        heroes = game.heroes(conn)
    return templates.TemplateResponse(
        request, "admin/heroes.html",
        {"title": "英雄", "user": user, "heroes": heroes, "name_zh": name_zh,
         "name_en": name_en, "nicknames": nicknames, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/heroes")
def hero_list(request: Request, user: Annotated[User, Depends(admin_user)]):
    return hero_list_page(request, user)


# Form fields default to "" so a blank field gets our message, not a 422.
@router.post("/admin/heroes")
def add_hero(request: Request, user: Annotated[User, Depends(admin_user)],
             name_zh: Annotated[str, Form()] = "",
             name_en: Annotated[str, Form()] = "",
             nicknames: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            hero = game.add_hero(conn, name_zh=name_zh, name_en=name_en,
                                 nicknames=nicknames)
    except game.Refused as refused:
        return hero_list_page(request, user, name_zh=name_zh, name_en=name_en,
                              nicknames=nicknames, error=refused.message)
    flash(request, f"已添加英雄：{hero.name_zh}（{hero.name_en}）。")
    return redirect("/admin/heroes")


def existing_hero(hero_id: int) -> game.Hero:
    with db.connect() as conn:
        hero = game.hero(conn, hero_id)
    if hero is None:
        raise HTTPException(status_code=404)
    return hero


def hero_edit_page(request: Request, user: User, hero: game.Hero, *,
                   name_zh: str, name_en: str, nicknames: str,
                   error: str | None = None):
    return templates.TemplateResponse(
        request, "admin/hero_edit.html",
        {"title": f"编辑英雄：{hero.name_zh}", "user": user, "hero": hero,
         "name_zh": name_zh, "name_en": name_en, "nicknames": nicknames,
         "error": error},
        status_code=400 if error else 200)


@router.get("/admin/heroes/{hero_id}/edit")
def hero_edit_form(request: Request, user: Annotated[User, Depends(admin_user)],
                   hero: Annotated[game.Hero, Depends(existing_hero)]):
    return hero_edit_page(request, user, hero, name_zh=hero.name_zh,
                          name_en=hero.name_en, nicknames="、".join(hero.nicknames))


@router.post("/admin/heroes/{hero_id}")
def edit_hero(request: Request, user: Annotated[User, Depends(admin_user)],
              hero: Annotated[game.Hero, Depends(existing_hero)],
              name_zh: Annotated[str, Form()] = "",
              name_en: Annotated[str, Form()] = "",
              nicknames: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            game.edit_hero(conn, hero.id, name_zh=name_zh, name_en=name_en,
                           nicknames=nicknames)
    except game.Refused as refused:
        return hero_edit_page(request, user, hero, name_zh=name_zh,
                              name_en=name_en, nicknames=nicknames,
                              error=refused.message)
    flash(request, "已保存英雄的官方名称和外号。")
    return redirect("/admin/heroes")


def term_list_page(request: Request, user: User, *, kind: str = "",
                   name_zh: str = "", name_en: str = "", nicknames: str = "",
                   error: str | None = None):
    with db.connect() as conn:
        terms = game.terms(conn)
    return templates.TemplateResponse(
        request, "admin/terms.html",
        {"title": "游戏术语", "user": user, "terms": terms, "kinds": game.KINDS,
         "kind": kind, "name_zh": name_zh, "name_en": name_en,
         "nicknames": nicknames, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/terms")
def term_list(request: Request, user: Annotated[User, Depends(admin_user)]):
    return term_list_page(request, user)


@router.post("/admin/terms")
def add_term(request: Request, user: Annotated[User, Depends(admin_user)],
             kind: Annotated[str, Form()] = "",
             name_zh: Annotated[str, Form()] = "",
             name_en: Annotated[str, Form()] = "",
             nicknames: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            term = game.add_term(conn, kind=kind, name_zh=name_zh, name_en=name_en,
                                 nicknames=nicknames)
    except game.Refused as refused:
        return term_list_page(request, user, kind=kind, name_zh=name_zh,
                              name_en=name_en, nicknames=nicknames,
                              error=refused.message)
    flash(request, f"已添加{term.kind_label}：{term.name_zh}（{term.name_en}）。")
    return redirect("/admin/terms")


def import_page(request: Request, user: User, *, error: str | None = None):
    return templates.TemplateResponse(
        request, "admin/term_import.html",
        {"title": "导入游戏术语", "user": user, "kinds": game.KINDS, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/terms/import")
def term_import_form(request: Request, user: Annotated[User, Depends(admin_user)]):
    return import_page(request, user)


@router.post("/admin/terms/import")
def preview_term_import(request: Request, user: Annotated[User, Depends(admin_user)],
                        file: Annotated[UploadFile | None, File()] = None):
    """Show what the chosen CSV file would add, change and reject. Nothing is
    saved until the Admin confirms; the file comes back with that form."""
    csv_bytes = file.file.read() if file else b""
    try:
        with db.connect() as conn:
            plan = game.plan_import(conn, csv_bytes)
    except game.Refused as refused:
        return import_page(request, user, error=refused.message)
    return templates.TemplateResponse(
        request, "admin/term_import_preview.html",
        {"title": "导入游戏术语：预览", "user": user, "plan": plan, "kinds": game.KINDS,
         "csv_file": base64.b64encode(csv_bytes).decode()})


@router.post("/admin/terms/import/confirm")
def confirm_term_import(request: Request, user: Annotated[User, Depends(admin_user)],
                        csv_file: Annotated[str, Form()] = ""):
    try:
        csv_bytes = base64.b64decode(csv_file, validate=True)
        with db.connect() as conn:
            plan = game.import_terms(conn, csv_bytes)
    except (ValueError, game.Refused):
        return import_page(request, user, error="导入失败：请重新选择 CSV 文件并预览。")
    rejected = f"{len(plan.rejected)} 行被拒绝，没有导入。" if plan.rejected else ""
    flash(request, f"已导入游戏术语：新增 {len(plan.added)} 个，"
                   f"修改 {len(plan.changed)} 个。{rejected}")
    return redirect("/admin/terms")


def existing_term(term_id: int) -> game.Term:
    """A Game Term other than a Hero (whose edit page is on the Hero list)."""
    with db.connect() as conn:
        term = game.term(conn, term_id)
    if term is None or term.kind == "hero":
        raise HTTPException(status_code=404)
    return term


def term_edit_page(request: Request, user: User, term: game.Term, *,
                   name_zh: str, name_en: str, nicknames: str,
                   error: str | None = None):
    return templates.TemplateResponse(
        request, "admin/term_edit.html",
        {"title": f"编辑{term.kind_label}：{term.name_zh}", "user": user,
         "term": term, "name_zh": name_zh, "name_en": name_en,
         "nicknames": nicknames, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/terms/{term_id}/edit")
def term_edit_form(request: Request, user: Annotated[User, Depends(admin_user)],
                   term: Annotated[game.Term, Depends(existing_term)]):
    return term_edit_page(request, user, term, name_zh=term.name_zh,
                          name_en=term.name_en, nicknames="、".join(term.nicknames))


# Declared after POST /admin/terms/import, which it would otherwise catch.
@router.post("/admin/terms/{term_id}")
def edit_term(request: Request, user: Annotated[User, Depends(admin_user)],
              term: Annotated[game.Term, Depends(existing_term)],
              name_zh: Annotated[str, Form()] = "",
              name_en: Annotated[str, Form()] = "",
              nicknames: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            game.edit_term(conn, term.id, name_zh=name_zh, name_en=name_en,
                           nicknames=nicknames)
    except game.Refused as refused:
        return term_edit_page(request, user, term, name_zh=name_zh,
                              name_en=name_en, nicknames=nicknames,
                              error=refused.message)
    flash(request, f"已保存{term.kind_label}的官方名称和外号。")
    return redirect("/admin/terms")


def patch_list_page(request: Request, user: User, *, name: str = "",
                    error: str | None = None):
    with db.connect() as conn:
        patches = game.patches(conn)
    return templates.TemplateResponse(
        request, "admin/patches.html",
        {"title": "版本", "user": user, "patches": patches, "name": name,
         "error": error},
        status_code=400 if error else 200)


@router.get("/admin/patches")
def patch_list(request: Request, user: Annotated[User, Depends(admin_user)]):
    return patch_list_page(request, user)


@router.post("/admin/patches")
def add_patch(request: Request, user: Annotated[User, Depends(admin_user)],
              name: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            patch = game.add_patch(conn, name)
    except game.Refused as refused:
        return patch_list_page(request, user, name=name, error=refused.message)
    flash(request, f"已添加版本 {patch.name}，它现在是当前版本。")
    return redirect("/admin/patches")
