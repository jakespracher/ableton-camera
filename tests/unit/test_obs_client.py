from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bridge.obs_client import ObsClientReal, newest_file_in_dir


def test_newest_empty_dir(tmp_path):
    assert newest_file_in_dir(tmp_path) is None


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
