from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from threading import Thread

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from bridge.recording_state import (
    RecordingEdge,
    RecordingSignals,
    RecordingStateMachine,
    format_signals,
)

logger = logging.getLogger(__name__)

RecordingHandler = Callable[[RecordingEdge, RecordingSignals], None]


def _osc_int(value: object) -> int | None:
    """Parse an OSC argument as int; AbletonOSC may send None for unsupported tracks."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _osc_bool(value: object) -> bool | None:
    parsed = _osc_int(value)
    if parsed is None:
        return None
    return bool(parsed)


class ReuseAddrOSCUDPServer(BlockingOSCUDPServer):
    """Allow quick restart when a previous bridge process was just killed."""

    allow_reuse_address = True


class OscListener:
    """Listens for AbletonOSC record property changes; emits STARTED/STOPPED edges."""

    def __init__(
        self,
        send_host: str,
        send_port: int,
        listen_host: str,
        listen_port: int,
        on_edge: RecordingHandler,
        on_count_in_finished: Callable[[RecordingSignals], None] | None = None,
        is_obs_recording: Callable[[], bool] | None = None,
    ) -> None:
        self._send_host = send_host
        self._send_port = send_port
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._on_edge = on_edge
        self._on_count_in_finished = on_count_in_finished
        self._is_obs_recording = is_obs_recording
        self._client = SimpleUDPClient(send_host, send_port)
        self._state = RecordingStateMachine()
        self._arrangement = 0
        self._session_status = 0
        self._is_playing = False
        self._counting_in = False
        self._record_mode_on_at: float | None = None
        self._count_in_osc_seen = False
        self._count_in_event = threading.Event()
        self._clip_recording = False
        self._clip_poll_thread: Thread | None = None
        self._stop_clip_poll = threading.Event()
        self._clip_reply_event = threading.Event()
        self._clip_reply_value: bool | None = None
        self._has_clip_reply_event = threading.Event()
        self._has_clip_reply_value: bool | None = None
        self._slot_reply_event = threading.Event()
        self._slot_reply_value: int | None = None
        self._server: BlockingOSCUDPServer | None = None
        self._thread: Thread | None = None
        self._lock = threading.Lock()
        self._num_tracks: int | None = None
        self._arms: dict[int, bool] = {}
        self._names: dict[int, str] = {}
        self._selected_track: int | None = None
        self._meta_event = threading.Event()
        self._query_lock = threading.RLock()
        self._last_recording_slots: dict[int, int] = {}

    @property
    def sent_messages(self) -> list[tuple[str, list]]:
        """Test seam: messages sent to AbletonOSC."""
        return getattr(self, "_sent_log", [])

    @property
    def signals(self) -> RecordingSignals:
        return RecordingSignals(self._arrangement, self._session_status, self._clip_recording)

    def subscribe(self) -> None:
        self._send("/live/song/start_listen/record_mode")
        self._send("/live/song/start_listen/session_record_status")
        self._send("/live/song/start_listen/is_playing")
        self._send("/live/song/start_listen/is_counting_in")
        self._query_initial_state()

    def _query_initial_state(self) -> None:
        self._send("/live/song/get/record_mode")
        self._send("/live/song/get/session_record_status")
        self._send("/live/song/get/is_playing")
        self._send("/live/song/get/is_counting_in")

    def is_transport_playing(self) -> bool:
        return self._is_playing

    def ms_since_record_mode_on(self) -> float | None:
        if self._record_mode_on_at is None:
            return None
        return (time.monotonic() - self._record_mode_on_at) * 1000.0

    def is_counting_in(self) -> bool:
        return self._counting_in

    def set_obs_recording_probe(self, probe: Callable[[], bool]) -> None:
        self._is_obs_recording = probe

    def _send(self, address: str, *args: int | float | str) -> None:
        payload = list(args) if args else []
        log = getattr(self, "_sent_log", None)
        if log is not None:
            log.append((address, payload))
        self._client.send_message(address, payload)

    def handle_record_mode(self, _address: str, *args: object) -> None:
        value = _osc_int(args[-1]) if args else None
        if value is not None:
            self._arrangement = value
            self._meta_event.set()

    def handle_session_status(self, _address: str, *args: object) -> None:
        value = _osc_int(args[-1]) if args else None
        if value is not None:
            self._session_status = value

    def apply_boot_sync(self) -> list[RecordingEdge]:
        return self._state.sync_initial(self.signals)

    def _dispatch_edges(self, *, source: str = "dispatch") -> None:
        edges = self._state.apply(self.signals)
        if edges:
            logger.info(
                "StateMachine %s → %s %s",
                source,
                [e.name for e in edges],
                format_signals(self.signals),
            )
        for edge in edges:
            self._on_edge(edge, self.signals)

    def _stop_obs_if_idle(self) -> None:
        """Stop OBS when Live is no longer writing audio but we missed the STOP edge."""
        if self.signals.stop_active:
            return
        if self._is_obs_recording is None or not self._is_obs_recording():
            return
        logger.info("Force stop: Live idle but OBS still recording %s", format_signals(self.signals))
        self._state.was_stop_active = False
        self._on_edge(RecordingEdge.STOPPED, self.signals)

    def _start_obs_if_session_recording(self) -> None:
        """Session record was already on; clip just began — start OBS without waiting for is_recording lag."""
        if self._session_status == 0:
            return
        if self._is_obs_recording is not None and self._is_obs_recording():
            logger.info("Clip→record but OBS already rolling; skip session clip start")
            return
        logger.info(
            "Path=session_clip_began_while_session_on %s",
            format_signals(self.signals),
        )
        self._on_edge(RecordingEdge.STARTED, self.signals)

    def fetch_record_mode(self, timeout_s: float) -> int:
        with self._query_lock:
            self._meta_event.clear()
            self._send("/live/song/get/record_mode")
            self._wait_meta(timeout_s)
            return self._arrangement

    def fetch_is_playing(self, timeout_s: float) -> bool:
        with self._query_lock:
            self._meta_event.clear()
            self._send("/live/song/get/is_playing")
            self._wait_meta(timeout_s)
            return self._is_playing

    def _on_record_mode(self, address: str, *args: object) -> None:
        prev = self._arrangement
        self.handle_record_mode(address, *args)
        if self._arrangement != prev:
            logger.info("Live record_mode %s→%s is_playing=%s", prev, self._arrangement, self._is_playing)
        if self._arrangement != 0 and prev == 0:
            self._record_mode_on_at = time.monotonic()
        elif self._arrangement == 0:
            self._record_mode_on_at = None
        self._dispatch_edges(source="record_mode")

    def _on_is_playing(self, _address: str, *args: object) -> None:
        if not args:
            return
        value = _osc_bool(args[-1])
        if value is None:
            return
        was_playing = self._is_playing
        self._is_playing = value
        self._meta_event.set()
        if was_playing == self._is_playing:
            return
        logger.info("Live is_playing %s→%s record_mode=%s", int(was_playing), int(self._is_playing), self._arrangement)

    def _on_session_status(self, address: str, *args: object) -> None:
        prev = self._session_status
        self.handle_session_status(address, *args)
        if self._session_status != prev:
            logger.info("Live session_record_status %s→%s", prev, self._session_status)
        self._dispatch_edges(source="session_status")
        # Session disengaged with no arrangement/clip tail: state machine may never have armed.
        if self._session_status == 0 and prev != 0:
            self._stop_obs_if_idle()

    def _on_counting_in(self, _address: str, *args: object) -> None:
        if not args:
            return
        value = _osc_bool(args[-1])
        if value is None:
            return
        self._count_in_osc_seen = True
        was_counting = self._counting_in
        self._counting_in = value
        self._count_in_event.set()
        if was_counting != self._counting_in:
            logger.info(
                "Live is_counting_in %s→%s %s",
                int(was_counting),
                int(self._counting_in),
                format_signals(self.signals),
            )
        if was_counting and not self._counting_in and self._on_count_in_finished:
            self._on_count_in_finished(self.signals)

    def count_in_osc_available(self) -> bool:
        return self._count_in_osc_seen

    def _wait_count_in(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._count_in_event.wait(timeout=0.05):
                self._count_in_event.clear()
                return

    def fetch_counting_in(self, timeout_s: float = 0.5) -> bool:
        with self._query_lock:
            self._count_in_event.clear()
            self._send("/live/song/get/is_counting_in")
            self._wait_count_in(timeout_s)
            return self._counting_in

    def _on_clip_is_recording(self, _address: str, *args: object) -> None:
        if len(args) >= 3:
            value = _osc_bool(args[2])
            if value is None:
                return
            self._clip_reply_value = value
            self._clip_reply_event.set()

    def _on_has_clip(self, _address: str, *args: object) -> None:
        if len(args) >= 3:
            value = _osc_bool(args[2])
            if value is None:
                return
            self._has_clip_reply_value = value
            self._has_clip_reply_event.set()

    def _on_playing_slot(self, _address: str, *args: object) -> None:
        if len(args) >= 2:
            value = _osc_int(args[1])
            if value is None:
                return
            self._slot_reply_value = value
            self._slot_reply_event.set()

    def _on_fired_slot(self, _address: str, *args: object) -> None:
        if len(args) >= 2:
            value = _osc_int(args[1])
            if value is None:
                return
            self._slot_reply_value = value
            self._slot_reply_event.set()

    def _wait_clip_reply(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._clip_reply_event.wait(timeout=0.05):
                self._clip_reply_event.clear()
                return

    def _wait_slot_reply(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._slot_reply_event.wait(timeout=0.05):
                self._slot_reply_event.clear()
                return

    def fetch_clip_is_recording(self, track_id: int, clip_id: int, timeout_s: float) -> bool:
        with self._query_lock:
            with self._lock:
                self._clip_reply_value = None
            self._clip_reply_event.clear()
            self._send("/live/clip/get/is_recording", track_id, clip_id)
            self._wait_clip_reply(timeout_s)
            with self._lock:
                return bool(self._clip_reply_value)

    def _wait_has_clip_reply(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._has_clip_reply_event.wait(timeout=0.05):
                self._has_clip_reply_event.clear()
                return

    def fetch_clip_slot_has_clip(self, track_id: int, clip_id: int, timeout_s: float) -> bool:
        with self._query_lock:
            with self._lock:
                self._has_clip_reply_value = None
            self._has_clip_reply_event.clear()
            self._send("/live/clip_slot/get/has_clip", track_id, clip_id)
            self._wait_has_clip_reply(timeout_s)
            with self._lock:
                return bool(self._has_clip_reply_value)

    def fetch_playing_slot_index(self, track_id: int, timeout_s: float) -> int:
        with self._query_lock:
            with self._lock:
                self._slot_reply_value = None
            self._slot_reply_event.clear()
            self._send("/live/track/get/playing_slot_index", track_id)
            self._wait_slot_reply(timeout_s)
            with self._lock:
                if self._slot_reply_value is None:
                    return -1
                return int(self._slot_reply_value)

    def fetch_fired_slot_index(self, track_id: int, timeout_s: float) -> int:
        with self._query_lock:
            with self._lock:
                self._slot_reply_value = None
            self._slot_reply_event.clear()
            self._send("/live/track/get/fired_slot_index", track_id)
            self._wait_slot_reply(timeout_s)
            with self._lock:
                if self._slot_reply_value is None:
                    return -1
                return int(self._slot_reply_value)

    def fetch_recording_track_index(self, timeout_s: float) -> int | None:
        """Track index for a session clip that is currently recording, if any."""
        from bridge.clip_recording import _slots_to_check
        from bridge.osc_clip_probe import LiveOscClipProbe

        with self._query_lock:
            probe = LiveOscClipProbe(self)
            for track_id in range(probe.get_num_tracks()):
                for clip_id in _slots_to_check(
                    probe,
                    track_id,
                    last_slots=self._last_recording_slots,
                ):
                    if probe.clip_slot_has_clip(track_id, clip_id) and probe.clip_is_recording(
                        track_id, clip_id
                    ):
                        return track_id
        return None

    def _scan_clip_recording(self) -> bool:
        from bridge.osc_clip_probe import LiveOscClipProbe

        return LiveOscClipProbe(self).any_recording()

    def _clip_poll_loop(self, interval_s: float) -> None:
        while not self._stop_clip_poll.is_set():
            try:
                clip_active = self._scan_clip_recording()
            except Exception:
                logger.exception("Clip recording scan failed")
                clip_active = self._clip_recording
            if clip_active != self._clip_recording:
                was_clip = self._clip_recording
                self._clip_recording = clip_active
                logger.info("Live clip_recording %s→%s", int(was_clip), int(clip_active))
                self._dispatch_edges(source="clip_poll")
                if not was_clip and clip_active:
                    self._start_obs_if_session_recording()
                if was_clip and not clip_active:
                    self._stop_obs_if_idle()
            self._stop_clip_poll.wait(interval_s)

    def start_clip_poll(self, interval_s: float = 0.15) -> None:
        self.stop_clip_poll()
        self._stop_clip_poll.clear()
        try:
            self._clip_recording = self._scan_clip_recording()
        except Exception:
            logger.exception("Initial clip scan failed; assuming not recording")
            self._clip_recording = False
        self._clip_poll_thread = Thread(
            target=self._clip_poll_loop,
            args=(interval_s,),
            daemon=True,
            name="clip-recording-poll",
        )
        self._clip_poll_thread.start()

    def stop_clip_poll(self) -> None:
        self._stop_clip_poll.set()
        if self._clip_poll_thread:
            self._clip_poll_thread.join(timeout=2)
            self._clip_poll_thread = None

    def _on_num_tracks(self, _address: str, *args: object) -> None:
        value = _osc_int(args[-1]) if args else None
        if value is None:
            return
        with self._lock:
            self._num_tracks = value
        self._meta_event.set()

    def _on_arm(self, _address: str, *args: object) -> None:
        if len(args) < 2:
            return
        track_id = _osc_int(args[0])
        armed = _osc_bool(args[1])
        if track_id is None or armed is None:
            logger.debug("Ignoring arm reply with missing values: %s", args)
            return
        with self._lock:
            self._arms[track_id] = armed
        self._meta_event.set()

    def _on_name(self, _address: str, *args: object) -> None:
        if len(args) < 2:
            return
        track_id = _osc_int(args[0])
        if track_id is None or args[1] is None:
            return
        name = str(args[1])
        with self._lock:
            self._names[track_id] = name
        self._meta_event.set()

    def _on_selected_track(self, _address: str, *args: object) -> None:
        value = _osc_int(args[-1]) if args else None
        if value is None:
            return
        with self._lock:
            self._selected_track = value
        self._meta_event.set()

    def _wait_meta(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._meta_event.wait(timeout=0.05):
                self._meta_event.clear()
                return

    def fetch_num_tracks(self, timeout_s: float) -> int:
        with self._query_lock:
            with self._lock:
                self._num_tracks = None
            self._meta_event.clear()
            self._send("/live/song/get/num_tracks")
            self._wait_meta(timeout_s)
            with self._lock:
                return self._num_tracks if self._num_tracks is not None else 0

    def fetch_arm(self, track_id: int, timeout_s: float) -> bool:
        with self._query_lock:
            with self._lock:
                self._arms.pop(track_id, None)
            self._meta_event.clear()
            self._send("/live/track/get/arm", track_id)
            self._wait_meta(timeout_s)
            with self._lock:
                return self._arms.get(track_id, False)

    def fetch_track_name(self, track_id: int, timeout_s: float) -> str:
        with self._query_lock:
            with self._lock:
                self._names.pop(track_id, None)
            self._meta_event.clear()
            self._send("/live/track/get/name", track_id)
            self._wait_meta(timeout_s)
            with self._lock:
                return self._names.get(track_id, "")

    def fetch_selected_track(self, timeout_s: float) -> int:
        with self._query_lock:
            with self._lock:
                self._selected_track = None
            self._meta_event.clear()
            self._send("/live/view/get/selected_track")
            self._wait_meta(timeout_s)
            with self._lock:
                if self._selected_track is None:
                    return -1
                return int(self._selected_track)

    def start(self) -> None:
        dispatcher = Dispatcher()
        dispatcher.map("/live/song/get/record_mode", self._on_record_mode)
        dispatcher.map("/live/song/get/session_record_status", self._on_session_status)
        dispatcher.map("/live/song/get/is_playing", self._on_is_playing)
        dispatcher.map("/live/song/get/is_counting_in", self._on_counting_in)
        dispatcher.map("/live/song/get/num_tracks", self._on_num_tracks)
        dispatcher.map("/live/track/get/arm", self._on_arm)
        dispatcher.map("/live/track/get/name", self._on_name)
        dispatcher.map("/live/view/get/selected_track", self._on_selected_track)
        dispatcher.map("/live/clip/get/is_recording", self._on_clip_is_recording)
        dispatcher.map("/live/clip_slot/get/has_clip", self._on_has_clip)
        dispatcher.map("/live/track/get/playing_slot_index", self._on_playing_slot)
        dispatcher.map("/live/track/get/fired_slot_index", self._on_fired_slot)
        self._server = ReuseAddrOSCUDPServer((self._listen_host, self._listen_port), dispatcher)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.subscribe()
        self.start_clip_poll()
        for edge in self.apply_boot_sync():
            self._on_edge(edge, self.signals)

    def stop(self) -> None:
        self.stop_clip_poll()
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=2)

    def inject(self, address: str, *args: object) -> None:
        """Test seam: simulate AbletonOSC reply."""
        if address == "/live/song/get/record_mode":
            self._on_record_mode(address, *args)
        elif address == "/live/song/get/session_record_status":
            self._on_session_status(address, *args)
        elif address == "/live/song/get/num_tracks":
            self._on_num_tracks(address, *args)
        elif address == "/live/track/get/arm":
            self._on_arm(address, *args)
        elif address == "/live/track/get/name":
            self._on_name(address, *args)
        elif address == "/live/view/get/selected_track":
            self._on_selected_track(address, *args)
        elif address == "/live/song/get/is_playing":
            self._on_is_playing(address, *args)
        elif address == "/live/song/get/is_counting_in":
            self._on_counting_in(address, *args)
