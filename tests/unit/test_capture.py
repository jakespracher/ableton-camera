import json
from datetime import datetime, timezone

from bridge.capture import capture_seconds, finalize_capture_take


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
