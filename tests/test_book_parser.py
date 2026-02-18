# tests/test_book_parser.py
import pytest
from book_parser import parse_text


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
