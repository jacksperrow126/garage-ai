"""Pure-dict tests for image URL extraction from Zalo webhook envelopes.

We don't have authoritative Zalo Bot docs for image messages, so we
cover the shapes we expect to encounter. When real envelopes show up
in prod logs and don't match, extend `_URL_FIELD_HINTS` or add a new
top-level path to `extract_image_urls` and add a case here."""

from __future__ import annotations

from app.services.zalo_attachments import extract_image_urls


def test_attachments_array_with_type_image() -> None:
    msg = {
        "attachments": [
            {"type": "image", "url": "https://cdn.zalo.example/abc.jpg"},
            {"type": "image", "url": "https://cdn.zalo.example/def.jpg"},
        ]
    }
    assert extract_image_urls(msg) == [
        "https://cdn.zalo.example/abc.jpg",
        "https://cdn.zalo.example/def.jpg",
    ]


def test_attachments_with_photo_type_and_href_field() -> None:
    msg = {
        "attachments": [
            {"type": "photo", "href": "https://cdn.example/x.png"},
        ]
    }
    assert extract_image_urls(msg) == ["https://cdn.example/x.png"]


def test_photo_field_dict() -> None:
    msg = {"photo": {"url": "https://cdn.example/p.jpg"}}
    assert extract_image_urls(msg) == ["https://cdn.example/p.jpg"]


def test_photo_field_list_of_sizes() -> None:
    """Telegram-style: photo is an array of size variants. Take all
    the URLs we can find — the agent caller picks the first."""
    msg = {
        "photo": [
            {"url": "https://cdn.example/small.jpg"},
            {"url": "https://cdn.example/large.jpg"},
        ]
    }
    assert extract_image_urls(msg) == [
        "https://cdn.example/small.jpg",
        "https://cdn.example/large.jpg",
    ]


def test_image_field_dict() -> None:
    msg = {"image": {"image_url": "https://cdn.example/i.jpg"}}
    assert extract_image_urls(msg) == ["https://cdn.example/i.jpg"]


def test_dedupes_repeated_urls() -> None:
    msg = {
        "attachments": [
            {"type": "image", "url": "https://cdn.example/a.jpg"},
            {"type": "image", "url": "https://cdn.example/a.jpg"},
        ]
    }
    assert extract_image_urls(msg) == ["https://cdn.example/a.jpg"]


def test_skips_non_image_attachments() -> None:
    msg = {
        "attachments": [
            {"type": "sticker", "url": "https://cdn.example/s.gif"},
            {"type": "file", "url": "https://cdn.example/f.pdf"},
        ]
    }
    assert extract_image_urls(msg) == []


def test_skips_non_http_urls() -> None:
    """Defensive: only http/https URLs are considered. Local file:// or
    relative paths are filtered out."""
    msg = {"image": {"url": "file:///tmp/local.jpg"}}
    assert extract_image_urls(msg) == []


def test_text_only_message_yields_no_urls() -> None:
    msg = {"text": "Còn dầu nhớt OIL5W30 không?"}
    assert extract_image_urls(msg) == []


def test_real_zalo_bot_image_envelope() -> None:
    """The actual shape Zalo Bot sends for message.image.received,
    captured from prod logs on 2026-05-07. Top-level `photo_url` string
    on the message — no nested `photo` object, no `attachments[]`."""
    msg = {
        "date": 1778134087088,
        "chat": {"chat_type": "PRIVATE", "id": "8f705344d20d3b53621c"},
        "caption": "hiểu ảnh này không",
        "message_id": "5b62112a2f7fde268769",
        "message_type": "CHAT_PHOTO",
        "from": {
            "id": "8f705344d20d3b53621c",
            "is_bot": False,
            "display_name": "Nguyễn Thành An",
        },
        "photo_url": (
            "https://photo-stal-30.zdn.vn/no/jpg/7c242a7c3a1cfa42a30d/"
            "4311211535202630369.jpg"
        ),
    }
    assert extract_image_urls(msg) == [
        "https://photo-stal-30.zdn.vn/no/jpg/7c242a7c3a1cfa42a30d/"
        "4311211535202630369.jpg"
    ]
