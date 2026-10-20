# ADR-003: A Hero's Slug is set once and never follows its name

**Status:** accepted
**Date:** 2026-10-17

## Context

Each Hero has a page on the site at its Slug, and every Guide's Slug starts with
its Hero's (`vanessa-12`). Links get copied and shared to other places. If the
Slug followed the name, links shared before a correction would stop working, and
people who saw them later could not find the page. The option rejected:
re-generating the Slug automatically whenever the English Official name is
corrected. Claude first built this in T02, and I reversed it in #15 for the same
reason: it breaks every link shared before the correction.

## Decision

A Hero's Slug is derived once from its English Official name when the Hero is
added (`Vanessa` → `vanessa`). Correcting either Official name later leaves the
Slug unchanged (`Vanesa` → `Vanessa` keeps `vanesa`).

## Consequences

- Hero pages and Guide links never move, so a shared link keeps working.
- A misspelled name lives on in the Slug after the name is fixed. The site only
  shows Official names, so readers see it in the address alone.
- An old misspelled Slug can block a later real Hero whose name gives the same
  Slug. Adding it is refused, naming the Hero that holds the Slug. Fixing this
  (a `-n` suffix, or letting Admins edit a Hero's Slug) is deferred from #15.
