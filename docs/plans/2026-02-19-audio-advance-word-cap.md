# Audio-End Auto-Advance + 1000-Word Page Cap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace timer-based auto-advance with JS audio-end detection, and cap each TTS page at 1000 words.

**Architecture:** (1) `book_parser.py` gains a `words_per_page=1000` guard that breaks pages when either the char limit OR the word limit is reached; `parse_pdf` sub-splits dense PDF pages using the same splitter. (2) `app.py` injects a zero-height `st.components.v1.html()` script that finds the `<audio>` element in the parent frame, binds an `ended` listener, and sets `?auto_advance=N` in the URL — Streamlit detects this on the next rerun and advances the page.

**Tech Stack:** Python, Streamlit (`st.components.v1.html`, `st.query_params`), vanilla JS, pytest

---

### Task 1: Add word-count guard to Latin text splitter

**Files:**
- Modify: `book_parser.py`
- Modify: `tests/test_book_parser.py`

**Step 1: Write failing tests**

Add to `tests/test_book_parser.py`:

```python
def test_parse_text_word_cap_splits_long_page():
    # 50 sentences × 25 words = 1250 words — exceeds 1000-word default
    sentence = "The quick brown fox jumps over the lazy dog and runs away fast. "
    text = sentence * 50
    pages = parse_text(text)
    word_counts = [len(p.split()) for p in pages]
    assert all(wc <= 1000 for wc in word_counts)


def test_parse_text_word_cap_custom_limit():
    sentence = "Hello world this is a test sentence with many words. "
    text = sentence * 30  # 30 × ~10 words = ~300 words
    pages = parse_text(text, words_per_page=50)
    word_counts = [len(p.split()) for p in pages]
    assert all(wc <= 50 for wc in word_counts)


def test_parse_text_word_cap_does_not_split_short_page():
    text = "Short sentence. Another one. Third one."
    pages = parse_text(text, words_per_page=1000)
    assert len(pages) == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_book_parser.py::test_parse_text_word_cap_splits_long_page tests/test_book_parser.py::test_parse_text_word_cap_custom_limit tests/test_book_parser.py::test_parse_text_word_cap_does_not_split_short_page -v
```

Expected: FAIL — `parse_text` does not accept `words_per_page`.

**Step 3: Update `_parse_text_latin` signature and logic in `book_parser.py`**

Replace `_parse_text_latin`:

```python
def _parse_text_latin(text: str, chars_per_page: int, words_per_page: int = 1000) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    pages, current, current_len, current_words = [], [], 0, 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and (
            current_len + len(sentence) > chars_per_page
            or current_words + sentence_words > words_per_page
        ):
            pages.append(' '.join(current))
            current, current_len, current_words = [sentence], len(sentence), sentence_words
        else:
            current.append(sentence)
            current_len += len(sentence) + 1
            current_words += sentence_words

    if current:
        pages.append(' '.join(current))

    return pages
```

Update `parse_text` to accept and pass through `words_per_page`:

```python
def parse_text(text: str, chars_per_page: int = 1500, words_per_page: int = 1000, lang: str = 'en') -> list[str]:
    if lang == 'zh':
        return _parse_text_chinese(text, chars_per_page if chars_per_page != 1500 else 600)
    return _parse_text_latin(text, chars_per_page, words_per_page)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_book_parser.py::test_parse_text_word_cap_splits_long_page tests/test_book_parser.py::test_parse_text_word_cap_custom_limit tests/test_book_parser.py::test_parse_text_word_cap_does_not_split_short_page -v
```

Expected: PASS

**Step 5: Run full test suite to check for regressions**

```bash
pytest tests/test_book_parser.py -v
```

Expected: all pass.

**Step 6: Commit**

```bash
git add book_parser.py tests/test_book_parser.py
git commit -m "feat: add words_per_page=1000 cap to text splitter"
```

---

### Task 2: Sub-split long PDF pages using word cap

**Files:**
- Modify: `book_parser.py`
- Modify: `tests/test_book_parser.py`

**Step 1: Write failing tests**

Add to `tests/test_book_parser.py`:

```python
def test_parse_pdf_sub_splits_page_over_word_limit():
    # Build a PDF page with ~100 words
    sentence = "The fox jumped over the lazy dog again. "
    long_text = sentence * 25  # ~200 words on one PDF page
    pdf = _make_pdf([long_text])
    pages = parse_pdf(pdf, words_per_page=50)
    assert len(pages) > 1
    word_counts = [len(p.split()) for p in pages]
    assert all(wc <= 50 for wc in word_counts)


def test_parse_pdf_does_not_split_page_under_word_limit():
    pdf = _make_pdf(["Short page with just a few words."])
    pages = parse_pdf(pdf, words_per_page=1000)
    assert len(pages) == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_book_parser.py::test_parse_pdf_sub_splits_page_over_word_limit tests/test_book_parser.py::test_parse_pdf_does_not_split_page_under_word_limit -v
```

Expected: FAIL — `parse_pdf` does not accept `words_per_page`.

**Step 3: Update `parse_pdf` in `book_parser.py`**

Replace:

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

With:

```python
def parse_pdf(file_bytes: bytes, words_per_page: int = 1000, lang: str = 'en') -> list[str]:
    """Extract text from PDF bytes. Sub-splits pages exceeding words_per_page."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text().strip()
        if not text:
            continue
        if len(text.split()) > words_per_page:
            sub_pages = parse_text(text, words_per_page=words_per_page, lang=lang)
            pages.extend(sub_pages)
        else:
            pages.append(text)
    doc.close()
    return pages
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_book_parser.py::test_parse_pdf_sub_splits_page_over_word_limit tests/test_book_parser.py::test_parse_pdf_does_not_split_page_under_word_limit -v
```

Expected: PASS

**Step 5: Run full test suite**

```bash
pytest tests/test_book_parser.py -v
```

Expected: all pass.

**Step 6: Update the PDF load call in `app.py` to pass `lang`**

In `_sidebar()`, find:

```python
pages = parse_pdf(uploaded.read())
```

Replace with:

```python
pages = parse_pdf(uploaded.read(), lang=st.session_state.lang)
```

**Step 7: Commit**

```bash
git add book_parser.py tests/test_book_parser.py app.py
git commit -m "feat: sub-split PDF pages exceeding 1000 words"
```

---

### Task 3: Replace timer auto-advance with JS audio-end detection

**Files:**
- Modify: `app.py`

This task has no unit-testable logic (pure JS↔Streamlit interaction), so we skip the test step and test manually.

**Step 1: Remove timer-related state keys from `_init()`**

In `_init()`, remove these two entries from the `defaults` dict:

```python
'_last_timed_page': -1,
'page_start_time': 0.0,
```

**Step 2: Remove timer reset from `_jump_to()`**

In `_jump_to()`, remove:

```python
st.session_state['_last_timed_page'] = -1  # reset timer for new page
```

**Step 3: Remove `import time` from the top of `app.py`**

Delete the line:

```python
import time
```

**Step 4: Replace the entire timer auto-advance block in `_player()`**

Find and delete this entire block (roughly lines 209–227):

```python
    # Auto-advance mode: timer starts after audio is ready
    if st.session_state.advance_mode == 'auto' and idx + 1 < total:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2000, key="auto_advance_tick")

        # Start timer the first time this page is displayed
        if st.session_state.get('_last_timed_page') != idx:
            st.session_state['page_start_time'] = time.time()
            st.session_state['_last_timed_page'] = idx

        elapsed = time.time() - st.session_state['page_start_time']
        estimated = len(pages[idx]) / 15  # ~900 chars/min ÷ 60 = 15 chars/sec
        remaining = max(0, int(estimated - elapsed))
        st.info(f"Auto-advancing in {remaining}s...")

        if elapsed >= estimated:
            cleanup(idx)
            st.session_state['_last_timed_page'] = -1
            st.session_state.current_page += 1
            st.rerun()
```

Replace with the query-param signal check + JS injection:

```python
    # JS audio-end auto-advance
    if st.session_state.advance_mode == 'auto':
        # Check for signal set by JS when audio ended
        advance_signal = st.query_params.get('auto_advance')
        if advance_signal is not None:
            try:
                signal_idx = int(advance_signal)
            except ValueError:
                signal_idx = -1
            st.query_params.pop('auto_advance', None)
            if signal_idx == idx and idx + 1 < total:
                cleanup(idx)
                st.session_state.current_page += 1
                st.rerun()

        # Inject JS that fires when the audio element ends
        if idx + 1 < total:
            st.components.v1.html(
                f"""<script>
                (function() {{
                    function tryBind() {{
                        var audio = window.parent.document.querySelector('audio');
                        if (!audio) {{ setTimeout(tryBind, 200); return; }}
                        if (audio.dataset.advanceBound === '{idx}') return;
                        audio.dataset.advanceBound = '{idx}';
                        audio.addEventListener('ended', function() {{
                            var url = new URL(window.parent.location.href);
                            url.searchParams.set('auto_advance', '{idx}');
                            window.parent.location.href = url.toString();
                        }});
                    }}
                    tryBind();
                }})();
                </script>""",
                height=0,
            )
```

**Step 5: Remove `_last_timed_page` resets from navigation buttons**

In the navigation button block, remove `st.session_state['_last_timed_page'] = -1` from both the Prev button handler and the Next button handler.

Find in `_player()`:

```python
        if idx > 0 and st.button("◀ Prev", key="prev_btn"):
            cleanup(idx)
            st.session_state['_last_timed_page'] = -1
            st.session_state.current_page -= 1
            st.rerun()
```

Replace with:

```python
        if idx > 0 and st.button("◀ Prev", key="prev_btn"):
            cleanup(idx)
            st.session_state.current_page -= 1
            st.rerun()
```

And:

```python
            if st.button("Next ▶", key="next_btn"):
                cleanup(idx)
                st.session_state['_last_timed_page'] = -1
                st.session_state.current_page += 1
                st.rerun()
```

Replace with:

```python
            if st.button("Next ▶", key="next_btn"):
                cleanup(idx)
                st.session_state.current_page += 1
                st.rerun()
```

**Step 6: Remove `streamlit-autorefresh` from `requirements.txt`**

Delete the line:

```
streamlit-autorefresh>=1.0.1
```

**Step 7: Commit**

```bash
git add app.py requirements.txt
git commit -m "feat: replace timer auto-advance with JS audio-end detection"
```

---

### Task 4: Manual smoke test

Start the app and verify both features end-to-end.

**Step 1: Install updated dependencies**

```bash
pip install -r requirements.txt
```

**Step 2: Run the app**

```bash
streamlit run app.py
```

**Step 3: Test word cap**

- Upload a multi-page PDF or long `.txt` file
- Check that no page shown has more than ~1000 words

**Step 4: Test audio-end auto-advance**

- Enable "Auto-advance" in the sidebar
- Play a page to completion
- Verify the app automatically advances to the next page without clicking "Next"
- Verify manual "Next" and "Prev" still work

**Step 5: Confirm no `streamlit_autorefresh` import errors**

- The app should start without errors related to `streamlit_autorefresh`

**Step 6: Commit if any minor fixes were needed; otherwise done.**
