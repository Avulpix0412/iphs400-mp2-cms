"""S1: writers upload images into Guides and Tournament items, with alt text
per language and a cover.

Seam 1 is the console over HTTP and Seam 2 is `render_site`. Seam 3, agreed for
this ticket only, is the media folder on disk: tests list the file names there,
to show that no file lands outside it and that deleted images are gone."""
from __future__ import annotations

import posixpath
import re
import struct
import zlib
from pathlib import Path
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from conftest import csrf_token
from test_t03_guides import (act, admin, editor, form_values, new_guide,  # noqa: F401
                             save, someone_elses_guide)
from test_t04_site_build import page as site_page, site  # noqa: F401
from test_t03_guides import slug_of
from test_t06_revisions_trash import (delete, delete_for_good, open_revision,
                                      published_guide, revision_page)
from test_t02_heroes_patches import submit as fill_in
from test_t08_pages_tournaments import (new_tournament_item, page_act,
                                        published_tournament_item, save_tournament_item,
                                        tournament_form_values)
from test_t04_site_build import pending_changes, press_update_site
from app.publish import render_site


def _png() -> bytes:
    """A real 1x1 PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + chunk(b"IEND", b""))


PNG = _png()
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00\x2f\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07\x00"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

SNIPPET = re.compile(r"<code>!\[\]\(([0-9a-f]{32}\.(?:png|jpg|webp|gif))\)</code>")


def upload(c: TestClient, edit_page: str, data: bytes, name: str = "lineup.png",
           values: dict[str, str] | None = None, **fields):
    """Choose a file in the editor's image section and press 上传. The rest
    of the editor form (`values`, or what the page shows) comes along."""
    page = c.get(edit_page).text
    sent = (form_values(page) if values is None else values) | fields
    return c.post(f"{edit_page.removesuffix('/edit')}/images",
                  data={"csrf_token": csrf_token(page), **sent},
                  files={"image": (name, data, "application/octet-stream")},
                  follow_redirects=False)


def images_on(page: str) -> list[str]:
    """The stored file names of the images an editor page lists, in order."""
    return SNIPPET.findall(page)


def uploaded(c: TestClient, edit_page: str, data: bytes = PNG,
             values: dict[str, str] | None = None, **fields) -> str:
    """Upload an image; returns its stored file name."""
    before = images_on(c.get(edit_page).text)
    response = upload(c, edit_page, data, values=values, **fields)
    assert response.status_code == 303, response.text
    [new] = [name for name in images_on(c.get(edit_page).text) if name not in before]
    return new


def image_url(edit_page: str, filename: str) -> str:
    return f"{edit_page.removesuffix('/edit')}/images/{filename}"


def test_an_editor_uploads_a_screenshot_to_their_own_draft(editor):
    edit_page = new_guide(editor)
    response = upload(editor, edit_page, PNG)
    assert response.status_code == 303
    page = editor.get(edit_page).text
    assert "图片已上传" in page
    [filename] = images_on(page)

    image = editor.get(image_url(edit_page, filename))
    assert image.status_code == 200
    assert image.content == PNG
    assert image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name, data, content_type", [
    ("deck.jpg", JPG, "image/jpeg"), ("deck.JPEG", JPG, "image/jpeg"),
    ("deck.webp", WEBP, "image/webp"), ("deck.gif", GIF, "image/gif"),
])
def test_jpg_webp_and_gif_screenshots_are_accepted_too(editor, name, data, content_type):
    edit_page = new_guide(editor)
    assert upload(editor, edit_page, data, name=name).status_code == 303
    [filename] = images_on(editor.get(edit_page).text)
    image = editor.get(image_url(edit_page, filename))
    assert image.content == data
    assert image.headers["content-type"] == content_type


@pytest.mark.parametrize("name, data, message", [
    ("deck.svg", SVG, "不支持 SVG"),
    ("deck.png", SVG, "内容不是 PNG、JPG、WebP 或 GIF 图片"),
    ("notes.png", b"%PDF-1.7 not an image", "内容不是 PNG、JPG、WebP 或 GIF 图片"),
    ("notes.txt", PNG, "只能上传 PNG、JPG、WebP 或 GIF 图片"),
    ("huge.png", PNG + b"\0" * (5 * 1024 * 1024), "图片不能超过 5 MB"),
    ("", b"", "请先选择要上传的图片"),
])
def test_anything_but_a_png_jpg_webp_or_gif_of_at_most_5_mb_is_refused_with_a_message(
        editor, name, data, message):
    edit_page = new_guide(editor)
    response = upload(editor, edit_page, data, name=name)
    assert response.status_code == 400
    assert message in response.text
    assert images_on(editor.get(edit_page).text) == []


def test_an_image_of_exactly_5_mb_is_accepted(editor):
    edit_page = new_guide(editor)
    data = PNG + b"\0" * (5 * 1024 * 1024 - len(PNG))
    assert upload(editor, edit_page, data).status_code == 303
    assert len(images_on(editor.get(edit_page).text)) == 1


def files_in(folder: Path) -> set[str]:
    return {path.name for path in folder.iterdir()} if folder.exists() else set()


def test_the_server_names_each_stored_file_so_an_uploaded_name_cannot_escape(
        editor, tmp_path):
    edit_page = new_guide(editor)
    before = files_in(tmp_path)
    for name in ["../../x.png", "..\\..\\x.png", "/tmp/x.png", "lineup.png"]:
        assert upload(editor, edit_page, PNG, name=name).status_code == 303
    stored = images_on(editor.get(edit_page).text)
    assert len(set(stored)) == 4
    assert files_in(tmp_path / "media") == set(stored)
    assert files_in(tmp_path) - before == {"media"}
    assert not (tmp_path.parent / "x.png").exists()


def test_the_editors_typed_text_is_saved_with_the_upload(editor):
    edit_page = new_guide(editor, body_zh="旧的正文。")
    assert upload(editor, edit_page, PNG, body_zh="还没保存的正文。").status_code == 303
    assert "还没保存的正文。" in editor.get(edit_page).text


def test_a_refused_upload_keeps_the_typed_text_on_screen_unsaved(editor):
    edit_page = new_guide(editor, body_zh="旧的正文。")
    response = upload(editor, edit_page, SVG, name="x.svg", body_zh="还没保存的正文。")
    assert response.status_code == 400
    assert "还没保存的正文。" in response.text
    assert "还没保存的正文。" not in editor.get(edit_page).text


def test_an_editor_cannot_upload_to_or_manage_images_on_someone_elses_guide(
        editor, admin, someone_elses_guide):
    filename = uploaded(admin, someone_elses_guide)
    guide = someone_elses_guide.removesuffix("/edit")
    [image_id] = re.findall(r'name="alt_zh_(\d+)"', admin.get(someone_elses_guide).text)
    token = csrf_token(editor.get("/admin/guides").text)

    assert editor.get(image_url(someone_elses_guide, filename)).status_code == 404
    response = editor.post(f"{guide}/images", data={"csrf_token": token},
                           files={"image": ("x.png", PNG, "image/png")})
    assert response.status_code == 404
    for path in [f"{guide}/images/{image_id}/delete", guide]:
        response = editor.post(path, data={"csrf_token": token, "title_zh": "改掉",
                                           f"alt_zh_{image_id}": "改掉"})
        assert response.status_code == 404
    page = admin.get(someone_elses_guide).text
    assert images_on(page) == [filename]
    assert "改掉" not in page


def test_an_editors_published_guide_takes_images_through_a_revision_only(editor, admin):
    edit_page = published_guide(editor, admin)
    assert 'name="image"' not in editor.get(edit_page).text
    response = upload(editor, edit_page, PNG, values={})
    assert response.status_code == 403
    assert "已发布的攻略要通过修订来修改" in response.text


def image_id(page: str, filename: str) -> str:
    """The id an editor page's alt text fields use for the image `filename`."""
    match = re.search(rf"<code>!\[\]\({re.escape(filename)}\)</code>.*?"
                      r'name="alt_zh_(\d+)"', page, re.DOTALL)
    assert match, f"no alt text fields for {filename}"
    return match.group(1)


def describe(c: TestClient, edit_page: str, filename: str, zh: str, en: str, **fields):
    """Fill in an image's alt text in each language and save the editor."""
    number = image_id(c.get(edit_page).text, filename)
    return save(c, edit_page, **{f"alt_zh_{number}": zh, f"alt_en_{number}": en},
                **fields)


def img_tags(html: str) -> list[str]:
    return re.findall(r"<img [^>]*>", html)


ARTICLE = re.compile(r'<article lang="(zh|en)[^"]*">(.*?)</article>', re.DOTALL)


def articles(page: str) -> dict[str, str]:
    """The preview's article in each language."""
    return dict(ARTICLE.findall(page))


def test_one_image_shows_in_both_texts_with_each_languages_alt_text(editor):
    edit_page = new_guide(editor)
    filename = uploaded(editor, edit_page)
    response = describe(editor, edit_page, filename, "终局阵容截图", "End-game lineup",
                        body_zh=f"终局阵容：\n\n![]({filename})",
                        title_en="Pirates", body_en=f"The lineup:\n\n![]({filename})")
    assert response.status_code == 303
    page = editor.get(edit_page).text
    assert 'value="终局阵容截图"' in page and 'value="End-game lineup"' in page

    preview_url = f"{edit_page.removesuffix('/edit')}/preview"
    shown = articles(editor.get(preview_url).text)
    [zh] = img_tags(shown["zh"])
    [en] = img_tags(shown["en"])
    assert 'alt="终局阵容截图"' in zh and 'alt="End-game lineup"' in en
    for tag in (zh, en):
        src = re.search(r'src="([^"]+)"', tag)
        assert src and not src.group(1).startswith("/")
        assert editor.get(urljoin(f"http://testserver{preview_url}", src.group(1))
                          ).content == PNG


def test_without_saved_alt_text_the_alt_written_in_the_markdown_is_used(editor):
    edit_page = new_guide(editor)
    filename = uploaded(editor, edit_page)
    save(editor, edit_page, body_zh=f"![船的位置]({filename})")
    [tag] = img_tags(editor.get(f"{edit_page.removesuffix('/edit')}/preview").text)
    assert 'alt="船的位置"' in tag


def chosen_cover(page: str) -> str | None:
    match = re.search(r'name="cover" value="([^"]*)" checked', page)
    return match.group(1) if match else None


def test_a_guides_cover_is_its_first_image_until_the_writer_chooses_another(editor):
    edit_page = new_guide(editor)
    assert chosen_cover(editor.get(edit_page).text) is None
    first = uploaded(editor, edit_page)
    second = uploaded(editor, edit_page)
    assert chosen_cover(editor.get(edit_page).text) == first

    assert save(editor, edit_page, cover=second).status_code == 303
    page = editor.get(edit_page).text
    assert chosen_cover(page) == second
    assert "不用封面" not in page  # a Guide always has one once it has images

    assert save(editor, edit_page, body_zh="不选封面的保存。").status_code == 303
    assert chosen_cover(editor.get(edit_page).text) == second


def delete_image(c: TestClient, edit_page: str, filename: str, **fields):
    """Press 删除这张图片 under the image `filename`; the editor form comes along."""
    page = c.get(edit_page).text
    return c.post(f"{edit_page.removesuffix('/edit')}/images/{image_id(page, filename)}/delete",
                  data={"csrf_token": csrf_token(page), **(form_values(page) | fields)},
                  follow_redirects=False)


def test_an_image_the_text_still_uses_cannot_be_deleted(editor, tmp_path):
    edit_page = new_guide(editor)
    filename = uploaded(editor, edit_page)
    save(editor, edit_page, title_en="Pirates", body_en=f"![]({filename})")
    response = delete_image(editor, edit_page, filename)
    assert response.status_code == 400
    assert "英文正文还在使用这张图片" in response.text
    assert images_on(editor.get(edit_page).text) == [filename]
    assert files_in(tmp_path / "media") == {filename}


def test_an_unused_image_is_deleted_with_its_file(editor, tmp_path):
    edit_page = new_guide(editor)
    kept = uploaded(editor, edit_page)
    gone = uploaded(editor, edit_page)
    save(editor, edit_page, body_zh=f"![]({gone})", cover=gone)
    # The reference is removed in the same press of the button.
    response = delete_image(editor, edit_page, gone, body_zh="不用图了。")
    assert response.status_code == 303
    page = editor.get(edit_page).text
    assert "图片已删除" in page
    assert images_on(page) == [kept]
    assert chosen_cover(page) == kept
    assert files_in(tmp_path / "media") == {kept}
    assert editor.get(image_url(edit_page, gone)).status_code == 404


def guide_with_images(editor: TestClient, admin: TestClient) -> tuple[str, str, str]:
    """A Published Guide by the Editor using two described images, the second
    as its cover. Returns its edit page and the two file names."""
    edit_page = new_guide(editor)
    first, second = uploaded(editor, edit_page), uploaded(editor, edit_page)
    describe(editor, edit_page, first, "开局", "Opening")
    describe(editor, edit_page, second, "终局阵容", "End-game lineup", cover=second,
             body_zh=f"开局：![]({first})\n\n终局：![]({second})",
             title_en="Pirates", body_en=f"Opening: ![]({first})")
    assert act(editor, edit_page, "submit").status_code == 303
    assert act(admin, edit_page, "publish").status_code == 303
    return edit_page, first, second


def shown_images(site: Path, path: str) -> list[tuple[Path, str]]:
    """Each image on the page at `path`: the file its src leads to, and its alt."""
    found = []
    for tag in img_tags(site_page(site, path)):
        src = re.search(r'src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        assert src and alt, tag
        assert not src.group(1).startswith("/"), tag
        found.append(((site / path / src.group(1)).resolve(), alt.group(1)))
    return found


def test_the_site_build_copies_the_images_and_shows_each_languages_alt_text(
        editor, admin, site):
    edit_page, first, second = guide_with_images(editor, admin)
    slug = slug_of(admin, edit_page)
    render_site(site)
    media = (site / "media").resolve()
    assert (media / first).read_bytes() == PNG and (media / second).read_bytes() == PNG
    assert shown_images(site, f"zh/guides/{slug}/") == [
        (media / first, "开局"), (media / second, "终局阵容")]
    assert shown_images(site, f"en/guides/{slug}/") == [(media / first, "Opening")]


def list_items(site: Path, path: str) -> list[str]:
    """The Guide list items on the page at `path`."""
    lists = re.findall(r'<ul class="guides">(.*?)</ul>', site_page(site, path), re.DOTALL)
    return [item for found in lists for item in re.findall(r"<li>(.*?)</li>", found, re.DOTALL)]


def test_list_items_on_home_hero_and_author_pages_show_the_guides_cover(
        editor, admin, site):
    edit_page, _, cover = guide_with_images(editor, admin)
    act(admin, new_guide(admin, title_zh="没有图片的攻略"), "publish")
    render_site(site)
    author = re.search(r'href="([./]*authors/\d+/)"',
                       site_page(site, f"zh/guides/{slug_of(admin, edit_page)}/"))
    assert author
    author_page = posixpath.normpath(f"zh/guides/x/{author.group(1)}").removeprefix("zh/")
    media = (site / "media").resolve()
    for lang, alt in [("zh", "终局阵容"), ("en", "End-game lineup")]:
        for path in [f"{lang}/", f"{lang}/heroes/vanessa/", f"{lang}/{author_page}/"]:
            items = list_items(site, path)
            [with_cover] = [item for item in items if "<img" in item]
            folder = site / path
            [(src, shown_alt)] = [
                ((folder / src).resolve(), shown_alt) for src, shown_alt in
                re.findall(r'<img src="([^"]+)" alt="([^"]*)"', with_cover)]
            assert (src, shown_alt) == (media / cover, alt), path
            if lang == "zh" and path != f"{lang}/{author_page}/":
                assert any("没有图片的攻略" in item and "<img" not in item
                           for item in items), path


def test_images_of_guides_that_are_not_published_never_reach_the_site(editor, admin, site):
    draft = new_guide(editor)
    submitted = new_guide(editor)
    trashed = published_guide(editor, admin)
    hidden = [uploaded(editor, draft), uploaded(editor, submitted),
              uploaded(admin, trashed)]
    act(editor, submitted, "submit")
    assert delete(admin, trashed).status_code == 303
    _, *shown = guide_with_images(editor, admin)
    render_site(site)
    assert files_in(site / "media") == set(shown)
    assert not any(name in file.read_text() for file in site.rglob("*.html")
                   for name in hidden)


def test_deleting_a_guide_from_the_trash_for_good_deletes_its_images(
        editor, admin, tmp_path):
    edit_page, *_ = guide_with_images(editor, admin)
    other = new_guide(editor)
    kept = uploaded(editor, other)
    assert delete(admin, edit_page).status_code == 303
    assert len(files_in(tmp_path / "media")) == 3  # in the Trash, still there
    assert delete_for_good(admin, edit_page).status_code == 303
    assert files_in(tmp_path / "media") == {kept}


def test_a_revision_changes_the_images_only_once_it_is_published(editor, admin, site):
    edit_page, first, second = guide_with_images(editor, admin)
    slug = slug_of(admin, edit_page)
    assert open_revision(editor, edit_page).status_code == 303
    revision = revision_page(edit_page)
    assert images_on(editor.get(revision).text) == [first, second]

    third = uploaded(editor, revision)
    describe(editor, revision, first, "新的开局", "New opening", cover=third,
             body_zh=f"开局：![]({first})\n\n新终局：![]({third})")
    assert delete_image(editor, revision, second).status_code == 303
    assert images_on(editor.get(revision).text) == [first, third]
    assert act(editor, revision, "submit").status_code == 303

    render_site(site)  # the Published Guide, as it was
    media = (site / "media").resolve()
    assert shown_images(site, f"zh/guides/{slug}/") == [
        (media / first, "开局"), (media / second, "终局阵容")]
    assert files_in(media) == {first, second}

    assert act(admin, revision, "publish").status_code == 303
    render_site(site)
    assert shown_images(site, f"zh/guides/{slug}/") == [
        (media / first, "新的开局"), (media / third, "")]
    assert files_in(media) == {first, third}
    [cover] = [item for item in list_items(site, "zh/") if "<img" in item]
    assert third in cover
    assert images_on(admin.get(edit_page).text) == [first, third]


def test_a_discarded_revision_leaves_the_guides_images_as_they_were(
        editor, admin, tmp_path):
    edit_page, first, second = guide_with_images(editor, admin)
    open_revision(editor, edit_page)
    revision = revision_page(edit_page)
    extra = uploaded(editor, revision)
    describe(editor, revision, first, "改过的说明", "Changed", cover=extra)
    discard = f"{revision.removesuffix('/edit')}/delete"
    assert fill_in(editor, discard, discard).status_code == 303

    page = admin.get(edit_page).text
    assert images_on(page) == [first, second]
    assert 'value="开局"' in page and chosen_cover(page) == second
    assert files_in(tmp_path / "media") == {first, second}


def test_an_admin_gives_a_tournament_item_images_and_an_optional_cover(admin, site):
    edit_page = new_tournament_item(admin)
    first = uploaded(admin, edit_page, values=tournament_form_values(admin, edit_page))
    second = uploaded(admin, edit_page, values=tournament_form_values(admin, edit_page))
    page = admin.get(edit_page).text
    assert images_on(page) == [first, second] and chosen_cover(page) == first
    number = image_id(page, first)
    response = save_tournament_item(
        admin, edit_page, cover="", body_zh=f"冠军阵容：![]({first})",
        title_en="October", body_en=f"The winner: ![]({first})",
        **{f"alt_zh_{number}": "冠军阵容", f"alt_en_{number}": "Winning lineup"})
    assert response.status_code == 303
    assert chosen_cover(admin.get(edit_page).text) == ""

    preview = f"{edit_page.removesuffix('/edit')}/preview"
    [tag, _] = img_tags(admin.get(preview).text)
    src = re.search(r'src="([^"]+)"', tag)
    assert 'alt="冠军阵容"' in tag and src
    assert admin.get(urljoin(f"http://testserver{preview}", src.group(1))).content == PNG

    assert page_act(admin, edit_page, "publish").status_code == 303
    render_site(site)
    item = f"tournaments/{edit_page.split('/')[3]}/"
    media = (site / "media").resolve()
    assert shown_images(site, f"zh/{item}") == [(media / first, "冠军阵容")]
    assert shown_images(site, f"en/{item}") == [(media / first, "Winning lineup")]
    assert shown_images(site, "zh/tournaments/") == []  # no cover chosen

    save_tournament_item(admin, edit_page, cover=second)
    render_site(site)
    assert shown_images(site, "zh/tournaments/") == [(media / second, "")]


def test_deleting_a_tournament_item_deletes_its_images(admin, editor, tmp_path):
    edit_page = new_tournament_item(admin)
    filename = uploaded(admin, edit_page, values=tournament_form_values(admin, edit_page))
    assert editor.get(image_url(edit_page, filename)).status_code == 403
    delete = f"{edit_page.removesuffix('/edit')}/delete"
    assert fill_in(admin, delete, delete).status_code == 303
    assert files_in(tmp_path / "media") == set()


def test_image_changes_to_published_content_count_as_not_on_the_site(editor, admin):
    edit_page = published_guide(admin, admin)
    item = published_tournament_item(admin)
    press_update_site(admin)
    # Bare presses of the buttons, without the rest of the editor form.
    uploaded(admin, edit_page, values={})
    uploaded(admin, item, values={})
    assert pending_changes(admin) == "2 项更改尚未更新到网站"
    press_update_site(admin)
    for page in (edit_page, item):
        [number] = re.findall(r'name="alt_zh_(\d+)"', admin.get(page).text)
        token = csrf_token(admin.get(page).text)
        response = admin.post(f"{page.removesuffix('/edit')}/images/{number}/delete",
                              data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303
    assert pending_changes(admin) == "2 项更改尚未更新到网站"


@pytest.mark.parametrize("make", ["guide", "revision", "tournament"])
def test_pressing_enter_in_an_editor_form_saves_it_rather_than_pressing_an_image_button(
        editor, admin, make):
    if make == "guide":
        edit_page = new_guide(editor)
    elif make == "revision":
        published = published_guide(editor, admin)
        open_revision(editor, published)
        edit_page = revision_page(published)
    else:
        edit_page = new_tournament_item(admin)
    c = admin if make == "tournament" else editor
    values = tournament_form_values(admin, edit_page) if make == "tournament" else None
    uploaded(c, edit_page, values=values)
    form = re.search(r'<form method="post" action="[^"]*">(?:(?!</form>).)*name="image"'
                     r'(?:(?!</form>).)*</form>', c.get(edit_page).text, re.DOTALL)
    assert form
    # A browser's Enter key presses the form's first submit button.
    first = re.search(r'<button type="submit"[^>]*>', form.group(0))
    assert first and "formaction" not in first.group(0)


def test_a_tampered_alt_text_field_is_ignored(editor):
    edit_page = new_guide(editor)
    uploaded(editor, edit_page)
    response = save(editor, edit_page, alt_zh_99999999999999999999="x", alt_en_7="y")
    assert response.status_code == 303


def test_a_file_name_mentioned_in_prose_does_not_stop_its_image_being_deleted(editor):
    edit_page = new_guide(editor)
    filename = uploaded(editor, edit_page)
    save(editor, edit_page, body_zh=f"上传的文件叫 {filename}。")
    assert delete_image(editor, edit_page, filename).status_code == 303
