from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bridge.recording_state import RecordingEdge, RecordingSignals
from bridge.recorder import Recorder
from tests.conftest import wire_recorder_probes
from tests.fakes.fake_osc_query import FakeOscQuery


def test_stop_without_staged_file_logs_and_does_not_crash(output_dir, staging_dir, caplog):
    obs = MagicMock()
    obs.start_record = MagicMock()
    obs.stop_record = MagicMock(return_value=None)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    recorder = Recorder(obs, metadata, output_dir, staging_dir)
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    with caplog.at_level("ERROR"):
        recorder.on_edge(RecordingEdge.STOPPED, RecordingSignals(0, 0, False))
    assert "No recording file" in caplog.text


def test_start_obs_failure_resets_state(output_dir, staging_dir):
    obs = MagicMock()
    obs.start_record = MagicMock(side_effect=RuntimeError("obs down"))
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Vocals"})
    recorder = Recorder(obs, metadata, output_dir, staging_dir)
    wire_recorder_probes(recorder)

    recorder.on_edge(RecordingEdge.STARTED, RecordingSignals(1, 0, False))
    assert recorder.is_recording is False
