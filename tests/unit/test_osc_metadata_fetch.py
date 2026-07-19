import time

from bridge.osc_client import OscListener
from bridge.osc_query import LiveOscQuery
from bridge.metadata import resolve_track_label


def _listener() -> OscListener:
    return OscListener("127.0.0.1", 11000, "127.0.0.1", 11001, lambda *_: None)


def _send_with_reply(listener: OscListener) -> None:
    original = listener._send

    def send(address: str, *args: int | float | str) -> None:
        original(address, *args)
        if address == "/live/song/get/num_tracks":
            listener.inject("/live/song/get/num_tracks", 4)
        elif address == "/live/track/get/arm":
            listener.inject("/live/track/get/arm", *args)
        elif address == "/live/track/get/name":
            listener.inject("/live/track/get/name", *args)
        elif address == "/live/view/get/selected_track":
            listener.inject("/live/view/get/selected_track", 2)

    listener._send = send


def test_fetch_num_tracks():
    listener = _listener()
    _send_with_reply(listener)
    assert listener.fetch_num_tracks(0.5) == 4


def test_fetch_arm_and_name():
    listener = _listener()

    def send(address: str, *args: int | float | str) -> None:
        if address == "/live/track/get/arm":
            listener.inject("/live/track/get/arm", 1, 1)
        elif address == "/live/track/get/name":
            listener.inject("/live/track/get/name", 1, "Synth")

    listener._send = send
    assert listener.fetch_arm(1, 0.5) is True
    assert listener.fetch_track_name(1, 0.5) == "Synth"


def test_fetch_selected_track():
    listener = _listener()
    _send_with_reply(listener)
    assert listener.fetch_selected_track(0.5) == 2


def test_on_arm_ignores_none_arm_value():
    listener = _listener()
    listener.inject("/live/track/get/arm", 2, None)
    assert listener.fetch_arm(2, 0.5) is False


def test_deferred_edge_handler_can_fetch_track_metadata_after_record_mode_callback():
    requested: list[tuple[str, tuple[int | float | str, ...]]] = []
    labels: list[str] = []
    listener: OscListener | None = None

    def on_edge(_edge, _signals):
        assert listener is not None
        labels.append(resolve_track_label(LiveOscQuery(listener, timeout_s=0.5)))

    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        on_edge,
        defer_callbacks=True,
    )

    def send(address: str, *args: int | float | str) -> None:
        requested.append((address, args))

    listener._send = send

    listener.inject("/live/song/get/record_mode", 1)

    def pop_request() -> tuple[str, tuple[int | float | str, ...]]:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if requested:
                return requested.pop(0)
            time.sleep(0.01)
        raise AssertionError("Timed out waiting for OSC metadata request")

    assert pop_request() == ("/live/song/get/num_tracks", ())
    listener.inject("/live/song/get/num_tracks", 1)
    assert pop_request() == ("/live/track/get/arm", (0,))
    listener.inject("/live/track/get/arm", 0, 1)
    assert pop_request() == ("/live/track/get/name", (0,))
    listener.inject("/live/track/get/name", 0, "Vocals")

    listener.stop()
    assert labels == ["Vocals"]
