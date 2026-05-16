import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bridge.config import AppConfig, load_config


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_config(fixtures_dir: Path) -> AppConfig:
    return load_config(fixtures_dir / "config_minimal.yaml")


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "output"
    dest.mkdir()
    return dest


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    return staging
