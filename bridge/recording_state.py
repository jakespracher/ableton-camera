from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RecordingEdge(Enum):
    STARTED = auto()
    STOPPED = auto()


@dataclass(frozen=True)
class RecordingSignals:
    arrangement: int
    session_status: int
    clip_recording: bool = False

    @property
    def stop_active(self) -> bool:
        """True while audio is still being written (arrangement or clip tail)."""
        return bool(self.arrangement == 1 or self.clip_recording)

    @property
    def active(self) -> bool:
        """Alias used by the state machine (stop_active drives start/stop edges)."""
        return self.stop_active


@dataclass
class RecordingStateMachine:
    """Tracks capture state; emits start/stop edges from stop_active."""

    was_active: bool = False

    def apply(self, signals: RecordingSignals) -> list[RecordingEdge]:
        edges: list[RecordingEdge] = []
        is_active = signals.stop_active

        if is_active and not self.was_active:
            edges.append(RecordingEdge.STARTED)
        elif not is_active and self.was_active:
            edges.append(RecordingEdge.STOPPED)

        self.was_active = is_active
        return edges

    def sync_initial(self, signals: RecordingSignals) -> list[RecordingEdge]:
        if signals.stop_active and not self.was_active:
            self.was_active = True
            return [RecordingEdge.STARTED]
        self.was_active = signals.stop_active
        return []
