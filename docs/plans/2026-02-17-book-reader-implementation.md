# Book Reader App — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Streamlit app that converts books (text/PDF/GitHub) to audio and plays them page by page, with background pre-fetch of the next page and automatic cleanup of played audio files.

**Architecture:** Four modules — `book_parser.py` (text extraction/pagination), `tts.py` (TTS wrapper), `audio_manager.py` (temp file lifecycle + background prefetch thread), `app.py` (Streamlit UI). All audio uses `tempfile` (no persistent disk). gTTS by default, OpenAI TTS when `OPENAI_API_KEY` present in secrets.

**Tech Stack:** Python 3.10+, Streamlit, gTTS, PyMuPDF (fitz), requests, openai (optional), pytest, pytest-mock

---

### Task 1: Project Scaffolding

No TDD needed — config files only.

**Files:**
- Create: `requirements.txt`
- Create: `.streamlit/config.toml`
- Create: `.streamlit/secrets.toml` (gitignored, local only)
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create `requirements.txt`**

```
streamlit>=1.31.0
gTTS>=2.5.0
PyMuPDF>=1.24.0
requests>=2.31.0
openai>=1.12.0
pytest>=7.4.0
pytest-mock>=3.12.0
```

**Step 2: Create `.streamlit/config.toml`**

```toml
[theme]
primaryColor = "#4A90D9"
backgroundColor = "#FAFAFA"
secondaryBackgroundColor = "#F0F0F0"
textColor = "#1A1A1A"

[server]
maxUploadSize = 50
```

**Step 3: Create `.gitignore`**

```
.streamlit/secrets.toml
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

**Step 4: Create `.streamlit/secrets.toml` (local only, gitignored)**

```toml
# Uncomment to use OpenAI TTS (higher quality) instead of gTTS (free)
# OPENAI_API_KEY = "sk-..."

# Uncomment to access private GitHub repos
# GITHUB_TOKEN = "ghp_..."
```

**Step 5: Create `tests/conftest.py`**

This patches the `streamlit` module before any test file imports it, so modules like `tts.py` and `audio_manager.py` get the fake module when they do `import streamlit as st`.

```python
import sys
from unittest.mock import MagicMock
import pytest


class _FakeSessionState(dict):
    """Dict that supports both dict-style and attribute-style access, like st.session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def setdefault(self, key, default=None):
        return dict.setdefault(self, key, default)

    def __contains__(self, key):
        return dict.__contains__(self, key)


_fake_st = MagicMock()
_fake_st.session_state = _FakeSessionState()
_fake_st.secrets = {}
sys.modules['streamlit'] = _fake_st


@pytest.fixture(autouse=True)
def reset_streamlit_state():
    """Clear session state and secrets before each test."""
    _fake_st.session_state.clear()
    _fake_st.secrets = {}
    yield
    _fake_st.session_state.clear()
```

**Step 6: Create `tests/__init__.py`** (empty file)

**Step 7: Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 8: Commit**

```bash
git add requirements.txt .gitignore .streamlit/config.toml tests/
git commit -m "chore: project scaffolding and test infrastructure"
```

---

### Task 2: book_parser.py — Text Parsing

**Files:**
- Create: `tests/test_book_parser.py`
- Create: `book_parser.py`

**Step 1: Write failing tests for `parse_text`**

```python
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
```

**Step 2: Run to confirm failure**

```bash
pytest tests/test_book_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'book_parser'`

**Step 3: Implement `parse_text` in `book_parser.py`**

```python
import re
import requests
import fitz  # PyMuPDF


def parse_text(text: str, chars_per_page: int = 1500) -> list[str]:
    """Split text into pages at sentence boundaries, targeting chars_per_page characters each."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    pages, current, current_len = [], [], 0

    for sentence in sentences:
        if current and current_len + len(sentence) > chars_per_page:
            pages.append(' '.join(current))
            current, current_len = [sentence], len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence) + 1

    if current:
        pages.append(' '.join(current))

    return pages
```

**Step 4: Run tests**

```bash
pytest tests/test_book_parser.py -v
```

Expected: 4 PASS

**Step 5: Commit**

```bash
git add book_parser.py tests/test_book_parser.py
git commit -m "feat: add text parsing to book_parser"
```

---

### Task 3: book_parser.py — PDF Parsing

**Files:**
- Modify: `tests/test_book_parser.py`
- Modify: `book_parser.py`

**Step 1: Add failing tests for `parse_pdf`**

Add these imports and tests to `tests/test_book_parser.py`:

```python
import fitz
from book_parser import parse_pdf


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
```

**Step 2: Run to confirm failure**

```bash
pytest tests/test_book_parser.py::test_parse_pdf_one_page_per_pdf_page -v
```

Expected: `ImportError: cannot import name 'parse_pdf'`

**Step 3: Implement `parse_pdf`**

Add to `book_parser.py`:

```python
def parse_pdf(file_bytes: bytes) -> list[str]:
    """Extract text from PDF bytes. Returns one string per non-blank PDF page."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text().strip()
        if text:
            pages.append(text)
    doc.close()
    return pages
```

**Step 4: Run all tests**

```bash
pytest tests/test_book_parser.py -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add book_parser.py tests/test_book_parser.py
git commit -m "feat: add PDF parsing to book_parser"
```

---

### Task 4: book_parser.py — GitHub Integration

**Files:**
- Modify: `tests/test_book_parser.py`
- Modify: `book_parser.py`

**Step 1: Add failing tests for GitHub functions**

Add these imports and tests to `tests/test_book_parser.py`:

```python
from unittest.mock import MagicMock
from book_parser import fetch_github_files, fetch_github_file


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
```

**Step 2: Run to confirm failure**

```bash
pytest tests/test_book_parser.py::test_fetch_github_files_returns_only_md_and_txt -v
```

Expected: `ImportError: cannot import name 'fetch_github_files'`

**Step 3: Implement GitHub functions**

Add to `book_parser.py`:

```python
def fetch_github_files(repo_url: str, token: str | None = None) -> list[dict]:
    """List .md and .txt files in a GitHub repo. Returns [{name, raw_url}]."""
    parts = repo_url.rstrip('/').split('/')
    owner, repo = parts[-2], parts[-1]

    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'

    resp = requests.get(f'https://api.github.com/repos/{owner}/{repo}', headers=headers)
    resp.raise_for_status()
    default_branch = resp.json()['default_branch']

    resp = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1',
        headers=headers,
    )
    resp.raise_for_status()

    files = []
    for item in resp.json().get('tree', []):
        if item['type'] == 'blob' and item['path'].endswith(('.md', '.txt')):
            raw_url = (
                f'https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{item["path"]}'
            )
            files.append({'name': item['path'], 'raw_url': raw_url})
    return files


def fetch_github_file(raw_url: str, token: str | None = None) -> str:
    """Fetch raw text content of a file from GitHub."""
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    resp = requests.get(raw_url, headers=headers)
    resp.raise_for_status()
    return resp.text
```

**Step 4: Run all tests**

```bash
pytest tests/test_book_parser.py -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add book_parser.py tests/test_book_parser.py
git commit -m "feat: add GitHub file fetching to book_parser"
```

---

### Task 5: tts.py

**Files:**
- Create: `tests/test_tts.py`
- Create: `tts.py`

**Step 1: Write failing tests**

```python
# tests/test_tts.py
import streamlit as st


def test_uses_gtts_when_no_api_key(mocker):
    st.secrets = {}  # no OPENAI_API_KEY

    mock_tts_instance = mocker.MagicMock()
    mock_tts_instance.write_to_fp.side_effect = lambda fp: fp.write(b'fake-mp3')
    mocker.patch('gtts.gTTS', return_value=mock_tts_instance)

    from tts import generate_audio
    result = generate_audio("Hello world")

    assert isinstance(result, bytes)
    assert b'fake-mp3' in result


def test_uses_openai_when_api_key_present(mocker):
    st.secrets = {'OPENAI_API_KEY': 'sk-fake'}

    mock_response = mocker.MagicMock()
    mock_response.content = b'openai-mp3'
    mock_client = mocker.MagicMock()
    mock_client.audio.speech.create.return_value = mock_response
    mocker.patch('openai.OpenAI', return_value=mock_client)

    from tts import generate_audio
    result = generate_audio("Hello world")

    assert result == b'openai-mp3'
```

**Step 2: Run to confirm failure**

```bash
pytest tests/test_tts.py -v
```

Expected: `ModuleNotFoundError: No module named 'tts'`

**Step 3: Implement `tts.py`**

```python
import io
import streamlit as st


def generate_audio(text: str) -> bytes:
    """Convert text to MP3 bytes. Uses OpenAI TTS if OPENAI_API_KEY in secrets, else gTTS."""
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if api_key:
        return _openai_tts(text, api_key)
    return _gtts(text)


def _gtts(text: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang='en').write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def _openai_tts(text: str, api_key: str) -> bytes:
    from openai import OpenAI
    response = OpenAI(api_key=api_key).audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    return response.content
```

**Step 4: Run tests**

```bash
pytest tests/test_tts.py -v
```

Expected: 2 PASS

**Step 5: Commit**

```bash
git add tts.py tests/test_tts.py
git commit -m "feat: add TTS module with gTTS/OpenAI auto-detection"
```

---

### Task 6: audio_manager.py

**Files:**
- Create: `tests/test_audio_manager.py`
- Create: `audio_manager.py`

**Step 1: Write failing tests**

```python
# tests/test_audio_manager.py
import os
import time
import streamlit as st


def test_ensure_audio_generates_and_caches(mocker):
    mocker.patch('tts.generate_audio', return_value=b'fake-audio')
    import audio_manager

    pages = ["Page one text."]
    result = audio_manager.ensure_audio(0, pages)

    assert result == b'fake-audio'
    assert 0 in st.session_state['audio_cache']
    # Temp file should exist on disk
    assert os.path.exists(st.session_state['audio_cache'][0])


def test_ensure_audio_uses_cache_on_second_call(mocker):
    call_count = {'n': 0}

    def counting_tts(text):
        call_count['n'] += 1
        return b'audio'

    mocker.patch('tts.generate_audio', side_effect=counting_tts)
    import audio_manager

    pages = ["Some text."]
    audio_manager.ensure_audio(0, pages)
    audio_manager.ensure_audio(0, pages)

    assert call_count['n'] == 1  # second call should not regenerate


def test_cleanup_deletes_temp_file_and_removes_from_cache(mocker):
    mocker.patch('tts.generate_audio', return_value=b'audio')
    import audio_manager

    audio_manager.ensure_audio(0, ["Text."])
    path = st.session_state['audio_cache'][0]
    assert os.path.exists(path)

    audio_manager.cleanup(0)

    assert not os.path.exists(path)
    assert 0 not in st.session_state['audio_cache']


def test_prefetch_populates_cache_in_background(mocker):
    mocker.patch('tts.generate_audio', return_value=b'prefetched')
    import audio_manager

    pages = ["Page one.", "Page two."]
    audio_manager.prefetch(1, pages)

    # Wait up to 5 seconds for background thread
    deadline = time.time() + 5
    while not audio_manager.is_prefetch_ready(1):
        assert time.time() < deadline, "Prefetch timed out after 5s"
        time.sleep(0.05)

    assert audio_manager.get_audio(1) == b'prefetched'


def test_prefetch_ignores_out_of_bounds_index(mocker):
    mocker.patch('tts.generate_audio', return_value=b'audio')
    import audio_manager

    # Should not raise
    audio_manager.prefetch(99, ["Only one page."])
    audio_manager.prefetch(-1, ["Only one page."])
```

**Step 2: Run to confirm failure**

```bash
pytest tests/test_audio_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'audio_manager'`

**Step 3: Implement `audio_manager.py`**

```python
import os
import tempfile
import threading
import streamlit as st
import tts


def _init_state():
    st.session_state.setdefault('audio_cache', {})
    st.session_state.setdefault('prefetch_thread', None)
    st.session_state.setdefault('prefetch_idx', None)


def get_audio(page_idx: int) -> bytes | None:
    """Return cached MP3 bytes for page_idx, or None if not ready."""
    _init_state()
    path = st.session_state['audio_cache'].get(page_idx)
    if path and os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    return None


def ensure_audio(page_idx: int, pages: list[str]) -> bytes:
    """Return MP3 bytes for page_idx, generating synchronously if not cached."""
    _init_state()
    cached = get_audio(page_idx)
    if cached:
        return cached

    audio_bytes = tts.generate_audio(pages[page_idx])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    tmp.write(audio_bytes)
    tmp.close()
    st.session_state['audio_cache'][page_idx] = tmp.name
    return audio_bytes


def prefetch(page_idx: int, pages: list[str]) -> None:
    """Start a background thread to generate audio for page_idx if not already cached."""
    _init_state()
    if page_idx < 0 or page_idx >= len(pages):
        return
    if get_audio(page_idx):
        return
    # Don't start a duplicate thread for the same index
    if st.session_state['prefetch_idx'] == page_idx:
        t = st.session_state['prefetch_thread']
        if t and t.is_alive():
            return

    def _worker():
        audio_bytes = tts.generate_audio(pages[page_idx])
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tmp.write(audio_bytes)
        tmp.close()
        st.session_state['audio_cache'][page_idx] = tmp.name

    t = threading.Thread(target=_worker, daemon=True)
    st.session_state['prefetch_thread'] = t
    st.session_state['prefetch_idx'] = page_idx
    t.start()


def is_prefetch_ready(page_idx: int) -> bool:
    """Return True if audio for page_idx is cached and its file exists."""
    return get_audio(page_idx) is not None


def cleanup(page_idx: int) -> None:
    """Delete temp file for page_idx and remove from cache."""
    _init_state()
    path = st.session_state['audio_cache'].pop(page_idx, None)
    if path and os.path.exists(path):
        os.unlink(path)
```

**Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add audio_manager.py tests/test_audio_manager.py
git commit -m "feat: add audio_manager with background prefetch and temp file cleanup"
```

---

### Task 7: app.py — Streamlit UI

No automated tests for the Streamlit UI. Verify manually.

**Files:**
- Create: `app.py`

**Step 1: Create `app.py`**

```python
import streamlit as st
from book_parser import parse_text, parse_pdf, fetch_github_files, fetch_github_file
from audio_manager import ensure_audio, prefetch, is_prefetch_ready, cleanup

st.set_page_config(page_title="Book Reader", page_icon="📖", layout="wide")


def _init():
    defaults = {
        'pages': [],
        'current_page': 0,
        'book_loaded': False,
        'audio_cache': {},
        'prefetch_thread': None,
        'prefetch_idx': None,
        'gh_files': [],
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _load_book(pages: list[str]):
    """Reset all state and load a new book."""
    for idx in list(st.session_state.audio_cache.keys()):
        cleanup(idx)
    st.session_state.pages = pages
    st.session_state.current_page = 0
    st.session_state.book_loaded = True
    st.session_state.audio_cache = {}
    st.session_state.prefetch_thread = None
    st.session_state.prefetch_idx = None


def _sidebar():
    with st.sidebar:
        st.title("📖 Book Reader")
        source = st.radio("Input source", ["Upload file", "GitHub repo"], key="source_radio")

        if source == "Upload file":
            uploaded = st.file_uploader("Upload .txt or .pdf", type=['txt', 'pdf'])
            if uploaded and st.button("Load Book", key="load_file_btn"):
                with st.spinner("Parsing book..."):
                    if uploaded.name.lower().endswith('.pdf'):
                        pages = parse_pdf(uploaded.read())
                    else:
                        pages = parse_text(uploaded.read().decode('utf-8'))
                if not pages:
                    st.error("No readable pages found.")
                else:
                    _load_book(pages)
                    st.rerun()

        else:  # GitHub
            repo_url = st.text_input(
                "GitHub repo URL", placeholder="https://github.com/user/repo"
            )
            token = st.secrets.get("GITHUB_TOKEN", None)

            if repo_url and st.button("List files", key="list_gh_btn"):
                with st.spinner("Fetching file list..."):
                    try:
                        files = fetch_github_files(repo_url, token)
                        st.session_state.gh_files = files
                    except Exception as e:
                        st.error(f"Could not fetch repo: {e}")

            if st.session_state.gh_files:
                options = {f['name']: f['raw_url'] for f in st.session_state.gh_files}
                selected = st.selectbox("Select file to read", list(options.keys()))
                if st.button("Load file", key="load_gh_btn"):
                    with st.spinner("Fetching and parsing..."):
                        try:
                            text = fetch_github_file(options[selected], token)
                            pages = parse_text(text)
                            _load_book(pages)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not load file: {e}")


def _player():
    pages = st.session_state.pages
    idx = st.session_state.current_page
    total = len(pages)

    st.markdown(f"### Page {idx + 1} / {total}")
    st.progress((idx + 1) / total)

    with st.expander("Page text", expanded=True):
        st.write(pages[idx])

    with st.spinner("Generating audio..."):
        audio_bytes = ensure_audio(idx, pages)

    st.audio(audio_bytes, format='audio/mp3')

    # Kick off background prefetch for next page
    if idx + 1 < total:
        prefetch(idx + 1, pages)

    # Show prefetch status
    if idx + 1 < total:
        if is_prefetch_ready(idx + 1):
            st.success("Next page audio: ready ✅")
        else:
            st.info("Next page audio: generating... ⏳")

    # Navigation buttons
    col1, col2, col3 = st.columns([1, 6, 1])
    with col1:
        if idx > 0 and st.button("◀ Prev", key="prev_btn"):
            st.session_state.current_page -= 1
            st.rerun()
    with col3:
        if idx + 1 < total and st.button("Next ▶", key="next_btn"):
            cleanup(idx - 1)  # delete the page before current
            st.session_state.current_page += 1
            st.rerun()

    if idx + 1 >= total:
        st.balloons()
        st.success("You've reached the end of the book! 🎉")


def main():
    _init()
    _sidebar()

    if not st.session_state.book_loaded:
        st.title("📖 Book Reader")
        st.markdown(
            "Upload a `.txt` or `.pdf` file, or paste a GitHub repo URL in the sidebar to begin."
        )
    else:
        _player()


if __name__ == "__main__":
    main()
```

**Step 2: Run all tests to make sure nothing broke**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 3: Run the app manually**

```bash
streamlit run app.py
```

Manual verification checklist:
- [ ] Upload a `.txt` file → pages parse and audio plays
- [ ] Upload a `.pdf` → pages split by PDF page, audio plays
- [ ] Enter a GitHub repo URL → file list appears → load a file → audio plays
- [ ] Click Next → "Next page: ready ✅" appears quickly (audio pre-generated)
- [ ] Audio for the previous page is cleaned up (check that temp files don't accumulate)
- [ ] Reaching the last page shows "end of book" message and balloons

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add Streamlit app UI with page player and GitHub input"
```

---

### Task 8: README and Deployment

**Files:**
- Create: `README.md`

**Step 1: Create `README.md`**

```markdown
# Book Reader

A Streamlit app that converts books to audio and plays them page by page.

## Supported Inputs
- Upload `.txt` or `.pdf` files (up to 50 MB)
- GitHub repo URL — browse and pick any `.md` or `.txt` file from the repo

## How It Works
- Each page's audio is generated on demand using text-to-speech
- The next page's audio is pre-generated in the background while you listen
- Played pages' audio files are deleted automatically to conserve memory

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optional Secrets

Create `.streamlit/secrets.toml` (this file is gitignored):

```toml
# Use OpenAI TTS for higher-quality audio (costs ~$0.015/1K characters)
OPENAI_API_KEY = "sk-..."

# Access private GitHub repositories
GITHUB_TOKEN = "ghp_..."
```

## Deploying to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → connect the repo → deploy
3. Optionally add secrets in the app's **Settings → Secrets** section
```

**Step 2: Run all tests one final time**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: add README with local and cloud deployment instructions"
```

---

**Implementation complete.** All modules are covered by tests. The app is ready for `streamlit run app.py` locally and deployment to Streamlit Cloud.
