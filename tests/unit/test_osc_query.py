from bridge.osc_client import OscListener
from bridge.osc_query import LiveOscQuery


def test_live_osc_query_delegates_to_listener():
    listener = OscListener("127.0.0.1", 11000, "127.0.0.1", 11001, lambda *_: None)

    def send(address: str, *args: int | float | str) -> None:
        if address == "/live/song/get/num_tracks":
            listener.inject("/live/song/get/num_tracks", 2)
        elif address == "/live/track/get/arm":
            listener.inject("/live/track/get/arm", 0, 1)
        elif address == "/live/track/get/name":
            listener.inject("/live/track/get/name", 0, "Kick")
        elif address == "/live/view/get/selected_track":
            listener.inject("/live/view/get/selected_track", 1)

    listener._send = send
    query = LiveOscQuery(listener, timeout_s=0.5)
    assert query.get_num_tracks() == 2
    assert query.is_armed(0) is True
    assert query.get_track_name(0) == "Kick"
    assert query.get_selected_track_index() == 1
