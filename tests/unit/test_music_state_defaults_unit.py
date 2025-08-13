from app.models.music_state import MusicState


def test_music_state_default_values():
    st = MusicState.default()
    assert st.volume == 25
    assert st.vibe.name == "Calm Night"
    assert st.radio_playing is True


