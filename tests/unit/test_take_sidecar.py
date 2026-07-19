import json
from datetime import datetime, timezone

from bridge.take_sidecar import (
    SIDECAR_POINTER_ENV,
    TakeSidecar,
    write_last_take,
    write_take_sidecars,
)


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


def test_write_take_sidecars_appends_history(output_dir):
    first_video = output_dir / "Vocals_2026-06-23_110000.mkv"
    second_video = output_dir / "Guitar_2026-06-23_110100.mkv"
    first_video.write_bytes(b"first")
    second_video.write_bytes(b"second")
    first = TakeSidecar(
        video_path=first_video,
        track_label="Vocals",
        recorded_start=datetime(2026, 6, 23, 11, 0, 0, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 6, 23, 11, 3, 12, tzinfo=timezone.utc),
        sync_offset_ms=120,
    )
    second = TakeSidecar(
        video_path=second_video,
        track_label="Guitar",
        recorded_start=datetime(2026, 6, 23, 11, 1, 0, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 6, 23, 11, 4, 0, tzinfo=timezone.utc),
        sync_offset_ms=-40,
    )

    last_path, history_path = write_take_sidecars(output_dir, first)
    write_take_sidecars(output_dir, second)

    assert last_path == output_dir / "last_take.json"
    assert history_path == output_dir / "take_history.json"
    latest = json.loads(last_path.read_text(encoding="utf-8"))
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert latest["track_label"] == "Guitar"
    assert history == {
        "schema_version": 1,
        "takes": [
            {
                "schema_version": 1,
                "video_path": str(first_video.resolve()),
                "track_label": "Vocals",
                "recorded_start": "2026-06-23T11:00:00+00:00",
                "finalized_at": "2026-06-23T11:03:12+00:00",
                "sync_offset_ms": 120,
            },
            {
                "schema_version": 1,
                "video_path": str(second_video.resolve()),
                "track_label": "Guitar",
                "recorded_start": "2026-06-23T11:01:00+00:00",
                "finalized_at": "2026-06-23T11:04:00+00:00",
                "sync_offset_ms": -40,
            },
        ],
    }


def test_write_take_sidecars_publishes_pointer(output_dir, monkeypatch):
    pointer_path = output_dir / "home" / "sidecar_path.json"
    monkeypatch.setenv(SIDECAR_POINTER_ENV, str(pointer_path))
    video_path = output_dir / "Vocals_2026-06-23_110000.mkv"
    video_path.write_bytes(b"video")
    take = TakeSidecar(
        video_path=video_path,
        track_label="Vocals",
        recorded_start=datetime(2026, 6, 23, 11, 0, 0, tzinfo=timezone.utc),
        finalized_at=datetime(2026, 6, 23, 11, 3, 12, tzinfo=timezone.utc),
    )

    last_path, history_path = write_take_sidecars(output_dir, take)

    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "last_take_path": str(last_path.resolve()),
        "take_history_path": str(history_path.resolve()),
    }
