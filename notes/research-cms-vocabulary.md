# Research: how CMSs model content, roles, and publishing

Date: 2026-10-16

Scope: WordPress, Drupal, and two static site generators (Hugo and Jekyll). I picked Hugo and Jekyll because their docs cover most of our terms. Eleventy gets one short note.

Method: official docs only. Every claim has its URL. Where the docs did not say something, I say so. "Not found" means I did not find it on the pages I read. It does not prove the docs never say it.

## 1. The big picture

- **WordPress** keeps everything in one table, `wp_posts`. A column called `post_type` says what kind of item it is. A column called `post_status` says where it is in the workflow. Source: https://wordpress.org/documentation/article/post-status/ and https://developer.wordpress.org/plugins/post-types/
- **Drupal** splits content into "content entity types" (such as Content item, which is also called a node). Each type has "bundles" called content types. Each content type has its own fields. Source: https://www.drupal.org/docs/user_guide/en/planning-data-types.html
- **Hugo and Jekyll** have no database. Content is Markdown files with front matter at the top. A build step turns the files into HTML. Source: https://gohugo.io/getting-started/glossary/ (front matter entry) and https://jekyllrb.com/docs/front-matter/

Our project sits in between. It has a database (like WordPress and Drupal) and a static export (like Hugo and Jekyll).

## 2. Term-by-term comparison

| Term | WordPress | Drupal | Hugo | Jekyll |
|---|---|---|---|---|
| Content type | `post_type`: post, page, attachment, revision, menu item, plus custom post types | Content type = a bundle of a content entity type, with its own fields | Inferred from the top-level directory, or `type` in front matter | Posts, pages, and collections (no separate "content type" term found) |
| Slug | `post_name`, from the title | Not found as a term. Uses "URL alias" | `slug` front matter | `slug` front matter, `:slug` placeholder |
| Draft / published | `post_status` | Published / Unpublished flag | `draft: true` | `_drafts/` folder or `published: false` |
| Role | Administrator, Editor, Author, Contributor, Subscriber | User-defined roles. Standard: anonymous, authenticated, administrator | Not found (no users) | Not found (no users) |
| Capability / permission | "Capability", e.g. `publish_posts` | "Permission", granted to roles | Not found | Not found |
| Permalink | The permanent URL of an item | Not found as a term | Absolute URL including scheme and host | The output path |
| Taxonomy | Categories, tags, custom taxonomies | Vocabularies of terms | Taxonomies of terms (config) | Categories and tags (no custom taxonomies found) |
| Theme | Design of the site | Files for look and feel | Module with layout and behavior | Gem or folder of layouts, includes, assets |
| Headless | Term not found in the pages I read | "Decoupled" / "headless" docs exist but are thin | Different meaning: "headless bundle" | Not found |

## 3. WordPress

**Content type.** WordPress calls this a "post type". The built-in ones are `post`, `page`, `attachment`, `revision` and nav menu items. Developers can register custom post types. They are stored in the same `posts` table. Sources: https://developer.wordpress.org/plugins/post-types/registering-custom-post-types/ and https://developer.wordpress.org/plugins/post-types/

**Slug.** The REST API describes it as "An alphanumeric identifier for the post unique to its type." Source: https://developer.wordpress.org/rest-api/reference/posts/. The `%postname%` tag turns "This Is A Great Post!" into `this-is-a-great-post`. Source: https://wordpress.org/documentation/article/customize-permalinks/. The slug function limits output to letters, digits, underscore and dash. Source: https://developer.wordpress.org/reference/functions/sanitize_title/. I did not verify how it treats Chinese characters.

**Post status.** There are 8 built-in statuses: publish, future, draft, pending, private, trash, auto-draft, inherit. Source: https://wordpress.org/documentation/article/post-status/. Key facts:
- `publish`: "Viewable by everyone."
- `draft`: incomplete post.
- `pending`: "Awaiting a user with the `publish_posts` capability (typically a user assigned the Editor role) to publish."
- A user with `edit_posts` but not `publish_posts` sees a "Submit for Review" button instead of "Publish". The post gets the `pending` status.

**Role.** "A Role defines a set of tasks a user assigned the role is allowed to perform." The docs add: "One particular role should not be considered to be senior to another role." Source: https://wordpress.org/documentation/article/roles-and-capabilities/. Default roles from the same page:
- Administrator: access to all admin features on one site.
- Editor: "can publish and manage posts including the posts of other users."
- Author: "can publish and manage their own posts."
- Contributor: "can write and manage their own posts but cannot publish them."
- Subscriber: "can only manage their profile."

**Capability.** A role is a set of capabilities, such as `publish_posts`. Capabilities can be added or removed with `add_cap()` and `remove_cap()`. Source: same roles page. Its capability table shows:
- Contributor has `edit_posts` and `delete_posts`. It does not have `publish_posts`.
- Author has `publish_posts` and `upload_files`.
- Editor also has `edit_others_posts`, `edit_pages` and `publish_pages`.

**Permalink.** "Permalinks are the permanent URLs of your posts, pages, categories, and other archive pages." The default "Plain" form is `?p=N`. "Pretty" forms use the post name. Source: https://wordpress.org/documentation/article/customize-permalinks/

**Taxonomy.** Source: https://developer.wordpress.org/plugins/taxonomies/ and https://developer.wordpress.org/plugins/taxonomies/working-with-custom-taxonomies/
- A taxonomy is a way to group things. It can be hierarchical or flat.
- Built-in: Categories (hierarchical) and Tags (flat).
- Custom taxonomies are registered with `register_taxonomy`.
- Category and tag archive URLs use a "base" prefix (`/category/name`, `/tag/name`). The default bases are `category` and `tag`. Source: https://wordpress.org/documentation/article/customize-permalinks/

**Theme.** "A WordPress theme represents the design of your website." Block themes and classic (PHP) themes exist. Source: https://developer.wordpress.org/themes/getting-started/what-is-a-theme/

**Headless.** The REST API lets you "bring your WordPress content into completely separate applications." Source: https://developer.wordpress.org/rest-api/. The word "headless" did not appear in that page. I found no official definition.

## 4. Drupal

**Content type.** A content entity is "An item of content data..." A content entity type groups entities with different purposes. A bundle (content type) is a subtype with smaller variations. A field is a "storage unit" holding one kind of data. Source: https://www.drupal.org/docs/user_guide/en/planning-data-types.html. The User Guide builds example types called Vendor and Recipe. Source: https://www.drupal.org/docs/user_guide/en/structure-content-type.html

**Slug and permalink.** Neither word is used. Drupal has a "path" (the last part of a URL, like `node/7`) and a "URL alias" that gives it a friendlier name. Source: https://www.drupal.org/docs/user_guide/en/content-paths.html

**Published / unpublished.** "The Content item entity type supports marking each content item as either Published or Unpublished." Permissions differ by state. The core Workflows module adds more states. Content Moderation lets you give roles permission to specific transitions. Source: https://www.drupal.org/docs/user_guide/en/planning-workflow.html

**Role and permission.** A permission is the ability to do one action. Permissions are grouped into roles. Users can have several roles. Standard roles: Anonymous, Authenticated, and Administrator (created at install, gets all permissions). Source: https://www.drupal.org/docs/user_guide/en/user-concept.html. Drupal says "permission" where WordPress says "capability".

**Taxonomy.** A vocabulary is a set of terms, such as "the set of all blog post tags." Terms attach to content through reference fields. Authors can either create terms freely or pick from a fixed list. Source: https://www.drupal.org/docs/user_guide/en/structure-taxonomy.html

**Theme.** "A theme is a set of files that define the visual look and feel of your site." Source: https://www.drupal.org/docs/user_guide/en/understanding-themes.html

**Headless.** Drupal has a "Decoupled Drupal" doc section. The "What is decoupled" page is marked "needs work" and gives no clear definition. Its outline says the backend "only exposes content via an API". Source: https://www.drupal.org/docs/develop/decoupled-drupal/what-is-decoupled. The core JSON:API module gives "RESTful CRUD for a Drupal site's content." Source: https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module

## 5. Hugo

**Content type.** "A classification of content inferred from the top-level directory name or the `type` set in front matter." Source: https://gohugo.io/getting-started/glossary/. A page in `content/posts/` is in the `posts` section. Source: https://gohugo.io/content-management/organization/

**Slug and URL.** By default the URL matches the file path. The `slug` field changes the last segment. The `url` field replaces the whole path. The `permalinks` setting can build URLs from tokens like `:section` and `:slug`. Source: https://gohugo.io/content-management/urls/ and https://gohugo.io/content-management/front-matter/

**Draft / published.** `draft` stops rendering unless you pass `--buildDrafts`. `publishDate` in the future also stops rendering. `expiryDate` stops it after a date. Source: https://gohugo.io/content-management/front-matter/. The glossary has no entry for "draft".

**Permalink.** The glossary calls it "The absolute URL of a published resource or a rendered page, including scheme and host." Source: https://gohugo.io/getting-started/glossary/. Note: this differs from WordPress, where a permalink is a stable URL. It also differs from our relative-path rule. Hugo has a `relativeURLs` setting, but the docs describe it as useful only for serverless sites. Source: https://gohugo.io/content-management/urls/

**Taxonomy.** "Taxonomies are classifications of logical relationships between content." Parts: taxonomy, term, value. Source: https://gohugo.io/content-management/taxonomies/
- Defaults are `tags` and `categories`. Config maps singular to plural, such as `category: categories`. Source: https://gohugo.io/configuration/taxonomies/
- You add terms in front matter, using the plural name.
- Hugo builds a list page of all terms and one page per term. Templates are `taxonomy.html` and `term.html`. Source: https://gohugo.io/templates/taxonomy/
- The docs I read show `author: author` as a custom example. Source: https://gohugo.io/configuration/taxonomies/

**Menus.** A page joins a menu with `menus: main` in front matter. Source: https://gohugo.io/content-management/menus/

**Theme.** "A module that delivers a complete set of components defining a site's layout, presentation, and behavior." Source: https://gohugo.io/getting-started/glossary/

**Roles.** Not found. Hugo has no users. Who can publish is decided by who can commit to the repo. That last part is my inference, not a quote.

**Headless.** In Hugo, "headless" means "headless bundles": unpublished pages whose content is reused in other pages. This is not a headless CMS. Source: https://gohugo.io/content-management/build-options/. The glossary has no "headless CMS" entry.

## 6. Jekyll

**Content type.** Posts live in `_posts` and are named `YEAR-MONTH-DAY-title.MARKUP`. Source: https://jekyllrb.com/docs/posts/. Pages are for "standalone content (content which is not date based...)". Source: https://jekyllrb.com/docs/pages/. Collections group other content. Posts are a built-in collection. Source: https://jekyllrb.com/docs/collections/

**Slug and permalink.** "Permalinks are the output path for your pages, posts, or collections." `:title` comes from the filename. `:slug` replaces non-alphanumerics with hyphens and lowercases. The `slug` front matter field overrides `:title`. Source: https://jekyllrb.com/docs/permalinks/

**Draft / published.** Drafts are "unpublished posts" kept in `_drafts/`. Source: https://jekyllrb.com/docs/structure/. `published: false` hides a post. Preview it with `--unpublished`. Source: https://jekyllrb.com/docs/front-matter/

**Taxonomy.** Posts have `categories` and `tags`. Categories can also come from the folder path above `_posts`. Categories can appear in the URL. Tags cannot. Source: https://jekyllrb.com/docs/posts/. `site.tags.TAG` lists the posts with a tag. Source: https://jekyllrb.com/docs/variables/. I found no built-in per-tag or per-category pages. You write them by hand or with a plugin (not verified in the docs).

**Theme.** Jekyll themes "package up assets, layouts, includes, and stylesheets in a way that can be overridden by your site's content." Source: https://jekyllrb.com/docs/themes/

**Roles and headless.** Not found.

**Eleventy note.** Tags in front matter create collections. Pagination can make one page per item, for example one per tag, using a `permalink` template. Sources: https://www.11ty.dev/docs/collections/ and https://www.11ty.dev/docs/pagination/

## 7. What this means for our project

These are suggestions, not decisions.

- **Borrow WordPress's status split.** Use `draft`, `pending`, `published`. WordPress's `pending` means "awaiting a user with the `publish_posts` capability". That matches the client's "admin reviews editor guides" flow.
- **Use two or three capabilities, not role checks everywhere.** For example `edit_own`, `edit_any`, `publish`. Roles are bundles of these. WordPress does it this way, and Drupal does it the same way with "permissions". Editor gets the first, admin gets all three. Route code checks the capability. Then the rule can change without touching routes.
- **Treat our "editor" like WordPress's Contributor, not WordPress's Editor.** In WordPress, Contributor can write but "cannot publish" their posts, and WordPress Editor can publish others' posts. Our editor is closer to a Contributor.
- **Hero and author as taxonomies.** Hugo's model fits: a taxonomy (`hero`, `author`) has terms, and content is assigned to terms. Hugo builds one list page per term and a terms index. Our `cms publish` could do the same with Jinja: loop over each hero and write `heroes/<slug>/index.html` with its published guides. Hugo's templates are `taxonomy.html` and `term.html`. WordPress and Drupal have the same idea (terms, vocabularies).
- **Author may not need to be a taxonomy table.** It is already a user relation. A per-author list page can come from the `author` column. Hero can be a small table with a slug and a Chinese display name. Both give the same output page shape.
- **Slugs must be decided early.** All four systems derive a slug from a title and use it in the URL. The WordPress slug function keeps only letters, digits, underscore and dash. I did not verify what happens to Chinese titles. For a Chinese-speaking audience, consider that a slug is typed or edited by the writer, ASCII or pinyin, and unique per type. This is a design risk to test, not a documented answer.
- **Keep paths relative.** Hugo's "permalink" is absolute by definition, and its relative mode is described as niche. Our hard rule (no `href="/..."`) means we compute relative paths ourselves, depending on page depth. Per-term pages like `heroes/<slug>/` are one level deeper than the home page.
- **Patch version field.** None of the systems has a built-in "patch version". It is just a custom field: Drupal fields, WordPress custom fields/post meta, Hugo front matter. A plain `patch_version` column on posts, shown on the page and used to flag stale guides, matches what the others do. Hugo's `expiryDate` is a related idea (stop rendering after a date), but a patch version fits balance patches better. That comparison is my own.
- **Navigation from published pages.** Hugo adds a page to a menu with `menus: main` in front matter. We could use a `show_in_nav` flag on pages, with the public nav built only from published rows.
- **Headless is optional.** A static export is a stronger form of decoupling than a headless API. Our admin is the content backend and the site is a build output. We do not need a public API.

## 8. Gaps

- Drupal: no "slug", "permalink" or "content editor" role definition found. Drupal's theme page on `drupal.org` redirects in some docs paths, so I used the User Guide URL that returned content.
- WordPress: no official definition of "headless" found.
- Hugo and Jekyll: no definition of roles or capabilities found, and none of "headless CMS".
- Jekyll: whether it can build per-term pages without a plugin is not stated on the pages I read.
- Chinese-character slug behavior: not verified for any system.
