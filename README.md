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

All of the code in this project was written by Claude Code using the pipeline of grill, spec, tickets, and  `/implement`, `/tdd`, `/code-review` and `/pr` for each ticket. Except for part of the session 01 using Sonnet 5.5 medium effort, all of the rest was done by Opus 5.5 high effort. I made the decisions in the grill, read all the review, and either confirmed or rejected Claude’s suggestions before anything was merged. I worked in two languages, because the project is in English, sometimes when the feedback is long and I don’t fully understand what it was saying, I will send it to a different session to let it explain to me to make sure I understand the context, then I will work with it and send my answer back. It also helped me collected the evidences and resources for my report and this statement, and based on the information, I wrote the report and this statement in my own word.

Below are the two prompts that I sent

1. On the budget plan (session 12): "If I hit the 5 hour limit, I'll just upgrade my plan, because I have other projects to work with Claude code, such as the project for IPHS 484 and I notice that opus 5.5 can de better job than sonnet 5, so it is necessary to stay in opus 5.5."
2. On one-character Chinese nicknames in T07 (session 16): "single character nickname in Chinese is rare but some people would use, so I think it is better (1) When an Admin records a one character Chinese nickname, show a notice on the term page that it will match every occurrence of that character and may cause many warnings. The Admin can still save it. (2) In the preview, show each unmarked nickname as one warning with a count, instead of one warning per occurrence."


One of the model failure is that in T08 (#9, session 17), Claude skipped the test-first step of `/tdd`. Its own summary said "most Tournament tests passed the first time they ran, because I wrote that code in one go." The tests was passed, and `/code-review` only reads the diff, so it would not been noticed, but Claude reported it to me and It then broke the recap link on purpose to prove the matching tests could fail, and I accepted that repair but decided to mention it later in the report or AI statment because I think it is a perfect example. 

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
| Anthropic | Opus 5.5, Sonnet 5.5 | 24 | 138 (Opus 127, Sonnet 11) | 2026-10-12 to 2026-10-18 |

No session used a non-Anthropic base URL, so no commit carries a `Backend:` trailer.
