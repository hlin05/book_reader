import os
import tempfile
import threading
import streamlit as st
import tts


def _init_state():
    st.session_state.setdefault('audio_cache', {})
    st.session_state.setdefault('prefetch_thread', None)
    st.session_state.setdefault('prefetch_idx', None)
    st.session_state.setdefault('_book_id', 0)


def get_audio(page_idx: int) -> bytes | None:
    """Return cached MP3 bytes for page_idx, or None if not ready."""
    _init_state()
    path = st.session_state['audio_cache'].get(page_idx)
    if path and os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    return None


def ensure_audio(page_idx: int, pages: list[str], lang: str = 'en', speed: float = 1.0) -> bytes:
    """Return MP3 bytes for page_idx, generating synchronously if not cached."""
    _init_state()
    cached = get_audio(page_idx)
    if cached:
        return cached

    audio_bytes = tts.generate_audio(pages[page_idx], lang=lang, speed=speed)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    tmp.write(audio_bytes)
    tmp.close()
    st.session_state['audio_cache'][page_idx] = tmp.name
    return audio_bytes


def prefetch(page_idx: int, pages: list[str], lang: str = 'en', speed: float = 1.0) -> None:
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

    # Resolve values in the main thread — background threads have no ScriptRunContext
    # so st.session_state and st.secrets are inaccessible from them.
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    # Capture the dict object directly. _worker writes into it without touching
    # st.session_state. If the book is reloaded, _load_book replaces
    # st.session_state['audio_cache'] with a new dict; stale workers then write
    # into the orphaned old dict — harmless, and the temp file is a minor leak.
    audio_cache = st.session_state['audio_cache']

    def _worker():
        audio_bytes = tts.generate_audio(pages[page_idx], api_key=api_key, lang=lang, speed=speed)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        tmp.write(audio_bytes)
        tmp.close()
        audio_cache[page_idx] = tmp.name  # dict write is thread-safe in CPython (GIL)

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
