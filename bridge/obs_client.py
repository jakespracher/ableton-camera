from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

PARTIAL_SUFFIXES = (".part", ".tmp", ".partial")


class ObsClient(Protocol):
    def start_record(self) -> None: ...

    def stop_record(self) -> Path | None: ...


def newest_file_in_dir(directory: Path, *, ignore_suffixes: tuple[str, ...] = PARTIAL_SUFFIXES) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = [
        p
        for p in directory.iterdir()
        if p.is_file() and not any(p.name.endswith(s) for s in ignore_suffixes)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def wait_for_stable_file(
    directory: Path,
    *,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.2,
    stable_checks: int = 3,
) -> Path | None:
    deadline = time.monotonic() + timeout_s
    last_path: Path | None = None
    last_size: int | None = None
    stable_count = 0

    while time.monotonic() < deadline:
        path = newest_file_in_dir(directory)
        if path is None:
            time.sleep(poll_interval_s)
            continue
        size = path.stat().st_size
        if path == last_path and size == last_size:
            stable_count += 1
            if stable_count >= stable_checks:
                return path
        else:
            stable_count = 1
            last_path = path
            last_size = size
        time.sleep(poll_interval_s)
    return last_path


class ObsClientReal:
    def __init__(self, host: str, port: int, password: str, staging_dir: Path) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._staging_dir = staging_dir
        self._client = None

    def _connect(self):
        if self._client is not None:
            return self._client
        import obsws_python as obs

        self._client = obs.ReqClient(
            host=self._host,
            port=self._port,
            password=self._password,
            timeout=5,
        )
        return self._client

    def start_record(self) -> None:
        self._connect().start_record()

    def stop_record(self) -> Path | None:
        client = self._connect()
        output_path: Path | None = None
        try:
            response = client.stop_record()
            out = getattr(response, "output_path", None) or (
                response.datain.get("outputPath") if hasattr(response, "datain") else None
            )
            if out:
                output_path = Path(str(out))
        except Exception as exc:
            logger.warning("stop_record response missing path: %s", exc)

        if output_path and output_path.is_file():
            return output_path

        resolved = wait_for_stable_file(self._staging_dir)
        return resolved
