import {
  AudioClip,
  AudioTrack,
  Song,
  initialize,
  type ActivationContext,
  type Handle,
} from "@ableton-extensions/sdk";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

import sidecarDialog from "./sidecar-dialog.html";

const COMMAND_PLACE_VIDEO = "abletonCamera.placeVideoBelow";
const SIDECAR_ENV = "ABLETON_CAMERA_LAST_TAKE";

type TakeSidecar = {
  schema_version: number;
  video_path: string;
  track_label: string;
  recorded_start: string;
  finalized_at: string;
  sync_offset_ms: number;
};

export function activate(activation: ActivationContext) {
  const context = initialize(activation, "1.0.0");

  context.commands.registerCommand(COMMAND_PLACE_VIDEO, async (arg: unknown) => {
    try {
      const sourceClip = context.getObjectFromHandle(arg as Handle, AudioClip);
      const sourceTrack = sourceClip.parent;
      if (!(sourceTrack instanceof AudioTrack)) {
        throw new Error("Selected audio clip does not belong to an audio track.");
      }
      const song = sourceTrack.parent;
      if (!(song instanceof Song)) {
        throw new Error("Could not resolve Live Set from selected track.");
      }

      const sidecarPath = await resolveSidecarPath(context);
      const sidecar = readSidecar(sidecarPath);
      const mediaPath = ensureImportableMedia(sidecar.video_path, sidecarPath);
      const importedPath = await context.resources.importIntoProject(mediaPath);
      const targetTrack = await findOrCreateCameraTrack(context, song, sourceTrack);
      const startTime = shiftedStartBeat(
        sourceClip.startTime,
        sidecar.sync_offset_ms,
        song.tempo,
      );
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
    } catch (error) {
      console.error("Ableton Camera Video placement failed:", error);
      throw error;
    }
  });

  context.ui.registerContextMenuAction(
    "AudioClip",
    "Place Camera Video Below",
    COMMAND_PLACE_VIDEO,
  );
}

async function resolveSidecarPath(context: ReturnType<typeof initialize>): Promise<string> {
  const envPath = process.env[SIDECAR_ENV];
  if (envPath && fs.existsSync(envPath)) {
    return envPath;
  }

  const defaultPath = envPath ?? "";
  const dialogUrl = `data:text/html,${encodeURIComponent(sidecarDialog)}?defaultPath=${encodeURIComponent(defaultPath)}`;
  const result = await context.ui.showModalDialog(dialogUrl, 520, 160);
  const parsed = JSON.parse(result) as { sidecarPath?: string };
  if (!parsed.sidecarPath) {
    throw new Error(`Set ${SIDECAR_ENV} or enter a last_take.json path.`);
  }
  return parsed.sidecarPath;
}

function readSidecar(sidecarPath: string): TakeSidecar {
  const raw = JSON.parse(fs.readFileSync(sidecarPath, "utf8")) as Partial<TakeSidecar>;
  if (raw.schema_version !== 1) {
    throw new Error(`Unsupported sidecar schema_version: ${String(raw.schema_version)}`);
  }
  if (!raw.video_path || !path.isAbsolute(raw.video_path)) {
    throw new Error("Sidecar video_path must be an absolute path.");
  }
  if (!fs.existsSync(raw.video_path)) {
    throw new Error(`Video file does not exist: ${raw.video_path}`);
  }
  return {
    schema_version: raw.schema_version,
    video_path: raw.video_path,
    track_label: raw.track_label ?? "",
    recorded_start: raw.recorded_start ?? "",
    finalized_at: raw.finalized_at ?? "",
    sync_offset_ms: Number(raw.sync_offset_ms ?? 0),
  };
}

async function findOrCreateCameraTrack(
  context: ReturnType<typeof initialize>,
  song: Song<"1.0.0">,
  sourceTrack: AudioTrack<"1.0.0">,
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

  const created = await context.withinTransaction(() => song.duplicateTrack(sourceTrack));
  if (!(created instanceof AudioTrack)) {
    throw new Error("Duplicating the source track did not create an audio track.");
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
