# Handoff: 大巴扎攻略站 CMS, after the README rewrite and before the .env fix

Repo: `/Users/yining/orca/workspaces/iphs400-mp2-cms/IPHS400-Mini-Project-2` (a git worktree on branch
`Avulpix0412/IPHS400-Mini-Project-2`, reused for every session; never delete it or the branch). The main
checkout is `/Users/yining/code/iphs400-mp2-cms` (on `main`), which holds the real local `cms.db`.

## Where things stand

- **The README is rewritten**, as the project's own README: intro, *Live URL*, *Run locally* and the
  *Generative AI Use Statement* heading with the models, skills and *Backends used* table. The user writes the
  statement itself. `.env.example` now has `CMS_SITE_TITLE="大巴扎攻略站"`.
  - Commit `c13f336` ("docs: …") is **local only, not pushed**, and no PR is open. It reaches `main` with the
    next PR.
- **Checker:** `uv run python scripts/check_submission.py --stage 2` passes 20/22. Still failing: *report named
  correctly* (the user is writing it) and *tag mp2-final exists* (last; ask before tagging or pushing tags).
- **Not committed yet:** `notes/usage-ledger.csv` rows, handoff 08, this handoff, and transcripts 21 and 22.
  They go into the next "Add transcripts NN–NN, …, and update usage ledger" commit, after the credential scan.
- **Phase label:** `.claude/state/phase` says `docs`. Set it to `#31` when that work starts.
- **#12 (S2, hosted console) will not be done.** The user will comment on the issue themselves. Don't touch it.

## Next session: #31

https://github.com/Avulpix0412/iphs400-mp2-cms/issues/31 has the problem, the requirements and the acceptance
criteria. Don't restate them. Why it matters: the rubric's judge runs the seed with no `--env-file`, so on a
clean clone it gets no accounts and can't walk through C.

Things the issue doesn't say:
- **`app/settings.py` reads `SECRET_KEY`, `SITE_TITLE` and `BASE_PATH` at import time.** `scripts/seed_demo.py:29`
  and `app/cli.py:11` both import `settings` at the top. So `.env` has to be loaded before those imports run,
  or those three must be read lazily. Loading inside `main()` is too late for them.
- **Load only in the entry points** (the `cms` command and the seed script), not when `app` is imported. The
  worktree has a real `.env`. If importing `app` loaded it, the tests would pick up its values (secret key,
  title, passwords). `tests/conftest.py:39` sets only `CMS_DATABASE` per test.
- `cms serve` runs uvicorn with a reloader (the serve log shows "Started reloader process"). The child
  process inherits `os.environ`, so loading in the parent is enough.
- Find `.env` relative to the repo root (`settings.ROOT`) or the working directory; pick one and say which in
  the README. The judge runs from the repo root, so both work there.
- How the bug was reproduced (2026-10-18): a fresh `git clone https://github.com/Avulpix0412/iphs400-mp2-cms.git`
  in the scratchpad, then `uv sync`, `cp .env.example .env`, and `uv run python scripts/seed_demo.py` → exit 1.
  Re-run exactly that on a fresh clone of the fix branch to prove it, then `uv run cms serve` and fetch `/login`.
  - A clone of GitHub only has what is pushed. Either push the branch first, or clone the local worktree
    path instead.
- An unquoted value with spaces makes uv's `--env-file` reject the whole file. Decide what the new loader
  does with one (the README currently tells people to quote such values).
- After the fix, update the README's *Run locally* section (drop `--env-file .env`, or say it's optional),
  and test the steps again on a fresh clone.
- Workflow from `CLAUDE.md`: post the `/code-review` findings and their resolutions on #31 before closing it.
  Earlier non-ticket issues used the commit prefix `#15:` / `#18:` / `#25:` and `Closes #N`. Confirm the
  prefix with the user. PR flow as in handoff 05.

## The report (the user writes it)

- **Evidence file:** `~/Documents/iphs400-report-evidence.md` (outside the repo; never commit it). It holds:
  - (a) grill overrides and client facts, with transcript line references;
  - (b) 11 drift cases, ranked for rubric G1(b), including #18, PR #29, and the plan's two 5-hour figures;
  - (c) the plan against the ledger;
  - (d) six exact prompts.
  A script checked every quote against the transcripts and issue comments.
- **Budget facts confirmed by the user:** the drop of the weekly and 5-hour meters on 2026-10-18, between
  04:10 and 04:49 UTC, was the user's **upgrade to Max**. The committed `notes/token-budget-plan.md` stays
  unchanged, even though its T01/T03 5-hour figures don't reproduce from the ledger (drift item (b)11).
- **Two ways to count the budget:** `scripts/usage_report.py` counts only rises between rows that share a phase.
  The plan credited each rise to the later row's phase. The two give different per-ticket numbers. The
  evidence file explains this, and the report should name its method.
- Requirements, by reference: manual §8.2, rubric A3, A4, B7(c), G1 and G2. File name
  `docs/iphs400_mp2-web-cms_report_nick-chen_YYYYMMDD.md`. Don't draft it unless the user asks.
- **Commit prefix** for the report and README commits: `docs:` (the user's choice).

## Working conventions

Handoffs 01–08 (`docs/handoff/`) still hold. In particular:
- the credential scan before a records commit (handoffs 06–07);
- the PR flow (handoff 05), never with `--delete-branch`;
- `rtk proxy` for `gh` output that goes missing;
- never the `mcp__claude-in-chrome__*` tools (use `/browse`);
- no `Backend:` trailer (Anthropic only);
- in zsh, a word starting with `=` fails, so use `-----` as a separator.

## Suggested skills

- `mattpocock-skills:tdd`: #31 test-first (environment wins over `.env`, a missing `.env`, quoted values).
- `code-review`: before closing #31; post the findings on the issue.
- `superpowers:verification-before-completion`: before saying a fresh clone works without `--env-file`.
- `mattpocock-skills:pr`: the PR body for #31.
- `mattpocock-skills:grilling`: only if the user wants their report answers pressure-tested.
- `mattpocock-skills:handoff`: at the end of the session.
