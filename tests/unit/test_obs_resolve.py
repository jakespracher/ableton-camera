import time

from bridge.obs_client import newest_file_in_dir, wait_for_stable_file


def test_newest_file_in_dir(staging_dir):
    older = staging_dir / "a.mkv"
    newer = staging_dir / "b.mkv"
    older.write_bytes(b"a")
    time.sleep(0.02)
    newer.write_bytes(b"b")
    assert newest_file_in_dir(staging_dir) == newer


def test_newest_ignores_partials(staging_dir):
    (staging_dir / "real.mkv").write_bytes(b"x")
    (staging_dir / "incomplete.part").write_bytes(b"x")
    assert newest_file_in_dir(staging_dir).name == "real.mkv"


def test_wait_for_stable_file(staging_dir):
    path = staging_dir / "take.mkv"
    path.write_bytes(b"1234")
    assert wait_for_stable_file(staging_dir, timeout_s=2.0, poll_interval_s=0.05) == path


def test_wait_for_stable_file_ignores_zero_byte_candidate(staging_dir):
    path = staging_dir / "take.mkv"
    path.write_bytes(b"")
    assert wait_for_stable_file(staging_dir, timeout_s=0.1, poll_interval_s=0.01) is None
