"""The FastAPI application.

T00: the admin console answers at /admin and the public site answers at /.
Ticket routes live in their own modules under app/routes/ and are included
here. Keep this file small.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from app import settings, web
from app.routes import auth, dashboard, game, guides, site, trash, users
from app.web import templates


def create_app() -> FastAPI:
    app = FastAPI(title="IPHS 400 MP2 CMS",
                  dependencies=[Depends(web.verify_csrf)])
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                       session_cookie=web.SESSION_COOKIE,
                       max_age=web.SESSION_MAX_AGE, same_site="lax")
    app.add_exception_handler(web.LoginRequired, web.login_required_handler)
    app.add_exception_handler(web.SetupRequired, web.setup_required_handler)
    app.add_exception_handler(web.AdminRequired, web.admin_required_handler)
    app.add_exception_handler(web.CsrfRejected, web.csrf_rejected_handler)

    @app.get("/admin")
    def admin_home(request: Request):
        return templates.TemplateResponse(
            request, "admin/hello.html", {"title": "Admin"}
        )

    @app.get("/")
    def public_home(request: Request):
        return templates.TemplateResponse(
            request, "public/home.html",
            {"title": settings.SITE_TITLE, "items": []},
        )

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(game.router)
    app.include_router(guides.router)
    app.include_router(site.router)
    app.include_router(trash.router)
    app.include_router(users.router)
    return app


app = create_app()
