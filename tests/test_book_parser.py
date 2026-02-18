# tests/test_book_parser.py
import pytest
import fitz
from book_parser import parse_text, parse_pdf


def test_parse_text_short_text_is_single_page():
    text = "Hello world. This is a short book."
    pages = parse_text(text)
    assert len(pages) == 1
    assert "Hello world" in pages[0]


def test_parse_text_long_text_splits_into_multiple_pages():
    # 100 repetitions × ~20 chars = ~2000 chars, should split at chars_per_page=500
    text = "This is a sentence. " * 100
    pages = parse_text(text, chars_per_page=500)
    assert len(pages) > 1


def test_parse_text_no_empty_pages():
    text = "First sentence. Second sentence. Third sentence."
    pages = parse_text(text, chars_per_page=20)
    assert all(p.strip() for p in pages)


def test_parse_text_splits_at_sentence_boundaries():
    # With small page size, each page should end at a sentence boundary
    text = "Hello world. Goodbye world. Another sentence here. One more."
    pages = parse_text(text, chars_per_page=20)
    for page in pages:
        assert page.strip()[-1] in '.!?'


# --- PDF parsing ---

def _make_pdf(pages: list[str]) -> bytes:
    """Helper: create minimal in-memory PDF with given pages."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text.strip():
            page.insert_text((50, 50), text)
    buf = doc.tobytes()
    doc.close()
    return buf


def test_parse_pdf_one_page_per_pdf_page():
    pdf = _make_pdf(["Page one content.", "Page two content."])
    pages = parse_pdf(pdf)
    assert len(pages) == 2


def test_parse_pdf_preserves_text():
    pdf = _make_pdf(["Hello from page one."])
    pages = parse_pdf(pdf)
    assert "Hello from page one" in pages[0]


def test_parse_pdf_skips_blank_pages():
    pdf = _make_pdf(["Content.", "", "More content."])
    pages = parse_pdf(pdf)
    assert len(pages) == 2  # blank page skipped
