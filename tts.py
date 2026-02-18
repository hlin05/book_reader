import io
import streamlit as st


def generate_audio(text: str) -> bytes:
    """Convert text to MP3 bytes. Uses OpenAI TTS if OPENAI_API_KEY in secrets, else gTTS."""
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
    response = OpenAI(api_key=api_key).audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    return response.content
