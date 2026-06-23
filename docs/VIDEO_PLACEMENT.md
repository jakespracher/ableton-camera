# Video Placement In Live

Ableton Live 12.4.5 Suite beta adds Extensions: one-shot JavaScript tools that can edit a Live Set from context menus. `ableton-camera` uses that layer to place the latest camera recording under the arrangement take you just recorded.

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

## Build

```bash
cd extensions/ableton-camera-video
npm install
npm run build
```

Install the built Extension using Live's Settings -> Extensions flow, or run it during development with:

```bash
npm run start
```

## Workflow

1. Start the bridge as usual:

   ```bash
   ableton-camera --output-dir ~/Movies/MySession
   ```

2. Record an arrangement take in Live.
3. Stop recording. The bridge moves the OBS file and writes `last_take.json` next to it.
4. In Arrangement View, right-click the recorded audio clip.
5. Run `Place Camera Video Below`.
6. If prompted, enter the full path to that session's `last_take.json`.

To skip the prompt, launch Live with this environment variable set:

```bash
ABLETON_CAMERA_LAST_TAKE=/path/to/session/last_take.json
```

The Extension reads `last_take.json`, imports the referenced media into the Live project, creates or reuses a `{Source Track} Camera` audio track, and creates a new arrangement clip at the selected audio clip's start beat.

## Placement Details

- The selected `AudioClip` is the alignment source of truth.
- The placed video clip uses the selected clip's `startTime` and `duration`.
- `sync_offset_ms` from `last_take.json` nudges placement:
  - Positive values move video later.
  - Negative values move video earlier, clamped at beat zero.
- Offset conversion uses the current song tempo at placement time.
- `.mkv` files are remuxed to `.mp4` with `ffmpeg -c copy` into `.ableton-camera-cache/` next to `last_take.json` before import.

## Track Behavior

The SDK beta exposes `Song.createAudioTrack()` but does not expose insertion or track move APIs. To get as close as possible to "track below the original," the Extension duplicates the source audio track when a matching camera track is not already directly below it, clears arrangement clips from the duplicate, and renames it `{Source Track} Camera`.

If a track immediately below the source is already named `{Source Track} Camera`, the Extension reuses it.

## Verification Notes

Compile-time SDK verification has been run with:

```bash
npm run build
```

Manual Live verification still needs to be performed in the beta:

- Right-click an arrangement audio clip and confirm the menu item appears.
- Confirm `.mp4` import creates an arrangement clip.
- Confirm actual OBS `.mkv` output remuxes and imports.
- Confirm Undo removes the created media/track edits as one transaction.

## Troubleshooting

- **Menu item missing:** Confirm the Extension is installed/enabled and right-click an arrangement audio clip, not a MIDI clip or empty space.
- **Missing `last_take.json`:** Record through the bridge after this feature is installed, or point the prompt to the correct session folder.
- **Video file missing:** The sidecar stores an absolute path. Confirm the file has not been moved.
- **`.mkv` import fails:** Confirm `ffmpeg` is installed and available to Live's Extension runtime.
- **Track not exactly below source:** This SDK beta has no track move API. Reorder the created `{Track} Camera` track manually if Live places duplicated tracks differently in a future beta.
