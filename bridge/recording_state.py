from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RecordingEdge(Enum):
    STARTED = auto()
    STOPPED = auto()


def format_signals(signals: "RecordingSignals") -> str:
    return (
        f"arr={signals.arrangement} session={signals.session_status} "
        f"clip={signals.clip_recording} start_active={signals.start_active} "
        f"stop_active={signals.stop_active}"
    )


@dataclass(frozen=True)
class RecordingSignals:
    arrangement: int
    session_status: int
    clip_recording: bool = False

    @property
    def start_active(self) -> bool:
        """True when the user has engaged record (transport), before clip tail semantics."""
        return bool(self.arrangement == 1 or self.session_status != 0)

    @property
    def stop_active(self) -> bool:
        """True while audio is still being written (arrangement or quantized clip tail)."""
        return bool(self.arrangement == 1 or self.clip_recording)

    @property
    def active(self) -> bool:
        """Alias for stop_active (used by count-in resume and idle checks)."""
        return self.stop_active


@dataclass
class RecordingStateMachine:
    """START on transport engage; STOP when arrangement/clip tail ends."""

    was_start_active: bool = False
    was_stop_active: bool = False

    def apply(self, signals: RecordingSignals) -> list[RecordingEdge]:
        edges: list[RecordingEdge] = []

        if signals.start_active and not self.was_start_active:
            edges.append(RecordingEdge.STARTED)
        self.was_start_active = signals.start_active

        if not signals.stop_active and self.was_stop_active:
            edges.append(RecordingEdge.STOPPED)
        self.was_stop_active = signals.stop_active

        return edges

    def sync_initial(self, signals: RecordingSignals) -> list[RecordingEdge]:
        edges: list[RecordingEdge] = []
        if signals.start_active and not self.was_start_active:
            edges.append(RecordingEdge.STARTED)
            self.was_start_active = True
        self.was_stop_active = signals.stop_active
        return edges
