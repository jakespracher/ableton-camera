# Ableton Camera

Sync video recording (iPhone via Continuity Camera → OBS on Mac) with Ableton Live. Start/stop OBS when Live starts/stops **arrangement** or **session** recording; save renamed files to a folder you choose at launch.

## Docs

- [Design](docs/DESIGN.md) — architecture, triggers, naming, sync
- [Build plan](docs/PLAN.md) — phased implementation
- [TDD plan](docs/TDD_PLAN.md) — test harness, fakes, and test order per phase
- [Sync / alignment](docs/SYNC.md) — clap test and OBS sync offset
- [Video placement](docs/VIDEO_PLACEMENT.md) — Ableton Extension workflow for placing video under arrangement takes
- [Capture MIDI](docs/CAPTURE_MIDI.md) — one-command MIDI capture with OBS Replay Buffer video

## Status

MVP bridge implemented; see [Build plan](docs/PLAN.md). Capture MIDI + replay buffer support is available through `ableton-camera capture`. Run tests: `pip install -e ".[dev]" && pytest`.

## Quick start

1. Install [AbletonOSC](https://github.com/ideoforms/AbletonOSC) and enable it in Live’s Control Surface preferences.
2. Enable OBS WebSocket; set OBS to record into a staging folder (see `config.example.yaml`).
3. `pip install -e .`
4. `ableton-camera` (or `python -m bridge`) — pick output folder, then record in Live (arrangement or session).

Use `--output-dir /path/to/folder` to skip the picker. Copy `config.example.yaml` to `config.local.yaml` for OBS password and paths.

For retroactive MIDI takes, keep the bridge running and trigger:

```bash
ableton-camera capture --bars 4 --destination arrangement
```
