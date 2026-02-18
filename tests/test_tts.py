# tests/test_tts.py
import streamlit as st


def test_uses_gtts_when_no_api_key(mocker):
    st.secrets = {}  # no OPENAI_API_KEY

    mock_tts_instance = mocker.MagicMock()
    mock_tts_instance.write_to_fp.side_effect = lambda fp: fp.write(b'fake-mp3')
    mocker.patch('gtts.gTTS', return_value=mock_tts_instance)

    from tts import generate_audio
    result = generate_audio("Hello world")

    assert isinstance(result, bytes)
    assert b'fake-mp3' in result


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
