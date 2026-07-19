import * as fs from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";

export const CLIP_CONTEXT_SCOPES = ["AudioClip", "MidiClip"] as const;
export const ARRANGEMENT_SELECTION_SCOPES = [
  "AudioTrack.ArrangementSelection",
  "MidiTrack.ArrangementSelection",
] as const;
export const SIDECAR_ENV = "ABLETON_CAMERA_LAST_TAKE";
export const SIDECAR_POINTER_ENV = "ABLETON_CAMERA_SIDECAR_POINTER";
export const SIDECAR_POINTER_FILENAME = "sidecar_path.json";
export const VIDEO_DURATION_TOLERANCE_SECONDS = 0.75;

export type TakeMode = "latest" | "all";

export type TakeSidecar = {
  schema_version: number;
  video_path: string;
  track_label: string;
  recorded_start: string;
  finalized_at: string;
  sync_offset_ms: number;
};

type TakeHistory = {
  schema_version: number;
  takes: TakeSidecar[];
};

type SidecarPointer = {
  schema_version: number;
  last_take_path?: string;
  take_history_path?: string;
};

export type TimelineClip = {
  startTime: number;
  duration: number;
};
export type VideoDurationProbe = (videoPath: string) => number | null;

type Environment = Record<string, string | undefined>;

export function resolveAutomaticSidecarPath(
  mode: TakeMode,
  environment: Environment = process.env,
): string | null {
  const envPath = environment[SIDECAR_ENV];
  if (envPath && fs.existsSync(envPath)) {
    return envPath;
  }

  const pointerPath = sidecarPointerPath(environment);
  if (!pointerPath || !fs.existsSync(pointerPath)) {
    return null;
  }

  const pointer = JSON.parse(fs.readFileSync(pointerPath, "utf8")) as SidecarPointer;
  if (pointer.schema_version !== 1) {
    return null;
  }
  if (mode === "all" && pointer.take_history_path && fs.existsSync(pointer.take_history_path)) {
    return pointer.take_history_path;
  }
  if (mode === "latest" && pointer.last_take_path) {
    return pointer.last_take_path;
  }
  return null;
}

export function readTakes(sidecarPath: string, mode: TakeMode): TakeSidecar[] {
  if (mode === "latest") {
    return [readTake(sidecarPath)];
  }

  const historyPath = resolveHistoryPath(sidecarPath);
  const history = JSON.parse(fs.readFileSync(historyPath, "utf8")) as Partial<TakeHistory>;
  if (history.schema_version !== 1 || !Array.isArray(history.takes)) {
    throw new Error("Unsupported take history file.");
  }
  return history.takes.map(validateTake);
}

export function selectTakeClipPairs<TClip extends TimelineClip>(
  clips: TClip[],
  takes: TakeSidecar[],
): Array<{ clip: TClip; take: TakeSidecar }> {
  if (clips.length !== takes.length) {
    throw new Error(`Selected ${clips.length} clips but take history has ${takes.length} takes.`);
  }

  const sortedClips = [...clips].sort((a, b) => a.startTime - b.startTime);
  const sortedTakes = [...takes].sort((a, b) =>
    a.recorded_start.localeCompare(b.recorded_start),
  );
  return sortedClips.map((clip, index) => ({ clip, take: sortedTakes[index]! }));
}

export function validateVideoDurationForClip(
  take: TakeSidecar,
  clip: TimelineClip,
  tempoBpm: number,
  probe: VideoDurationProbe = readVideoDurationSeconds,
): void {
  const videoSeconds = probe(take.video_path);
  if (videoSeconds === null) {
    return;
  }

  const clipSeconds = beatsToSeconds(clip.duration, tempoBpm);
  if (videoSeconds + VIDEO_DURATION_TOLERANCE_SECONDS >= clipSeconds) {
    return;
  }

  throw new Error(
    `Video ${path.basename(take.video_path)} is ${videoSeconds.toFixed(2)}s, ` +
      `but the selected clip is ${clipSeconds.toFixed(2)}s. ` +
      "Record a new take after restarting the bridge, then place again.",
  );
}

export function readVideoDurationSeconds(videoPath: string): number | null {
  const result = spawnSync(
    "ffprobe",
    [
      "-v",
      "error",
      "-show_entries",
      "format=duration",
      "-of",
      "default=nw=1:nk=1",
      videoPath,
    ],
    { encoding: "utf8" },
  );
  const error = result.error as { code?: string; message?: string } | undefined;
  if (error?.code === "ENOENT") {
    return null;
  }
  if (error) {
    throw new Error(`Could not inspect video duration: ${error.message ?? String(error)}`);
  }
  if (result.status !== 0) {
    throw new Error(
      `Could not read video duration for ${path.basename(videoPath)}: ` +
        (result.stderr || result.stdout || "ffprobe failed"),
    );
  }

  const duration = Number.parseFloat(result.stdout.trim());
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error(`Could not read video duration for ${path.basename(videoPath)}.`);
  }
  return duration;
}

function sidecarPointerPath(environment: Environment): string | null {
  const override = environment[SIDECAR_POINTER_ENV];
  if (override) {
    return override;
  }

  const home = environment.HOME ?? environment.USERPROFILE;
  if (!home) {
    return null;
  }
  if (process.platform === "darwin") {
    return path.join(
      home,
      "Library",
      "Application Support",
      "ableton-camera",
      SIDECAR_POINTER_FILENAME,
    );
  }
  if (process.platform === "win32") {
    return path.join(
      environment.APPDATA ?? path.join(home, "AppData", "Roaming"),
      "ableton-camera",
      SIDECAR_POINTER_FILENAME,
    );
  }
  return path.join(
    environment.XDG_CONFIG_HOME ?? path.join(home, ".config"),
    "ableton-camera",
    SIDECAR_POINTER_FILENAME,
  );
}

function resolveHistoryPath(sidecarPath: string): string {
  if (path.basename(sidecarPath) === "take_history.json") {
    return sidecarPath;
  }
  return path.join(path.dirname(sidecarPath), "take_history.json");
}

function beatsToSeconds(durationBeats: number, tempoBpm: number): number {
  return (durationBeats / tempoBpm) * 60;
}

function readTake(sidecarPath: string): TakeSidecar {
  const raw = JSON.parse(fs.readFileSync(sidecarPath, "utf8")) as Partial<TakeSidecar>;
  return validateTake(raw);
}

function validateTake(raw: Partial<TakeSidecar>): TakeSidecar {
  if (raw.schema_version !== 1) {
    throw new Error(`Unsupported sidecar schema_version: ${String(raw.schema_version)}`);
  }
  if (!raw.video_path || !path.isAbsolute(raw.video_path)) {
    throw new Error("Sidecar video_path must be an absolute path.");
  }
  if (!fs.existsSync(raw.video_path)) {
    throw new Error(`Video file does not exist: ${raw.video_path}`);
  }
  const stats = fs.statSync(raw.video_path);
  if (!stats.isFile()) {
    throw new Error(`Video path is not a file: ${raw.video_path}`);
  }
  if (stats.size <= 0) {
    throw new Error(`Video file is empty: ${raw.video_path}`);
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
