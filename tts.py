import io
import streamlit as st


_OPENAI_MAX_CHARS = 4096


def generate_audio(text: str, api_key: str | None = None) -> bytes:
    """Convert text to MP3 bytes. Uses OpenAI TTS if api_key provided or in secrets, else gTTS.

    Pass api_key explicitly when calling from a background thread (st.secrets is not thread-safe).
    """
    if api_key is None:
        api_key = st.secrets.get("OPENAI_API_KEY", None)
    if api_key:
        return _openai_tts(text, api_key)
    return _gtts(text)


def _gtts(text: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang='en').write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def _openai_tts(text: str, api_key: str) -> bytes:
    from openai import OpenAI
    # OpenAI TTS API limit is 4096 characters; truncate to avoid a 400 error.
    truncated = text[:_OPENAI_MAX_CHARS]
    response = OpenAI(api_key=api_key).audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=truncated,
    )
    return response.content
