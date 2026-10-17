# The Bazaar Guide Site (大巴扎攻略站)

A small CMS where streamers (up主) and invited writers in the Chinese-speaking
community of the card game The Bazaar publish written guides, so players can
find a build for a given hero and patch without scrubbing through videos.

## Language

### People

**Admin** (管理员):
One of the few top streamers who run the site. Reviews and publishes other
people's Guides and manages users.
_Avoid_: owner, superuser

**Editor** (编辑):
An invited guide writer (another up主 or an experienced player). Writes
Guides but cannot publish them or manage users.
_Avoid_: author (as a role name), contributor, writer

**Reader** (读者):
Anyone who plays the game and reads the public site. Has no account.
_Avoid_: user, visitor, member

**Author** (作者):
The Admin or Editor who wrote a Guide. Readers can browse all of an Author's
Published Guides on that Author's page.
_Avoid_: owner, creator, up主 (not every Author is a streamer)

**Submission ban** (禁止投稿):
An account state in which an Editor can still log in and work on Drafts but
cannot Submit Guides or Revisions. Their Published Guides stay on the site.
_Avoid_: suspension, block, mute

**Deactivated** (已停用):
An account state in which the person cannot log in at all. Their Published
Guides stay on the site.
_Avoid_: deleted, disabled, banned

**First-login setup** (首次登录设置):
The step a person with a temporary password must finish before using the
console: they choose their own password and their Display name.
_Avoid_: onboarding, activation, registration

**Display name** (昵称):
The name an Author chooses to be shown under publicly. It is never their
login username.
_Avoid_: username, handle

### Content

**Guide** (攻略):
A written strategy piece about one Hero on one Patch, typically built around
screenshots of a lineup or deck with an explanation of how it plays. Guides
for tournament mode are still Guides.
_Avoid_: article, tutorial, post

**Page** (页面):
A standalone piece of site content written by an Admin, such as About (关于),
that appears in the public navigation.
_Avoid_: static page

**Tournament announcement** (锦标赛预告):
An Admin-written notice about an upcoming in-game Tournament.
_Avoid_: event, news, post

**Tournament recap** (锦标赛回顾):
An Admin-written account of a Tournament that has already happened. It is a
separate item from that Tournament's announcement.
_Avoid_: event, report, result

**Chinese text / English text** (中文版 / 英文版):
The two language versions of a Guide (or other content), each with its own
title and body. Chinese is required. English is optional, and content without
it does not appear on the English site.
_Avoid_: translation, localization, body

### The game

**Game Term** (游戏术语):
A named thing in The Bazaar that has an official Chinese name and an official
English name, stored as a pair. It is one of seven kinds: Hero, Item, Skill,
Enchantment, Monster, Merchant, or Event.
_Avoid_: keyword, tag, entity

**Item** (物品):
The Game Term kind for the cards a player builds with.
_Avoid_: card

**Event** (事件):
The Game Term kind for an in-game event a player encounters during a run. The
word means only this; it is never used for a Tournament.
_Avoid_: using "event" for Tournaments or site activity

**Hero** (英雄):
The Game Term for a playable character. Every Guide is about exactly one Hero.
_Avoid_: character, class

**Official name** (官方名称):
The name the game itself uses for a Game Term in a given language. The site
only ever shows Official names.
_Avoid_: nickname (外号), alias, translation

**Slug** (网址名):
The short web-address name of a Hero or a Guide. A Hero's is derived from its
English Official name (`Vanessa` → `vanessa`) and follows that name when it is
corrected. A Guide's is `<hero-slug>-<id>` (`vanessa-12`), given when the Guide
is created; it never changes on its own (not with the title, the Hero or a
Revision), only when an Admin edits it, so shared links keep working. No two
Heroes, and no two Guides, share one.
_Avoid_: URL name, permalink, handle

**Patch** (版本):
The game version a Guide was written for, such as `6.7`. Picked by the
writer. It describes when the Guide was written and is not a verdict on
whether the Guide is out of date.
_Avoid_: version (also used for edits to a Guide), season

**Current Patch** (当前版本):
The Patch an Admin added most recently. Adding a Patch always makes it the
Current Patch, even if its number is lower than an earlier one's.
_Avoid_: latest version, live patch

**Tournament** (锦标赛):
An experimental in-game mode in which many players (up to about 100) play one
game together until there is one champion. It is run by the game, not
organized by players. It has its own section on the site.
_Avoid_: event, competition, league, match

### Workflow

**Draft** (草稿):
A Guide its writer has not finished yet. Only its writer and Admins can see it.
_Avoid_: unpublished

**Submitted** (待审核):
A Guide its writer has marked finished, waiting for an Admin to review it.
_Avoid_: pending, draft, ready

**Return** (退回):
An Admin's decision that a Submitted Guide is not ready. It goes back to its
writer as a Draft, with the Admin's notes.
_Avoid_: reject, decline

**Review note** (审核意见):
Part of a Return: a passage quoted from the Guide together with the Admin's
advice on how to fix it.
_Avoid_: comment (comments stay on Bilibili), feedback

**Publish** (发布):
An Admin's approval of a Submitted Guide, which makes it Published. Publishing
does not by itself change the public site.
_Avoid_: approve, go live

**Unpublish** (撤下):
An Admin taking a Published Guide off the site without deleting it. The Guide
goes back to its Author as a Draft, optionally with Review notes.
_Avoid_: hide, archive, take offline

**Published** (已发布):
A Guide an Admin has approved. It will appear on the public site after the
next Site build.
_Avoid_: live, approved

**Trash** (回收站):
Where deleted Guides go. Only Admins can see it, and they can restore a Guide
from it or delete it for good. A Guide in the Trash is never on the site.
_Avoid_: archive, recycle bin, deleted

**Revision** (修订):
A proposed change to a Published Guide. While it waits for review the
Published Guide stays on the site unchanged. Once published, it replaces the
old content and the old content is not shown.
_Avoid_: version, new version, edit

**Site build** (更新网站):
Regenerating the public site from everything that is Published, and putting it
online. This is the only step that changes what Readers see.
_Avoid_: publish, deploy, export

## Flagged ambiguities

- "Draft" was being used for both an unfinished Guide and a finished one
  awaiting review. Those are now **Draft** and **Submitted**.
- "Version" can mean the game's Patch or an edit to a Guide. Use **Patch** for
  the game and **Revision** for an edit.
- "Publish" meant both an Admin's approval and regenerating the site. Approval
  is **Publish**; regenerating is **Site build**. An Editor never publishes:
  their button is Submit (提交审核).
- "Event" is a Game Term kind (事件). Tournament items are announcements and
  recaps, never "events".
- "Card" and "Item" are the same thing. Use **Item**.
