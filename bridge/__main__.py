from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from bridge.config import AppConfig, load_config
from bridge.naming import default_project_name, resolve_output_dir
from bridge.obs_client import ObsClientReal
from bridge.osc_client import OscListener
from bridge.osc_query import LiveOscQuery
from bridge.prompts import OutputDirCancelled, choose_output_dir
from bridge.recorder import Recorder
from bridge.recording_state import RecordingEdge, RecordingSignals, format_signals

logger = logging.getLogger(__name__)


def _default_config_path() -> Path:
    for candidate in (
        Path("config.local.yaml"),
        Path("config.yaml"),
        Path("config.example.yaml"),
    ):
        if candidate.is_file():
            return candidate
    return Path("config.example.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync OBS recording with Ableton Live")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to YAML config",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Skip picker and use this output directory",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        metavar="NAME",
        help="Project subfolder under the output directory (e.g. output/MyAlbum/Vocals_....mkv)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    try:
        if args.output_dir is not None:
            from bridge.prompts import validate_output_dir

            config.output_dir = validate_output_dir(args.output_dir, create=True)
        else:
            config.output_dir = choose_output_dir()
    except OutputDirCancelled as exc:
        logger.error("%s", exc)
        return 1
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    project_name = (args.project if args.project is not None else config.project_name).strip()
    if not project_name:
        project_name = default_project_name()
    session_output_dir = resolve_output_dir(config.output_dir, project_name)

    logger.info("Output folder: %s", session_output_dir)
    logger.info("Project: %s (under %s)", project_name, config.output_dir)
    logger.info("Config: %s", args.config.resolve())
    logger.info("OBS WebSocket: %s:%s", config.obs.host, config.obs.port)

    obs = ObsClientReal(
        config.obs.host,
        config.obs.port,
        config.obs.password,
        config.staging_dir,
    )
    def on_edge(edge: RecordingEdge, signals: RecordingSignals) -> None:
        recorder.on_edge(edge, signals)

    def on_count_in_finished(signals: RecordingSignals) -> None:
        recorder.on_count_in_finished(signals)

    listener = OscListener(
        config.osc.send_host,
        config.osc.send_port,
        config.osc.listen_host,
        config.osc.listen_port,
        on_edge,
        on_count_in_finished=on_count_in_finished,
    )
    metadata = LiveOscQuery(listener)
    recorder = Recorder(
        obs,
        metadata,
        session_output_dir,
        config.staging_dir,
        track_merge=config.track_merge,
        sync_offset_ms=config.sync_offset_ms,
    )
    recorder.set_counting_in_probe(
        listener.fetch_counting_in,
        osc_available=listener.count_in_osc_available,
        record_mode_latency_ms=listener.ms_since_record_mode_on,
    )
    listener.set_obs_recording_probe(lambda: recorder.is_recording)

    def shutdown(_signum=None, _frame=None) -> None:
        logger.info("Shutting down...")
        listener.stop()  # also stops clip poll thread
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        if obs.stop_orphan_recording():
            logger.info("Cleared orphaned OBS recording from a previous session")
    except Exception:
        logger.exception(
            "Could not check OBS record status; ensure OBS is running and WebSocket is enabled"
        )
        return 1

    try:
        listener.start()
    except OSError as exc:
        if getattr(exc, "errno", None) == 48:  # Address already in use
            logger.error(
                "Port %s is in use (another ableton-camera still running?). "
                "Kill it with: pkill -f ableton-camera",
                config.osc.listen_port,
            )
        raise

    listener.fetch_counting_in(0.5)
    logger.info(
        "Count-in OSC probe: available=%s is_counting_in=%s "
        "(if available=False, run scripts/patch_abletonosc_count_in.py and restart Live)",
        listener.count_in_osc_available(),
        listener.is_counting_in(),
    )
    logger.info(
        "Start policy: arrangement → OBS on record_mode 0→1 (arm record, then play when ready). "
        "Session → defer count-in if OSC works."
    )
    logger.info(
        "Initial Live state: %s",
        format_signals(listener.signals),
    )
    logger.info("Listening on %s:%s (use -v for debug)", config.osc.listen_host, config.osc.listen_port)
    signal.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
