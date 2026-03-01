import asyncio
import io
import re
import time
import streamlit as st
from book_parser import _is_chinese


_OPENAI_MAX_CHARS = 4096


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax so TTS speaks only the prose content."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)   # headings
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)       # bold/italic
    text = re.sub(r'`[^`\n]+`', '', text)                          # inline code
    text = re.sub(r'```[\s\S]*?```', '', text)                     # code blocks
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)          # links → label
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE) # hr
    text = re.sub(r'^[>\-\*\+]\s+', '', text, flags=re.MULTILINE)  # blockquote/list
    return text.strip()

_EDGE_VOICE = {
    'zh': 'zh-CN-XiaoxiaoNeural',
    'en': 'en-US-JennyNeural',
}


def generate_audio(text: str, api_key: str | None = None, lang: str = 'en', speed: float = 1.0) -> bytes:
    """Convert text to MP3 bytes. Uses OpenAI TTS if api_key provided or in secrets,
    edge-tts for Chinese, else gTTS.

    Pass api_key explicitly when calling from a background thread (st.secrets is not thread-safe).
    speed: 0.5–2.0, default 1.0.
    """
    if api_key is None:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
    text = _strip_markdown(text)
    if lang != 'zh' and _is_chinese(text):
        lang = 'zh'
    if api_key:
        return _openai_tts(text, api_key, speed=speed)
    return _edge_tts(text, lang, speed=speed)


def _edge_tts(text: str, lang: str = 'zh', speed: float = 1.0) -> bytes:
    import edge_tts
    voice = _EDGE_VOICE.get(lang, _EDGE_VOICE['en'])
    rate = f"{int((speed - 1) * 100):+d}%"  # e.g. 1.5 → "+50%", 0.75 → "-25%"

    if not text.strip():
        # Blank page — return a quiet gTTS clip rather than hitting edge_tts
        return _gtts(' ', 'en')

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                buf.write(chunk['data'])
        buf.seek(0)
        return buf.read()

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return asyncio.run(_run())
        except edge_tts.exceptions.NoAudioReceived as e:
            last_err = e
            if attempt < 2:
                time.sleep(1)

    # All retries exhausted — gTTS fallback only for English (Chinese gTTS rate-limits fast)
    if lang == 'en':
        return _gtts(text, lang)
    raise RuntimeError(
        f"edge-tts failed to produce audio after 3 attempts: {last_err}"
    ) from last_err


def _gtts(text: str, lang: str = 'en') -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    GTS_LANG = 'zh' if lang == 'zh' else lang
    gTTS(text=text, lang=GTS_LANG).write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def _openai_tts(text: str, api_key: str, speed: float = 1.0) -> bytes:
    from openai import OpenAI
    # OpenAI TTS API limit is 4096 characters; truncate to avoid a 400 error.
    truncated = text[:_OPENAI_MAX_CHARS]
    response = OpenAI(api_key=api_key).audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=truncated,
        speed=max(0.25, min(4.0, speed)),
    )
    return response.content
