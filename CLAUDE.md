# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Streamlit app (hosted on Streamlit Cloud) that converts books to audio and plays them page by page. Supports text files, PDFs, and GitHub repository URLs as input. Uses streaming audio architecture: while a page plays, the next page's audio is pre-generated in the background; played pages are immediately deleted to conserve memory.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
streamlit run app.py

# Run with custom port
streamlit run app.py --server.port 8502
```

## Architecture

### File Structure (intended)
```
app.py                 # Main Streamlit entry point
book_parser.py         # Extracts and paginates content from text/PDF/GitHub
tts.py                 # Text-to-speech conversion wrapper
audio_manager.py       # Audio lifecycle: generate, queue, delete played files
requirements.txt
.streamlit/
  config.toml          # Streamlit config (theme, server settings)
  secrets.toml         # Local secrets (not committed); GitHub token, TTS API keys
```

### Core Data Flow
1. User provides input (upload text/PDF or paste GitHub URL)
2. `book_parser.py` extracts raw text and splits into pages
3. `audio_manager.py` manages a rolling window of audio files: only `[current, next]` pages exist on disk at any time
4. TTS for page `N+1` is triggered in a background thread as page `N` begins playing
5. Once page `N` finishes playing, its temp audio file is deleted

### Page Definition
- **PDF**: one page = one PDF page
- **Text**: one page = configurable chunk (default ~1500 characters), split at sentence boundaries
- **GitHub repo**: fetches README or a specified file, then treats as text

### Key Technical Decisions

**TTS Engine**: Use `gTTS` (Google Text-to-Speech) as default — no API key required, works on Streamlit Cloud. Optionally support OpenAI TTS (`openai` library) via `st.secrets["OPENAI_API_KEY"]`.

**Audio Playback in Streamlit**: Streamlit's `st.audio()` widget does not support true streaming. Workaround: write audio to a `tempfile.NamedTemporaryFile`, pass the bytes or file path to `st.audio()`, and use `st.session_state` + `st.rerun()` to advance pages.

**Background Pre-fetching**: Use `threading.Thread` to generate TTS for the next page while the current plays. Store the thread and result in `st.session_state`.

**Temp File Management**: All audio files are `tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")`. The audio manager tracks paths in session state and deletes the previous page's file after advancing.

**Streamlit Cloud Constraints**:
- No persistent disk — all files must use `tempfile`
- No background processes survive reruns — pre-fetch threads must be re-checked on each rerun
- Secrets via `.streamlit/secrets.toml` locally; Streamlit Cloud secrets UI in production
- GitHub token (optional, for private repos): `st.secrets.get("GITHUB_TOKEN")`

### Session State Keys
| Key | Purpose |
|-----|---------|
| `pages` | List of text strings, one per page |
| `current_page` | Index of currently playing page |
| `audio_paths` | Dict mapping page index → temp file path |
| `prefetch_thread` | Background thread for next-page TTS |
| `book_loaded` | Boolean, gates playback UI |

### Dependencies (requirements.txt)
```
streamlit
gTTS
PyMuPDF          # PDF parsing (imported as fitz)
requests         # GitHub raw file fetching
openai           # Optional: higher-quality TTS
```

## Streamlit Cloud Deployment

Deploy from GitHub. Set any secrets (e.g., `OPENAI_API_KEY`) in the app's Secrets section in the Streamlit Cloud dashboard. The app must not write outside of `tempfile` directories.
