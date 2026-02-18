# tests/test_book_parser.py
import pytest
import fitz
from unittest.mock import MagicMock
from book_parser import parse_text, parse_pdf, fetch_github_files, fetch_github_file


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


# --- GitHub integration ---

def _mock_github_responses(mocker, default_branch, tree_items):
    """Helper: mock the two GitHub API calls made by fetch_github_files."""
    repo_resp = MagicMock()
    repo_resp.json.return_value = {'default_branch': default_branch}
    repo_resp.raise_for_status.return_value = None

    tree_resp = MagicMock()
    tree_resp.json.return_value = {'tree': tree_items}
    tree_resp.raise_for_status.return_value = None

    mocker.patch('requests.get', side_effect=[repo_resp, tree_resp])


def test_fetch_github_files_returns_only_md_and_txt(mocker):
    _mock_github_responses(mocker, 'main', [
        {'type': 'blob', 'path': 'README.md'},
        {'type': 'blob', 'path': 'src/script.py'},    # excluded
        {'type': 'blob', 'path': 'docs/chapter1.txt'},
        {'type': 'tree', 'path': 'src'},               # excluded (directory)
    ])
    files = fetch_github_files('https://github.com/user/repo')
    names = [f['name'] for f in files]
    assert 'README.md' in names
    assert 'docs/chapter1.txt' in names
    assert 'src/script.py' not in names
    assert 'src' not in names


def test_fetch_github_files_constructs_correct_raw_url(mocker):
    _mock_github_responses(mocker, 'main', [
        {'type': 'blob', 'path': 'README.md'},
    ])
    files = fetch_github_files('https://github.com/user/repo')
    assert files[0]['raw_url'] == 'https://raw.githubusercontent.com/user/repo/main/README.md'


def test_fetch_github_file_returns_text(mocker):
    mock_resp = MagicMock()
    mock_resp.text = "# My Book\n\nHello world."
    mock_resp.raise_for_status.return_value = None
    mocker.patch('requests.get', return_value=mock_resp)

    text = fetch_github_file('https://raw.githubusercontent.com/user/repo/main/README.md')
    assert "Hello world" in text
