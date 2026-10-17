"""The `cms` command: serve, publish, deploy.

    uv run cms serve      # admin console + public preview at http://localhost:8000
    uv run cms publish    # render site/ from published content
    uv run cms deploy     # push site/ to the gh-pages branch (Pages serves it)
"""
from __future__ import annotations

import argparse

from app import publish, settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cms")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the admin console locally")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", default=True)
    sub.add_parser("publish", help="render site/ from published content")
    deploy = sub.add_parser("deploy", help="push site/ to gh-pages")
    deploy.add_argument("--message", default="Publish site")
    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("app.main:app", port=args.port, reload=args.reload)
        return 0

    if args.command == "publish":
        out = publish.render_site()
        print(f"Wrote {out}. Preview it with:  python3 -m http.server -d {out} 8001")
        return 0

    if args.command == "deploy":
        if not settings.SITE.exists():
            print("site/ does not exist yet — run `uv run cms publish` first.")
            return 1
        try:
            publish.deploy(settings.SITE, args.message)
        except publish.DeployFailed as failed:
            print(f"Deploy failed: {failed.message}")
            return 1
        print("Pushed to gh-pages. Settings -> Pages -> Deploy from a branch -> "
              "gh-pages / root, then wait up to 10 minutes.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
