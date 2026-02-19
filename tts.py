import asyncio
import io
import streamlit as st


_OPENAI_MAX_CHARS = 4096

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
    if api_key:
        return _openai_tts(text, api_key, speed=speed)
    if lang == 'zh':
        return _edge_tts(text, lang, speed=speed)
    return _gtts(text, lang=lang)


def _edge_tts(text: str, lang: str = 'zh', speed: float = 1.0) -> bytes:
    import edge_tts
    voice = _EDGE_VOICE.get(lang, _EDGE_VOICE['zh'])
    rate = f"{int((speed - 1) * 100):+d}%"  # e.g. 1.5 → "+50%", 0.75 → "-25%"

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                buf.write(chunk['data'])
        buf.seek(0)
        return buf.read()

    return asyncio.run(_run())


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
