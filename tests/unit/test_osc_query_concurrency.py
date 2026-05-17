import threading

from bridge.osc_client import OscListener


def test_metadata_fetch_while_clip_poll_runs():
    """Clip poll and track metadata must not share replies on the same OSC event."""
    listener = OscListener("127.0.0.1", 11000, "127.0.0.1", 11001, lambda *_: None)
    replies: dict[str, tuple] = {
        "/live/song/get/num_tracks": (4,),
        "/live/track/get/arm": (1, 1),
        "/live/track/get/name": (1, "Synth"),
        "/live/view/get/selected_track": (1,),
        "/live/track/get/playing_slot_index": (1, 0),
        "/live/track/get/fired_slot_index": (1, -1),
        "/live/clip_slot/get/has_clip": (1, 0, 1),
        "/live/clip/get/is_recording": (1, 0, 0),
    }
    original = listener._send

    def send(address: str, *args: int | float | str) -> None:
        original(address, *args)
        if address in replies:
            listener.inject(address, *replies[address])

    listener._send = send
    listener.start_clip_poll(interval_s=0.05)

    try:
        for _ in range(20):
            assert listener.fetch_arm(1, 0.5) is True
            assert listener.fetch_track_name(1, 0.5) == "Synth"
    finally:
        listener.stop_clip_poll()
