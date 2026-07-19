# Video Placement In Live

Ableton Live 12.4.5 Suite beta adds Extensions: one-shot JavaScript tools that can edit a Live Set from context menus. `ableton-camera` uses that layer to place camera recordings under arrangement audio or MIDI takes.

## Requirements

- Ableton Live 12.4.5 Suite beta or newer with Extensions enabled.
- Ableton Extensions SDK `1.0.0-beta.0`.
- Node.js compatible with the SDK.
- Existing `ableton-camera` bridge setup with OBS and AbletonOSC.
- `ffmpeg` on `PATH` if OBS records `.mkv` files.

The Extension lives in `extensions/ableton-camera-video/`. Its `package.json` points at the SDK tarballs from the downloaded SDK bundle:

```text
~/Downloads/extensions-sdk-1.0.0-beta.0/ableton-extensions-sdk-1.0.0-beta.0.tgz
~/Downloads/extensions-sdk-1.0.0-beta.0/ableton-extensions-cli-1.0.0-beta.0.tgz
```

## Build And Install

```bash
cd extensions/ableton-camera-video
nvm install
nvm use
npm install
npm run package
```

Install `extensions/ableton-camera-video/dist/ableton-camera-video.ablx` by dropping it into Live's Settings -> Extensions page.

For development, run the Extension Host directly:

```bash
npm run start
```

## Workflow

1. Start the bridge as usual:

   ```bash
   ableton-camera --output-dir ~/Movies/MySession
   ```

2. Record an arrangement take in Live.
3. Stop recording. The bridge moves the OBS file, writes `last_take.json` and `take_history.json` next to it, and publishes the active sidecar pointer for the Extension.
4. In Arrangement View, right-click the recorded audio or MIDI clip.
5. Run `Place Camera Video Below`.

To place every saved take in one action:

1. Drag-select the arrangement audio or MIDI clips that correspond to the recorded takes.
2. Right-click the arrangement selection.
3. Run `Place All Camera Videos Below`.

The all-takes command pairs selected clips and saved takes chronologically. It expects the number of selected clips to match the number of takes in `take_history.json`.

The bridge publishes the current sidecar location to:

```bash
~/Library/Application Support/ableton-camera/sidecar_path.json
```

The Extension reads that file automatically, so normal usage should not prompt for a path. If you need to override it for development, set `ABLETON_CAMERA_LAST_TAKE` to a specific `last_take.json`, or set `ABLETON_CAMERA_SIDECAR_POINTER` to an alternate pointer JSON file before launching the Extension Host.

The Extension reads the sidecar, imports the referenced media into the Live project, creates or reuses a `{Source Track} Camera` audio track, and creates a new arrangement clip at the selected source clip's start beat.

Placement runs inside Live's standard progress dialog. The Extension also writes each placement step and any error details to Live's Extension Host log:

```text
~/Library/Preferences/Ableton/Live x.x.x/ExtensionHost.txt
```

## Placement Details

- The selected `AudioClip` or `MidiClip` is the alignment source of truth.
- The placed video clip uses the selected clip's `startTime` and `duration`.
- `sync_offset_ms` from the take sidecar nudges placement:
  - Positive values move video later.
  - Negative values move video earlier, clamped at beat zero.
- Offset conversion uses the current song tempo at placement time.
- `.mkv` files are remuxed to `.mp4` with `ffmpeg -c copy` into `.ableton-camera-cache/` next to the sidecar before import.
- Empty or missing video files are rejected before import. A failed latest recording clears stale `last_take.json` metadata so the command cannot silently place the previous take by mistake.

## Track Behavior

The SDK beta exposes `Song.createAudioTrack()` but does not expose insertion or track move APIs. To get as close as possible to "track below the original," the Extension duplicates an audio source track when a matching camera track is not already directly below it, clears arrangement clips from the duplicate, and renames it `{Source Track} Camera`.

If a track immediately below the source is already named `{Source Track} Camera`, the Extension reuses it.

For MIDI source tracks, the Extension creates an audio track and renames it `{Source Track} Camera`, because video media must be placed on an audio track.

## Verification Notes

Compile-time SDK verification has been run with:

```bash
npm run build
```

Manual Live verification still needs to be performed in the beta:

- Right-click an arrangement audio clip and a MIDI clip and confirm the latest-video menu item appears.
- Select multiple arrangement clips and confirm the all-takes menu item appears.
- Confirm `.mp4` import creates an arrangement clip.
- Confirm actual OBS `.mkv` output remuxes and imports.
- Confirm Undo removes the created media/track edits as one transaction.

## Troubleshooting

- **Menu item missing:** Confirm the `.ablx` Extension is installed/enabled and right-click an arrangement audio/MIDI clip or arrangement selection.
- **Unexpected path prompt:** Record once through the updated bridge, or confirm `~/Library/Application Support/ableton-camera/sidecar_path.json` points at an existing sidecar.
- **Missing `last_take.json`:** Record through the bridge after this feature is installed, or point the prompt to the correct session folder.
- **Missing `take_history.json`:** Record at least one take with the updated bridge; older sessions only have `last_take.json`.
- **All-takes mismatch:** Select the same number of arrangement clips as there are takes in `take_history.json`.
- **Video file missing:** The sidecar stores an absolute path. Confirm the file has not been moved.
- **Video file empty/corrupt:** The bridge will not publish an empty latest take, and the Extension will show a placement error instead of importing it. Record another valid take; do not rely on the previous `last_take.json`.
- **`.mkv` import fails:** Confirm `ffmpeg` is installed and available to Live's Extension runtime.
- **Track not exactly below source:** This SDK beta has no track move API. Reorder the created `{Track} Camera` track manually if Live places duplicated tracks differently in a future beta.
