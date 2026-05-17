from datetime import datetime, timezone

from pathlib import Path

from bridge.naming import (
    build_filename,
    default_project_name,
    extension_from_path,
    resolve_output_dir,
    sanitize_component,
)


def test_sanitize_component_replaces_invalid_chars():
    assert sanitize_component("Vocals / Main") == "Vocals_Main"


def test_sanitize_empty_becomes_unknown():
    assert sanitize_component("   ") == "Unknown"


def test_build_filename_format():
    at = datetime(2026, 5, 16, 14, 30, 22, tzinfo=timezone.utc)
    assert build_filename("Vocals", at, ext="mkv") == "Vocals_2026-05-16_143022.mkv"


def test_default_project_name_is_local_date():
    at = datetime(2026, 5, 16, 23, 59, 0, tzinfo=timezone.utc)
    assert default_project_name(at) == "2026-05-16"


def test_resolve_output_dir_without_project(tmp_path: Path):
    base = tmp_path / "videos"
    assert resolve_output_dir(base, None) == base
    assert resolve_output_dir(base, "") == base


def test_resolve_output_dir_creates_project_subfolder(tmp_path: Path):
    base = tmp_path / "videos"
    assert resolve_output_dir(base, "My Album") == base / "My_Album"


def test_extension_from_path():
    assert extension_from_path(__import__("pathlib").Path("clip.MOV")) == "MOV"
