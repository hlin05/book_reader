# Page Jump & Bookmarks — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a sidebar Navigation section with a page-jump control, named bookmarks, and a choice of manual or auto-advance page mode.

**Architecture:** All changes are in `app.py` only. Bookmarks live in `st.session_state.bookmarks`. A `_jump_to()` helper handles navigation. Auto-advance uses `streamlit-autorefresh` to rerun every 2 s and compares elapsed time against an estimated page duration (~900 chars/min). No modules, no tests change.

**Tech Stack:** Streamlit session state, `streamlit-autorefresh`, `st.number_input`, `st.button`, `st.columns`

---

### Task 1: Add bookmarks to session state and implement `_jump_to`

**Files:**
- Modify: `app.py`

**Step 1: Add `bookmarks` to `_init()` defaults**

In `_init()`, add `'bookmarks': []` to the `defaults` dict:

```python
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
        'bookmarks': [],      # <-- add this line
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)
```

**Step 2: Clear bookmarks in `_load_book()`**

Add `st.session_state.bookmarks = []` at the end of `_load_book()`:

```python
def _load_book(pages: list[str]):
    """Reset all state and load a new book."""
    st.session_state['_book_id'] = st.session_state.get('_book_id', 0) + 1
    for idx in list(st.session_state.audio_cache.keys()):
        cleanup(idx)
    st.session_state.pages = pages
    st.session_state.current_page = 0
    st.session_state.book_loaded = True
    st.session_state.audio_cache = {}
    st.session_state.prefetch_thread = None
    st.session_state.prefetch_idx = None
    st.session_state.bookmarks = []    # <-- add this line
```

**Step 3: Add `_jump_to()` helper after `_load_book()`**

Insert this new function between `_load_book` and `_sidebar`:

```python
def _jump_to(page_idx: int):
    """Navigate to page_idx, cleaning up the current page's audio."""
    cleanup(st.session_state.current_page)
    st.session_state.current_page = page_idx
    st.rerun()
```

**Step 4: Verify tests still pass**

```bash
python -m pytest C:/Users/taoga/projects/book_reader/tests/ -v
```

Expected: 17 passed

**Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add bookmarks state and _jump_to helper"
```

---

### Task 2: Add Navigation section to sidebar

**Files:**
- Modify: `app.py`

**Step 1: Add the Navigation section at the end of `_sidebar()`**

After the GitHub block (after the closing `except` block), still inside the `with st.sidebar:` block, add:

```python
        # Navigation section (only shown when a book is loaded)
        if st.session_state.book_loaded:
            st.divider()
            st.subheader("Navigation")

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
```

**Step 2: Verify tests still pass**

```bash
python -m pytest C:/Users/taoga/projects/book_reader/tests/ -v
```

Expected: 17 passed

**Step 3: Manual verification**

Start the app:
```bash
python -m streamlit run C:/Users/taoga/projects/book_reader/app.py --server.headless true
```

Checklist:
- [ ] Load a book — Navigation section appears in sidebar
- [ ] Page jump: change number to 5, click Go → jumps to page 5
- [ ] Page jump: value updates as you navigate with Prev/Next buttons
- [ ] Add bookmark: open expander, enter label "Chapter 1", click button → bookmark appears in list
- [ ] Add bookmark with empty label → shows warning, does not add
- [ ] Bookmark Go button → jumps to that page
- [ ] Bookmark ✕ button → removes that bookmark
- [ ] Load a new book → bookmarks list is cleared

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add page jump and bookmarks to sidebar navigation"
```

---

### Task 3: Auto-advance mode

**Files:**
- Modify: `requirements.txt`
- Modify: `app.py`

**Context:** Streamlit's `st.audio()` fires no events when audio ends, so there is no way to detect playback completion. Instead, we estimate page duration from text length and use `streamlit-autorefresh` to trigger a rerun every 2 seconds, checking if enough time has elapsed to advance.

Duration formula: `estimated_seconds = len(page_text) / 15`
(900 chars/min ÷ 60 = 15 chars/sec — a reasonable gTTS speaking rate)

**Step 1: Add `streamlit-autorefresh` to `requirements.txt`**

Append to `requirements.txt`:
```
streamlit-autorefresh>=0.0.1
```

Install it:
```bash
pip install streamlit-autorefresh
```

**Step 2: Add advance mode and timer keys to `_init()` defaults**

Add these three keys to the `defaults` dict in `_init()`:

```python
        'advance_mode': 'manual',     # 'manual' or 'auto'
        '_last_timed_page': -1,       # tracks which page the timer was started for
        'page_start_time': 0.0,       # wall-clock time when current page became ready
```

**Step 3: Reset timer state in `_load_book()`**

Add these lines at the end of `_load_book()` (after `st.session_state.bookmarks = []`):

```python
    st.session_state['_last_timed_page'] = -1
    st.session_state['page_start_time'] = 0.0
```

**Step 4: Add advance mode radio to Navigation section in `_sidebar()`**

Inside the `if st.session_state.book_loaded:` block in `_sidebar()`, add a radio button before the page jump widget. Replace the current `st.subheader("Navigation")` line with:

```python
            st.subheader("Navigation")

            # Advance mode toggle
            st.session_state.advance_mode = st.radio(
                "Page advance",
                options=["manual", "auto"],
                format_func=lambda x: "Manual (Next button)" if x == "manual" else "Auto-advance",
                key="advance_mode_radio",
                index=0 if st.session_state.advance_mode == "manual" else 1,
            )
```

**Step 5: Add auto-advance logic to `_player()`, right after `st.audio()`**

After the `st.audio(audio_bytes, format='audio/mp3')` line, add:

```python
    # Auto-advance mode
    if st.session_state.advance_mode == 'auto' and idx + 1 < total:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2000, key="auto_advance_tick")

        # Start the page timer the first time this page is displayed (after audio is ready)
        if st.session_state.get('_last_timed_page') != idx:
            st.session_state['page_start_time'] = time.time()
            st.session_state['_last_timed_page'] = idx

        elapsed = time.time() - st.session_state['page_start_time']
        estimated = len(pages[idx]) / 15  # ~900 chars/min
        remaining = max(0, int(estimated - elapsed))
        st.info(f"Auto-advancing in {remaining}s...")

        if elapsed >= estimated:
            cleanup(idx)
            st.session_state.current_page += 1
            st.rerun()
```

Also add `import time` at the top of `app.py` (after the existing imports).

**Step 6: Verify tests still pass**

```bash
python -m pytest C:/Users/taoga/projects/book_reader/tests/ -v
```

Expected: 17 passed

**Step 7: Manual verification**

Checklist:
- [ ] Load a book, set mode to "Auto-advance" → countdown appears below audio player
- [ ] Countdown counts down and page advances automatically
- [ ] Switch to "Manual" → countdown disappears, Next button appears again
- [ ] Auto mode at last page → no countdown (no more pages)
- [ ] Advance mode choice persists while navigating between pages

**Step 8: Commit**

```bash
git add requirements.txt app.py
git commit -m "feat: add auto-advance mode with configurable per-page timer"
```
