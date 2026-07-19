import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import test from "node:test";

import { registerContextMenuActions } from "./menu.js";
import { parseSidecarDialogResult } from "./dialog.js";
import {
  ARRANGEMENT_SELECTION_SCOPES,
  CLIP_CONTEXT_SCOPES,
  SIDECAR_POINTER_ENV,
  validateVideoDurationForClip,
  readTakes,
  resolveAutomaticSidecarPath,
  selectTakeClipPairs,
  type TakeSidecar,
} from "./placement.js";

function writeJson(filePath: string, payload: unknown): void {
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function makeTake(dir: string, name: string, recordedStart: string): TakeSidecar {
  const videoPath = path.join(dir, `${name}.mkv`);
  fs.writeFileSync(videoPath, "video");
  return {
    schema_version: 1,
    video_path: videoPath,
    track_label: name,
    recorded_start: recordedStart,
    finalized_at: recordedStart,
    sync_offset_ms: 0,
  };
}

test("registers clip and arrangement scopes for audio and MIDI", () => {
  assert.deepEqual(CLIP_CONTEXT_SCOPES, ["AudioClip", "MidiClip"]);
  assert.deepEqual(ARRANGEMENT_SELECTION_SCOPES, [
    "AudioTrack.ArrangementSelection",
    "MidiTrack.ArrangementSelection",
  ]);
});

test("registerContextMenuActions logs registered scopes", async () => {
  const registered: Array<[string, string, string]> = [];
  const messages: string[] = [];
  await registerContextMenuActions(
    {
      ui: {
        registerContextMenuAction: async (scope: string, title: string, commandId: string) => {
          registered.push([scope, title, commandId]);
          return async () => undefined;
        },
      },
    },
    { log: (message: string) => messages.push(message) },
  );

  assert.deepEqual(
    registered.map(([scope]) => scope),
    [
      "AudioClip",
      "MidiClip",
      "AudioTrack.ArrangementSelection",
      "MidiTrack.ArrangementSelection",
    ],
  );
  assert.equal(
    messages.at(-1),
    "Ableton Camera Video registered 4 context menu actions.",
  );
});

test("readTakes reads latest and resolves history next to last_take", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ableton-camera-sidecars-"));
  const first = makeTake(dir, "Vocals", "2026-06-23T11:00:00+00:00");
  const second = makeTake(dir, "Guitar", "2026-06-23T11:05:00+00:00");
  const lastPath = path.join(dir, "last_take.json");
  const historyPath = path.join(dir, "take_history.json");
  writeJson(lastPath, second);
  writeJson(historyPath, { schema_version: 1, takes: [first, second] });

  assert.deepEqual(
    readTakes(lastPath, "latest").map((take) => take.track_label),
    ["Guitar"],
  );
  assert.deepEqual(
    readTakes(lastPath, "all").map((take) => take.track_label),
    ["Vocals", "Guitar"],
  );
});

test("readTakes rejects a sidecar that points at an empty video file", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ableton-camera-empty-video-"));
  const videoPath = path.join(dir, "Empty.mov");
  fs.writeFileSync(videoPath, "");
  const sidecarPath = path.join(dir, "last_take.json");
  writeJson(sidecarPath, {
    schema_version: 1,
    video_path: videoPath,
    track_label: "Vocals",
    recorded_start: "2026-06-23T11:00:00+00:00",
    finalized_at: "2026-06-23T11:00:05+00:00",
    sync_offset_ms: 0,
  });

  assert.throws(() => readTakes(sidecarPath, "latest"), /Video file is empty/);
});

test("parseSidecarDialogResult rejects empty dialog results with a clear error", () => {
  assert.throws(() => parseSidecarDialogResult(""), /No sidecar path selected/);
});

test("resolveAutomaticSidecarPath reads the bridge-published pointer", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ableton-camera-pointer-"));
  const pointerPath = path.join(dir, "sidecar_path.json");
  const lastPath = path.join(dir, "last_take.json");
  const historyPath = path.join(dir, "take_history.json");
  const take = makeTake(dir, "Vocals", "2026-06-23T11:00:00+00:00");
  writeJson(lastPath, take);
  writeJson(historyPath, { schema_version: 1, takes: [take] });
  writeJson(pointerPath, {
    schema_version: 1,
    last_take_path: lastPath,
    take_history_path: historyPath,
  });

  assert.equal(
    resolveAutomaticSidecarPath("latest", { [SIDECAR_POINTER_ENV]: pointerPath }),
    lastPath,
  );
  assert.equal(
    resolveAutomaticSidecarPath("all", { [SIDECAR_POINTER_ENV]: pointerPath }),
    historyPath,
  );
});

test("resolveAutomaticSidecarPath does not fall back to history for latest takes", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ableton-camera-pointer-missing-latest-"));
  const pointerPath = path.join(dir, "sidecar_path.json");
  const missingLastPath = path.join(dir, "last_take.json");
  const historyPath = path.join(dir, "take_history.json");
  const take = makeTake(dir, "Vocals", "2026-06-23T11:00:00+00:00");
  writeJson(historyPath, { schema_version: 1, takes: [take] });
  writeJson(pointerPath, {
    schema_version: 1,
    last_take_path: missingLastPath,
    take_history_path: historyPath,
  });

  assert.equal(
    resolveAutomaticSidecarPath("latest", { [SIDECAR_POINTER_ENV]: pointerPath }),
    missingLastPath,
  );
  assert.equal(
    resolveAutomaticSidecarPath("all", { [SIDECAR_POINTER_ENV]: pointerPath }),
    historyPath,
  );
});

test("selectTakeClipPairs maps takes to selected clips chronologically", () => {
  const takes = [
    {
      track_label: "Second",
      recorded_start: "2026-06-23T11:05:00+00:00",
    },
    {
      track_label: "First",
      recorded_start: "2026-06-23T11:00:00+00:00",
    },
  ] as TakeSidecar[];
  const clips = [
    { id: "clip-b", startTime: 12, duration: 4 },
    { id: "clip-a", startTime: 4, duration: 4 },
  ];

  assert.deepEqual(
    selectTakeClipPairs(clips, takes).map(({ clip, take }) => [clip.id, take.track_label]),
    [
      ["clip-a", "First"],
      ["clip-b", "Second"],
    ],
  );
});

test("selectTakeClipPairs rejects mismatched selected clips and takes", () => {
  assert.throws(
    () =>
      selectTakeClipPairs(
        [{ id: "clip-a", startTime: 4, duration: 4 }],
        [
          { track_label: "First", recorded_start: "2026-06-23T11:00:00+00:00" },
          { track_label: "Second", recorded_start: "2026-06-23T11:05:00+00:00" },
        ] as TakeSidecar[],
      ),
    /Selected 1 clips but take history has 2 takes/,
  );
});

test("validateVideoDurationForClip rejects videos shorter than the selected clip", () => {
  const take = {
    video_path: "/tmp/Grand_Piano_2026-07-19_142950.mov",
  } as TakeSidecar;

  assert.throws(
    () =>
      validateVideoDurationForClip(
        take,
        { startTime: 4, duration: 16 },
        120,
        () => 3.07,
      ),
    /Video Grand_Piano_2026-07-19_142950.mov is 3\.07s, but the selected clip is 8\.00s/,
  );
});

test("package scripts build a production bundle and installable ablx", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  ) as { scripts: Record<string, string> };

  assert.equal(
    packageJson.scripts["build:production"],
    "tsc --noEmit && tsx build.ts --production",
  );
  assert.equal(
    packageJson.scripts.package,
    "npm run build:production && extensions-cli package -o dist/ableton-camera-video.ablx",
  );
  assert.equal(
    packageJson.scripts.start,
    'tsx build.ts && extensions-cli run --live "/Applications/Ableton Live 12 Beta.app"',
  );
  assert.equal(
    packageJson.scripts["start:suite"],
    'tsx build.ts && extensions-cli run --live "/Applications/Ableton Live 12 Suite.app"',
  );
});
