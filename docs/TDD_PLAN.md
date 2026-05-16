# TDD plan

Test-driven implementation guide for [DESIGN.md](./DESIGN.md), aligned with build [PLAN.md](./PLAN.md).

**Principle:** Write a failing automated test → implement the minimum code → refactor → repeat. Manual checks (Live, OBS, Continuity) stay as a thin **smoke** layer on top; everything else runs headless in CI.

---

## Test pyramid

```text
        ┌─────────────────────────┐
        │  Manual smoke (few)     │  Live + OBS + Continuity
        ├─────────────────────────┤
        │  Integration (some)     │  Fake OSC peer, file moves
        ├─────────────────────────┤
        │  Unit (most)            │  Pure logic, fakes, contracts
        └─────────────────────────┘
```

| Layer | Runs in CI? | Needs Live/OBS? | Purpose |
|-------|-------------|-----------------|--------|
| **Unit** | Yes | No | Logic, state machine, naming, config |
| **Integration** | Yes | No (fakes) or optional OBS job | OSC UDP, file move, wired recorder |
| **Contract** | Yes | No | OSC address/arity matches AbletonOSC README |
| **Smoke / e2e** | No (local) | Yes | Real AbletonOSC + OBS + Continuity |

---

## Harness overview

### Tooling

| Tool | Role |
|------|------|
| **pytest** | Runner, fixtures, parametrize |
| **pytest-cov** | Coverage on `bridge/` (target 85%+ for non-`__main__` modules) |
| **freezegun** | Deterministic `{timestamp}` in filenames |
| **`tmp_path` / `tmp_path_factory`** | Staging + output dirs per test |
| **`unittest.mock` / `pytest-mock`** | Patch picker, UDP ports, OBS client |

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "pytest-mock>=3", "freezegun>=1.4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: uses threads, UDP, or filesystem timing",
    "obs: requires running OBS with WebSocket",
    "live: requires Ableton Live + AbletonOSC",
]
addopts = "-m 'not obs and not live'"   # default: fast suite only
```

**Default developer command:** `pytest` (unit + integration with fakes).

**Before release / locally:** `pytest -m ""` then `pytest -m obs` then manual live smoke.

### Repository layout

```
tests/
  conftest.py              # shared fixtures, marker registration
  unit/
    test_naming.py
    test_recording_state.py
    test_config.py
    test_prompts.py
    test_metadata.py
    test_recorder.py
    test_obs_resolve.py
  integration/
    test_osc_listener.py
    test_finalize_move.py
  contract/
    test_abletonosc_addresses.py
  fakes/
    fake_obs.py              # in-memory OBS (records Start/Stop calls)
    fake_osc_peer.py         # simulates AbletonOSC replies
    osc_test_server.py       # binds 11000/11001 on localhost for one test
  fixtures/
    config_minimal.yaml
```

Production code should expose **test seams**:

| Module | Seam |
|--------|------|
| `prompts.py` | `choose_output_dir(prompt_fn=...)` injectable |
| `obs_client.py` | `ObsClient` protocol; `ObsClientReal` vs tests use `FakeObsClient` |
| `osc_client.py` | `OscGateway` with `send()` / register handler; tests use `FakeOscPeer` |
| `recorder.py` | Constructor takes `obs`, `osc`, `output_dir`, `staging_dir`, `clock` |

Keep **pure functions** in dedicated modules (easy TDD, no mocks):

- `bridge/naming.py` — `sanitize_component()`, `build_filename(track, at: datetime) -> str`
- `bridge/recording_state.py` — `RecordingState` dataclass + `apply_update(arrangement, session) -> edges`

---

## Fakes (core of the harness)

### `FakeObsClient`

Records call sequence; simulates staging file appearance.

```python
# Behavior contract tests rely on:
start_record() -> None          # sets recording=True
stop_record() -> Path | None    # creates empty file in tmp staging if not set
# Tests inject pre-built staging file to test resolve/newest-file logic
```

### `FakeOscPeer`

Implements the subset of AbletonOSC the bridge uses.

| Outbound (bridge → 11000) | Fake response (→ 11001) |
|---------------------------|-------------------------|
| `/live/song/start_listen/record_mode` | ack (optional) |
| `/live/song/get/record_mode` | reply `0` or `1` |
| `/live/song/start_listen/session_record_status` | ack |
| `/live/song/get/session_record_status` | reply `0` or `2` (configurable) |
| `/live/song/get/num_tracks` | reply `N` |
| `/live/track/get/arm` + id | reply `track_id, 0/1` |
| `/live/track/get/name` + id | reply `track_id, "Vocals"` |
| `/live/view/get/selected_track` | reply `index` |

**Drive tests** by calling `fake.emit("/live/song/get/record_mode", 1)` into the bridge listener.

### `osc_test_server` (integration)

Lightweight UDP thread:

- Listens on `127.0.0.1:11001` (bridge’s listen port in test config).
- Records messages sent to `11000`.
- Allows tests to push OSC packets to the bridge as if from AbletonOSC.

Use ephemeral ports in tests (`port=0`) except contract tests that assert default 11000/11001 strings in config only.

---

## TDD order mapped to build phases

Each subsection is the **recommended test-writing order** within that phase. Implement production code only to satisfy the listed tests.

### Phase 0 — Environment (no TDD)

Manual only; optional `scripts/smoke_abletonosc.sh` and `scripts/smoke_obs.py` (not pytest — run by hand).

**Gate before Phase 1:** smoke scripts pass once on your machine.

---

### Phase 1 — Scaffold + folder prompt

**Set up harness first** (before feature code):

1. `pyproject.toml` + `tests/conftest.py` with `minimal_config` fixture loading `tests/fixtures/config_minimal.yaml`.
2. Empty `bridge/` package; `pytest` collects zero tests → add first test.

| Order | Test file | Example tests (write failing first) |
|-------|-----------|-------------------------------------|
| 1 | `test_config.py` | loads yaml; expands `~/` on `staging_dir`; missing file raises |
| 2 | `test_prompts.py` | `validate_output_dir` accepts writable dir; rejects file path; creates dir when asked |
| 3 | `test_prompts.py` | `choose_output_dir(prompt_fn=lambda: "/tmp/x")` returns Path; cancel raises `SystemExit` |
| 4 | `test_naming.py` | `sanitize_component` strips bad chars; `build_filename` format |

| Production module | Driven by |
|-------------------|-----------|
| `bridge/config.py` | `test_config.py` |
| `bridge/prompts.py` | `test_prompts.py` |
| `bridge/naming.py` | `test_naming.py` |

**Integration (optional):** none yet.

**Manual:** `python -m bridge` with injected `prompt_fn` in dev; picker tested once by hand.

---

### Phase 2 — OBS client

Introduce `ObsClient` protocol + `FakeObsClient` in `tests/fakes/` before `ObsClientReal`.

| Order | Test file | Example tests |
|-------|-----------|---------------|
| 1 | `test_obs_resolve.py` | `newest_file_in_dir(tmp_path)` picks latest mtime; ignores `.part` if we filter |
| 2 | `test_obs_resolve.py` | stable size poll: returns when size unchanged (mock time or small wait with tiny file) |
| 3 | `unit` or `integration` with fake | `ObsClientReal` mocked websocket: `start_record` sends correct op (mock `obsws`) |

| Production module | Notes |
|-------------------|--------|
| `bridge/obs_client.py` | `resolve_recorded_file(staging_dir) -> Path` pure enough to test without WS |
| `@pytest.mark.obs` | One test: real `StartRecord`/`StopRecord` if `OBS_WEBSOCKET_PASSWORD` set |

**TDD loop:** resolve logic first (no network), then thin WebSocket wrapper.

---

### Phase 3 — OSC + combined recording state

**Pure logic first** (fastest TDD payoff):

| Order | Test file | Example tests |
|-------|-----------|---------------|
| 1 | `test_recording_state.py` | `(0,0)→idle`; `(1,0)→start`; `(0,2)→start`; `(1,2)→no second start` |
| 2 | `test_recording_state.py` | `(1,2)→(1,0)` no stop; `(1,2)→(0,0)` stop |
| 3 | `test_recording_state.py` | boot sync: initial `(1,0)` emits `started` if was idle |

Document discovered `session_record_status` values in a **parametrize** table once known:

```python
@pytest.mark.parametrize("status,expected_session_on", [(0, False), (1, True), ...])
```

| Order | Test file | Example tests |
|-------|-----------|---------------|
| 4 | `test_osc_listener.py` | on startup, fake receives both `start_listen` addresses |
| 5 | `test_osc_listener.py` | emit `record_mode=1` → handler called with `recording_active=True` |
| 6 | `test_osc_listener.py` | session only on/off |
| 7 | `contract/test_abletonosc_addresses.py` | snapshot list of OSC paths used by bridge (guard against typos) |

| Production module | Driven by |
|-------------------|-----------|
| `bridge/recording_state.py` | `test_recording_state.py` |
| `bridge/osc_client.py` | `test_osc_listener.py` + fake peer |

**Not yet:** OBS calls from OSC handler (recorder wires that in Phase 5).

---

### Phase 4 — Track metadata

Test against `FakeOscPeer` only — no Live.

| Order | Test file | Example tests |
|-------|-----------|---------------|
| 1 | `test_metadata.py` | one armed track → `"Vocals"` |
| 2 | `test_metadata.py` | two armed → `"Vocals_Guitar"` (or first-only if design decision changes) |
| 3 | `test_metadata.py` | none armed, selected index 2 → track 2 name |
| 4 | `test_metadata.py` | none armed, no name → `"UnknownTrack"` |
| 5 | `test_metadata.py` | OSC query order / track count loop 0..N-1 |

| Production module | Driven by |
|-------------------|-----------|
| `bridge/metadata.py` | `get_track_label(osc) -> str` |

---

### Phase 5 — Recorder + finalize (integration-heavy)

| Order | Test file | Example tests |
|-------|-----------|---------------|
| 1 | `test_recorder.py` | start edge → `obs.start_record` once; captures metadata snapshot |
| 2 | `test_recorder.py` | stop edge → `obs.stop_record` + file moved to `output_dir` with `build_filename` name |
| 3 | `test_recorder.py` | second take → two distinct filenames (freezegun tick) |
| 4 | `test_recorder.py` | OBS failure on start → log error, stay idle, recover on next edge |
| 5 | `test_recorder.py` | stop with no staging file → error logged, idle, no crash |
| 6 | `test_finalize_move.py` | move not copy; source gone; dest exists |
| 7 | `integration/test_recorder_osc.py` | wire `OscListener` + `Recorder` + fakes; emit OSC sequence → fake OBS state |

Use **freezegun** on start timestamp so filename assertions are exact.

| Production module | Driven by |
|-------------------|-----------|
| `bridge/recorder.py` | all above |

**Manual smoke (checklist, not pytest):**

- [ ] Session record in Live
- [ ] Arrangement record in Live
- [ ] File in user-picked folder

---

### Phase 6 — Sync doc

No automated tests; optional `test_sync_doc_exists` if `SYNC.md` is added.

---

### Phase 7 — Polish

| Feature | Test approach |
|---------|----------------|
| Remember last folder | `test_prompts.py` reads/writes `last_output_dir` in tmp config home |
| Count-in delay | extend `recording_state` or recorder with `is_counting_in`; parametrize |
| Unit test coverage gate | CI fails if `bridge/` coverage below 85% |

---

## Red-green-refactor workflow (per feature)

```text
1. Add test in tests/unit/... (or integration)
2. pytest path/to/test.py  →  FAIL (import error or assertion)
3. Implement minimal bridge/... code
4. pytest  →  PASS
5. Refactor; pytest + ruff (if configured)
6. Commit test + production together
```

Avoid writing production modules ahead of tests for `naming`, `recording_state`, `metadata`, `recorder` — those are the highest-value TDD targets.

---

## CI vs local commands

| Command | What runs |
|---------|-----------|
| `pytest` | Unit + integration (fakes), under ~5s |
| `pytest --cov=bridge --cov-report=term-missing` | Coverage report |
| `pytest -m integration` | UDP/thread tests only |
| `pytest -m obs` | Real OBS (optional nightly / manual) |
| `pytest -m live` | Real Ableton (manual only; never CI) |

GitHub Actions (when added): `pip install -e ".[dev]" && pytest`.

---

## What not to automate (v1)

| Item | Why |
|------|-----|
| Continuity Camera picture quality | Human/visual |
| Lip-sync offset | Documented manual procedure in SYNC.md |
| AbletonOSC install path | Manual Phase 0 |
| Full OBS encoder behavior | Fake + one `obs` marker test enough |

---

## Definition of done (TDD MVP)

Aligned with [PLAN.md](./PLAN.md) Phases 1–5:

- [ ] `pytest` passes with default markers (no Live/OBS)
- [ ] Coverage at least 85% on `bridge/` excluding `__main__.py`
- [ ] Contract tests list every OSC path the bridge sends
- [ ] `RecordingState` table covers arrangement + session combinations agreed in design
- [ ] Integration test proves: OSC `record_mode=1` → fake OBS `recording=True` → stop → file in injected `output_dir`
- [ ] Manual smoke once: real Live + OBS

---

## Suggested first PR sequence

Split PRs so each stays green in CI:

1. **Harness only** — pytest, conftest, fakes, `naming` + `recording_state` + tests (no CLI).
2. **Config + prompts** — Phase 1.
3. **OBS resolve + client** — Phase 2.
4. **OSC client + recording_state wiring** — Phase 3.
5. **Metadata** — Phase 4.
6. **Recorder + integration** — Phase 5.
7. **SYNC.md** — Phase 6.

This keeps TDD honest: every PR adds tests first, then implementation.

---

## Open TDD decisions (align with design review)

| Decision | Test impact |
|----------|-------------|
| Multiple armed tracks → join vs first | Change `test_metadata.py` parametrization |
| Move vs copy | `test_finalize_move.py` asserts `not source.exists()` vs both exist |
| Count-in wait | New `test_recorder.py` cases with `is_counting_in` fixture |
| `session_record_status` enum | Update `test_recording_state.py` parametrize after one manual Live session |

Once those are locked, update parametrized tables before implementing Phase 3–5.
