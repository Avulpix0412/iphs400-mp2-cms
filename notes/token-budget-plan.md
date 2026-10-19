# Token budget plan

(Part 5.4 of the manual. Fill this in before your first /implement.)

**Written late.** This plan was written on 2026-10-17, after T04 closed, not
before the first /implement as the manual asks. The upside is that the numbers
below are measured from `notes/usage-ledger.csv`, not guessed.

## Decision

Keep using **Opus 5.5 at high effort** for every remaining ticket (T05–T09, S1, S2).

- Opus 5.5 has done a noticeably better job than Sonnet on this project, so I
  am not dropping to Sonnet or lowering effort to save budget.
- If I hit the 5-hour limit, I will **upgrade my plan** rather than switch
  models or wait it out. I also use Claude Code for other courses (e.g. my IPHS 484
  project), so the higher plan is worth it beyond this
  project.

## What tickets have cost so far

Per-ticket cost = sum of the row-to-row rises in `weekly_pct` (and
`five_h_pct`) for rows labelled with that ticket. The ledger reports whole
percent, so each figure is ±1.

| Ticket | Weekly % | 5-hour % | Follow-up fix | Weekly % with follow-up |
|--------|---------:|---------:|---------------|------------------------:|
| T01    | 2 | 10 | —         | 2 |
| T02    | 2 | 12 | —         | 2 |
| T03    | 3 | 24 | #15 (+1)  | 4 |
| T04    | 2 | 11 | #18 (+0)  | 2 |
| **Average** | **2.25** | **14.25** | | **2.5** |

Notes:
- The weekly window reset during T03 (2026-10-17, between 13:00 and 17:10 UTC).
  Any usage between the last pre-reset row and the reset is lost, so T03's 3% is
  a lower bound.
- `exB` (2% weekly) is course exercise work, not a ticket, and is left out.
- Pre-ticket stages (research, grill, spec, tickets, plus unlabelled setup) cost
  16% weekly in total; that was the previous week.

## Projection for the remaining tickets

Remaining: T05, T06, T07, T08, T09, S1, S2 = **7 tickets**.

| | Per ticket | × 7 tickets |
|---|---:|---:|
| Base (ticket only) | 2.25% | ≈ 16% |
| With a follow-up fix like #15 / #18 | 2.5% | ≈ 18% |

Weekly usage is at **6%** now (last ledger row, 2026-10-17 19:02 UTC).
**Projected weekly total after all 7 tickets: ≈ 22%** (≈ 24% with follow-ups),
well under the weekly cap even if S1/S2 (stretch tickets, likely bigger) cost
double.

## Where the limit will actually bite

The 5-hour window is tighter than the weekly one. A ticket costs about 14% of a
5-hour window (T03 cost 24%), and the current window was already at 47% after
T04 and #18. Doing more than about three tickets in one sitting could hit the
5-hour limit; per the decision above, that is when I upgrade.

## Checkpoints

- Re-read the ledger after each ticket. If a ticket costs more than 5% weekly,
  update this plan before the next one.
- Keep writing the ticket id into `.claude/state/phase` so the ledger stays
  labelled.

## Correction (2026-10-18)

The 5-hour figures for T01 and T03 in the table above are wrong. Recomputed
from `notes/usage-ledger.csv`, they are **8** (not 10) for T01 and **21** (not
24) for T03. The table is left as originally written; the report uses the
corrected numbers.
