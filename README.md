# 大巴扎攻略站 (The Bazaar Guides)

A small CMS for the Chinese-speaking community of the card game *The Bazaar*.
A few streamers (up主) run the site as Admins; invited writers join as Editors
and write Guides, which an Admin reviews and publishes. Readers, who have no
account, find a written build for a given Hero and Patch on the public site
instead of scrubbing through videos.

The admin console runs on a laptop only. `cms publish` renders the published
content into `site/` as static HTML in Chinese and English, and that is what
GitHub Pages serves. The project's vocabulary is in `CONTEXT.md`.

## Live URL

https://avulpix0412.github.io/iphs400-mp2-cms/

## Run locally

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer.

```bash
git clone https://github.com/Avulpix0412/iphs400-mp2-cms.git
cd iphs400-mp2-cms
uv sync
cp .env.example .env    # then change the passwords and the secret key
uv run python scripts/seed_demo.py
uv run cms serve    # then open http://localhost:8000/login
```

Run these from the repository root: the `cms` command and the seed script load
`.env` from the folder you run them in. A variable already set in your shell
wins over the same key in `.env`, and `uv run --env-file .env …` still works.
The loader skips blank lines, `#` comments and a leading `export `, strips the
quotes around a quoted value, and warns about (and skips) any line that is not
`KEY=value`.

The seed script creates `admin@example.test` (Admin, 演示管理员) and
`editor@example.test` (Editor, 演示编辑), with the passwords you set in `.env` as
`CMS_ADMIN_PASSWORD` and `CMS_EDITOR_PASSWORD`. It refuses to run without them;
there are no default passwords. It also adds demo Heroes, the Patches 6.5–6.7
(6.7 is the Current Patch), Draft, Submitted and Published Guides, an About
page and two Tournament items. Running it again leaves existing records unchanged.

To build the public site from what is published:

```bash
uv run cms publish    # writes site/; it prints a preview command
```

## Generative AI Use Statement

Models (all through Anthropic):

- Claude Opus 5.5 (`claude-opus-5-5`): every session.
- Claude Sonnet 5.5 (`claude-sonnet-5-5`): part of the first session, 2026-10-12.

Skills:

- mattpocock-skills: `grill-with-docs`, `grilling` and `domain-modeling` (the
  grill); `to-spec` and `to-tickets`; `implement` and `tdd` (each ticket);
  `code-review`; `pr`; `handoff`; `research`.
- Claude Code's built-in `/code-review`.
- gstack `/browse`, for checking pages in a headless browser and taking the
  screenshots.

### Backends used

| Provider | Models | Ledger sessions | Ledger rows | Dates |
|---|---|---|---|---|
| Anthropic | Opus 5.5, Sonnet 5.5 | 22 | 130 (Opus 119, Sonnet 11) | 2026-10-12 to 2026-10-18 |

No session used a non-Anthropic base URL, so no commit carries a `Backend:` trailer.
