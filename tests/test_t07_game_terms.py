"""T07: Admins manage Game Terms, and `[[term]]` markers show each one's
Official name in the Reader's language (Seam 1: the console over HTTP; Seam 2:
the files `render_site` writes)."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from app.publish import render_site
from conftest import csrf_token
from test_t02_heroes_patches import edit_hero, edit_link, submit
from test_t03_guides import act, admin, editor, new_guide, slug_of  # noqa: F401
from test_t04_site_build import page, published_guide, site  # noqa: F401


def add_term(c: TestClient, kind: str, name_zh: str, name_en: str,
             nicknames: str = ""):
    return submit(c, "/admin/terms", "/admin/terms", kind=kind, name_zh=name_zh,
                  name_en=name_en, nicknames=nicknames)


def test_admin_adds_an_item_and_sees_it_listed_with_its_kind(admin):
    response = add_term(admin, "item", "海盗弯刀", "Pirate Scimitar")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/terms"

    page = admin.get("/admin/terms").text
    assert "<td>物品</td><td>海盗弯刀</td><td>Pirate Scimitar</td>" in page


@pytest.mark.parametrize("kind", ["item", "skill", "enchantment", "monster",
                                  "merchant", "event"])
@pytest.mark.parametrize("name_zh, name_en, message", [
    ("", "Pirate Scimitar", "请填写官方中文名"),
    ("海盗弯刀", "  ", "请填写官方英文名"),
])
def test_a_game_term_of_any_kind_needs_both_official_names(admin, kind, name_zh,
                                                           name_en, message):
    response = add_term(admin, kind, name_zh, name_en)
    assert response.status_code == 400
    assert message in response.text
    assert "还没有游戏术语" in admin.get("/admin/terms").text


def test_each_of_the_six_kinds_besides_hero_can_be_added(admin):
    for kind, label in [("item", "物品"), ("skill", "技能"), ("enchantment", "附魔"),
                        ("monster", "怪物"), ("merchant", "商人"), ("event", "事件")]:
        add_term(admin, kind, f"中文{kind}", f"English {kind}")
        assert f"<td>{label}</td><td>中文{kind}</td>" in admin.get("/admin/terms").text


@pytest.mark.parametrize("kind", ["", "card", "hero"])
def test_a_game_term_without_a_known_kind_is_refused(admin, kind):
    response = add_term(admin, kind, "海盗弯刀", "Pirate Scimitar")
    assert response.status_code == 400
    assert "请选择术语种类" in response.text


def test_two_terms_of_one_kind_cannot_share_an_english_name(admin):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar")
    response = add_term(admin, "item", "另一把弯刀", "pirate scimitar ")
    assert response.status_code == 400
    assert "官方英文名 Pirate Scimitar 已被物品 海盗弯刀 使用" in response.text

    # Another kind may use the same name; a marker naming it then gets a
    # preview warning.
    assert add_term(admin, "monster", "海盗弯刀怪", "Pirate Scimitar").status_code == 303


def term_edit_link(c: TestClient, listed_en: str) -> str:
    """The edit page linked from the Game Term list row showing `listed_en`."""
    row = next(r for r in c.get("/admin/terms").text.split("<tr>")
               if f"<td>{listed_en}</td>" in r)
    match = re.search(r'href="([./]*admin/terms/\d+/edit)"', row)
    assert match, f"no edit link for {listed_en}"
    return urljoin("/admin/terms", match.group(1))


def edit_term(c: TestClient, listed_en: str, **fields):
    edit_page = term_edit_link(c, listed_en)
    return submit(c, edit_page, edit_page.removesuffix("/edit"), **fields)


def test_admin_records_nicknames_against_a_game_term(admin):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar", nicknames="弯刀、大刀 | 刀")
    page = admin.get("/admin/terms").text
    assert "<td>弯刀、大刀、刀</td>" in page


def test_admin_corrects_a_game_terms_names_and_nicknames(admin):
    add_term(admin, "skill", "快速装填", "Quick Reload", nicknames="快装")
    response = edit_term(admin, "Quick Reload", name_zh="迅速装填",
                         name_en="Quick Reloading", nicknames="快装|速装")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/terms"
    page = admin.get("/admin/terms").text
    assert "<td>技能</td><td>迅速装填</td><td>Quick Reloading</td><td>快装、速装</td>" in page

    response = edit_term(admin, "Quick Reloading", name_zh="", name_en="Quick Reload",
                         nicknames="")
    assert response.status_code == 400
    assert "请填写官方中文名" in response.text
    assert "<td>迅速装填</td>" in admin.get("/admin/terms").text


def test_an_edited_term_cannot_take_another_terms_english_name(admin):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar")
    add_term(admin, "item", "船锚", "Anchor")
    response = edit_term(admin, "Anchor", name_zh="船锚", name_en="PIRATE SCIMITAR")
    assert response.status_code == 400
    assert "官方英文名 Pirate Scimitar 已被物品 海盗弯刀 使用" in response.text


def test_a_missing_game_term_has_no_edit_page(admin):
    assert admin.get("/admin/terms/999/edit").status_code == 404


def test_admin_records_nicknames_against_a_hero(admin):
    response = edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa",
                         nicknames="瓦姐|V姐")
    assert response.status_code == 303
    assert "瓦姐、V姐" in admin.get(edit_link(admin, "Vanessa")).text
    assert "瓦姐、V姐" in admin.get("/admin/heroes").text


def test_a_marker_shows_the_official_name_in_each_sites_language(admin, site):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar")
    slug = published_guide(admin, body_zh="[[Vanessa]] 先拿 [[pirate scimitar]]。",
                           title_en="Vanessa pirates",
                           body_en="Play [[瓦妮莎]] with [[海盗弯刀]].")
    render_site(site)
    zh, en = page(site, f"zh/guides/{slug}/"), page(site, f"en/guides/{slug}/")
    assert ('<span class="term">瓦妮莎</span> 先拿 <span class="term">海盗弯刀</span>。'
            in zh)
    assert ('Play <span class="term">Vanessa</span> with'
            ' <span class="term">Pirate Scimitar</span>.' in en)
    assert "[[" not in zh + en
    assert ".term {" in (site / "style.css").read_text()


def preview_of(c: TestClient, edit_page: str) -> str:
    response = c.get(edit_page.removesuffix("/edit") + "/preview")
    assert response.status_code == 200
    return response.text


def test_the_preview_shows_markers_as_the_site_will(editor):
    edit_page = new_guide(editor, body_zh="先拿 [[Vanessa]]。", title_en="Pirates",
                          body_en="Play [[瓦妮莎]].")
    preview = preview_of(editor, edit_page)
    assert '先拿 <span class="term">瓦妮莎</span>。' in preview
    assert 'Play <span class="term">Vanessa</span>.' in preview
    assert "没有需要注意的游戏术语" in preview


def test_the_preview_warns_about_a_marker_that_names_no_game_term(editor):
    edit_page = new_guide(editor, body_zh="先拿 [[瓦姐]] 再拿 [[Vanessa]]。")
    preview = preview_of(editor, edit_page)
    assert "[[瓦姐]] 没有对应的游戏术语" in preview
    assert "Vanessa]] 没有" not in preview
    assert "先拿 瓦姐 再拿" in preview


def test_the_preview_warns_about_a_nickname_written_without_a_marker(admin, editor):
    edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa",
              nicknames="瓦姐|Van")
    edit_page = new_guide(editor, title_zh="瓦姐海盗流",
                          body_zh="先拿 [[瓦妮莎]]，`瓦姐` 只在代码里。",
                          title_en="Pirates", body_en="Van is strong. Vanguard is not.")
    preview = preview_of(editor, edit_page)
    assert "中文标题：外号“瓦姐”没有标记（1 处），官方名称是 瓦妮莎（Vanessa）" in preview
    assert "英文正文：外号“Van”没有标记（1 处），官方名称是 瓦妮莎（Vanessa）" in preview
    assert "中文正文" not in preview  # the marked name and the code don't count


def test_the_preview_warns_when_a_marker_names_several_game_terms(admin, editor):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar")
    add_term(admin, "monster", "弯刀海盗", "Pirate Scimitar")
    edit_page = new_guide(editor, body_zh="小心 [[Pirate Scimitar]]。")
    preview = preview_of(editor, edit_page)
    assert ("[[Pirate Scimitar]] 对应多个游戏术语：物品 海盗弯刀（Pirate Scimitar）、"
            "怪物 弯刀海盗（Pirate Scimitar）。网站上会显示为“海盗弯刀”。") in preview


def test_a_guide_with_preview_warnings_can_still_be_submitted(editor):
    edit_page = new_guide(editor, body_zh="先拿 [[瓦姐]]。")
    assert "[[瓦姐]] 没有对应的游戏术语" in preview_of(editor, edit_page)
    assert act(editor, edit_page, "submit").status_code == 303
    assert "待审核" in editor.get(edit_page).text


def test_a_marker_that_names_no_game_term_shows_its_text_on_the_site(admin, site):
    slug = published_guide(admin, body_zh="先拿 [[瓦姐]]。")
    assert "<p>先拿 瓦姐。</p>" in page(render_site(site), f"zh/guides/{slug}/")


def test_a_malicious_game_term_name_cannot_inject_html(admin, editor, site):
    add_term(admin, "item", '<img src=x onerror="alert(1)">', "<script>alert(1)</script>")
    edit_page = new_guide(editor, body_zh="[[<script>alert(1)</script>]]",
                          title_en="Evil", body_en='[[<img src=x onerror="alert(1)">]]')
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    slug = slug_of(admin, edit_page)
    render_site(site)
    zh, en = page(site, f"zh/guides/{slug}/"), page(site, f"en/guides/{slug}/")
    for html in [preview_of(editor, edit_page), zh, en]:
        assert "<script>alert" not in html and "<img src=x" not in html
    assert '<span class="term">&lt;img src=x onerror="alert(1)"&gt;</span>' in zh
    assert '<span class="term">&lt;script&gt;alert(1)&lt;/script&gt;</span>' in en


CSV_HEADER = "kind,name_zh,name_en,nicknames\n"


def upload_csv(c: TestClient, text: str, encoding: str = "utf-8"):
    """Choose `text` as the CSV file on the import page and upload it."""
    token = csrf_token(c.get("/admin/terms/import").text)
    return c.post("/admin/terms/import", data={"csrf_token": token},
                  files={"file": ("terms.csv", text.encode(encoding), "text/csv")},
                  follow_redirects=False)


def confirm_import(c: TestClient, preview: str):
    """Press 确认导入 on an import preview, sending its hidden fields."""
    match = re.search(r'<form method="post" action="([./]*admin/terms/import/confirm)">'
                      r'(.*?)</form>', preview, re.DOTALL)
    assert match, "no 确认导入 form"
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"',
                             match.group(2)))
    return c.post(urljoin("/admin/terms/import", match.group(1)),
                  data={name: html.unescape(value) for name, value in fields.items()},
                  follow_redirects=False)


def test_a_csv_import_shows_what_it_will_add_and_change_before_saving(admin):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar", nicknames="弯刀")
    preview = upload_csv(admin, CSV_HEADER
                         + "英雄,朱尔斯,Jules,\n"
                         + "item,新海盗弯刀,pirate scimitar,\n"
                         + "skill,快速装填,Quick Reload,快装|速装\n")
    assert preview.status_code == 200
    assert "将新增 2 个" in preview.text
    assert "<td>英雄</td><td>朱尔斯</td><td>Jules</td>" in preview.text
    assert "<td>技能</td><td>快速装填</td><td>Quick Reload</td><td>快装、速装</td>" in preview.text
    assert "将修改 1 个" in preview.text
    assert "海盗弯刀（Pirate Scimitar）→ 新海盗弯刀（pirate scimitar）" in preview.text

    terms = admin.get("/admin/terms").text
    assert "快速装填" not in terms and "新海盗弯刀" not in terms
    assert "朱尔斯" not in admin.get("/admin/heroes").text


def test_confirming_a_csv_import_saves_the_previewed_rows(admin):
    add_term(admin, "item", "海盗弯刀", "Pirate Scimitar", nicknames="弯刀")
    preview = upload_csv(admin, CSV_HEADER
                         + "英雄,朱尔斯,Jules,\n"
                         + "item,新海盗弯刀,Pirate Scimitar,\n"
                         + "Skill,快速装填,Quick Reload,快装|速装\n")
    response = confirm_import(admin, preview.text)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/terms"

    terms = admin.get("/admin/terms").text
    assert "已导入游戏术语：新增 2 个，修改 1 个。" in terms
    # An empty nicknames cell keeps the nicknames a term already has.
    assert "<td>物品</td><td>新海盗弯刀</td><td>Pirate Scimitar</td><td>弯刀</td>" in terms
    assert "<td>技能</td><td>快速装填</td><td>Quick Reload</td><td>快装、速装</td>" in terms
    assert "<td>朱尔斯</td><td>Jules</td><td><code>jules</code></td>" in admin.get(
        "/admin/heroes").text


def test_csv_rows_missing_a_name_or_with_an_unknown_kind_are_rejected_by_row(admin):
    preview = upload_csv(admin, CSV_HEADER
                         + "item,海盗弯刀,Pirate Scimitar,\n"
                         + "item,,Anchor,\n"
                         + "card,船锚,Anchor,\n"
                         + "skill,快速装填,  ,\n"
                         + ",,,\n"
                         + "monster,海怪,Kraken,\n"
                         + "item,海盗弯刀二,PIRATE SCIMITAR,\n")
    assert preview.status_code == 200
    text = preview.text
    assert '<td>第 3 行</td><td class="wrap">缺少官方中文名。</td>' in text
    assert '<td>第 4 行</td><td class="wrap">未知的种类“card”' in text
    assert '<td>第 5 行</td><td class="wrap">缺少官方英文名。</td>' in text
    assert '<td>第 8 行</td><td class="wrap">和第 2 行是同一个游戏术语（种类和官方英文名都相同）。</td>' in text
    assert "第 6 行" not in text  # a wholly blank row is skipped
    assert "将新增 2 个" in text

    confirm_import(admin, text)
    terms = admin.get("/admin/terms").text
    assert "已导入游戏术语：新增 2 个，修改 0 个。4 行被拒绝，没有导入。" in terms
    assert "<td>海盗弯刀</td>" in terms and "<td>海怪</td>" in terms
    assert "船锚" not in terms and "快速装填" not in terms and "海盗弯刀二" not in terms


def test_a_csv_hero_whose_slug_is_taken_is_rejected(admin):
    preview = upload_csv(admin, CSV_HEADER + "英雄,另一个瓦妮莎,Vanessa!,\n"
                         + "英雄,黑骑士,Black Knight,\n" + "英雄,黑骑士二,Black-Knight,\n")
    assert '<td>第 2 行</td><td class="wrap">网址名 vanessa 已被英雄 瓦妮莎（Vanessa）使用。</td>' in preview.text
    assert '<td>第 4 行</td><td class="wrap">网址名 black-knight 已被第 3 行的英雄使用。</td>' in preview.text
    assert "将新增 1 个" in preview.text


@pytest.mark.parametrize("text, encoding, message", [
    ("name_zh,name_en\n海盗弯刀,Pirate Scimitar\n", "utf-8", "第一行必须是表头"),
    (CSV_HEADER + "物品,海盗弯刀,Pirate Scimitar,\n", "gbk", "UTF-8"),
    ("", "utf-8", "第一行必须是表头"),
])
def test_a_csv_file_that_cannot_be_read_is_refused_whole(admin, text, encoding, message):
    response = upload_csv(admin, text, encoding)
    assert response.status_code == 400
    assert message in response.text
    assert "确认导入" not in response.text


def test_a_csv_saved_by_excel_with_a_byte_order_mark_is_read(admin):
    preview = upload_csv(admin, CSV_HEADER + "物品,海盗弯刀,Pirate Scimitar,\n",
                         "utf-8-sig")
    assert "将新增 1 个" in preview.text


def test_seed_imports_demo_game_terms_once(tmp_path, monkeypatch):
    from test_t02_seed import seeded_admin

    admin = seeded_admin(tmp_path, monkeypatch, times=2)
    terms = admin.get("/admin/terms").text
    assert terms.count("<td>物品</td>") >= 3
    assert terms.count("<td>Anchor</td>") == 1
    assert "瓦姐" in admin.get("/admin/heroes").text


def test_every_game_term_and_csv_route_is_behind_an_admin_only_guard():
    from fastapi.routing import APIRoute

    from app.routes import game
    from test_t09_users import admin_only_routes

    term_routes = {(method, route.path) for route in game.router.routes
                   if isinstance(route, APIRoute) and route.path.startswith("/admin/terms")
                   for method in route.methods or ()}
    assert len(term_routes) == 7
    assert term_routes <= set(admin_only_routes())


def test_an_editor_is_refused_a_csv_import_with_a_real_file(admin, editor):
    token = csrf_token(editor.get("/admin/dashboard").text)
    response = editor.post("/admin/terms/import", data={"csrf_token": token},
                           files={"file": ("terms.csv", (CSV_HEADER + "物品,船锚,Anchor,\n")
                                           .encode(), "text/csv")})
    assert response.status_code == 403
    assert "船锚" not in admin.get("/admin/terms").text


def test_a_title_is_plain_text_so_the_preview_asks_for_the_official_name(admin, editor):
    edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa", nicknames="瓦姐")
    edit_page = new_guide(editor, title_zh="瓦姐和[[Vanessa]]")
    preview = preview_of(editor, edit_page)
    assert "中文标题：外号“瓦姐”没有标记（1 处），官方名称是 瓦妮莎（Vanessa），标题里请直接写 瓦妮莎。" in preview
    assert "中文标题：标题里的 [[Vanessa]] 会原样显示，请直接写官方名称。" in preview


def test_a_csv_file_that_is_not_a_valid_csv_is_refused_whole(admin):
    # An unclosed quote runs the rest of the file into one overlong cell.
    response = upload_csv(admin, CSV_HEADER + '物品,"船锚,Anchor,' + "x" * 200_000)
    assert response.status_code == 400
    assert "读不出这个 CSV 文件" in response.text


def test_seeding_again_leaves_game_terms_an_admin_has_edited(tmp_path, monkeypatch):
    from test_t01_seed import run_seed
    from test_t02_seed import ENV, seeded_admin

    admin = seeded_admin(tmp_path, monkeypatch)
    edit_term(admin, "Anchor", name_zh="锚", name_en="Anchor", nicknames="")
    edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa", nicknames="")
    result = run_seed({"CMS_DATABASE": str(tmp_path / "seeded.db"), **ENV})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "<td>物品</td><td>锚</td><td>Anchor</td><td></td>" in admin.get("/admin/terms").text
    assert "瓦姐" not in admin.get("/admin/heroes").text


def test_each_unmarked_nickname_is_one_preview_warning_with_a_count(admin, editor):
    edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa",
              nicknames="瓦姐|Van")
    edit_page = new_guide(editor, body_zh="瓦姐先拿船。\n\n**瓦姐**再拿炮，瓦姐最后叠盾。",
                          title_en="Pirates", body_en="VAN and van. Vanguard.")
    preview = preview_of(editor, edit_page)
    assert preview.count("外号“瓦姐”没有标记") == 1
    assert "中文正文：外号“瓦姐”没有标记（3 处）" in preview
    assert "英文正文：外号“Van”没有标记（2 处）" in preview


ONE_CHARACTER_NOTICE = "只有一个汉字"


def test_a_one_character_chinese_nickname_is_saved_with_a_notice(admin):
    response = add_term(admin, "item", "船锚", "Anchor", nicknames="锚|大锚")
    assert response.status_code == 303
    terms = admin.get("/admin/terms").text
    assert "<td>锚、大锚</td>" in terms
    assert ("外号“锚”只有一个汉字：预览会把正文里每一个“锚”都当作这个外号，"
            "可能出现很多提醒。") in terms
    # The term's own page keeps saying so while the nickname is there.
    assert ONE_CHARACTER_NOTICE in admin.get(term_edit_link(admin, "Anchor")).text

    edit_term(admin, "Anchor", name_zh="船锚", name_en="Anchor", nicknames="大锚|V")
    assert ONE_CHARACTER_NOTICE not in admin.get("/admin/terms").text
    assert ONE_CHARACTER_NOTICE not in admin.get(term_edit_link(admin, "Anchor")).text


def test_a_one_character_chinese_nickname_on_a_hero_is_saved_with_a_notice(admin):
    response = edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa",
                         nicknames="瓦")
    assert response.status_code == 303
    assert "外号“瓦”只有一个汉字" in admin.get("/admin/heroes").text
    assert ONE_CHARACTER_NOTICE in admin.get(edit_link(admin, "Vanessa")).text


def test_a_csv_import_preview_points_out_one_character_chinese_nicknames(admin):
    preview = upload_csv(admin, CSV_HEADER + "物品,船锚,Anchor,锚|大锚\n"
                         + "物品,火药桶,Powder Keg,桶\n")
    assert "第 2 行：外号“锚”只有一个汉字" in preview.text
    assert "第 3 行：外号“桶”只有一个汉字" in preview.text
    assert "将新增 2 个" in preview.text
