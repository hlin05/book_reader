# tests/test_tts.py
import streamlit as st


def test_uses_edge_tts_for_english_when_no_api_key(mocker):
    st.secrets = {}  # no OPENAI_API_KEY
    mock_edge = mocker.patch('tts._edge_tts', return_value=b'edge-mp3')

    from tts import generate_audio
    result = generate_audio("Hello world", lang='en')

    assert result == b'edge-mp3'
    mock_edge.assert_called_once()


def test_uses_openai_when_api_key_present(mocker):
    st.secrets = {'OPENAI_API_KEY': 'sk-fake'}

    mock_response = mocker.MagicMock()
    mock_response.content = b'openai-mp3'
    mock_client = mocker.MagicMock()
    mock_client.audio.speech.create.return_value = mock_response
    mocker.patch('openai.OpenAI', return_value=mock_client)

    from tts import generate_audio
    result = generate_audio("Hello world")

    assert result == b'openai-mp3'
