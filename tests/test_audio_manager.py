# tests/test_audio_manager.py
import os
import time
import streamlit as st


def test_ensure_audio_generates_and_caches(mocker):
    mocker.patch('tts.generate_audio', return_value=b'fake-audio')
    import audio_manager

    pages = ["Page one text."]
    result = audio_manager.ensure_audio(0, pages)

    assert result == b'fake-audio'
    assert 0 in st.session_state['audio_cache']
    # Temp file should exist on disk
    assert os.path.exists(st.session_state['audio_cache'][0])


def test_ensure_audio_uses_cache_on_second_call(mocker):
    call_count = {'n': 0}

    def counting_tts(text, api_key=None, lang='en', speed=1.0):
        call_count['n'] += 1
        return b'audio'

    mocker.patch('tts.generate_audio', side_effect=counting_tts)
    import audio_manager

    pages = ["Some text."]
    audio_manager.ensure_audio(0, pages)
    audio_manager.ensure_audio(0, pages)

    assert call_count['n'] == 1  # second call should not regenerate


def test_cleanup_deletes_temp_file_and_removes_from_cache(mocker):
    mocker.patch('tts.generate_audio', return_value=b'audio')
    import audio_manager

    audio_manager.ensure_audio(0, ["Text."])
    path = st.session_state['audio_cache'][0]
    assert os.path.exists(path)

    audio_manager.cleanup(0)

    assert not os.path.exists(path)
    assert 0 not in st.session_state['audio_cache']


def test_prefetch_populates_cache_in_background(mocker):
    mocker.patch('tts.generate_audio', return_value=b'prefetched')
    import audio_manager

    pages = ["Page one.", "Page two."]
    audio_manager.prefetch(1, pages)

    # Wait up to 5 seconds for background thread
    deadline = time.time() + 5
    while not audio_manager.is_prefetch_ready(1):
        assert time.time() < deadline, "Prefetch timed out after 5s"
        time.sleep(0.05)

    assert audio_manager.get_audio(1) == b'prefetched'


def test_prefetch_populates_cache_when_book_id_nonzero(mocker):
    """Regression: prefetch must cache audio even when book_id > 0.

    In Streamlit's runtime, background threads have no ScriptRunContext so
    st.session_state returns a default-empty view.  The previous _worker checked
    `st.session_state.get('_book_id') == book_id`; with book_id=1 the thread saw
    _book_id=0 -> mismatch -> deleted the audio file without caching it.
    Fix: _worker writes directly to the captured dict reference instead.
    """
    mocker.patch('tts.generate_audio', return_value=b'prefetched')
    import audio_manager

    st.session_state['_book_id'] = 1  # simulates state after book load
    pages = ["Page one.", "Page two."]
    audio_manager.prefetch(1, pages)

    deadline = time.time() + 5
    while not audio_manager.is_prefetch_ready(1):
        assert time.time() < deadline, "Prefetch timed out — audio_cache never populated"
        time.sleep(0.05)

    assert audio_manager.get_audio(1) == b'prefetched'


def test_prefetch_ignores_out_of_bounds_index(mocker):
    mocker.patch('tts.generate_audio', return_value=b'audio')
    import audio_manager

    # Should not raise
    audio_manager.prefetch(99, ["Only one page."])
    audio_manager.prefetch(-1, ["Only one page."])
