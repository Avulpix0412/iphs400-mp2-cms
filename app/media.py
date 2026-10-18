"""Uploaded images: checking them, storing them, and the rows that say whose
they are.

An image belongs to one owner, a Guide, a Guide's open Revision or a
Tournament item, named by a key such as "guide/12" (its `media_owner`). It can be
used in both languages' text, as `![](<filename>)`, and has optional alt text
per language. The owner's cover is one of its images, by file name, kept on
the owner's own row: NULL means the first image, and '' means none.

Only PNG, JPG, WebP and GIF are accepted, recognised by their content (an SVG
can carry script, so it never is). The stored file name is generated here;
the uploaded name is only checked for its extension and never touches the
disk. Files live in the media folder (settings.media_path()), the store of
Images' files. A Revision's images are copies of its Guide's rows that share
their files, so a file is deleted only once no row names it. Files are
written and deleted along with the transaction that adds or removes their
rows (db.after_commit).

Who may change an owner's images is decided by app/guides.py and
app/content.py, which call these functions once they have checked.
"""
from __future__ import annotations

import re
import secrets
import shutil
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app import db, settings

MAX_BYTES = 5 * 1024 * 1024
ALLOWED = "PNG、JPG、WebP 或 GIF"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
                 ".gif": "image/gif"}
FILENAME = re.compile(r"[0-9a-f]{32}\.(png|jpg|webp|gif)")


class BadImage(Exception):
    """An upload that is refused, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Upload:
    """A file as the browser sent it. `data` holds at most MAX_BYTES + 1
    bytes, enough to tell that a file is too large."""
    name: str
    data: bytes


@dataclass(frozen=True)
class Image:
    id: int
    filename: str
    alt_zh: str
    alt_en: str

    def alt(self, lang: str) -> str:
        return getattr(self, f"alt_{lang}")


@dataclass(frozen=True)
class ImageFields:
    """What an editor form sends about its images: alt text by image id, as
    (Chinese, English), for the images it showed, and the chosen cover's file
    name. cover is None when the form sent no choice."""
    alts: Mapping[int, tuple[str, str]] = field(default_factory=dict)
    cover: str | None = None


def _kind_by_content(data: bytes) -> str | None:
    """The extension that `data` really is, by its first bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def checked(upload: Upload) -> str:
    """The extension to store `upload` under, or BadImage saying why not."""
    if not upload.name and not upload.data:
        raise BadImage("请先选择要上传的图片。")
    extension = Path(upload.name.lower()).suffix
    if extension not in EXTENSIONS:
        raise BadImage(f"只能上传 {ALLOWED} 图片（不支持 SVG），"
                       f"“{upload.name}”不是。")
    if len(upload.data) > MAX_BYTES:
        raise BadImage(f"图片不能超过 5 MB，“{upload.name}”太大了。")
    kind = _kind_by_content(upload.data)
    if kind is None:
        raise BadImage(f"“{upload.name}”的内容不是 {ALLOWED} 图片，"
                       "可能只是改了扩展名。")
    return kind


def images(conn: sqlite3.Connection, owner: str) -> list[Image]:
    """The owner's images, in the order they were uploaded."""
    rows = conn.execute("SELECT id, filename, alt_zh, alt_en FROM images"
                        " WHERE owner = ? ORDER BY id", (owner,)).fetchall()
    return [Image(**dict(row)) for row in rows]


def add(conn: sqlite3.Connection, owner: str, upload: Upload) -> Image:
    """Check `upload` and store it as the owner's newest image."""
    filename = secrets.token_hex(16) + checked(upload)
    folder = settings.media_path()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(upload.data)
    db.after_commit(conn, rolled_back=(folder / filename).unlink)
    cur = conn.execute("INSERT INTO images (owner, filename) VALUES (?, ?)",
                       (owner, filename))
    return Image(cur.lastrowid or 0, filename, "", "")


def image(conn: sqlite3.Connection, owner: str, image_id: int) -> Image | None:
    return next((found for found in images(conn, owner) if found.id == image_id), None)


def file(conn: sqlite3.Connection, owner: str, filename: str) -> Path | None:
    """The file of the owner's image called `filename`, if it has one."""
    if not FILENAME.fullmatch(filename) or not any(
            found.filename == filename for found in images(conn, owner)):
        return None
    path = settings.media_path() / filename
    return path if path.is_file() else None


def content_type(filename: str) -> str:
    return CONTENT_TYPES[Path(filename).suffix]


def save_alts(conn: sqlite3.Connection, owner: str, fields: ImageFields) -> None:
    """Keep the alt text the form sent for the owner's images."""
    conn.executemany("UPDATE images SET alt_zh = ?, alt_en = ? WHERE id = ? AND owner = ?",
                     [(zh.strip(), en.strip(), image_id, owner)
                      for image_id, (zh, en) in fields.alts.items()])


def checked_cover(conn: sqlite3.Connection, owner: str, cover: str | None, *,
                  optional: bool) -> str | None:
    """The cover to keep from what a form sent: None (the first image) unless
    it names one of the owner's images, or is '' and the owner may have no
    cover at all."""
    if cover == "" and optional:
        return ""
    return cover if any(found.filename == cover for found in images(conn, owner)) else None


def cover(found: list[Image], chosen: str | None) -> Image | None:
    """The cover among `found` (an owner's images): the chosen one, else the
    first, or none if the owner chose none or has no images."""
    if chosen == "":
        return None
    return next((image for image in found if image.filename == chosen),
                found[0] if found else None)


def _delete_unused_files(conn: sqlite3.Connection, filenames: Iterable[str]) -> None:
    """Delete the files no image row names any more, once that is committed."""
    for filename in set(filenames):
        if not conn.execute("SELECT 1 FROM images WHERE filename = ?",
                            (filename,)).fetchone():
            db.after_commit(conn, committed=lambda path=settings.media_path() / filename:
                            path.unlink(missing_ok=True))


def remove_unused(conn: sqlite3.Connection, owner: str, image_id: int,
                  body_zh: str, body_en: str) -> bool:
    """Delete the owner's image, unless its text (`body_zh`, `body_en`) still
    uses it, which raises BadImage. False if the owner has no such image."""
    found = image(conn, owner, image_id)
    if found is None:
        return False
    # Written `![alt](<filename>)`, with any spaces or angle brackets
    # Markdown allows around the address.
    used = re.compile(rf"!\[[^\]]*\]\(\s*<?{re.escape(found.filename)}[\s>)]")
    for where, body in [("中文正文", body_zh), ("英文正文", body_en)]:
        if used.search(body):
            raise BadImage(f"{where}还在使用这张图片。请先从{where}里删掉"
                           f" ![]({found.filename})，再删除图片。")
    conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
    _delete_unused_files(conn, [found.filename])
    return True


def remove_all(conn: sqlite3.Connection, owner: str) -> None:
    filenames = [found.filename for found in images(conn, owner)]
    conn.execute("DELETE FROM images WHERE owner = ?", (owner,))
    _delete_unused_files(conn, filenames)


def copy_all(conn: sqlite3.Connection, source: str, target: str) -> None:
    """Give `target` its own copy of each of `source`'s images (rows only;
    the two share the files)."""
    remove_all(conn, target)
    conn.execute("INSERT INTO images (owner, filename, alt_zh, alt_en)"
                 " SELECT ?, filename, alt_zh, alt_en FROM images WHERE owner = ?"
                 " ORDER BY id", (target, source))


def move_all(conn: sqlite3.Connection, source: str, target: str) -> None:
    """Replace `target`'s images with `source`'s, which `source` loses."""
    old = [found.filename for found in images(conn, target)]
    conn.execute("DELETE FROM images WHERE owner = ?", (target,))
    conn.execute("UPDATE images SET owner = ? WHERE owner = ?", (target, source))
    _delete_unused_files(conn, old)


def sources(found: list[Image], lang: str, src: str) -> dict[str, tuple[str, str]]:
    """What render_markdown needs to show `found` (an owner's images) on one
    page in `lang`: each file name, as written in the text, mapped to the
    `src` to use there (`src` with "{}" in place of the file name) and its alt
    text in `lang`."""
    return {image.filename: (src.format(image.filename), image.alt(lang))
            for image in found}


def copy_files(found: Iterable[Image], out: Path) -> None:
    """Copy the files of the images `found` into the folder `out`."""
    for image in found:
        source = settings.media_path() / image.filename
        if source.is_file():
            out.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, out / image.filename)
