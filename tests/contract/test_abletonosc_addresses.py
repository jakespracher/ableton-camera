"""Guard against OSC address typos — paths the bridge must use."""

BRIDGE_OSC_PATHS = frozenset(
    {
        "/live/song/start_listen/record_mode",
        "/live/song/start_listen/session_record_status",
        "/live/song/get/record_mode",
        "/live/song/get/session_record_status",
        "/live/song/get/is_playing",
        "/live/song/start_listen/is_playing",
        "/live/song/get/is_counting_in",
        "/live/song/start_listen/is_counting_in",
        "/live/song/get/num_tracks",
        "/live/track/get/arm",
        "/live/track/get/name",
        "/live/view/get/selected_track",
    }
)


def test_paths_are_documented_style():
    for path in BRIDGE_OSC_PATHS:
        assert path.startswith("/live/")
        assert " " not in path
