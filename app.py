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
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


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
            cleanup(idx)  # page just played; going back means we're done with it
            st.session_state.current_page -= 1
            st.rerun()
    with col3:
        if idx + 1 < total and st.button("Next ▶", key="next_btn"):
            cleanup(idx)  # page just finished playing
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
