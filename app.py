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
        '_book_id': 0,
        'bookmarks': [],
        'advance_mode': 'manual',
        'lang': 'en',
        'speed': 1.0,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _on_speed_change():
    """Clear audio cache when speed changes so next render regenerates at new speed."""
    for idx in list(st.session_state.audio_cache.keys()):
        cleanup(idx)
    st.session_state.prefetch_thread = None
    st.session_state.prefetch_idx = None


def _load_book(pages: list[str]):
    """Reset all state and load a new book."""
    # Increment _book_id first so any in-flight prefetch thread discards its result
    st.session_state['_book_id'] = st.session_state.get('_book_id', 0) + 1
    for idx in list(st.session_state.audio_cache.keys()):
        cleanup(idx)
    st.session_state.pages = pages
    st.session_state.current_page = 0
    st.session_state.book_loaded = True
    st.session_state.audio_cache = {}
    st.session_state.prefetch_thread = None
    st.session_state.prefetch_idx = None
    st.session_state.bookmarks = []


def _jump_to(page_idx: int):
    """Navigate to page_idx, cleaning up the current page's audio."""
    cleanup(st.session_state.current_page)
    st.session_state.current_page = page_idx
    st.rerun()


def _sidebar():
    with st.sidebar:
        st.title("📖 Book Reader")
        st.session_state.lang = st.radio(
            "Language",
            options=["en", "zh"],
            format_func=lambda x: "English" if x == "en" else "Chinese (中文)",
            key="lang_radio",
            index=0 if st.session_state.lang == "en" else 1,
        )
        st.select_slider(
            "Reading speed",
            options=[0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
            value=st.session_state.speed,
            format_func=lambda x: f"{x}×",
            key="speed",
            on_change=_on_speed_change,
        )
        source = st.radio("Input source", ["Upload file", "GitHub repo"], key="source_radio")

        if source == "Upload file":
            uploaded = st.file_uploader("Upload .txt or .pdf", type=['txt', 'pdf'])
            if uploaded and st.button("Load Book", key="load_file_btn"):
                with st.spinner("Parsing book..."):
                    if uploaded.name.lower().endswith('.pdf'):
                        pages = parse_pdf(uploaded.read(), lang=st.session_state.lang)
                    else:
                        pages = parse_text(uploaded.read().decode('utf-8'), lang=st.session_state.lang)
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
                st.caption(f"`{selected}`")
                if st.button("Load file", key="load_gh_btn"):
                    with st.spinner("Fetching and parsing..."):
                        try:
                            text = fetch_github_file(options[selected], token)
                            pages = parse_text(text, lang=st.session_state.lang)
                            _load_book(pages)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not load file: {e}")

        # Navigation section (only shown when a book is loaded)
        if st.session_state.book_loaded:
            st.divider()
            st.subheader("Navigation")

            # Advance mode
            st.session_state.advance_mode = st.radio(
                "Page advance",
                options=["manual", "auto"],
                format_func=lambda x: "Manual (Next button)" if x == "manual" else "Auto-advance",
                key="advance_mode_radio",
                index=0 if st.session_state.advance_mode == "manual" else 1,
            )

            # Page jump
            total = len(st.session_state.pages)
            idx = st.session_state.current_page
            col_input, col_btn = st.columns([3, 1])
            with col_input:
                target = st.number_input(
                    "Jump to page",
                    min_value=1,
                    max_value=total,
                    value=idx + 1,
                    step=1,
                    key="page_jump_input",
                )
            with col_btn:
                st.write("")  # vertical alignment spacer
                if st.button("Go", key="page_jump_btn"):
                    _jump_to(int(target) - 1)

            # Bookmark list
            st.markdown("**Bookmarks**")
            bookmarks = st.session_state.bookmarks
            if not bookmarks:
                st.caption("No bookmarks yet.")
            else:
                for i, bm in enumerate(bookmarks):
                    col_label, col_go, col_del = st.columns([4, 1, 1])
                    with col_label:
                        st.write(f"{bm['label']} (p.{bm['page'] + 1})")
                    with col_go:
                        if st.button("Go", key=f"bm_go_{i}"):
                            _jump_to(bm['page'])
                    with col_del:
                        if st.button("✕", key=f"bm_del_{i}"):
                            st.session_state.bookmarks.pop(i)
                            st.rerun()

            # Add bookmark form
            with st.expander("+ Add bookmark", expanded=False):
                label = st.text_input(
                    "Label",
                    placeholder=f"e.g. Chapter {idx + 1}",
                    key="bm_label_input",
                )
                if st.button(f"Bookmark page {idx + 1}", key="bm_add_btn"):
                    if not label.strip():
                        st.warning("Please enter a label.")
                    else:
                        st.session_state.bookmarks.append(
                            {"label": label.strip(), "page": idx}
                        )
                        st.rerun()


def _player():
    pages = st.session_state.pages
    idx = st.session_state.current_page
    total = len(pages)

    st.markdown(f"### Page {idx + 1} / {total}")
    st.progress((idx + 1) / total)

    with st.expander("Page text", expanded=True):
        st.write(pages[idx])

    with st.spinner("Generating audio..."):
        audio_bytes = ensure_audio(idx, pages, lang=st.session_state.lang, speed=st.session_state.speed)

    st.audio(audio_bytes, format='audio/mp3')

    # Audio-end auto-advance: poll every 1s and check if the audio element has ended
    if st.session_state.advance_mode == 'auto' and idx + 1 < total:
        from streamlit_autorefresh import st_autorefresh
        from streamlit_js_eval import streamlit_js_eval
        st_autorefresh(interval=1000, key="audio_end_poll")
        audio_ended = streamlit_js_eval(
            js_expressions="document.querySelector('audio')?.ended === true",
            key=f"audio_end_{idx}",
        )
        if audio_ended:
            cleanup(idx)
            st.session_state.current_page += 1
            st.rerun()

    # Kick off background prefetch for next page
    if idx + 1 < total:
        prefetch(idx + 1, pages, lang=st.session_state.lang, speed=st.session_state.speed)

    # Show prefetch status
    if idx + 1 < total:
        if is_prefetch_ready(idx + 1):
            st.success("Next page audio: ready ✅")
        else:
            st.info("Next page audio: generating... ⏳")

    # Navigation buttons (always show Prev; Next only in manual mode)
    col1, col2, col3 = st.columns([1, 6, 1])
    with col1:
        if idx > 0 and st.button("◀ Prev", key="prev_btn"):
            cleanup(idx)
            st.session_state.current_page -= 1
            st.rerun()
    with col3:
        if st.session_state.advance_mode == 'manual' and idx + 1 < total:
            if st.button("Next ▶", key="next_btn"):
                cleanup(idx)
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
