# Handoff: 大巴扎攻略站 CMS, after the .env fix (#31) and before the report

Repo: `/Users/yining/orca/workspaces/iphs400-mp2-cms/IPHS400-Mini-Project-2` (a git worktree on branch
`Avulpix0412/IPHS400-Mini-Project-2`, reused for every session; never delete it or the branch). The main
checkout is `/Users/yining/code/iphs400-mp2-cms` (on `main`), which holds the real local `cms.db`.

## Where things stand

- **#31 is done and merged.** PR #32 (https://github.com/Avulpix0412/iphs400-mp2-cms/pull/32) was merged with
  `--merge` as `c78190c`, and it closed #31. The branch was kept. PR #32 also carried `c13f336`, the README
  rewrite. The `/code-review` findings and their resolutions are on #31.
- **Records commit `f07aa39`** (transcripts 21–22, handoffs 08–09, ledger rows) is pushed to the branch but
  **not on `main` yet**. It reaches `main` with the next PR.
- **Checker:** `uv run python scripts/check_submission.py --stage 2` passes 20/22 (489 tests). Still failing:
  - *report named correctly*: the user is writing it;
  - *tag mp2-final exists*: last; ask before tagging or pushing tags.
- **Not committed yet:** this handoff, this session's transcript (23, written by the SessionEnd hook) and this
  session's ledger rows. They go into the next "Add transcripts NN–NN, …, and update usage ledger" commit,
  after the credential scan.
- **Phase label:** `.claude/state/phase` says `#31`. Change it when the next stage starts (the report commits
  used `docs` before).
- **Main checkout:** still on the pre-#31 `main`. Run `git pull` there before using it, or its commands still
  need `--env-file .env`.
- **#12 (S2, hosted console) will not be done.** The user will comment on the issue themselves. Don't touch it.

## Next session: the report (the user writes it)

Everything in handoff 09's *The report* section still holds: the evidence file at
`~/Documents/iphs400-report-evidence.md` (never commit it), the budget facts the user confirmed, the two ways
to count the budget, the requirements by reference, and the file name pattern. Don't draft the report unless
the user asks. Commit prefix for the report: `docs:`.

New since handoff 09, possibly worth a line in the report:
- **#31 is a rubric-driven fix found by re-running the judge's commands** (rubric §10 T3) on a fresh clone. The
  README had documented `--env-file`, but the judge doesn't pass it. The issue body has the before/after;
  the PR #32 body has the evidence.
- **Two mid-session corrections**, both recorded on #31:
  - The review found two tests leaking variables into later tests, because `monkeypatch.delenv(raising=False)`
    records nothing for an unset key.
  - The first fresh-clone re-run hit a 500 from a stale server left over from my earlier run, not from the
    code (see *Working conventions* below).

## What #31 left behind (not obvious from the diff)

- **The `cms` command and the seed script load `.env` from the working folder** (`app/envfile.py`). Shell
  variables win. Importing `app` never loads it.
- `settings.secret_key()`, `site_title()` and `base_path()` are now functions. `base_path()` has no callers;
  removing it was left out of #31's scope.
- **Tests must never read the real `.env`.** `run_seed` in `tests/test_t01_seed.py` runs from an empty temp
  folder. Any new test that loads `.env` in-process uses `unset()` from `tests/test_31_env_file.py`, so the
  loaded keys are removed afterwards.

## Working conventions

Handoffs 01–09 (`docs/handoff/`) still hold. In particular:
- **Credential scan** (handoffs 06–07), with one update:
  - Both `.env` files now hold the public `.env.example` placeholders for `CMS_ADMIN_PASSWORD` and
    `CMS_EDITOR_PASSWORD`. Hits for those two are therefore expected.
  - The real `CMS_SECRET_KEY` must still count 0. Check first that the passwords still equal the placeholders;
    compare names and verdicts only, never print values.
  - In transcript 22, three argon2 "hits" are only the prose `` `$argon2id$` ``, with no hash after it.
- **The PR flow** (handoff 05), never with `--delete-branch`. Check each test claimed in a PR body against the
  test file.
- **Stopping `cms serve`:** `pkill -f "cms serve --port N"` leaves uvicorn's reloader running. Kill the
  listener by PID instead: `lsof -tiTCP:N -sTCP:LISTEN`, then `pkill -9 -P <pid>; kill -9 <pid>`. Put `-m 5`
  on curl, so a hung server can't stall the shell.
- Also from earlier handoffs:
  - `rtk proxy` for `gh` output that goes missing;
  - never the `mcp__claude-in-chrome__*` tools (use `/browse`);
  - no `Backend:` trailer (Anthropic only);
  - in zsh, a word starting with `=` fails.
- `/implement` and `/handoff` aren't in the skill list. The handoff skill is at
  `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.3.1/skills/productivity/handoff/SKILL.md`;
  read it by hand. The user wants handoffs saved in `docs/handoff/`, not `$TMPDIR`.

## Suggested skills

- `mattpocock-skills:grilling`: only if the user wants their report answers pressure-tested.
- `superpowers:verification-before-completion`: before claiming the checker passes or the report is complete.
- `mattpocock-skills:pr`: the body for the next PR, which brings `f07aa39` and the report to `main`.
- `code-review`: only if code changes again.
- `/handoff` (read by hand, as above): at the end of the session.
