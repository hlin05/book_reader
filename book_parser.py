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
