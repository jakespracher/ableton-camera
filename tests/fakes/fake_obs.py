from __future__ import annotations

from pathlib import Path


class FakeObsClient:
    def __init__(self, staging_dir: Path) -> None:
        self.staging_dir = staging_dir
        self.recording = False
        self.calls: list[str] = []
        self._staged_file: Path | None = None

    def set_staged_file(self, path: Path) -> None:
        self._staged_file = path

    def start_record(self) -> None:
        self.calls.append("start")
        self.recording = True

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
