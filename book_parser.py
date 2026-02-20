import re
import requests
import fitz  # PyMuPDF


def parse_text(text: str, chars_per_page: int = 1500, words_per_page: int = 1000, lang: str = 'en') -> list[str]:
    """Split text into pages at sentence boundaries, targeting chars_per_page characters each.

    For Chinese (lang='zh'), splits on Chinese punctuation and joins without spaces.
    Default chars_per_page is lower for Chinese since characters are more content-dense.
    """
    if lang == 'zh':
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
    """Split Chinese text at sentence-ending punctuation (。！？), no spaces between sentences."""
    sentences = re.split(r'(?<=[。！？])', text.strip())
    pages, current, current_len = [], [], 0

    for sentence in sentences:
        if current and current_len + len(sentence) > chars_per_page:
            pages.append(''.join(current))
            current, current_len = [sentence], len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)

    if current:
        pages.append(''.join(current))

    return pages


def parse_pdf(file_bytes: bytes, words_per_page: int = 1000, lang: str = 'en') -> list[str]:
    """Extract text from PDF bytes. Sub-splits pages exceeding words_per_page."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text().strip()
        if not text:
            continue
        if len(text.split()) > words_per_page:
            # Both limits apply. For typical prose, chars_per_page=1500 (~200-300 words) binds first;
            # the word cap is binding only for text with unusually long sentences.
            # For Chinese (lang='zh'), parse_text routes to _parse_text_chinese which uses chars_per_page=600
            # and ignores words_per_page — Chinese word-count semantics differ from Latin-script text.
            sub_pages = parse_text(text, words_per_page=words_per_page, lang=lang)
            pages.extend(sub_pages)
        else:
            pages.append(text)
    doc.close()
    return pages


def fetch_github_files(repo_url: str, token: str | None = None) -> list[dict]:
    """List .md and .txt files in a GitHub repo. Returns [{name, raw_url}]."""
    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 5 or 'github.com' not in parts:
        raise ValueError(f"Not a valid GitHub repo URL: {repo_url!r}")
    owner, repo = parts[-2], parts[-1]
    if not owner or not repo:
        raise ValueError(f"Could not extract owner/repo from URL: {repo_url!r}")

    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'

    resp = requests.get(f'https://api.github.com/repos/{owner}/{repo}', headers=headers)
    resp.raise_for_status()
    default_branch = resp.json()['default_branch']

    resp = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1',
        headers=headers,
    )
    resp.raise_for_status()

    files = []
    for item in resp.json().get('tree', []):
        if item['type'] == 'blob' and item['path'].endswith(('.md', '.txt')):
            raw_url = (
                f'https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{item["path"]}'
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
