"""The 更新网站 button: the Site build, which is the only step that changes what
Readers see. Admins only."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import publish
from app.accounts import User
from app.web import AdminRequired, flash, redirect, signed_in_user

router = APIRouter()


def site_builder(user: Annotated[User, Depends(signed_in_user)]) -> User:
    if not user.can("build_site"):
        raise AdminRequired
    return user


@router.post("/admin/site-build", dependencies=[Depends(site_builder)])
def update_site(request: Request):
    try:
        publish.build_site()
    except publish.DeployFailed as failed:
        flash(request, f"更新网站失败，读者看到的还是之前的网站。原因：{failed.message}",
              "error")
    else:
        flash(request, "网站已更新。GitHub Pages 可能需要几分钟才会显示新内容。")
    return redirect("/admin/dashboard")
