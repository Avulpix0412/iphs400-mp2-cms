# IPHS 400 MP2plus Report: Guide website for the Bazaar
Nick Chen · 2026-10-20
Repo: https://github.com/Avulpix0412/iphs400-mp2-cms
Live site: https://avulpix0412.github.io/iphs400-mp2-cms/

| Id | Evidence |
|----|----------|
| F6 | issue #37; tests/test_comments.py; mp2plus-comments-1280.png, mp2plus-comments-390.png |
| F9 | issue #42; tests/test_production.py; mp2plus-production-1280.png, mp2plus-production-390.png |
| P1 | PR #38 closing issue #37; carries F6 |
| P2 | docs/handoff/11_prototype-comment-language_20261019.md; branch prototype-comment-language; decision in app/comments.py |
| P3 | CONTEXT.md Decisions table; docs/adr/ADR-003-hero-slug-is-fixed.md |
| S2 | tests/test_login_hardening.py; fixture login_clock in tests/conftest.py |
| P4 | before: commit 19a2b59; after: commit TBD; see the P4 section |

F6: left broken: Comments have to be entered by an Admin and then approved by an Admin, which is an extra step when there is only one Admin; real reader comments need the console to be online.

F9: left broken: If CMS_ENV=production is exported in the shell with unsafe values, even importing the app fails, because create_app() runs the check at import time.

P1: left broken: Nothing left broken; the review findings belong to F6.

P2: left broken: Comments like "GG" or emoji only don't really belong to either language, so the Admin still has to guess.

P3: left broken: An old misspelled Slug can block a later real Hero that would get the same Slug; fixing this was deferred from #15.

S2: left broken: An Admin resetting a password does not lift that email's lockout, so the user still waits up to 15 minutes.

P4: left broken: The prediction and the actual costs are on different scales, because the prediction came from tickets done on the Pro plan and the MP2plus exercises ran on 5× Max, so the prediction can't really judge MP2plus costs.

## P4

### After

Command: `uv run python scripts/usage_report.py --remaining 0` (no exercises left, so the script prints no Forecast line).

Tickets done: 11 · average weekly cost per ticket: 1.4%

### Cost table (MP2plus phases only)

| Phase | Turns | 5h spent | Weekly |
|---|---|---|---|
| P0 | 1 | 0.0% | 0.0% |
| P2 | 4 | 6.0% | 1.0% |
| T37 (F6) | 4 | 2.0% | 1.0% |
| P1 | 3 | 0.0% | 0.0% |
| P3 | 2 | 0.0% | 0.0% |
| S2 | 5 | 2.0% | 0.0% |
| T42 (F9) | 4 | 1.0% | 0.0% |
| P4 | 2 | 0.0% | 0.0% |

The S1 row in the phase table is MP2's image-upload ticket, from before mp2plus-base.

### Explanation

Before the run, the prediction is 1.6% of the weekly cap for each ticket, so about 8% for 5 tickets, but F9 (T42) actually cost 0.0%, and all MP2plus phases together cost about 2%. This is because the prediction's average came from T01–T09, which I did on the Pro plan, while every MP2plus exercise ran after I upgraded my plan to  5× Max, which has larger weekly cap, so the same amount of work shows much smaller usage. The meter also only counts the whole percents, so small exercises like F9 round down to 0%.

