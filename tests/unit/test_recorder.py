from datetime import datetime, timezone
from pathlib import Path

from freezegun import freeze_time

from bridge.recording_state import RecordingEdge, RecordingSignals
from bridge.recorder import Recorder
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
    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
    assert list(project_dir.glob("Vocals_*.mkv"))
    assert not list(output_dir.glob("*.mkv"))


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
