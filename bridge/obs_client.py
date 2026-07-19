from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

PARTIAL_SUFFIXES = (".part", ".tmp", ".partial")
STOP_RECORD_ATTEMPTS = 5
STOP_RECORD_RETRY_DELAY_S = 0.4


class ObsClient(Protocol):
    def is_recording(self) -> bool: ...

    def start_record(self) -> None: ...

    def stop_record(self) -> Path | None: ...

    def stop_orphan_recording(self) -> bool: ...

    def is_replay_buffer_active(self) -> bool: ...

    def start_replay_buffer(self) -> None: ...

    def ensure_replay_buffer(self) -> bool: ...

    def save_replay_buffer(self) -> Path | None: ...


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
    min_size_bytes: int = 1,
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
        if size < min_size_bytes:
            last_path = path
            last_size = size
            stable_count = 0
            time.sleep(poll_interval_s)
            continue
        if path == last_path and size == last_size:
            stable_count += 1
            if stable_count >= stable_checks:
                return path
        else:
            stable_count = 1
            last_path = path
            last_size = size
        time.sleep(poll_interval_s)
    return None


def wait_for_new_stable_file(
    directory: Path,
    *,
    after: Path | None,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.2,
    stable_checks: int = 3,
    min_size_bytes: int = 1,
) -> Path | None:
    deadline = time.monotonic() + timeout_s
    last_path: Path | None = None
    last_size: int | None = None
    stable_count = 0
    after_mtime = after.stat().st_mtime if after is not None and after.exists() else None

    while time.monotonic() < deadline:
        path = newest_file_in_dir(directory)
        if path is None:
            time.sleep(poll_interval_s)
            continue
        if after is not None and path == after:
            time.sleep(poll_interval_s)
            continue
        if after_mtime is not None and path.stat().st_mtime < after_mtime:
            time.sleep(poll_interval_s)
            continue
        size = path.stat().st_size
        if size < min_size_bytes:
            last_path = path
            last_size = size
            stable_count = 0
            time.sleep(poll_interval_s)
            continue
        if path == last_path and size == last_size:
            stable_count += 1
            if stable_count >= stable_checks:
                return path
        else:
            stable_count = 1
            last_path = path
            last_size = size
        time.sleep(poll_interval_s)
    return None


def _record_output_active(response: object) -> bool:
    active = getattr(response, "output_active", None)
    if active is not None:
        return bool(active)
    datain = getattr(response, "datain", None)
    if isinstance(datain, dict):
        return bool(datain.get("outputActive"))
    return False


def _profile_parameter_value(response: object) -> str | None:
    value = getattr(response, "parameter_value", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    datain = getattr(response, "datain", None)
    if isinstance(datain, dict):
        value = datain.get("parameterValue")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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

    def is_recording(self) -> bool:
        try:
            response = self._connect().get_record_status()
        except Exception:
            logger.exception("Failed to query OBS record status")
            raise
        return _record_output_active(response)

    def start_record(self) -> None:
        self._connect().start_record()

    def is_replay_buffer_active(self) -> bool:
        try:
            response = self._connect().get_replay_buffer_status()
        except Exception:
            logger.exception("Failed to query OBS replay buffer status")
            raise
        return _record_output_active(response)

    def start_replay_buffer(self) -> None:
        self._connect().start_replay_buffer()

    def ensure_replay_buffer(self) -> bool:
        if self.is_replay_buffer_active():
            return True
        logger.info("OBS Replay Buffer inactive; starting it now")
        self.start_replay_buffer()
        return False

    def _recording_directory(self) -> Path:
        try:
            client = self._connect()
            mode = _profile_parameter_value(client.get_profile_parameter("Output", "Mode"))
            if mode and mode.lower() == "advanced":
                response = client.get_profile_parameter("AdvOut", "RecFilePath")
            else:
                response = client.get_profile_parameter("SimpleOutput", "FilePath")
            raw_path = _profile_parameter_value(response)
        except Exception as exc:
            logger.debug("Could not read OBS recording path; using configured staging dir: %s", exc)
            return self._staging_dir

        if not raw_path:
            return self._staging_dir

        directory = Path(raw_path).expanduser()
        if directory != self._staging_dir:
            logger.warning(
                "OBS recording path is %s, but config staging_dir is %s; watching OBS path",
                directory,
                self._staging_dir,
            )
        return directory

    def save_replay_buffer(self) -> Path | None:
        directory = self._recording_directory()
        before = newest_file_in_dir(directory)
        self._connect().save_replay_buffer()
        return wait_for_new_stable_file(directory, after=before)

    def stop_orphan_recording(self) -> bool:
        """Stop OBS if it was left recording (e.g. after a bridge crash)."""
        if not self.is_recording():
            return False
        logger.warning("OBS was still recording; stopping orphaned capture")
        self.stop_record()
        return True

    def stop_record(self) -> Path | None:
        client = self._connect()
        output_path: Path | None = None
        last_error: Exception | None = None
        still_recording_after_error: bool | None = None
        try:
            for attempt in range(1, STOP_RECORD_ATTEMPTS + 1):
                try:
                    response = client.stop_record()
                    out = getattr(response, "output_path", None) or (
                        response.datain.get("outputPath") if hasattr(response, "datain") else None
                    )
                    if out:
                        output_path = Path(str(out))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    try:
                        still_recording = self.is_recording()
                    except Exception as status_exc:
                        logger.warning("Could not verify OBS recording state after StopRecord failure: %s", status_exc)
                        return None
                    still_recording_after_error = still_recording
                    if not still_recording:
                        logger.warning(
                            "OBS StopRecord failed, but OBS is no longer recording; resolving finalized file: %s",
                            exc,
                        )
                        last_error = None
                        break
                    if attempt >= STOP_RECORD_ATTEMPTS:
                        break
                    logger.warning(
                        "OBS StopRecord failed (attempt %s/%s): %s",
                        attempt,
                        STOP_RECORD_ATTEMPTS,
                        exc,
                    )
                    time.sleep(STOP_RECORD_RETRY_DELAY_S)

            if last_error is not None and (still_recording_after_error if still_recording_after_error is not None else self.is_recording()):
                logger.warning("OBS is still recording after StopRecord failed: %s", last_error)
                return None
        except Exception as exc:
            logger.warning("Could not verify OBS recording state after StopRecord failure: %s", exc)
            return None

        if output_path and output_path.is_file():
            return output_path

        resolved = wait_for_stable_file(self._recording_directory())
        return resolved
