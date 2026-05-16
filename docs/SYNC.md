# Audio / video alignment

Your bridge starts OBS when Ableton starts recording. That does **not** produce sample-perfect sync. It produces **repeatable** sync once you measure and apply one offset.

## What you are aligning

```text
Ableton audio (in the .als / exported audio)
        vs
OBS file (Camo video, maybe Camo mic on the same .mkv)
```

Typical total mismatch: **~100–300 ms** from:

- OSC + Python + OBS WebSocket
- OBS encoder start
- Camo / Wi‑Fi / USB pipeline
- Ableton buffer / monitoring path

Goal: **one number** (milliseconds) you apply every session so lip sync looks right.

---

## One-time calibration (clap test)

### 1. Prepare

- Same setup you will use for real takes: Camo, OBS, cable vs Wi‑Fi, buffer sizes.
- `ableton-camera` running, output folder set.
- Ableton: one armed track, metronome optional.
- OBS: **Camo** source, canvas resolution you record at.

### 2. Record

1. Start the bridge: `ableton-camera --output-dir ~/Movies/testsession`
2. In Live, start **arrangement or session** record (same as you will in production).
3. **Clap once** loudly, on beat or with a clear transient (snare hit works too).
4. Stop recording in Live (OBS stops via the bridge).

You should have:

- A video in `~/Movies/testsession/` (or your folder)
- Audio in the Live clip on the armed track

### 3. Measure offset

Use any editor that shows waveforms on a timeline.

**Option A — Use audio on the video file (if Camo/OBS recorded mic)**  
Import only the `.mkv` into DaVinci Resolve (free), Reaper, Audacity, or Logic.

**Option B — Use Live’s audio (often cleaner)**  
Export the recorded clip from Live as WAV. Import **video + WAV** into the same project and align the WAV to the video’s clap spike (or vice versa).

**How to read it:**

| What you see | Meaning | OBS fix |
|--------------|---------|--------|
| Video clap **before** audio | Video is **early** | **Increase** sync offset (delay video) |
| Video clap **after** audio | Video is **late** | **Decrease** sync offset (negative if needed) |

Note the offset in **milliseconds** (e.g. video early by 120 ms → add **+120 ms** sync on the Camo source in OBS).

### 4. Apply in OBS (persists in your scene)

1. Right‑click the **Camo** source → **Properties** (or **Advanced**).
2. Find **Sync Offset** / **Audio Sync Offset** (wording varies by source type).
3. Enter your measured value in **ms**.
4. Record another clap test; adjust until sharp.

Store the value somewhere (Notes app or `config.local.yaml` under `sync.obs_source_sync_offset_ms` as a **reminder** — the bridge does not apply it automatically in v1; OBS holds the real setting.

Example `config.local.yaml` (documentation only):

```yaml
sync:
  obs_source_sync_offset_ms: 120   # applied manually in OBS Camo source
```

---

## If you only care about Live audio in the final edit

Common workflow:

1. **Ignore** the mic on the OBS file (mute or delete that track in the editor).
2. Use **only** audio exported from Ableton.
3. Align that WAV to the video clap once per project template.

Then OBS “sync offset” matters less for lip sync; you nudge the Ableton WAV on the timeline.

---

## Keeping sync stable

Re-measure if you change:

- Camo **USB vs Wi‑Fi**
- OBS **resolution / frame rate**
- Mac **buffer** or Camo quality settings
- Ableton **audio buffer** size
- How you trigger record (session vs arrangement) — usually small difference

You do **not** need Ableton Link for this.

---

## Session clip stop (quantized bar tail)

When you stop a **session clip** with the slot stop button, Live keeps recording audio until the next **quantization** boundary (global **Clip Trigger Quantization** or per-clip launch quantization). The bridge used to stop OBS as soon as the transport/session flag dropped, so **video ended early**.

**Now:** OBS keeps recording while any clip has `is_recording` true (polled from AbletonOSC). That matches the end of the bar in most setups.

Readable from Live via OSC:

- `/live/song/get/clip_trigger_quantization` — global grid (0=None, 4=1 Bar, etc.)
- `/live/clip/get/launch_quantization` — per-clip override

You do not need to enter this manually unless clip polling fails; then set a fallback in config (future).

---

## Count-in (3 beats ≈ 2 s at 90 BPM)

If Ableton’s **metronome count-in** is on, the bridge **waits until count-in finishes** before starting OBS (when `is_counting_in` is available via AbletonOSC).

At **89.5 BPM**, **3 beats** ≈ `3 × (60 / 89.5)` ≈ **2.01 seconds** — exactly the kind of offset you saw if OBS used to start on the record button.

After updating:

1. Run `python scripts/patch_abletonosc_count_in.py` if needed (or use the patched install).
2. **Quit and reopen Live** so AbletonOSC reloads.
3. Re-run the clap test; remaining offset should be small (Camo/OBS latency only).

To disable count-in in Live: metronome / record menu → **Count-In** → **None**.

---

## Limits (what not to expect)

| Expectation | Reality |
|-------------|---------|
| Sample-accurate like timecode | Not with this stack |
| Perfect without one calibration | No |
| Same offset on a different phone / room | Re-check |
| Fix drift over a 10‑minute take | Rare; if it drifts, hardware clock issue |

For broadcast-grade lock: LTC/timecode or a single device recording both (not v1).

---

## Optional future improvements (not built yet)

- OBS always recording + timestamp sidecar from the bridge (trim in post; removes start jitter)
- Post-export script: shift video with `ffmpeg` by `sync_offset_ms`
- `SetInputAudioSyncOffset` / input settings via WebSocket (video offset API is limited; manual OBS UI is still the reliable path)

---

## Quick checklist

- [ ] Clap test recorded through bridge + Live
- [ ] Offset measured in ms
- [ ] Sync offset set on **Camo** source in OBS
- [ ] Second clap test looks good
- [ ] Value noted in `config.local.yaml` or project notes
