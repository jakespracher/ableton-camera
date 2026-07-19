import {
  AudioClip,
  AudioTrack,
  DataModelObject,
  MidiClip,
  MidiTrack,
  Song,
  initialize,
  type ActivationContext,
  type ArrangementSelection,
  type ExtensionContext,
  type Handle,
} from "@ableton-extensions/sdk";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

import {
  SIDECAR_ENV,
  readTakes,
  resolveAutomaticSidecarPath,
  selectTakeClipPairs,
  validateVideoDurationForClip,
  type TakeMode,
  type TakeSidecar,
  type TimelineClip,
} from "./placement.js";
import {
  COMMAND_PLACE_ALL_VIDEOS,
  COMMAND_PLACE_VIDEO,
  registerContextMenuActions,
} from "./menu.js";
import { parseSidecarDialogResult, renderMessageDialog } from "./dialog.js";
import sidecarDialog from "./sidecar-dialog.html";

type Context = ExtensionContext<"1.0.0">;
type SourceClip = AudioClip<"1.0.0"> | MidiClip<"1.0.0">;
type SourceTrack = AudioTrack<"1.0.0"> | MidiTrack<"1.0.0">;
type ClipPlacement = TimelineClip & {
  clip: SourceClip;
  sourceTrack: SourceTrack;
  song: Song<"1.0.0">;
};
type ProgressReporter = (message: string, progress?: number) => Promise<void>;

export async function activate(activation: ActivationContext) {
  const context = initialize(activation, "1.0.0");

  context.commands.registerCommand(COMMAND_PLACE_VIDEO, async (arg: unknown) => {
    await runPlacementCommand(context, "Placing camera video...", async (progress) => {
      await progress("Reading selected clip", 5);
      const sourceClip = getSourceClip(context, arg);
      const sourceTrack = getSourceTrack(sourceClip);
      const song = getSong(sourceTrack);
      await progress("Reading latest take sidecar", 15);
      const sidecarPath = await resolveSidecarPath(context, "latest");
      const [sidecar] = readTakes(sidecarPath, "latest");
      if (!sidecar) {
        throw new Error("No latest take found.");
      }
      await placeTakeForClip(context, song, sourceTrack, sourceClip, sidecar, sidecarPath, progress);
      await progress("Done", 100);
    });
  });

  context.commands.registerCommand(COMMAND_PLACE_ALL_VIDEOS, async (arg: unknown) => {
    await runPlacementCommand(context, "Placing camera videos...", async (progress) => {
      await progress("Reading take history", 5);
      const sidecarPath = await resolveSidecarPath(context, "all");
      const takes = readTakes(sidecarPath, "all");
      await progress("Reading selected arrangement clips", 15);
      const placements = collectArrangementClipPlacements(context, arg as ArrangementSelection);
      const pairs = selectTakeClipPairs(placements, takes);
      for (const [index, { clip: placement, take }] of pairs.entries()) {
        const baseProgress = 20 + (index / pairs.length) * 75;
        const progressSpan = 75 / pairs.length;
        const scopedProgress: ProgressReporter = async (message, progressValue = 0) => {
          await progress(
            `${index + 1}/${pairs.length} ${message}`,
            baseProgress + (progressValue / 100) * progressSpan,
          );
        };
        await placeTakeForClip(
          context,
          placement.song,
          placement.sourceTrack,
          placement.clip,
          take,
          sidecarPath,
          scopedProgress,
        );
      }
      await progress("Done", 100);
    });
  });

  await registerContextMenuActions(context);
}

async function resolveSidecarPath(context: Context, mode: TakeMode): Promise<string> {
  const automaticPath = resolveAutomaticSidecarPath(mode);
  if (automaticPath) {
    return automaticPath;
  }

  const defaultPath = process.env[SIDECAR_ENV] ?? "";
  const dialogUrl = `data:text/html,${encodeURIComponent(renderSidecarDialog(defaultPath))}`;
  const result = await context.ui.showModalDialog(dialogUrl, 520, 160);
  return parseSidecarDialogResult(result);
}

function renderSidecarDialog(defaultPath: string): string {
  const defaultPathJson = JSON.stringify(defaultPath).replace(/</g, "\\u003c");
  return sidecarDialog.replace("__ABLETON_CAMERA_DEFAULT_PATH_JSON__", defaultPathJson);
}

function getSourceClip(context: Context, arg: unknown): SourceClip {
  const object = context.getObjectFromHandle(arg as Handle, DataModelObject);
  if (object instanceof AudioClip || object instanceof MidiClip) {
    return object;
  }
  throw new Error("Select an audio or MIDI arrangement clip.");
}

function getSourceTrack(sourceClip: SourceClip): SourceTrack {
  const sourceTrack = sourceClip.parent;
  if (sourceTrack instanceof AudioTrack || sourceTrack instanceof MidiTrack) {
    return sourceTrack;
  }
  throw new Error("Selected clip does not belong to an audio or MIDI track.");
}

function getSong(sourceTrack: SourceTrack): Song<"1.0.0"> {
  const song = sourceTrack.parent;
  if (song instanceof Song) {
    return song;
  }
  throw new Error("Could not resolve Live Set from selected track.");
}

async function placeTakeForClip(
  context: Context,
  song: Song<"1.0.0">,
  sourceTrack: SourceTrack,
  sourceClip: SourceClip,
  sidecar: TakeSidecar,
  sidecarPath: string,
  progress: ProgressReporter,
): Promise<void> {
  await progress(`Preparing ${path.basename(sidecar.video_path)}`, 25);
  await progress("Checking video duration", 35);
  validateVideoDurationForClip(sidecar, sourceClip, song.tempo);
  const mediaPath = ensureImportableMedia(sidecar.video_path, sidecarPath);
  await progress("Importing video into project", 45);
  const importedPath = await context.resources.importIntoProject(mediaPath);
  await progress("Finding camera track", 65);
  const targetTrack = await findOrCreateCameraTrack(context, song, sourceTrack);
  const startTime = shiftedStartBeat(sourceClip.startTime, sidecar.sync_offset_ms, song.tempo);
  await progress("Creating arrangement clip", 85);
  const placedClip = await context.withinTransaction(() =>
    targetTrack.createAudioClip({
      filePath: importedPath,
      startTime,
      duration: sourceClip.duration,
      isWarped: false,
    }),
  );

  context.withinTransaction(() => {
    placedClip.name = path.parse(sidecar.video_path).name;
  });
  await progress("Placed video clip", 95);
}

async function runPlacementCommand(
  context: Context,
  title: string,
  command: (progress: ProgressReporter) => Promise<void>,
): Promise<void> {
  try {
    await context.ui.withinProgressDialog(title, { progress: 0 }, async (update, signal) => {
      const progress: ProgressReporter = async (message, progressValue) => {
        console.log(`Ableton Camera Video: ${message}`);
        await update(message, progressValue);
        signal.throwIfAborted();
      };
      await command(progress);
    });
  } catch (error) {
    if (isAbortError(error)) {
      console.warn("Ableton Camera Video placement canceled.");
      return;
    }
    console.error("Ableton Camera Video placement failed:", error);
    await showErrorDialog(context, placementErrorMessage(error));
  }
}

async function showErrorDialog(context: Context, message: string): Promise<void> {
  const dialogUrl = `data:text/html,${encodeURIComponent(
    renderMessageDialog("Ableton Camera Video", message),
  )}`;
  try {
    await context.ui.showModalDialog(dialogUrl, 520, 200);
  } catch (dialogError) {
    console.error("Ableton Camera Video error dialog failed:", dialogError);
  }
}

function placementErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function collectArrangementClipPlacements(
  context: Context,
  selection: ArrangementSelection,
): ClipPlacement[] {
  const start = selection.time_selection_start;
  const end = selection.time_selection_end;
  const placements: ClipPlacement[] = [];

  for (const laneHandle of selection.selected_lanes) {
    const sourceTrack = getTrackFromLaneHandle(context, laneHandle);
    if (!sourceTrack) {
      continue;
    }
    const song = getSong(sourceTrack);
    for (const clip of sourceTrack.arrangementClips) {
      if (!(clip instanceof AudioClip || clip instanceof MidiClip)) {
        continue;
      }
      if (clip.startTime < end && clip.endTime > start) {
        placements.push({
          clip,
          sourceTrack,
          song,
          startTime: clip.startTime,
          duration: clip.duration,
        });
      }
    }
  }

  return placements;
}

function getTrackFromLaneHandle(context: Context, handle: Handle): SourceTrack | null {
  const object = context.getObjectFromHandle(handle, DataModelObject);
  if (object instanceof AudioTrack || object instanceof MidiTrack) {
    return object;
  }
  const parent = object.parent;
  if (parent instanceof AudioTrack || parent instanceof MidiTrack) {
    return parent;
  }
  return null;
}

async function findOrCreateCameraTrack(
  context: Context,
  song: Song<"1.0.0">,
  sourceTrack: SourceTrack,
): Promise<AudioTrack<"1.0.0">> {
  const tracks = song.tracks;
  const sourceIndex = tracks.findIndex((track) => track.handle.id === sourceTrack.handle.id);
  if (sourceIndex < 0) {
    throw new Error(`Could not find source track: ${sourceTrack.name}`);
  }

  const expectedName = `${sourceTrack.name} Camera`;
  const nextTrack = tracks[sourceIndex + 1];
  if (nextTrack instanceof AudioTrack && nextTrack.name === expectedName) {
    return nextTrack;
  }

  const created =
    sourceTrack instanceof AudioTrack
      ? await context.withinTransaction(() => song.duplicateTrack(sourceTrack))
      : await context.withinTransaction(() => song.createAudioTrack());
  if (!(created instanceof AudioTrack)) {
    throw new Error("Creating the camera track did not create an audio track.");
  }
  await context.withinTransaction(() => {
    created.name = expectedName;
    return created.clearClipsInRange(0, 1_000_000);
  });
  return created;
}

function shiftedStartBeat(startBeat: number, syncOffsetMs: number, tempoBpm: number): number {
  const offsetBeats = (syncOffsetMs / 1000) * (tempoBpm / 60);
  return Math.max(0, startBeat + offsetBeats);
}

function ensureImportableMedia(videoPath: string, sidecarPath: string): string {
  if (path.extname(videoPath).toLowerCase() !== ".mkv") {
    return videoPath;
  }

  const cacheDir = path.join(path.dirname(sidecarPath), ".ableton-camera-cache");
  fs.mkdirSync(cacheDir, { recursive: true });
  const mp4Path = path.join(cacheDir, `${path.parse(videoPath).name}.mp4`);
  if (isFresh(mp4Path, videoPath)) {
    return mp4Path;
  }

  const result = spawnSync("ffmpeg", ["-y", "-i", videoPath, "-c", "copy", mp4Path], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`ffmpeg remux failed: ${result.stderr || result.stdout}`);
  }
  return mp4Path;
}

function isFresh(candidatePath: string, sourcePath: string): boolean {
  if (!fs.existsSync(candidatePath)) {
    return false;
  }
  return fs.statSync(candidatePath).mtimeMs >= fs.statSync(sourcePath).mtimeMs;
}
