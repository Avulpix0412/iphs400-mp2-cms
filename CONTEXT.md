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
that appears in the public navigation once Published, after 攻略 and 锦标赛, in
the order Pages were added. Its address is an Admin-set ASCII Slug. Pages are
never reviewed: a Page is a Draft or Published, and deleting one is for good
(the Trash is for Guides only).
_Avoid_: static page

**Tournament announcement** (锦标赛预告):
An Admin-written notice about an upcoming in-game Tournament.
_Avoid_: event, news, post

**Tournament recap** (锦标赛回顾):
An Admin-written account of a Tournament that has already happened. It is a
separate item from that Tournament's announcement, which it may link to.
_Avoid_: event, report, result

**Tournament item** (锦标赛内容):
A Tournament announcement or a Tournament recap. Each has the Tournament's
date and Patch. Like Pages, they are never reviewed: each is a Draft or
Published, and deleting one is for good. The 锦标赛 section lists them newest
Tournament date first, badged 预告 or 回顾.
_Avoid_: event, post, news

**Chinese text / English text** (中文版 / 英文版):
The two language versions of a Guide (or other content), each with its own
title and body. Chinese is required. English is optional, and content without
it does not appear on the English site.
_Avoid_: translation, localization, body

**Image** (图片):
A screenshot (PNG, JPG, WebP or GIF, at most 5 MB) uploaded into one Guide or
Tournament item. It belongs to that item, can be used in both its Chinese
text and its English text, and is deleted with it. A Revision has its own copy
of its Guide's images.
_Avoid_: attachment, picture, file (in code, the media folder is just where
Images' files are stored)

**Alt text** (图片说明):
An Image's optional short description, one per language, shown in place of
the Image to Readers whose screen reader reads it or whose image fails to
load.
_Avoid_: caption, description, title

**Cover** (封面):
The Image shown with an item in the site's lists. A Guide's is its first Image
unless the writer chooses another; a Tournament item may also have none.
_Avoid_: featured image, banner

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
No two Heroes share an English Official name (ignoring case).
_Avoid_: character, class

**Official name** (官方名称):
The name the game itself uses for a Game Term in a given language. The site
only ever shows Official names.
_Avoid_: nickname (外号), alias, translation

**Nickname** (外号):
A name players use for a Game Term that the game itself doesn't, such as 瓦姐
for 瓦妮莎. Admins record them so the preview can warn a writer who uses one
without a Game Term marker. The site never shows a nickname in place of an
Official name.
_Avoid_: alias, abbreviation, slang

**Game Term marker** (术语标记):
`[[瓦妮莎]]` or `[[Vanessa]]` in a Guide's text: a Game Term named by either
Official name, shown on the site as its Official name in the Reader's
language. A marker that names no Game Term shows its text without the
brackets, and the preview warns about it.
_Avoid_: tag, link, shortcode

**Slug** (网址名):
The short web-address name of a Hero or a Guide. A Hero's is derived from its
English Official name (`Vanessa` → `vanessa`) when the Hero is added, and stays
the same when that name is later corrected. A Guide's is `<hero-slug>-<id>` (`vanessa-12`), given when the Guide
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
An Admin's decision that a Submitted Guide or Revision is not ready. It goes
back to its writer as a Draft, with the Admin's notes. A Returned Revision
leaves the Published Guide as it is.
_Avoid_: reject (that is for Comments), decline

**Review note** (审核意见):
Part of a Return: a passage quoted from the Guide together with the Admin's
advice on how to fix it.
_Avoid_: comment (a Comment is a Reader's, shown under a Guide), feedback

**Publish** (发布):
An Admin's decision that a Submitted Guide is ready, which makes it Published.
Publishing does not by itself change the public site.
_Avoid_: approve (that is for Comments), go live

**Unpublish** (撤下):
An Admin taking a Published Guide off the site without deleting it. The Guide
goes back to its Author as a Draft, optionally with Review notes. An
Unpublished Page or Tournament item simply becomes a Draft again.
_Avoid_: hide, archive, take offline

**Published** (已发布):
A Guide an Admin has Published. It will appear on the public site after the
next Site build.
_Avoid_: live, approved (that is a Comment's status)

**Trash** (回收站):
Where deleted Guides go. Only Admins can see it, and they can restore a Guide
from it or delete it for good. A Guide in the Trash is never on the site.
_Avoid_: archive, recycle bin, deleted

**Revision** (修订):
A proposed change to a Published Guide. While it waits for review the
Published Guide stays on the site unchanged. Once published, it replaces the
old content and the old content is not shown.
_Avoid_: version, new version, edit

**Comment** (评论):
Something a Reader said about a Published Guide, with the Reader's name as
they gave it. Readers have no way to comment on the site: an Admin adds the
Comment in the Moderation queue, where it is Pending (待处理) until Approved
or Rejected. A Comment is never edited. Only Approved Comments appear, under
their Guide's page, after the next Site build; while the Guide is Unpublished
or in the Trash, its Comments are off the site too. Its time is when the
Admin added it. Pages and Tournament items have none.
_Avoid_: reply, review, feedback, message

**Comment language** (评论语言):
Chinese or English, picked by the Admin when adding a Comment (Chinese unless
they choose English). An Approved Comment appears only on its Guide's page in
that language, so an English Comment needs a Guide with English text. It is
never guessed from the text, since Chinese Readers often write with no
Chinese characters (666, yyds); an English Comment that has some only gets a
warning.
_Avoid_: locale, comment translation

**Moderation queue** (评论审核):
The Admin-only console page listing every Pending Comment, where Comments are
added, Approved and Rejected.
_Avoid_: comment inbox, review queue (that is for Submitted Guides)

**Approve** (通过):
An Admin's decision that a Pending Comment may go on the site; the Comment's
status is then approved (已通过). Its opposite is **Reject** (拒绝): the
Comment never reaches the site. Either is final, and either counts as a change
not yet on the site. Approving a Comment is not Publishing: Guides are
Published, Comments are Approved, and neither word is used for the other.
_Avoid_: accept, publish (that is for Guides)

**Site build** (更新网站):
Regenerating the public site from everything that is Published, and putting it
online. This is the only step that changes what Readers see.
_Avoid_: publish, deploy, export

### Time

**Beijing time** (北京时间):
UTC+8, the clock the Admins, Editors and most Readers live by. Every time
the console or the site shows is in Beijing time, to the minute
(`2026-10-17 21:05`), or as a Beijing date on the site. Times are stored in
UTC and compared as stored; only what is shown is converted.
_Avoid_: local time, server time

## Flagged ambiguities

- "Draft" was being used for both an unfinished Guide and a finished one
  awaiting review. Those are now **Draft** and **Submitted**.
- "Version" can mean the game's Patch or an edit to a Guide. Use **Patch** for
  the game and **Revision** for an edit.
- "Publish" meant both an Admin's decision on a Guide and regenerating the
  site. The decision is **Publish**; regenerating is **Site build**. An
  Editor never publishes: their button is Submit (提交审核).
- "Event" is a Game Term kind (事件). Tournament items are announcements and
  recaps, never "events".
- "Card" and "Item" are the same thing. Use **Item**.
- "Approve" could mean Publishing a Guide or letting a Comment onto the site.
  A Guide is **Published**; a Comment is **Approved** (its status is
  `approved`). "Reject" is only for Comments; a Guide that is not ready is
  **Returned**.
- "Pending" is only for a Comment awaiting a decision. A Guide awaiting
  review is **Submitted**.

## Decisions

| Question | Choice | Why |
|---|---|---|
| Does a Hero's slug change when its name is corrected? | No. A slug is fixed once it is created. | Claude asked me this question and suggested that technically the slug could follow the name, but I thought that was not very reasonable, because links might be copied and shared to other places, and if the slug followed the name, the links shared previously would stop working. People who see them later would not be able to find the page, which would be clearly bad experiences for them, so I decided that the slug should not change relatively. |
| How does the language switch work? | It switches the whole site, so a reader stays in one language. | This setting is a more intuitive one. Users definitely don't want their screen filled with content in two languages. This matches the language switch logic of most websites, and I would say it also matches the needs of this web page’s actual audiences. |
| Can an Editor delete their own published Guide? | Yes, at any time and without asking for approval, editors can delete only their own Guides. | At the time Claude suggested that Editors could not delete their own published guides, and I thought this was kind of counterintuitive. I have used forums with a similar mechanism, and as a user the experience was not too good, so I let claude make the editors capable of deleting their own published guides at any time without asking, but they can only delete their own Guides. |
| Does a submission ban hide the editor's published Guides? | No. It only stops new submissions. | At the time claude suggested that after a submission ban, all of the editor's published guides should be hidden, but I decided not to do that and only stop them from new submissions, because there could be multiple reasons for a ban. Even if some of their earlier guides broke the rules, if this editor has posted many articles, it is unlikely that all of them have broken the rules and nobody noticed before, so the admin can handle the problem guide by hand, and others can stay. From the readers' point of view, this is more reasonable and also better for them. |
| How is a Comment's language decided? | The Admin picks it when adding the Comment, Chinese by default. | Initially I decided to detect automatically whether a comment is in Chinese or English, then claude noticed me that some comments mix Chinese and English, and then I thought that mixing the two is a habit only Chinese users have, because English users won't put Chinese in their comments, so the detecting mechanisms can work this way, but claude then pointed out that there might be comments from Chinese users written only in English letters, or only in numbers, so we ran a test and only 9 of 16 passed, and all 7 misses were Chinese-style comments with no Chinese characters, so in the end I changed it to what it is now: the admin picks the language when adding a comment, Chinese by default. |