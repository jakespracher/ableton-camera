from __future__ import annotations

from pathlib import Path


class FakeObsClient:
    def __init__(self, staging_dir: Path) -> None:
        self.staging_dir = staging_dir
        self.recording = False
        self.replay_buffer_active = False
        self.calls: list[str] = []
        self._staged_file: Path | None = None
        self._replay_file: Path | None = None

    def set_staged_file(self, path: Path) -> None:
        self._staged_file = path

    def set_replay_file(self, path: Path) -> None:
        self._replay_file = path

    def is_recording(self) -> bool:
        return self.recording

    def stop_orphan_recording(self) -> bool:
        if not self.recording:
            return False
        self.stop_record()
        return True

    def start_record(self) -> None:
        self.calls.append("start")
        self.recording = True

    def is_replay_buffer_active(self) -> bool:
        return self.replay_buffer_active

    def start_replay_buffer(self) -> None:
        self.calls.append("start_replay")
        self.replay_buffer_active = True

    def ensure_replay_buffer(self) -> bool:
        if self.replay_buffer_active:
            return True
        self.start_replay_buffer()
        return False

    def save_replay_buffer(self) -> Path | None:
        self.calls.append("save_replay")
        if self._replay_file is not None:
            return self._replay_file
        path = self.staging_dir / "replay.mkv"
        path.write_bytes(b"fake replay")
        return path

    def stop_record(self) -> Path | None:
        self.calls.append("stop")
        self.recording = False
        if self._staged_file is not None:
            return self._staged_file
        if self.staging_dir is not None:
            path = self.staging_dir / "recording.mkv"
            path.write_bytes(b"fake video")
            return path
        return None
