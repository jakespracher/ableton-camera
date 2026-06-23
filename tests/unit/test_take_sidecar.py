import json
from datetime import datetime, timezone

from bridge.take_sidecar import TakeSidecar, write_last_take


def test_write_last_take_creates_json_with_absolute_video_path(output_dir):
    video_path = output_dir / "Vocals_2026-06-23_110000.mkv"
    video_path.write_bytes(b"video")
    take = TakeSidecar(
        video_path=video_path,
        track_label="Vocals",
        recorded_start=datetime(2026, 6, 23, 11, 0, 0, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 6, 23, 11, 3, 12, tzinfo=timezone.utc),
        sync_offset_ms=120,
    )

    sidecar_path = write_last_take(output_dir, take)

    assert sidecar_path == output_dir / "last_take.json"
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "video_path": str(video_path.resolve()),
        "track_label": "Vocals",
        "recorded_start": "2026-06-23T11:00:00+00:00",
        "finalized_at": "2026-06-23T11:03:12+00:00",
        "sync_offset_ms": 120,
    }


def test_write_last_take_replaces_existing_sidecar(output_dir):
    existing = output_dir / "last_take.json"
    existing.write_text('{"old": true}', encoding="utf-8")
    video_path = output_dir / "Guitar_2026-06-23_110100.mkv"
    video_path.write_bytes(b"video")
    take = TakeSidecar(
        video_path=video_path,
        track_label="Guitar",
        recorded_start=datetime(2026, 6, 23, 11, 1, 0, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 6, 23, 11, 2, 0, tzinfo=timezone.utc),
    )

    write_last_take(output_dir, take)

    payload = json.loads(existing.read_text(encoding="utf-8"))
    assert payload["track_label"] == "Guitar"
    assert "old" not in payload
