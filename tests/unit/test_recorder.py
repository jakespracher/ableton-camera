import json
from datetime import datetime, timezone
from pathlib import Path

from freezegun import freeze_time

from bridge.recording_state import RecordingEdge, RecordingSignals
from bridge.recorder import Recorder
from tests.conftest import wire_recorder_probes
from tests.fakes.fake_obs import FakeObsClient
from tests.fakes.fake_osc_query import FakeOscQuery


@freeze_time("2026-05-16 14:30:22", tz_offset=0)
def test_start_stop_moves_file_to_output(output_dir: Path, staging_dir: Path):
    obs = FakeObsClient(staging_dir)
    staged = staging_dir / "raw.mkv"
    staged.write_bytes(b"video")
    obs.set_staged_file(staged)

    clock = lambda: datetime(2026, 5, 16, 14, 30, 22, tzinfo=timezone.utc)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    recorder = Recorder(
        obs,
        metadata,
        output_dir,
        staging_dir,
        clock=clock,
    )
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    assert obs.recording is True

    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
    dest = output_dir / "Vocals_2026-05-16_143022.mkv"
    assert dest.is_file()
    assert not staged.exists()
    assert obs.calls == ["start", "stop"]


def test_duplicate_start_ignored(output_dir: Path, staging_dir: Path):
    obs = FakeObsClient(staging_dir)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    recorder = Recorder(obs, metadata, output_dir, staging_dir)
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    assert obs.calls.count("start") == 1


def test_saves_under_project_subfolder(output_dir: Path, staging_dir: Path):
    from bridge.naming import resolve_output_dir

    project_dir = resolve_output_dir(output_dir, "My Album")
    obs = FakeObsClient(staging_dir)
    staged = staging_dir / "take.mkv"
    staged.write_bytes(b"fake")
    obs.set_staged_file(staged)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    recorder = Recorder(obs, metadata, project_dir, staging_dir)
    wire_recorder_probes(recorder)
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
    assert list(project_dir.glob("Vocals_*.mkv"))
    assert not list(output_dir.glob("*.mkv"))


def test_stop_writes_last_take_sidecar(output_dir: Path, staging_dir: Path):
    obs = FakeObsClient(staging_dir)
    staged = staging_dir / "take.mkv"
    staged.write_bytes(b"fake")
    obs.set_staged_file(staged)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    clock_values = [
        datetime(2026, 6, 23, 11, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 23, 11, 3, 12, tzinfo=timezone.utc),
    ]
    recorder = Recorder(
        obs,
        metadata,
        output_dir,
        staging_dir,
        clock=lambda: clock_values.pop(0),
        sync_offset_ms=120,
    )
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))

    payload = json.loads((output_dir / "last_take.json").read_text(encoding="utf-8"))
    assert payload["video_path"] == str((output_dir / "Vocals_2026-06-23_110000.mkv").resolve())
    assert payload["track_label"] == "Vocals"
    assert payload["recorded_start"] == "2026-06-23T11:00:00+00:00"
    assert payload["finalized_at"] == "2026-06-23T11:03:12+00:00"
    assert payload["sync_offset_ms"] == 120


def test_stop_without_staged_file_does_not_update_sidecar(output_dir: Path, staging_dir: Path):
    class MissingFileObs(FakeObsClient):
        def stop_record(self) -> Path | None:
            self.calls.append("stop")
            self.recording = False
            return None

    existing = output_dir / "last_take.json"
    existing.write_text('{"track_label": "Previous"}', encoding="utf-8")
    recorder = Recorder(
        MissingFileObs(staging_dir),
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))

    assert json.loads(existing.read_text(encoding="utf-8")) == {"track_label": "Previous"}


def test_sidecar_write_failure_removes_stale_last_take(output_dir: Path, staging_dir: Path, monkeypatch):
    def fail_write_last_take(*_args, **_kwargs):
        raise OSError("sidecar disk failure")

    existing = output_dir / "last_take.json"
    existing.write_text('{"track_label": "Previous"}', encoding="utf-8")
    staged = staging_dir / "take.mkv"
    staged.write_bytes(b"fake")
    obs = FakeObsClient(staging_dir)
    obs.set_staged_file(staged)
    recorder = Recorder(
        obs,
        FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"}),
        output_dir,
        staging_dir,
    )
    wire_recorder_probes(recorder)
    monkeypatch.setattr("bridge.recorder.write_last_take", fail_write_last_take)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))

    assert list(output_dir.glob("Vocals_*.mkv"))
    assert not existing.exists()


def test_second_take_distinct_filenames(output_dir: Path, staging_dir: Path):
    obs = FakeObsClient(staging_dir)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    times = [
        datetime(2026, 5, 16, 14, 30, 22, tzinfo=timezone.utc),
        datetime(2026, 5, 16, 14, 31, 00, tzinfo=timezone.utc),
    ]
    idx = {"i": 0}

    def clock():
        return times[idx["i"]]

    recorder = Recorder(obs, metadata, output_dir, staging_dir, clock=clock)
    wire_recorder_probes(recorder)

    for _ in range(2):
        staged = staging_dir / f"take{idx['i']}.mkv"
        staged.write_bytes(b"v")
        obs.set_staged_file(staged)
        recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
        recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
        idx["i"] += 1

    files = list(output_dir.glob("*.mkv"))
    assert len(files) == 2
    assert files[0] != files[1]
