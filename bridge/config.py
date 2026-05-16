from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OscConfig:
    send_host: str
    send_port: int
    listen_host: str
    listen_port: int


@dataclass
class ObsConfig:
    host: str
    port: int
    password: str


@dataclass
class AppConfig:
    osc: OscConfig
    obs: ObsConfig
    staging_dir: Path
    track_merge: str
    output_dir: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        osc = data["osc"]
        obs = data["obs"]
        paths = data["paths"]
        naming = data.get("naming", {})
        return cls(
            osc=OscConfig(
                send_host=str(osc["send_host"]),
                send_port=int(osc["send_port"]),
                listen_host=str(osc["listen_host"]),
                listen_port=int(osc["listen_port"]),
            ),
            obs=ObsConfig(
                host=str(obs["host"]),
                port=int(obs["port"]),
                password=str(obs.get("password", "")),
            ),
            staging_dir=Path(paths["staging_dir"]).expanduser(),
            track_merge=str(naming.get("track_merge", "_")),
            output_dir=None,
        )


def load_config(path: Path) -> AppConfig:
    if not path.is_file():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config format in {path}")
    return AppConfig.from_dict(data)
