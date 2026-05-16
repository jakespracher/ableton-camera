# Build plan

Phased plan to implement [DESIGN.md](./DESIGN.md). Each phase has deliverables and manual acceptance checks.

---

## Phase 0: Environment setup

**Goal:** Machine ready; no custom code yet.

| Task | Notes |
|------|--------|
| Install [AbletonOSC](https://github.com/ideoforms/AbletonOSC) | Control Surface → AbletonOSC; “Listening on port 11000” |
| Enable OBS WebSocket | Port + password |
| Continuity Camera in OBS | Preview works |
| OBS record path → **staging** only | e.g. `~/Movies/OBS-Staging` (not the user album folder) |

**Acceptance**

- [ ] `oscsend localhost 11000 /live/test` → Live status bar
- [ ] OBS `StartRecord` / `StopRecord` via WebSocket works
- [ ] Continuity preview in OBS

**Estimate:** 30–60 min

---

## Phase 1: Project scaffold + output folder prompt

**Goal:** Repo structure, config, **ask for output folder on start**.

| Task | Notes |
|------|--------|
| `pyproject.toml` | `obsws-python`, `python-osc`, `pyyaml` |
| `config.example.yaml` | OSC, OBS, `staging_dir` only — no `output_dir` |
| `bridge/prompts.py` | Folder picker (macOS native or tkinter); validate/create dir; cancel → exit |
| `bridge/config.py` | Load yaml; hold runtime `output_dir` from prompt |
| `bridge/__main__.py` | Prompt first, then start listeners |

**Acceptance**

- [ ] `pip install -e .` succeeds
- [ ] `python -m bridge` opens folder picker; chosen path printed; persists for session
- [ ] Cancel picker → clean exit

**Estimate:** 2–3 hours

---

## Phase 2: OBS client

**Goal:** Reliable start/stop and locate recorded file in staging.

| Task | Notes |
|------|--------|
| `bridge/obs_client.py` | `StartRecord`, `StopRecord`, `GetRecordStatus` |
| Resolve path after stop | Response metadata or newest file in `staging_dir` |
| `--test-obs` flag | Optional CLI test without Live |

**Acceptance**

- [ ] Test flag records to staging; file exists

**Estimate:** 2–3 hours

---

## Phase 3: OSC client + dual record listeners

**Goal:** React to **arrangement and session** recording without polling.

| Task | Notes |
|------|--------|
| `bridge/osc_client.py` | UDP 11001 listen, send to 11000 |
| Subscribe | `start_listen/record_mode`, `start_listen/session_record_status` |
| Combined `recording_active` | OR of arrangement + session; edge detect |
| Boot sync | Query both getters once if bridge starts mid-take |
| Log `session_record_status` values | Document enum while testing Session Record |

**Acceptance**

- [ ] Arrangement Record → console “recording on/off”
- [ ] Session Record → console “recording on/off”
- [ ] Either can start; stops only when **both** off
- [ ] No OBS yet

**Estimate:** 3–5 hours

---

## Phase 4: Track metadata for naming

**Goal:** Resolve track label at record start (no project name from Live).

| Task | Notes |
|------|--------|
| `bridge/metadata.py` | `get_track_label()` only |
| Armed tracks loop | `/live/track/get/arm`, `/live/track/get/name` |
| Fallback | `/live/view/get/selected_track` + name |

**Acceptance**

- [ ] Log at start: `track=Vocals` (or merged armed names)
- [ ] No AbletonOSC patch for `file_path`

**Estimate:** 2–3 hours

---

## Phase 5: Recorder state machine + finalize

**Goal:** End-to-end wiring.

| Task | Notes |
|------|--------|
| `bridge/recorder.py` | IDLE / RECORDING / FINALIZING |
| On start | metadata + `obs.start_record()` |
| On stop | `obs.stop_record()` + **move** to session `output_dir` as `{track}_{timestamp}.ext` |

**Acceptance**

- [ ] Session record in Live → file in **user-picked folder** with correct name
- [ ] Arrangement record → same
- [ ] Second take → new timestamp, no overwrite
- [ ] Two triggers in one “session” share same output folder until app restart

**Estimate:** 3–4 hours

---

## Phase 6: Sync calibration doc

| Task | Notes |
|------|--------|
| `docs/SYNC.md` | Clap test; OBS Sync Offset on Continuity source |

**Acceptance**

- [ ] One calibration pass documented and repeatable

**Estimate:** ~1 hour

---

## Phase 7: Polish (optional)

| Item | Priority |
|------|----------|
| Remember last output folder in user config | Medium |
| `launchd` / menu bar auto-start | Medium |
| Count-in aware start (`is_counting_in`) | Low |
| Clip-slot `is_recording` trigger | Low |
| Continuous record + JSONL sidecar | Low |
| See [TDD_PLAN.md](./TDD_PLAN.md) — coverage gate, CI | Medium |

---

## Build order

```
Phase 0 → environment
Phase 1 → scaffold + folder prompt
Phase 2 → OBS client
Phase 3 → OSC (arrangement + session)
Phase 4 → track metadata
Phase 5 → integrate (MVP)
Phase 6 → sync doc
Phase 7 → polish
```

**MVP:** Phases 0–5 — arrangement **or** session record → renamed video in the folder chosen at launch.

**Estimate:** ~12–17 hours implementation

---

## Risks

| Risk | Mitigation |
|------|------------|
| `session_record_status` semantics unclear | Log on first install; document in code comment |
| OBS path not returned on stop | Newest file in staging + stable size poll |
| User picks read-only folder | Validate writable at prompt time |
| Overlapping arrangement + session | AND-off to stop; single OBS record session |

---

## Review checklist

- [x] Session recording in v1
- [x] Output folder at startup (not from Live)
- [x] Filename: `{track}_{timestamp}` only
- [ ] Multiple armed tracks: join all vs first vs selected?
- [ ] Move vs copy on finalize?
- [ ] Count-in: immediate OBS start or wait?
