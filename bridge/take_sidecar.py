from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LAST_TAKE_FILENAME = "last_take.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TakeSidecar:
    video_path: Path
    track_label: str
    recorded_start: datetime
    finalized_at: datetime
    sync_offset_ms: int = 0

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "video_path": str(self.video_path.resolve()),
            "track_label": self.track_label,
            "recorded_start": self.recorded_start.isoformat(),
            "finalized_at": self.finalized_at.isoformat(),
            "sync_offset_ms": self.sync_offset_ms,
        }


def write_last_take(output_dir: Path, take: TakeSidecar) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / LAST_TAKE_FILENAME
    tmp_path = output_dir / f".{LAST_TAKE_FILENAME}.tmp"
    tmp_path.write_text(
        json.dumps(take.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, sidecar_path)
    return sidecar_path
