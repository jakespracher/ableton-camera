import json
from datetime import datetime, timezone
from pathlib import Path

from bridge.capture import (
    CaptureRequest,
    CaptureResponse,
    CaptureService,
    capture_seconds,
    destination_code,
    finalize_capture_take,
)
from bridge.control import send_capture_request, start_control_server
from tests.fakes.fake_obs import FakeObsClient


def test_capture_seconds_uses_tempo_and_signature():
    assert capture_seconds(bars=4, tempo_bpm=120, beats_per_bar=4) == 8
    assert capture_seconds(bars=2, tempo_bpm=90, beats_per_bar=3) == 4


def test_capture_sidecar_includes_capture_metadata(output_dir, staging_dir):
    source = staging_dir / "replay.mov"
    source.write_bytes(b"video")

    result = finalize_capture_take(
        source_path=source,
        output_dir=output_dir,
        track_label="Grand Piano",
        clock=lambda: datetime(2026, 7, 19, 15, 0, 0, tzinfo=timezone.utc),
        sync_offset_ms=0,
        bars=4,
        tempo_bpm=120,
        beats_per_bar=4,
        live_current_song_time=32,
        trim_seconds=None,
    )

    payload = json.loads((output_dir / "last_take.json").read_text(encoding="utf-8"))
    assert payload["take_type"] == "capture_midi"
    assert payload["bars"] == 4
    assert payload["tempo_bpm"] == 120
    assert payload["beats_per_bar"] == 4
    assert payload["live_current_song_time"] == 32
    assert result.video_path.name.startswith("Grand_Piano_capture_2026-07-19_150000")
    assert result.video_path.read_bytes() == b"video"
    assert not source.exists()


class FakeCaptureQuery:
    def __init__(self) -> None:
        self.capture_destinations: list[int] = []

    def get_num_tracks(self) -> int:
        return 1

    def is_armed(self, track_id: int) -> bool:
        return track_id == 0

    def get_track_name(self, track_id: int) -> str:
        return "Grand Piano" if track_id == 0 else ""

    def get_selected_track_index(self) -> int:
        return 0

    def get_recording_track_index(self) -> int | None:
        return None

    def get_tempo(self) -> float:
        return 120.0

    def get_signature_numerator(self) -> int:
        return 4

    def get_current_song_time(self) -> float:
        return 64.0

    def capture_midi(self, destination: int) -> None:
        self.capture_destinations.append(destination)


def test_destination_code_matches_abletonosc_contract():
    assert destination_code("auto") == 0
    assert destination_code("session") == 1
    assert destination_code("arrangement") == 2


def test_capture_service_starts_replay_buffer_before_first_capture(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    query = FakeCaptureQuery()
    service = CaptureService(
        obs=obs,
        query=query,
        output_dir=output_dir,
        clock=lambda: datetime(2026, 7, 19, 15, 0, 0, tzinfo=timezone.utc),
    )

    response = service.capture_midi(CaptureRequest(bars=4, destination="arrangement"))

    assert response == CaptureResponse(
        ok=False,
        message="OBS Replay Buffer was started; run capture again after it has history.",
        error="replay_buffer_started",
    )
    assert obs.calls == ["start_replay"]
    assert query.capture_destinations == []


def test_capture_service_saves_replay_buffer_and_writes_sidecar(output_dir, staging_dir):
    source = staging_dir / "replay.mov"
    source.write_bytes(b"video")
    obs = FakeObsClient(staging_dir)
    obs.replay_buffer_active = True
    obs.set_replay_file(source)
    query = FakeCaptureQuery()
    service = CaptureService(
        obs=obs,
        query=query,
        output_dir=output_dir,
        clock=lambda: datetime(2026, 7, 19, 15, 0, 0, tzinfo=timezone.utc),
        trim_replay=lambda path, seconds: (path, seconds),
    )

    response = service.capture_midi(CaptureRequest(bars=2, destination="arrangement"))

    assert response.ok is True
    assert response.error is None
    assert response.video_path is not None
    assert response.video_path.name.startswith("Grand_Piano_capture_2026-07-19_150000")
    assert response.video_path.read_bytes() == b"video"
    assert response.sidecar_path == output_dir / "last_take.json"
    assert query.capture_destinations == [2]
    assert obs.calls == ["save_replay"]
    payload = json.loads((output_dir / "last_take.json").read_text(encoding="utf-8"))
    assert payload["take_type"] == "capture_midi"
    assert payload["bars"] == 2
    assert payload["trim_seconds"] == 4.0


def test_control_server_round_trips_capture_request():
    received: list[CaptureRequest] = []

    def handler(request: CaptureRequest) -> CaptureResponse:
        received.append(request)
        return CaptureResponse(
            ok=True,
            message="Captured",
            video_path=Path("/tmp/video.mov"),
            sidecar_path=Path("/tmp/last_take.json"),
        )

    server = start_control_server("127.0.0.1", 0, handler)
    try:
        response = send_capture_request(
            "127.0.0.1",
            server.server_address[1],
            CaptureRequest(bars=1, destination="session"),
            timeout_s=1,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert received == [CaptureRequest(bars=1, destination="session")]
    assert response == CaptureResponse(
        ok=True,
        message="Captured",
        video_path=Path("/tmp/video.mov"),
        sidecar_path=Path("/tmp/last_take.json"),
    )
