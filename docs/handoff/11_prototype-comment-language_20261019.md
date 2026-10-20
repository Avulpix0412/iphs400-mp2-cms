# Handoff: 大巴扎攻略站 CMS, after the P2 prototype (comment language) and before F6

Repo: `/Users/yining/orca/workspaces/iphs400-mp2-cms/IPHS400-Mini-Project-2` (a git worktree). This session
ran on the throwaway branch `prototype-comment-language`, not on the usual `Avulpix0412/IPHS400-Mini-Project-2`.
Exercise order and points are in `notes/mp2plus-plan.md`: P2 is done; F6 is next.

## The prototype (P2)

- **Question:** Does the rule "a comment containing any Chinese character is Chinese, otherwise English" put
  each comment on the right language page?
- **What was tried:** branch `prototype-comment-language`, commit `c335771`, pushed with `-u`
  (https://github.com/Avulpix0412/iphs400-mp2-cms/tree/prototype-comment-language). One throwaway script,
  `app/prototype_comment_language.py` (run: `python3 app/prototype_comment_language.py`), checks the rule on
  16 sample comments: pure Chinese, Chinese with English game terms, pure English, and Chinese internet-style
  comments with no Chinese characters. The branch is out of `main` and must never be merged.
- **Finding:** 9 of 16 right. All 7 misses were Chinese internet-style comments with no Chinese characters
  (`666`, `yyds`, `GG`, `6.7??`, `xswl`, `😂😂😂`, `👍👍`), which the rule sent to the English page. Every comment
  that did contain a Chinese character really was Chinese (6 of 6), so that half of the rule is always right.
  The other half ("no Chinese characters means English") is not.
- **A wrong turn, corrected by the user:** I first proposed taking the language from the page the comment was
  posted on, then a commenter-chosen language. Both assumed a public comment form. **F6 has no public comment
  form:** an Admin adds comments in the Moderation queue, so there is no page language to start from.

## The decision (the user's)

- The **Admin picks the comment's language** (`zh` or `en`) when adding it. The default is **Chinese**, because
  most readers are Chinese.
- If the Admin picks English but the comment contains a Chinese character, **show a warning and keep the
  Admin's choice**. The detection is only a warning, never an override.
- The **server accepts only `zh` or `en`** and refuses anything else.
- **No editing after approval.** Editing comments is out of F6's scope, so a wrong language cannot be fixed
  after approval.
- **An English comment on a Guide with no English text is refused with a message.**

## What was carried back

The decision landed with F6 (#37, PR #38, merged into `main` as `fda9529`). Path: **`app/comments.py`**.

- `LANGUAGES` (`{"zh": "中文", "en": "英文"}`, the first is the default): the only two Comment languages.
- `add()`: refuses any language but `zh` or `en`, and refuses an English Comment on a Guide with no
  English text, with a message (`guide.has_text_in(lang)`).
- `Comment.language_warning`: the warning when the Admin picked English and the text has a Chinese
  character. It never changes the language. `app/routes/comments.py`'s `add_comment()` flashes it after
  adding, and `templates/admin/comments.html` shows it on the pending Comment.
- `approved()`: Approved Comments grouped by (Guide, Comment language). `render_site()` in
  `app/publish.py` puts only the matching language's Comments on each Guide page.

Nothing from the prototype script is reused except the Chinese-character test (CJK ranges `㐀-䶿`,
`一-鿿`), now `_CHINESE` in `app/comments.py`, and only for the warning. Tests:
`tests/test_comments.py`: `test_step2_the_comment_language_defaults_to_chinese_and_must_be_zh_or_en`,
`test_step2_an_english_comment_on_a_guide_without_english_text_is_refused` and
`test_step2_english_picked_for_text_with_chinese_warns_and_keeps_the_choice`. Glossary: **Comment
language** in `CONTEXT.md`.

## Before F6 starts

- **There is no F6 issue yet.** When it exists, leave a pointer on it to the prototype branch and to this
  handoff (the prototype process requires it), and put the decision above into its acceptance criteria.
- **`CONTEXT.md` conflicts with F6.** Under **Review note** it says "comments stay on Bilibili". Update the
  glossary when F6 is specced: add Comment, Comment language and Moderation queue, and fix that line.
  `CONTEXT.md` avoids "approve" for Guides (it uses Publish); decide whether a comment is "approved" or uses
  another word, and record it, rather than using both.
- **Switch branches first.** This worktree is on `prototype-comment-language`. Go back to the usual branch
  (or the branch P1 calls for) before writing F6 code, so no F6 work lands on the prototype branch.
- **Phase label:** `.claude/state/phase` says `P2`. Change it to `F6` when F6 starts.

## Not committed yet

- This handoff (the user asked to keep it uncommitted for now).
- Transcript 29 (`docs/transcripts/iphs400_mp2-cms_chat-session_29_nick-chen_20261018.md`) and this session's
  rows in `notes/usage-ledger.csv`.

These are uncommitted working-tree changes, so they follow the branch switch. They go into the next
"Add transcripts …, and update usage ledger" commit on the usual branch, after the credential scan.

## Working conventions

Handoffs 01–10 (`docs/handoff/`) still hold: the credential scan, the PR flow (never `--delete-branch`), how
to stop `cms serve`, `rtk proxy` for missing `gh` output, `/browse` instead of the `mcp__claude-in-chrome__*`
tools, and no `Backend:` trailer. `/handoff` is still
not in the skill list; read
`~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.3.1/skills/productivity/handoff/SKILL.md`
by hand and save to `docs/handoff/`.

## Suggested skills

- `mattpocock-skills:domain-modeling`: add the comment terms to `CONTEXT.md` and fix the Bilibili line.
- `mattpocock-skills:tdd`: build F6 test-first, starting with the language rules above.
- `mattpocock-skills:code-review`: before the commit that closes the F6 ticket; post the findings on the issue.
- `mattpocock-skills:pr`: the P1 pull request carrying F6.
- `/handoff` (read by hand, as above): at the end of the session.
