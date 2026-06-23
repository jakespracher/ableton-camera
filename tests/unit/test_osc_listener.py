from bridge.osc_client import OscListener
from bridge.recording_state import RecordingEdge, RecordingSignals


def test_subscribe_sends_listen_addresses():
    edges: list[tuple[RecordingEdge, RecordingSignals]] = []

    listener = OscListener("127.0.0.1", 11000, "127.0.0.1", 11001, lambda e, s: edges.append((e, s)))
    listener._sent_log = []
    listener.subscribe()
    addresses = [a for a, _ in listener.sent_messages]
    assert "/live/song/start_listen/record_mode" in addresses
    assert "/live/song/start_listen/session_record_status" in addresses
    assert "/live/song/start_listen/is_playing" in addresses


def test_inject_record_mode_start_stop():
    edges: list[RecordingEdge] = []
    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        lambda edge, _signals: edges.append(edge),
    )
    listener._clip_recording = False
    listener.inject("/live/song/get/record_mode", 1)
    assert edges == [RecordingEdge.STARTED]
    listener.inject("/live/song/get/record_mode", 0)
    assert edges[-1] == RecordingEdge.STOPPED


def test_session_record_engaged_fires_start():
    edges: list[RecordingEdge] = []
    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        lambda edge, _signals: edges.append(edge),
    )
    listener._clip_recording = False
    listener.inject("/live/song/get/session_record_status", 1)
    assert RecordingEdge.STARTED in edges


def test_session_disengage_stops_obs_when_idle():
    edges: list[RecordingEdge] = []
    obs_recording = [True]

    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        lambda edge, _signals: edges.append(edge),
        is_obs_recording=lambda: obs_recording[0],
    )
    listener._clip_recording = False
    listener.inject("/live/song/get/session_record_status", 1)
    assert RecordingEdge.STARTED in edges
    obs_recording[0] = True
    listener.inject("/live/song/get/session_record_status", 0)
    assert edges[-1] == RecordingEdge.STOPPED
    obs_recording[0] = False


def test_clip_tail_keeps_stop_active_after_session_off():
    edges: list[RecordingEdge] = []
    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        lambda edge, _signals: edges.append(edge),
    )
    listener._clip_recording = True
    listener.inject("/live/song/get/record_mode", 1)
    listener._clip_recording = True
    listener.inject("/live/song/get/record_mode", 0)
    assert RecordingEdge.STOPPED not in edges
    listener._clip_recording = False
    listener._dispatch_edges()
    assert edges[-1] == RecordingEdge.STOPPED
