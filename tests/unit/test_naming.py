from datetime import datetime, timezone

from bridge.naming import build_filename, extension_from_path, sanitize_component


def test_sanitize_component_replaces_invalid_chars():
    assert sanitize_component("Vocals / Main") == "Vocals_Main"


def test_sanitize_empty_becomes_unknown():
    assert sanitize_component("   ") == "Unknown"


def test_build_filename_format():
    at = datetime(2026, 5, 16, 14, 30, 22, tzinfo=timezone.utc)
    assert build_filename("Vocals", at, ext="mkv") == "Vocals_2026-05-16_143022.mkv"


def test_extension_from_path():
    assert extension_from_path(__import__("pathlib").Path("clip.MOV")) == "MOV"
