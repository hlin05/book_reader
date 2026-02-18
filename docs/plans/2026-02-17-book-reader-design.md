# Book Reader App — Design Document

**Date:** 2026-02-17
**Status:** Approved

## Overview

A Streamlit app deployable on Streamlit Cloud that converts books to audio and plays them page by page. Supports text files, PDFs, and GitHub repository file selection as input.

## Requirements

- Accept books as: uploaded `.txt`, uploaded `.pdf`, or GitHub repo URL (with file picker)
- Convert each page to audio using TTS
- Play audio page by page with manual "Next/Prev" buttons
- Pre-generate next page audio in background while current page plays
- Delete played pages' audio files immediately to conserve memory
- Deploy to Streamlit Cloud (no persistent disk, secrets for API keys)

## TTS Engine

- Default: **gTTS** (free, no API key, works on Streamlit Cloud)
- Upgrade: **OpenAI TTS** (`tts-1` model) when `OPENAI_API_KEY` is present in `st.secrets`
- Detection is automatic — no code changes needed to switch

## Page Advancement

Manual buttons (Prev / Next) with background prefetch:
- When page N is displayed, page N+1 is already being generated in a background thread
- Status indicator shows "Next page: ✅ ready" or "⏳ generating..."
- Clicking Next: deletes page N-1 audio, advances to N+1 (instant, already cached), starts generating N+2

## Architecture

### Files
```
app.py            # Streamlit UI: sidebar input, main player area
book_parser.py    # Text/PDF/GitHub → pages[]
tts.py            # TTS wrapper (gTTS / OpenAI)
audio_manager.py  # Temp file lifecycle + background prefetch thread
requirements.txt
.streamlit/
  config.toml
  secrets.toml    # Local only, not committed
```

### Data Flow
```
User Input (sidebar)
  ├── Upload .txt / .pdf
  └── GitHub repo URL → file picker
         ↓
   book_parser.py → pages: list[str]
         ↓
   session_state.pages, current_page = 0
         ↓
   audio_manager: generate page 0 (blocking + spinner)
                  prefetch page 1 (background thread)
         ↓
   st.audio(current page bytes) + [◀ Prev] [Next ▶]
         ↓ on Next
   delete page N-1 file
   serve page N+1 from cache (instant)
   prefetch page N+2 in background
```

### Module API

**`book_parser.py`**
```python
parse_text(text: str, chars_per_page: int = 1500) -> list[str]
parse_pdf(file_bytes: bytes) -> list[str]
fetch_github_files(repo_url: str, token: str | None) -> list[dict]  # [{name, raw_url}]
fetch_github_file(raw_url: str) -> str
```

**`tts.py`**
```python
generate_audio(text: str) -> bytes  # MP3 bytes
```

**`audio_manager.py`**
```python
get_audio(page_idx: int) -> bytes | None
ensure_audio(page_idx: int, pages: list[str]) -> bytes   # blocking
prefetch(page_idx: int, pages: list[str]) -> None        # non-blocking thread
cleanup(page_idx: int) -> None                           # delete tmp file
```

### Session State Keys
| Key | Type | Purpose |
|-----|------|---------|
| `pages` | `list[str]` | All page text content |
| `current_page` | `int` | Index of currently displayed page |
| `audio_cache` | `dict[int, str]` | page idx → temp file path |
| `prefetch_thread` | `Thread \| None` | Background TTS thread |
| `book_loaded` | `bool` | Gates player UI |

## Deployment

- Streamlit Cloud: connect GitHub repo, set secrets in dashboard
- Optional secrets: `OPENAI_API_KEY`, `GITHUB_TOKEN` (for private repos)
- All file I/O uses `tempfile.NamedTemporaryFile(delete=False)` — no writes outside /tmp
