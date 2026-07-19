# Replay Buffer MIDI Capture Design

## Goal

Add a capture workflow for improvised MIDI ideas:

1. Keep OBS Replay Buffer running while the normal `ableton-camera` bridge is running.
2. Add a one-shot `ableton-camera capture` command.
3. When invoked, the command tells Live to Capture MIDI and saves the OBS replay buffer.
4. The saved replay is trimmed to the last requested number of bars, moved into the project output folder, and published through the same sidecar/history files used by video placement.

This workflow provides one deliberate trigger for both Live Capture MIDI and video capture. It does not passively observe clicks on Live's native Capture MIDI UI button.

## Approach

Use the long-running bridge as the replay-buffer owner. On startup, after OBS connection succeeds, the bridge checks Replay Buffer status and starts it when it is inactive. Replay Buffer stays on until OBS or the bridge stops.

Add a `capture` subcommand to the CLI:

```sh
ableton-camera capture --bars 4
```

The command is a one-shot control client. It connects to the long-running bridge over a local TCP control port. The bridge performs the capture because it already owns the AbletonOSC reply port and OBS connection. This avoids a second process fighting the bridge for OSC replies on `listen_port`.

Default control endpoint:

```text
127.0.0.1:11002
```

If the bridge sees Replay Buffer is inactive when a capture request arrives, it starts the buffer and returns a clear response that the buffer needs time to fill before a useful capture can be saved.

## Data Flow

1. The long-running bridge resolves config, output root, and project folder using the existing CLI rules.
2. The bridge starts a localhost control server after OBS, AbletonOSC, and Replay Buffer initialization.
3. `ableton-camera capture --bars 4` sends one JSON request to the control server and waits for one JSON response.
4. The bridge queries Live for tempo, time signature, current song time, and track label.
5. The bridge sends `/live/song/capture_midi` to Live through AbletonOSC.
6. The bridge asks OBS to `SaveReplayBuffer`.
7. The bridge resolves the newest replay file in the staging directory.
8. The bridge computes requested duration:

```text
seconds = bars * beats_per_bar * 60 / tempo_bpm
```

9. The bridge trims the replay to the final `seconds` with ffmpeg when ffmpeg is available.
10. The bridge moves the trimmed file into the project output folder.
11. The bridge writes `last_take.json` and appends `take_history.json`.

## Sidecar Metadata

Capture sidecars must remain compatible with the existing extension and add these fields for capture-mode takes:

- `take_type`: `recording` or `capture_midi`
- `bars`: requested bars for capture mode
- `tempo_bpm`: Live tempo used for duration conversion
- `beats_per_bar`: time-signature numerator
- `live_current_song_time`: Live's current arrangement time near capture
- `source_video_path`: original replay-buffer file when a trimmed derivative is created

Existing fields stay present:

- `video_path`
- `track_label`
- `recorded_start`
- `finalized_at`
- `sync_offset_ms`

## Placement Behavior

The extension can continue to place captured videos using the existing latest/all workflows. For this first PR, placement should use the selected clip start plus `sync_offset_ms`, exactly like normal takes. The new timing metadata creates room for a later placement improvement but does not block capture mode.

## Error Handling

- OBS not reachable: fail with the existing OBS connection error.
- Replay Buffer disabled in OBS settings: show the OBS WebSocket error and explain that Replay Buffer must be enabled in OBS Output settings.
- Replay Buffer inactive: start it and exit without saving, so the user does not get an empty capture.
- No replay file found after save: fail without updating sidecars.
- ffmpeg missing: keep the full replay file, log a warning, and still write sidecars.
- ffmpeg trim failure: fail without replacing the original replay file or updating sidecars.
- Live Capture MIDI no-ops: still save the replay, because AbletonOSC does not currently expose a reliable `can_capture_midi` preflight.

## Tests

Add unit tests for:

- OBS replay-buffer status parsing, start, save, and saved-file resolution.
- Local capture control request/response parsing.
- Capture duration calculation from bars, tempo, and time signature.
- Capture finalization writes sidecar/history with `take_type: capture_midi`.
- `capture` starts Replay Buffer and exits clearly when the buffer was inactive.
- Existing record-sync tests still pass.

Add CLI tests around parser behavior for:

- default `--bars`
- `--destination auto|session|arrangement`
- control host/port defaults

## Out Of Scope

- Detecting clicks on Live's native Capture MIDI button.
- Adding Max for Live integration.
- Perfect sample-clock sync or LTC.
- Matching video length to the captured MIDI clip length.
