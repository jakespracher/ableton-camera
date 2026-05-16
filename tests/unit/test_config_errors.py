import pytest

from bridge.config import load_config


def test_invalid_config_not_dict(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("just a string\n")
    with pytest.raises(ValueError, match="Invalid config"):
        load_config(path)
