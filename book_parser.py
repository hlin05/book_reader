import re
import requests
import fitz  # PyMuPDF
from urllib.parse import unquote


def _is_chinese(text: str) -> bool:
    """Return True if >20% of non-whitespace characters in the first 2000 chars are CJK."""
    sample = text[:2000]
    non_ws = [c for c in sample if not c.isspace()]
    if not non_ws:
        return False
    cjk = sum(1 for c in non_ws if '\u4e00' <= c <= '\u9fff')
    return cjk / len(non_ws) > 0.2


def parse_text(text: str, chars_per_page: int = 1500, words_per_page: int = 1000, lang: str = 'en') -> list[str]:
    """Split text into pages at sentence boundaries, targeting chars_per_page characters each.

    For Chinese content (lang='zh' or auto-detected), splits on Chinese punctuation and
    paragraph breaks. Auto-detection means Chinese files load correctly even when the UI
    language selector is left on English.
    """
    if lang == 'zh' or _is_chinese(text):
        return _parse_text_chinese(text, chars_per_page if chars_per_page != 1500 else 600)
    return _parse_text_latin(text, chars_per_page, words_per_page)


def _parse_text_latin(text: str, chars_per_page: int, words_per_page: int = 1000) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    pages, current, current_len, current_words = [], [], 0, 0

    # Note: a single sentence that individually exceeds either limit is always accepted as-is
    # (the `if current` guard skips the flush for the first item in a new page).
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


def _parse_text_chinese(text: str, chars_per_page: int) -> list[str]:
    """Split Chinese text at sentence-ending punctuation (。！？) or paragraph breaks.

    Markdown files use blank lines between paragraphs rather than Chinese terminal
    punctuation, so we split on both to avoid entire files becoming one huge page.
    """
    # Normalise line endings (GitHub files often use CRLF)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Split on Chinese sentence endings OR blank-line paragraph breaks
    segments = re.split(r'(?<=[。！？])|(?:\n{2,})', text.strip())
    segments = [s.strip() for s in segments if s.strip()]

    pages, current, current_len = [], [], 0

    for seg in segments:
        if current and current_len + len(seg) > chars_per_page:
            pages.append('\n\n'.join(current))
            current, current_len = [seg], len(seg)
        else:
            current.append(seg)
            current_len += len(seg)

    if current:
        pages.append('\n\n'.join(current))

    return pages


def parse_pdf(file_bytes: bytes, words_per_page: int = 500, lang: str = 'en') -> list[str]:
    """Extract text from PDF bytes and split into app pages.

    Short PDF pages are merged until the size limit is reached, then flushed. Oversized chunks
    are sub-split via parse_text. For Chinese (lang='zh'), accumulation uses char count instead
    of word count because Chinese text has no spaces between characters, making split()-based
    word counting wildly underestimate page size (e.g. 800-char page counts as ~1 "word").
    """
    # Chinese: target 600 chars/page (matches parse_text's Chinese default).
    # English: target words_per_page words/page.
    _zh_chars_limit = 600

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # Auto-detect Chinese from the first non-blank pages (skip cover/image-only pages).
    # Scan up to 20 pages collecting text until we have 2000 chars — enough for _is_chinese.
    if lang != 'zh':
        sample_parts: list[str] = []
        for p in doc[:20]:
            t = p.get_text().strip()
            if t:
                sample_parts.append(t)
            if sum(len(s) for s in sample_parts) >= 2000:
                break
        if _is_chinese(''.join(sample_parts)):
            lang = 'zh'

    pages: list[str] = []
    current_chunks: list[str] = []
    current_words = 0
    current_chars = 0

    def _flush():
        combined = '\n\n'.join(current_chunks)
        too_large = (len(combined) > _zh_chars_limit) if lang == 'zh' else (len(combined.split()) > words_per_page)
        if too_large:
            pages.extend(parse_text(combined, words_per_page=words_per_page, lang=lang))
        else:
            pages.append(combined)

    for page in doc:
        text = page.get_text().strip()
        if not text:
            continue
        page_words = len(text.split())
        page_chars = len(text)
        if lang == 'zh':
            should_flush = current_chunks and current_chars + page_chars > _zh_chars_limit
        else:
            should_flush = current_chunks and current_words + page_words > words_per_page
        if should_flush:
            _flush()
            current_chunks, current_words, current_chars = [text], page_words, page_chars
        else:
            current_chunks.append(text)
            current_words += page_words
            current_chars += page_chars

    if current_chunks:
        _flush()

    doc.close()
    return pages


def _parse_github_url(repo_url: str) -> tuple[str, str, str | None, str | None]:
    """Parse a GitHub URL into (owner, repo, branch, path).

    Handles formats:
      https://github.com/{owner}/{repo}
      https://github.com/{owner}/{repo}/tree/{branch}
      https://github.com/{owner}/{repo}/tree/{branch}/{path}
      https://github.com/{owner}/{repo}/blob/{branch}/{path}   ← file page
      https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
    """
    url = repo_url.rstrip('/')

    # raw.githubusercontent.com direct file link
    m = re.match(r'https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)', url)
    if m:
        owner, repo, branch, path = m.group(1), m.group(2), m.group(3), m.group(4)
        return owner, repo, branch, unquote(path)

    # github.com blob (file page) or tree (directory) link
    m = re.match(
        r'https?://github\.com/([^/]+)/([^/]+)(?:/(blob|tree)/([^/]+)(?:/(.+))?)?/?$',
        url,
    )
    if not m:
        raise ValueError(f"Not a valid GitHub URL: {repo_url!r}")
    owner, repo, branch, path = m.group(1), m.group(2), m.group(4), m.group(5)
    if path:
        path = unquote(path)
    return owner, repo, branch, path


def github_url_to_raw(repo_url: str) -> str | None:
    """If the URL points directly to a file, return its raw download URL. Otherwise None."""
    url = repo_url.rstrip('/')

    # Already a raw URL
    if url.startswith('https://raw.githubusercontent.com/'):
        return url

    m = re.match(
        r'https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)',
        url,
    )
    if m:
        owner, repo, branch, path = m.group(1), m.group(2), m.group(3), unquote(m.group(4))
        return f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}'

    return None


def fetch_github_files(repo_url: str, token: str | None = None) -> list[dict]:
    """List .md and .txt files in a GitHub repo (or subdirectory). Returns [{name, raw_url}]."""
    owner, repo, branch, subpath = _parse_github_url(repo_url)

    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'

    if branch is None:
        resp = requests.get(f'https://api.github.com/repos/{owner}/{repo}', headers=headers)
        resp.raise_for_status()
        branch = resp.json()['default_branch']

    resp = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1',
        headers=headers,
    )
    resp.raise_for_status()

    # Normalise subpath for prefix filtering (no leading/trailing slash)
    prefix = (subpath.strip('/') + '/') if subpath else ''

    files = []
    for item in resp.json().get('tree', []):
        if item['type'] == 'blob' and item['path'].endswith(('.md', '.txt')):
            if prefix and not item['path'].startswith(prefix):
                continue
            raw_url = (
                f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{item["path"]}'
            )
            files.append({'name': item['path'], 'raw_url': raw_url})
    return files


def fetch_github_file(raw_url: str, token: str | None = None) -> str:
    """Fetch raw text content of a file from GitHub."""
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    resp = requests.get(raw_url, headers=headers)
    resp.raise_for_status()
    return resp.text
