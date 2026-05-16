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
4. **Settings → Output → Recording** → set path to staging, e.g. `~/Movies/OBS-Staging` (must match `paths.staging_dir` in config).
5. Add **Continuity Camera** (or iPhone) as a video source in your scene.

---

## ableton-camera bridge

```bash
source .venv/bin/activate
pip install -e ".[dev]"
ableton-camera --output-dir ~/Movies/MySession
```

Or run without `--output-dir` to use the folder picker.
