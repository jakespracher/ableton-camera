from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from bridge.config import AppConfig, load_config
from bridge.obs_client import ObsClientReal
from bridge.osc_client import OscListener
from bridge.osc_query import LiveOscQuery
from bridge.prompts import OutputDirCancelled, choose_output_dir
from bridge.recorder import Recorder
from bridge.recording_state import RecordingEdge, RecordingSignals

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

    logger.info("Output folder: %s", config.output_dir)
    logger.info("Config: %s", args.config.resolve())
    logger.info("OBS WebSocket: %s:%s", config.obs.host, config.obs.port)

    obs = ObsClientReal(
        config.obs.host,
        config.obs.port,
        config.obs.password,
        config.staging_dir,
    )
    recorder: Recorder | None = None

    def on_edge(edge: RecordingEdge, signals: RecordingSignals) -> None:
        assert recorder is not None
        recorder.on_edge(edge, signals)

    listener = OscListener(
        config.osc.send_host,
        config.osc.send_port,
        config.osc.listen_host,
        config.osc.listen_port,
        on_edge,
    )
    metadata = LiveOscQuery(listener)
    recorder = Recorder(
        obs,
        metadata,
        config.output_dir,
        config.staging_dir,
        track_merge=config.track_merge,
    )

    def shutdown(_signum=None, _frame=None) -> None:
        logger.info("Shutting down...")
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    listener.start()
    logger.info("Listening for Ableton recording (arrangement + session)...")
    signal.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
