# Handoff: 大巴扎攻略站 CMS, after the Stage 2 screenshots

Repo: `/Users/yining/orca/workspaces/iphs400-mp2-cms/IPHS400-Mini-Project-2` (a git worktree on branch
`Avulpix0412/IPHS400-Mini-Project-2`, reused for every session; do not delete it, or the branch, after merging).
The main checkout is `/Users/yining/code/iphs400-mp2-cms` (on `main`), which holds the real local `cms.db`.

## Where things stand

- **The 12 Stage 2 screenshots are done, merged and on `main`.**
  - PR: https://github.com/Avulpix0412/iphs400-mp2-cms/pull/30 (merge commit `9f96c2b`; work commit `2695d97`).
    It also carried transcripts 18–20, handoffs 06–07 and the compaction-log row.
  - The branch and `main` are level.
- **Not committed yet:** this file, this session's transcript (21, written by the SessionEnd hook), and this
  session's ledger rows. They go into the next "Add transcript NN" commit, after the credential scan.
- **The ledger rows for the screenshot session are labelled `S1`.** `.claude/state/phase` still says `S1`. The
  screenshot work is not one of the stages `CLAUDE.md` lists. Ask the user what label the writing session
  should use (for example `report`), and write it into the phase file before starting.
- **Open issues:** #12 S2 hosted console (stretch) and spec #1. The user has not said whether #12 will be
  done. Ask before assuming.
- **Deadlines:** the manual's dates are stale. The professor extended them, so do not flag anything as overdue.

## Next session: the Stage 2 writing

`uv run python scripts/check_submission.py --stage 2` passed 18/22 at handoff (482 tests passed). The four
failures:

| Check | What is missing |
|---|---|
| report named correctly | `docs/iphs400_mp2-web-cms_report_nick-chen_YYYYMMDD.md` does not exist yet. |
| README has run-locally section | The checker looks for the words "Run locally". The README's section is called "Run it". |
| AI Use Statement was rewritten | `README.md` still has the template placeholder paragraph. |
| tag mp2-final exists | Tag it last, once everything else passes. Ask the user before tagging and pushing tags. |

Requirements, by reference (do not restate them in the docs):
- **Report:** manual `docs/manual_iphs400_mp2-web-cms_20260922.md` §8.2 (the four questions, 1–2 pages).
  Rubric `docs/mp2-grading-rubric_20260922.md` A3 (report voice), the AI-tells list under A5, and G1.
- **README:** manual §8.2 and Part 9 (the *Backends used* table). Rubric A4 and G2.
- **Submission email:** manual §8.2 (subject line, three links, report attached). The user sends it.

What the writing has to get right (not obvious from the rubric):
- **The user writes it.** The rubric's single biggest cost is unedited model output (A3, manual §8.2). Help
  find evidence and check claims; do not hand over a finished draft unless the user asks for one. Never invent
  a prompt, a failure or a number.
- **Every claim must be checkable in the repo** (G1). Point at the source:
  - grill decisions: the grill transcripts in `docs/transcripts/` and spec #1;
  - drift or invention caught by the workflow: the `/code-review` comments on the ticket issues, and the
    two wrong test claims in #29's first PR draft (handoff 07);
  - budget numbers: `notes/usage-ledger.csv`, `notes/token-budget-plan.md`, `scripts/usage_report.py`,
    `docs/process/compaction-log.md`;
  - real prompts to quote: the transcripts.
- **README fixes beyond the four failures:**
  - The README is still the template's starter README (title, "Click **Use this template**", the old
    deadlines, "What is here" describing the T00 skeleton). Ask the user how much of it to rewrite.
  - The *Live URL* check passes only because `http://localhost:8000` is in the file. The real Pages URL is
    https://avulpix0412.github.io/iphs400-mp2-cms/ (Pages status: built). Add it as a *Live URL* section.
  - *Run locally* must work on a clean clone (manual §8.2). Test the steps in a scratch clone before claiming
    they work.
  - *Backends used* table: every session so far ran on Anthropic models. No ledger row has a non-Anthropic
    backend, and no session has used a `Backend:` trailer.
- **Naming:** `{first}-{last}` is `nick-chen` (the transcripts already use it). Lowercase, date as `YYYYMMDD`.

## Things the screenshot session learned

- **The local `.env` demo passwords are the `.env.example` placeholders**, in both checkouts. The credential
  scan showed this (values masked, never printed). The user approved committing transcript 20, whose hits are
  those public placeholders. They should change before #12 puts the console online.
  - **The scan rule "admin and editor passwords must count 0" will keep failing** on any transcript that
    prints `.env.example`, until the user changes `.env`. Report the hits with masked context and ask; do not
    edit transcripts on your own.
- **How the screenshots were made** (to redo one):
  1. `sqlite3 <main>/cms.db ".backup '<scratch>/cms.db'"` and `cp -R <main>/media <scratch>/media`. The backup
     only reads the original.
  2. In the copy only: set new argon2 hashes for both users with `argon2.PasswordHasher`, and
     `DELETE FROM sessions`. Never read the original's hashes or `.env`.
  3. `CMS_DATABASE=<scratch>/cms.db CMS_MEDIA=<scratch>/media CMS_SECRET_KEY=<random> .venv/bin/python -m
     uvicorn app.main:app --host 127.0.0.1 --port 8765`. The app does not load `.env` itself.
  4. `/browse`: `viewport 1280x900` / `390x844`, sign in through the form, `screenshot docs/screenshots/<screen>-<w>.png`
     (full page), then check `document.documentElement.scrollWidth`.
  - Screens: content-list is `/admin/guides`. The editor screen is `/admin/guides/4/edit`, the 马克药水流（6.7）
    Guide (it owns the only uploaded image). For editor-denied, the Editor opens `/admin/users` (403, 没有权限).
  - On `users-390.png` the table scrolls inside its box, as #25 designed. That is not a bug.
- **zsh quirk:** a word starting with `=` (like `echo ======`) fails with "not found". Use `-----` as a
  separator.

## Working conventions

Everything in the "Working conventions" sections of handoffs 01 to 07 (`docs/handoff/0{1..7}_*.md`) still
holds: credential scan before each records commit (procedure in handoffs 06–07), the PR flow (handoff 05:
`gh pr create --base main --head Avulpix0412/IPHS400-Mini-Project-2`, check
`rtk proxy gh pr view N --json mergeable,mergeStateStatus`, `gh pr merge N --merge`, never `--delete-branch`),
and `rtk proxy` for `gh` commands whose output goes missing.

Records commits use a plain message (`Add transcript NN, …, and update usage ledger`), no ticket prefix.
Ask the user which prefix, if any, the report and README commits should carry.

No `Backend:` trailer this session: no non-Anthropic base URL was set.

## Suggested skills

- `mattpocock-skills:research`: gather the report's evidence (grill decisions, drift caught, ledger numbers,
  quotable prompts) from the transcripts, issues and ledger into notes the user writes from.
- `mattpocock-skills:writing-for-agents` is **not** the right skill for the report; it is for agent docs.
  No skill drafts the report. The user writes it.
- `mattpocock-skills:grilling`: if the user wants their report answers pressure-tested before writing.
- `superpowers:verification-before-completion`: before saying the checker passes, or that the *Run locally*
  steps work on a clean clone.
- `mattpocock-skills:pr`: the PR body template used for #22 to #30.
- `browse`: check the live Pages URL before putting it in the README. Never use the `mcp__claude-in-chrome__*`
  tools (the user's global `CLAUDE.md`).
- If #12 is taken instead: see handoff 07's suggested skills.
