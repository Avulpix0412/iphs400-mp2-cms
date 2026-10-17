"""Heroes and Patches, managed by Admins only.

The router itself requires an Admin, so no route here can forget to; each
route's own `admin_user` is the same (cached) check, there to get the user.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app import db, game
from app.accounts import User
from app.web import admin_user, flash, redirect, templates

router = APIRouter(dependencies=[Depends(admin_user)])


def hero_list_page(request: Request, user: User, *, name_zh: str = "",
                   name_en: str = "", error: str | None = None):
    with db.connect() as conn:
        heroes = game.heroes(conn)
    return templates.TemplateResponse(
        request, "admin/heroes.html",
        {"title": "英雄", "user": user, "heroes": heroes, "name_zh": name_zh,
         "name_en": name_en, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/heroes")
def hero_list(request: Request, user: Annotated[User, Depends(admin_user)]):
    return hero_list_page(request, user)


# Form fields default to "" so a blank field gets our message, not a 422.
@router.post("/admin/heroes")
def add_hero(request: Request, user: Annotated[User, Depends(admin_user)],
             name_zh: Annotated[str, Form()] = "",
             name_en: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            hero = game.add_hero(conn, name_zh=name_zh, name_en=name_en)
    except game.Refused as refused:
        return hero_list_page(request, user, name_zh=name_zh, name_en=name_en,
                              error=refused.message)
    flash(request, f"已添加英雄：{hero.name_zh}（{hero.name_en}）。")
    return redirect("/admin/heroes")


def existing_hero(hero_id: int) -> game.Hero:
    with db.connect() as conn:
        hero = game.hero(conn, hero_id)
    if hero is None:
        raise HTTPException(status_code=404)
    return hero


def hero_edit_page(request: Request, user: User, hero: game.Hero, *,
                   name_zh: str, name_en: str, error: str | None = None):
    return templates.TemplateResponse(
        request, "admin/hero_edit.html",
        {"title": f"编辑英雄：{hero.name_zh}", "user": user, "hero": hero,
         "name_zh": name_zh, "name_en": name_en, "error": error},
        status_code=400 if error else 200)


@router.get("/admin/heroes/{hero_id}/edit")
def hero_edit_form(request: Request, user: Annotated[User, Depends(admin_user)],
                   hero: Annotated[game.Hero, Depends(existing_hero)]):
    return hero_edit_page(request, user, hero, name_zh=hero.name_zh,
                          name_en=hero.name_en)


@router.post("/admin/heroes/{hero_id}")
def edit_hero(request: Request, user: Annotated[User, Depends(admin_user)],
              hero: Annotated[game.Hero, Depends(existing_hero)],
              name_zh: Annotated[str, Form()] = "",
              name_en: Annotated[str, Form()] = ""):
    try:
        with db.connect() as conn:
            game.edit_hero(conn, hero.id, name_zh=name_zh, name_en=name_en)
    except game.Refused as refused:
        return hero_edit_page(request, user, hero, name_zh=name_zh,
                              name_en=name_en, error=refused.message)
    flash(request, "已保存英雄的官方名称。")
    return redirect("/admin/heroes")


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
