# Design: JS Audio-End Auto-Advance + 1000-Word Page Cap

Date: 2026-02-19

## Overview

Two features:
1. **1000-word page cap** — each TTS chunk is bounded by both a character limit and 1000 words; whichever is smaller wins.
2. **JS audio-end auto-advance** — when the current page's audio finishes playing, the next page starts immediately without any button click or timer.

---

## Feature 1: 1000-Word Page Cap

### Problem
Currently `parse_text` splits only by character count (1500 chars ≈ 250 words for English). PDF pages use the full PDF page with no word-count guard — a dense page could be several thousand words, making TTS generation slow and the chunk unwieldy.

### Design

**`book_parser.py`**

Add a `words_per_page: int = 1000` parameter to `parse_text`, `_parse_text_latin`, and `_parse_text_chinese`.

When accumulating sentences into a page, break if *either* limit is exceeded:
- `current_len + len(sentence) > chars_per_page` (existing), OR
- `current_word_count + word_count(sentence) > words_per_page` (new)

For Chinese, count characters as a proxy for words (no whitespace-based word split), keeping the existing `chars_per_page` as the single limit — but add a `words_per_page` guard using `len(sentence)` since each character ≈ 1 word.

**`parse_pdf` update**

After extracting raw text per PDF page, if the page exceeds 1000 words, sub-split it with `parse_text(text, words_per_page=1000, lang=lang)` and extend the page list instead of appending as one chunk.

**Callers (`app.py`)**

No signature change needed — `words_per_page=1000` defaults apply everywhere. No UI change.

---

## Feature 2: JS Audio-End Auto-Advance

### Problem
Streamlit's `st.audio()` renders a native `<audio>` element in an iframe. Python has no way to receive the `ended` event. The current timer-based workaround fires at an estimated time, often off by seconds.

### Design

Replace the timer + `streamlit_autorefresh` auto-advance with a JS-based approach:

1. **JS component** — Inject HTML+JS via `st.components.v1.html()` alongside `st.audio()`. The script:
   - Walks up from the component's iframe to find the nearest `<audio>` element in the parent document.
   - Attaches an `ended` event listener.
   - When `ended` fires, increments a counter stored in `sessionStorage` and reloads the Streamlit app via `window.parent.location.reload()` (or uses `window.parent.postMessage`).

2. **Streamlit side** — On each rerun, check a query param or a dedicated Streamlit state signal. Because `window.parent.location.reload()` triggers a full Streamlit rerun, we use a `st.query_params` key (e.g., `auto_advance`) as the signal. If the key is present and equals the current page index, advance to the next page and clear the key.

3. **Advance mode** — The existing `advance_mode` radio ("Manual" / "Auto-advance") still controls whether the JS component is rendered. In manual mode, no JS is injected. In auto mode, JS is always active.

4. **Remove old timer logic** — Delete the `page_start_time`, `_last_timed_page`, `elapsed`/`estimated` timer block and the `st_autorefresh` import for auto-advance (keep it only if used elsewhere).

### JS snippet (pseudocode)
```javascript
// Walk up to find the <audio> in the parent frame
const audio = window.parent.document.querySelector('audio');
if (audio && !audio.dataset.advanceBound) {
  audio.dataset.advanceBound = '1';
  audio.addEventListener('ended', () => {
    const url = new URL(window.parent.location.href);
    url.searchParams.set('auto_advance', '<current_page_idx>');
    window.parent.location.href = url.toString();
  });
}
```

### State flow
```
Page N renders → st.audio() + JS component injected
→ User listens to audio
→ audio.ended fires
→ JS sets ?auto_advance=N in URL → Streamlit reruns
→ app.py detects auto_advance==N → advance to page N+1, clear param
→ Page N+1 renders
```

---

## Files to Change

| File | Change |
|------|--------|
| `book_parser.py` | Add `words_per_page=1000` param; apply word-count guard in both Latin and Chinese splitters; update `parse_pdf` to sub-split long pages |
| `app.py` | Replace timer auto-advance with JS component; detect `st.query_params['auto_advance']`; remove `page_start_time` / `_last_timed_page` / `st_autorefresh` timer logic |

No new dependencies required (`st.components.v1.html` is built-in).
