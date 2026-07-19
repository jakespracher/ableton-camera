from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bridge.obs_client import ObsClientReal, newest_file_in_dir


def test_newest_empty_dir(tmp_path):
    assert newest_file_in_dir(tmp_path) is None


def test_is_recording_reads_output_active(tmp_path):
    mock_ws = MagicMock()
    status = MagicMock()
    status.output_active = True
    mock_ws.get_record_status.return_value = status

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", tmp_path)
        assert client.is_recording() is True

    status.output_active = None
    status.datain = {"outputActive": False}
    assert client.is_recording() is False


def test_stop_orphan_recording_when_active(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    mock_ws = MagicMock()
    status = MagicMock()
    status.output_active = True
    mock_ws.get_record_status.return_value = status
    stop_resp = MagicMock()
    stop_resp.output_path = str(staging / "orphan.mkv")
    mock_ws.stop_record.return_value = stop_resp

    def stop_and_clear_recording():
        status.output_active = False
        return stop_resp

    mock_ws.stop_record.side_effect = stop_and_clear_recording

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        (staging / "orphan.mkv").write_bytes(b"x")
        assert client.stop_orphan_recording() is True
        assert client.stop_orphan_recording() is False

    mock_ws.stop_record.assert_called_once()


def test_obs_client_real_start_stop(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    mock_ws = MagicMock()
    stop_resp = MagicMock()
    stop_resp.output_path = str(staging / "out.mkv")
    mock_ws.stop_record.return_value = stop_resp

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        client.start_record()
        (staging / "out.mkv").write_bytes(b"x")
        path = client.stop_record()

    assert path == staging / "out.mkv"
    mock_ws.start_record.assert_called_once()
    mock_ws.stop_record.assert_called_once()


def test_replay_buffer_status_reads_output_active(tmp_path):
    mock_ws = MagicMock()
    status = MagicMock()
    status.output_active = True
    mock_ws.get_replay_buffer_status.return_value = status

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", tmp_path)
        assert client.is_replay_buffer_active() is True

    status.output_active = None
    status.datain = {"outputActive": False}
    assert client.is_replay_buffer_active() is False


def test_ensure_replay_buffer_starts_when_inactive(tmp_path):
    mock_ws = MagicMock()
    inactive = MagicMock()
    inactive.output_active = False
    mock_ws.get_replay_buffer_status.return_value = inactive

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", tmp_path)
        assert client.ensure_replay_buffer() is False

    mock_ws.start_replay_buffer.assert_called_once()


def test_save_replay_buffer_resolves_newest_stable_file(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    existing = staging / "existing.mov"
    existing.write_bytes(b"old")
    replay = staging / "replay.mov"
    mock_ws = MagicMock()

    def save_replay():
        replay.write_bytes(b"video")

    mock_ws.save_replay_buffer.side_effect = save_replay

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        assert client.save_replay_buffer() == replay

    mock_ws.save_replay_buffer.assert_called_once()


def test_save_replay_buffer_uses_obs_advanced_recording_path(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    actual = tmp_path / "actual"
    staging.mkdir()
    actual.mkdir()
    mock_ws = MagicMock()

    def profile_parameter(category: str, parameter: str):
        values = {
            ("Output", "Mode"): "Advanced",
            ("AdvOut", "RecFilePath"): str(actual),
        }
        return SimpleNamespace(parameter_value=values[(category, parameter)])

    watched: list[Path] = []

    def fake_wait(directory: Path, **_kwargs):
        watched.append(directory)
        return directory / "replay.mov"

    mock_ws.get_profile_parameter.side_effect = profile_parameter
    monkeypatch.setattr("bridge.obs_client.wait_for_new_stable_file", fake_wait)

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        assert client.save_replay_buffer() == actual / "replay.mov"

    assert watched == [actual]
    mock_ws.save_replay_buffer.assert_called_once()


def test_stop_record_does_not_return_fallback_file_when_obs_still_active(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    active_file = staging / "active.mov"
    active_file.write_bytes(b"still recording")
    monkeypatch.setattr("bridge.obs_client.STOP_RECORD_ATTEMPTS", 2)
    monkeypatch.setattr("bridge.obs_client.STOP_RECORD_RETRY_DELAY_S", 0)
    mock_ws = MagicMock()
    mock_ws.stop_record.side_effect = RuntimeError("StopRecord failed")
    status = MagicMock()
    status.output_active = True
    mock_ws.get_record_status.return_value = status

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        assert client.stop_record() is None

    assert mock_ws.stop_record.call_count == 2
    assert mock_ws.get_record_status.call_count == 2


def test_stop_record_resolves_file_when_failed_stop_already_stopped_obs(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    finalized_file = staging / "finalized.mov"
    finalized_file.write_bytes(b"finalized")
    monkeypatch.setattr("bridge.obs_client.STOP_RECORD_ATTEMPTS", 3)
    monkeypatch.setattr("bridge.obs_client.STOP_RECORD_RETRY_DELAY_S", 0)
    mock_ws = MagicMock()
    mock_ws.stop_record.side_effect = RuntimeError("StopRecord returned code 501")
    status = MagicMock()
    status.output_active = False
    mock_ws.get_record_status.return_value = status

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        assert client.stop_record() == finalized_file

    mock_ws.stop_record.assert_called_once()
    mock_ws.get_record_status.assert_called_once()
