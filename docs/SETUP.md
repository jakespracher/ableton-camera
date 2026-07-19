# Setup checklist

## AbletonOSC (automated on this machine)

Installed to:

`~/Music/Ableton/User Library/Remote Scripts/AbletonOSC`

Re-run installer:

```bash
./scripts/install_abletonosc.sh
```

### You must do in Ableton Live

1. **Quit Live completely** (if it was open during install).
2. Reopen Live.
3. **Preferences → Link / Tempo / MIDI**
4. **Control Surface** dropdown → choose **AbletonOSC**
5. Confirm the status message: `AbletonOSC: Listening for OSC on port 11000`

### Verify

With Live running and AbletonOSC selected:

```bash
source .venv/bin/activate
python scripts/smoke_abletonosc.py
```

You should see a confirmation in Live’s status bar.

Logs (after first run): `~/Music/Ableton/User Library/Remote Scripts/AbletonOSC/logs/`

---

## OBS

OBS Studio is installed at `/Applications/OBS.app` (via Homebrew: `brew install --cask obs`).

1. **Open OBS once** (creates settings; complete any first-run prompts).
2. **Tools → WebSocket Server Settings** → enable server, set a password.
3. Copy password into `config.local.yaml` under `obs.password`.
4. **Settings → Output → Recording** → set path to staging, e.g. `~/Movies/OBS-Staging`.
5. **Settings → Output → Replay Buffer** → enable Replay Buffer and set maximum replay time longer than your biggest Capture MIDI window.
6. Add **Continuity Camera** (or iPhone) as a video source in your scene.

If OBS **Output Mode** is set to **Advanced**, use the Recording tab’s **Recording Path**. OBS can keep a separate Simple-mode file path, and the bridge will follow the active OBS path if it differs from `paths.staging_dir`.

For trimmed Capture MIDI videos, install `ffmpeg`:

```bash
brew install ffmpeg
```

Without `ffmpeg`, capture mode still saves a video, but it uses the full replay buffer file instead of trimming to the requested bars.

---

## ableton-camera bridge

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ableton-camera --output-dir ~/Movies/MySession
```

Or run without `--output-dir` to use the folder picker.

The bridge starts OBS Replay Buffer automatically and opens a local capture-control port from config:

```yaml
control:
  host: 127.0.0.1
  port: 11002
```

Keep the bridge process running while using Live. In another terminal, trigger Capture MIDI + replay video:

```bash
ableton-camera capture --bars 4 --destination arrangement
```

`capture` talks to the running bridge; it does not prompt for an output folder. The video lands in the same session/project folder selected when the bridge started. If the first capture says the Replay Buffer was just started, wait long enough for it to collect history and run the command again.
