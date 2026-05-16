from pathlib import Path

import pytest

from bridge.config import load_config


def test_load_minimal_config(minimal_config, fixtures_dir):
    assert minimal_config.osc.send_port == 11000
    assert minimal_config.staging_dir == Path("/tmp/ableton-camera-staging")
    assert minimal_config.track_merge == "_"
    assert load_config(fixtures_dir / "config_minimal.yaml").obs.host == "127.0.0.1"


def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")
