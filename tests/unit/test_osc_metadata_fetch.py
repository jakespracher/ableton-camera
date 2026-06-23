from bridge.osc_client import OscListener


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
