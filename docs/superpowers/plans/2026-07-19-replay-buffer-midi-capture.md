# Replay Buffer MIDI Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build always-on OBS Replay Buffer support plus an `ableton-camera capture` command that asks the running bridge to invoke Live Capture MIDI and save a trimmed replay video.

**Architecture:** The long-running bridge owns OBS, AbletonOSC, output folder state, and a localhost JSON control server. The `capture` CLI is a thin client that sends `{command:"capture_midi"}` to the bridge and prints the result. Capture finalization is isolated in `bridge/capture.py` so OBS, OSC, CLI, and file-moving logic stay testable.

**Tech Stack:** Python 3.14, pytest, python-osc, obsws-python, ffmpeg command-line tool, stdlib `socketserver`/`socket`.

## Global Constraints

- Replay Buffer starts automatically when the long-running `ableton-camera` bridge starts.
- `ableton-camera capture` does not detect clicks on Live's native Capture MIDI button; it invokes Capture MIDI itself.
- The bridge owns capture execution because it owns the AbletonOSC reply port and OBS connection.
- Default control endpoint is `127.0.0.1:11002`.
- Capture video duration is `bars * beats_per_bar * 60 / tempo_bpm`.
- Existing record-sync behavior and extension placement behavior must keep passing.
- Unrelated untracked `scripts/*` files must remain unstaged.

---

## File Structure

- Modify `bridge/obs_client.py`: add Replay Buffer protocol methods and real OBS WebSocket calls.
- Modify `tests/fakes/fake_obs.py`: fake Replay Buffer state and replay file saves.
- Create `bridge/capture.py`: capture request model, duration math, ffmpeg trim helper, finalization service.
- Create `tests/unit/test_capture.py`: capture duration/finalization/control behavior tests.
- Modify `bridge/take_sidecar.py`: allow capture-specific metadata fields while preserving existing JSON.
- Modify `bridge/osc_client.py`: add tempo, time signature, current song time, and Capture MIDI send methods.
- Modify `bridge/osc_query.py`: expose capture metadata wrappers.
- Create `bridge/control.py`: localhost JSON request/response server and client.
- Modify `bridge/config.py`: add `ControlConfig(host="127.0.0.1", port=11002)`.
- Modify `bridge/__main__.py`: split parser into bridge mode and `capture` subcommand; start Replay Buffer/control server in bridge mode.
- Modify `docs/CAPTURE_MIDI.md` and `docs/SETUP.md`: document Replay Buffer setup, bridge startup, and `ableton-camera capture --bars 4`.

---

### Task 1: OBS Replay Buffer API

**Files:**
- Modify: `bridge/obs_client.py`
- Modify: `tests/fakes/fake_obs.py`
- Test: `tests/unit/test_obs_client.py`

**Interfaces:**
- Produces: `ObsClient.is_replay_buffer_active() -> bool`
- Produces: `ObsClient.start_replay_buffer() -> None`
- Produces: `ObsClient.save_replay_buffer() -> Path | None`
- Produces: `ObsClient.ensure_replay_buffer() -> bool`

- [ ] **Step 1: Write failing OBS tests**

Add tests like:

```python
def test_replay_buffer_status_reads_output_active(tmp_path):
    mock_ws = MagicMock()
    status = MagicMock()
    status.output_active = True
    mock_ws.get_replay_buffer_status.return_value = status

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", tmp_path)
        assert client.is_replay_buffer_active() is True


def test_save_replay_buffer_resolves_newest_stable_file(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    replay = staging / "replay.mov"
    mock_ws = MagicMock()

    def save():
        replay.write_bytes(b"video")

    mock_ws.save_replay_buffer.side_effect = save

    with patch("obsws_python.ReqClient", return_value=mock_ws):
        client = ObsClientReal("127.0.0.1", 4455, "", staging)
        assert client.save_replay_buffer() == replay
```

- [ ] **Step 2: Run failing tests**

Run: `.venv/bin/python -m pytest tests/unit/test_obs_client.py -q`

Expected: failures because replay methods do not exist.

- [ ] **Step 3: Implement OBS replay methods**

In `ObsClient` protocol add the four replay methods. In `ObsClientReal`, use:

```python
def is_replay_buffer_active(self) -> bool:
    response = self._connect().get_replay_buffer_status()
    return _record_output_active(response)

def start_replay_buffer(self) -> None:
    self._connect().start_replay_buffer()

def ensure_replay_buffer(self) -> bool:
    if self.is_replay_buffer_active():
        return True
    self.start_replay_buffer()
    return False

def save_replay_buffer(self) -> Path | None:
    before = newest_file_in_dir(self._staging_dir)
    self._connect().save_replay_buffer()
    return wait_for_new_stable_file(self._staging_dir, after=before)
```

Add `wait_for_new_stable_file(directory: Path, after: Path | None, ...)`.

- [ ] **Step 4: Update fake OBS**

Add fake fields:

```python
self.replay_buffer_active = False
self._replay_file: Path | None = None
```

Add methods matching the protocol.

- [ ] **Step 5: Verify**

Run: `.venv/bin/python -m pytest tests/unit/test_obs_client.py -q`

Expected: pass.

---

### Task 2: Capture Sidecar Metadata and Finalization

**Files:**
- Create: `bridge/capture.py`
- Modify: `bridge/take_sidecar.py`
- Test: `tests/unit/test_capture.py`
- Test: `tests/unit/test_take_sidecar.py`

**Interfaces:**
- Produces: `capture_seconds(bars: int, tempo_bpm: float, beats_per_bar: int) -> float`
- Produces: `CaptureContext`
- Produces: `finalize_capture_take(...) -> CaptureResult`

- [ ] **Step 1: Write failing capture math and sidecar tests**

```python
def test_capture_seconds_uses_tempo_and_signature():
    assert capture_seconds(bars=4, tempo_bpm=120, beats_per_bar=4) == 8
    assert capture_seconds(bars=2, tempo_bpm=90, beats_per_bar=3) == 4


def test_capture_sidecar_includes_capture_metadata(output_dir, staging_dir):
    source = staging_dir / "replay.mov"
    source.write_bytes(b"video")
    result = finalize_capture_take(
        source_path=source,
        output_dir=output_dir,
        track_label="Grand Piano",
        clock=lambda: datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc),
        sync_offset_ms=0,
        bars=4,
        tempo_bpm=120,
        beats_per_bar=4,
        live_current_song_time=32,
        trim_seconds=None,
    )
    payload = json.loads((output_dir / "last_take.json").read_text())
    assert payload["take_type"] == "capture_midi"
    assert payload["bars"] == 4
    assert payload["tempo_bpm"] == 120
    assert result.video_path.name.startswith("Grand_Piano_capture_")
```

- [ ] **Step 2: Run failing tests**

Run: `.venv/bin/python -m pytest tests/unit/test_capture.py tests/unit/test_take_sidecar.py -q`

Expected: failures because `bridge.capture` and metadata fields do not exist.

- [ ] **Step 3: Implement metadata-friendly sidecars**

In `TakeSidecar`, add:

```python
extra: dict[str, object] = field(default_factory=dict)
```

Merge `extra` into `to_json_dict()` after existing fields.

- [ ] **Step 4: Implement capture finalization**

`finalize_capture_take` should move/copy a source replay into output using `build_capture_filename(track_label, at, ext)` and call `write_take_sidecars` with `extra`.

- [ ] **Step 5: Verify**

Run: `.venv/bin/python -m pytest tests/unit/test_capture.py tests/unit/test_take_sidecar.py -q`

Expected: pass.

---

### Task 3: Live Capture MIDI Metadata

**Files:**
- Modify: `bridge/osc_client.py`
- Modify: `bridge/osc_query.py`
- Test: `tests/unit/test_osc_metadata_fetch.py`
- Test: `tests/unit/test_osc_query.py`

**Interfaces:**
- Produces: `OscListener.fetch_tempo(timeout_s: float) -> float`
- Produces: `OscListener.fetch_signature_numerator(timeout_s: float) -> int`
- Produces: `OscListener.fetch_current_song_time(timeout_s: float) -> float`
- Produces: `OscListener.capture_midi(destination: int) -> None`
- Produces: `LiveOscQuery.get_tempo() -> float`
- Produces: `LiveOscQuery.get_signature_numerator() -> int`
- Produces: `LiveOscQuery.get_current_song_time() -> float`
- Produces: `LiveOscQuery.capture_midi(destination: int) -> None`

- [ ] **Step 1: Write failing OSC tests**

```python
def test_fetch_capture_metadata():
    listener = _listener()

    def send(address, *args):
        if address == "/live/song/get/tempo":
            listener.inject(address, 123.0)
        elif address == "/live/song/get/signature_numerator":
            listener.inject(address, 3)
        elif address == "/live/song/get/current_song_time":
            listener.inject(address, 48.5)

    listener._send = send
    assert listener.fetch_tempo(0.5) == 123.0
    assert listener.fetch_signature_numerator(0.5) == 3
    assert listener.fetch_current_song_time(0.5) == 48.5


def test_capture_midi_sends_destination():
    listener = _listener()
    sent = []
    listener._send = lambda address, *args: sent.append((address, args))
    listener.capture_midi(2)
    assert sent == [("/live/song/capture_midi", (2,))]
```

- [ ] **Step 2: Run failing tests**

Run: `.venv/bin/python -m pytest tests/unit/test_osc_metadata_fetch.py tests/unit/test_osc_query.py -q`

Expected: failures for missing methods.

- [ ] **Step 3: Implement OSC fetchers and handlers**

Add storage fields `_tempo`, `_signature_numerator`, `_current_song_time`; handlers; dispatcher maps; `inject` branches; fetch methods that clear `_meta_event`, send the right `/live/song/get/...` address, wait, and return fallback values.

- [ ] **Step 4: Verify**

Run: `.venv/bin/python -m pytest tests/unit/test_osc_metadata_fetch.py tests/unit/test_osc_query.py -q`

Expected: pass.

---

### Task 4: Capture Service and Control Server

**Files:**
- Create: `bridge/control.py`
- Modify: `bridge/capture.py`
- Test: `tests/unit/test_capture.py`

**Interfaces:**
- Produces: `CaptureRequest(command: str, bars: int, destination: str)`
- Produces: `CaptureResponse(ok: bool, message: str, video_path: str | None = None, error: str | None = None)`
- Produces: `CaptureService.capture_midi(bars: int, destination: str) -> CaptureResponse`
- Produces: `start_control_server(host: str, port: int, handler: Callable[[CaptureRequest], CaptureResponse])`
- Produces: `send_capture_request(host: str, port: int, request: CaptureRequest, timeout_s: float = 10) -> CaptureResponse`

- [ ] **Step 1: Write failing control tests**

```python
def test_control_round_trip(tmp_path):
    responses = []

    def handle(request):
        responses.append(request)
        return CaptureResponse(ok=True, message="saved", video_path="/tmp/replay.mov")

    server = start_control_server("127.0.0.1", 0, handle)
    try:
        host, port = server.server_address
        response = send_capture_request(host, port, CaptureRequest(command="capture_midi", bars=4, destination="auto"))
    finally:
        server.shutdown()
        server.server_close()

    assert response.ok is True
    assert response.video_path == "/tmp/replay.mov"
    assert responses[0].bars == 4
```

- [ ] **Step 2: Run failing tests**

Run: `.venv/bin/python -m pytest tests/unit/test_capture.py -q`

Expected: failures for missing control types.

- [ ] **Step 3: Implement JSON line control**

Use one JSON object per connection. Request keys: `command`, `bars`, `destination`. Response keys: `ok`, `message`, `video_path`, `error`.

- [ ] **Step 4: Implement `CaptureService.capture_midi`**

Sequence:

```python
if not obs.ensure_replay_buffer():
    return CaptureResponse(ok=False, error="replay_buffer_started", message="Replay Buffer just started; try again after it has enough history.")
tempo = query.get_tempo()
beats = query.get_signature_numerator()
song_time = query.get_current_song_time()
track = resolve_track_label(query, track_merge)
query.capture_midi(destination_code(destination))
source = obs.save_replay_buffer()
seconds = capture_seconds(bars, tempo, beats)
result = finalize_capture_take(...)
return CaptureResponse(ok=True, message="Saved capture", video_path=str(result.video_path))
```

- [ ] **Step 5: Verify**

Run: `.venv/bin/python -m pytest tests/unit/test_capture.py -q`

Expected: pass.

---

### Task 5: CLI and Bridge Startup Wiring

**Files:**
- Modify: `bridge/config.py`
- Modify: `bridge/__main__.py`
- Test: `tests/unit/test_config_obs_host.py`
- Create or modify: `tests/unit/test_main_cli.py`

**Interfaces:**
- Produces: config field `control.host`
- Produces: config field `control.port`
- Produces: `ableton-camera capture --bars 4 --destination auto`

- [ ] **Step 1: Write failing config and CLI tests**

```python
def test_control_defaults():
    config = AppConfig.from_dict(base_config())
    assert config.control.host == "127.0.0.1"
    assert config.control.port == 11002


def test_capture_command_sends_control_request(monkeypatch):
    sent = {}

    def fake_send(host, port, request):
        sent["request"] = request
        return CaptureResponse(ok=True, message="saved", video_path="/tmp/video.mov")

    monkeypatch.setattr("bridge.__main__.send_capture_request", fake_send)
    assert main(["capture", "--bars", "4"]) == 0
    assert sent["request"].bars == 4
```

- [ ] **Step 2: Run failing tests**

Run: `.venv/bin/python -m pytest tests/unit/test_config_obs_host.py tests/unit/test_main_cli.py -q`

Expected: failures for missing config/CLI.

- [ ] **Step 3: Implement config defaults**

Add:

```python
@dataclass
class ControlConfig:
    host: str
    port: int
```

Read `control.host` and `control.port` with defaults.

- [ ] **Step 4: Split CLI parser**

Use subparsers. No subcommand means bridge mode. `capture` means client mode.

- [ ] **Step 5: Start Replay Buffer and control server in bridge mode**

After OBS orphan check:

```python
obs.ensure_replay_buffer()
control_server = start_control_server(config.control.host, config.control.port, capture_service.capture_midi)
```

Stop it in `shutdown`.

- [ ] **Step 6: Verify**

Run: `.venv/bin/python -m pytest tests/unit/test_config_obs_host.py tests/unit/test_main_cli.py -q`

Expected: pass.

---

### Task 6: Docs, Full Verification, Commit, Push, PR

**Files:**
- Modify: `docs/CAPTURE_MIDI.md`
- Modify: `docs/SETUP.md`

- [ ] **Step 1: Update docs**

Document:

```sh
ableton-camera --output-dir "/Volumes/Samsung 990 PRO 4TB/Video/Ableton Camera"
ableton-camera capture --bars 4
```

Mention OBS Output settings must enable Replay Buffer and set max duration longer than the requested bar length.

- [ ] **Step 2: Run full verification**

Run:

```sh
.venv/bin/python -m pytest -q
zsh -lc 'source ~/.nvm/nvm.sh && nvm use && npm --prefix extensions/ableton-camera-video test'
zsh -lc 'source ~/.nvm/nvm.sh && nvm use && npm --prefix extensions/ableton-camera-video run build'
git diff --check
```

Expected: all pass.

- [ ] **Step 3: Commit implementation**

```sh
git add bridge tests docs config.example.yaml
git commit -m "Add replay buffer MIDI capture"
```

- [ ] **Step 4: Push and create PR**

```sh
git push -u origin codex/replay-buffer-midi-capture
```

Open a PR against `main`.
