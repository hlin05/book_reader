# Page Jump & Bookmarks — Design Document

**Date:** 2026-02-18
**Status:** Approved

## Overview

Add two navigation features to the sidebar: a page-jump control and a named bookmark system. Both live in a "Navigation" section that appears only when a book is loaded. No new modules — only `app.py` changes.

## Features

### Page Jump
- `st.number_input` (min=1, max=total pages, value=current page+1)
- "Go" button: cleans up audio for the current page, sets `current_page = N-1`, reruns

### Bookmarks
- Stored in `st.session_state.bookmarks: list[dict]`, each entry: `{"label": str, "page": int}` (0-indexed)
- Listed in sidebar: label + `(p.N)` + **Go** button + **✕** delete button
- "Go" navigates the same way as page jump
- "Add bookmark" form: text input for label + button — adds current page; empty label shows a warning

## Session State Changes

| Key | Type | Added/Modified |
|-----|------|----------------|
| `bookmarks` | `list[dict]` | New — initialized to `[]` in `_init()` and cleared in `_load_book()` |

## UI Layout (sidebar, when book loaded)

```
── Navigation ─────────────────────
Jump to page:  [ 42 ]   [Go]

Bookmarks
  Chapter 3    (p.12)  [Go] [✕]
  Great quote  (p.47)  [Go] [✕]

  ─ Add bookmark ─
  Label: [__________]
  [Bookmark page 42]
```

## Navigation Logic (shared for page jump and bookmark Go)

```python
def _jump_to(page_idx: int):
    cleanup(st.session_state.current_page)  # discard current page audio
    st.session_state.current_page = page_idx
    st.rerun()
```

## Scope

- Only `app.py` is modified
- No changes to `book_parser.py`, `tts.py`, `audio_manager.py`, or any test files
