from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from threading import Thread

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from bridge.recording_state import RecordingEdge, RecordingSignals, RecordingStateMachine

logger = logging.getLogger(__name__)

RecordingHandler = Callable[[RecordingEdge, RecordingSignals], None]


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
    ) -> None:
        self._send_host = send_host
        self._send_port = send_port
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._on_edge = on_edge
        self._on_count_in_finished = on_count_in_finished
        self._client = SimpleUDPClient(send_host, send_port)
        self._state = RecordingStateMachine()
        self._arrangement = 0
        self._session_status = 0
        self._counting_in = False
        self._count_in_event = threading.Event()
        self._clip_recording = False
        self._clip_poll_thread: Thread | None = None
        self._stop_clip_poll = threading.Event()
        self._clip_reply_event = threading.Event()
        self._clip_reply_value: bool | None = None
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
        self._send("/live/song/start_listen/is_counting_in")
        self._query_initial_state()

    def _query_initial_state(self) -> None:
        self._send("/live/song/get/record_mode")
        self._send("/live/song/get/session_record_status")
        self._send("/live/song/get/is_counting_in")

    def is_counting_in(self) -> bool:
        return self._counting_in

    def _send(self, address: str, *args: int | float | str) -> None:
        payload = list(args) if args else []
        log = getattr(self, "_sent_log", None)
        if log is not None:
            log.append((address, payload))
        self._client.send_message(address, payload)

    def handle_record_mode(self, _address: str, *args: int) -> None:
        if args:
            self._arrangement = int(args[-1])

    def handle_session_status(self, _address: str, *args: int) -> None:
        if args:
            self._session_status = int(args[-1])

    def apply_boot_sync(self) -> list[RecordingEdge]:
        return self._state.sync_initial(self.signals)

    def _dispatch_edges(self) -> None:
        for edge in self._state.apply(self.signals):
            self._on_edge(edge, self.signals)

    def _on_record_mode(self, address: str, *args: int) -> None:
        self.handle_record_mode(address, *args)
        self._dispatch_edges()

    def _on_session_status(self, address: str, *args: int) -> None:
        prev = self._session_status
        self.handle_session_status(address, *args)
        # Session record engaged: start OBS even before clip is_recording is visible.
        if self._session_status != 0 and prev == 0:
            self._on_edge(RecordingEdge.STARTED, self.signals)
        self._dispatch_edges()

    def _on_counting_in(self, _address: str, *args: int) -> None:
        if not args:
            return
        was_counting = self._counting_in
        self._counting_in = bool(int(args[-1]))
        self._count_in_event.set()
        if was_counting and not self._counting_in and self._on_count_in_finished:
            self._on_count_in_finished(self.signals)

    def _wait_count_in(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._count_in_event.wait(timeout=0.05):
                self._count_in_event.clear()
                return

    def fetch_counting_in(self, timeout_s: float = 0.5) -> bool:
        self._count_in_event.clear()
        self._send("/live/song/get/is_counting_in")
        self._wait_count_in(timeout_s)
        return self._counting_in

    def _on_clip_is_recording(self, _address: str, *args: int) -> None:
        if len(args) >= 3:
            self._clip_reply_value = bool(int(args[2]))
            self._clip_reply_event.set()

    def _on_playing_slot(self, _address: str, *args: int) -> None:
        if len(args) >= 2:
            self._slot_reply_value = int(args[1])
            self._slot_reply_event.set()

    def _on_fired_slot(self, _address: str, *args: int) -> None:
        if len(args) >= 2:
            self._slot_reply_value = int(args[1])
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
        with self._lock:
            self._clip_reply_value = None
        self._clip_reply_event.clear()
        self._send("/live/clip/get/is_recording", track_id, clip_id)
        self._wait_clip_reply(timeout_s)
        with self._lock:
            return bool(self._clip_reply_value)

    def fetch_playing_slot_index(self, track_id: int, timeout_s: float) -> int:
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
        with self._lock:
            self._slot_reply_value = None
        self._slot_reply_event.clear()
        self._send("/live/track/get/fired_slot_index", track_id)
        self._wait_slot_reply(timeout_s)
        with self._lock:
            if self._slot_reply_value is None:
                return -1
            return int(self._slot_reply_value)

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
                self._clip_recording = clip_active
                logger.info("clip_recording=%s", clip_active)
                self._dispatch_edges()
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

    def _on_num_tracks(self, _address: str, *args: int) -> None:
        if args:
            with self._lock:
                self._num_tracks = int(args[-1])
            self._meta_event.set()

    def _on_arm(self, _address: str, *args: int) -> None:
        if len(args) >= 2:
            with self._lock:
                self._arms[int(args[0])] = bool(int(args[1]))
            self._meta_event.set()

    def _on_name(self, _address: str, *args) -> None:
        if len(args) >= 2:
            track_id = int(args[0])
            name = str(args[1])
            with self._lock:
                self._names[track_id] = name
            self._meta_event.set()

    def _on_selected_track(self, _address: str, *args: int) -> None:
        if args:
            with self._lock:
                self._selected_track = int(args[-1])
            self._meta_event.set()

    def _wait_meta(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._meta_event.wait(timeout=0.05):
                self._meta_event.clear()
                return

    def fetch_num_tracks(self, timeout_s: float) -> int:
        with self._lock:
            self._num_tracks = None
        self._meta_event.clear()
        self._send("/live/song/get/num_tracks")
        self._wait_meta(timeout_s)
        with self._lock:
            return self._num_tracks if self._num_tracks is not None else 0

    def fetch_arm(self, track_id: int, timeout_s: float) -> bool:
        self._meta_event.clear()
        self._send("/live/track/get/arm", track_id)
        self._wait_meta(timeout_s)
        with self._lock:
            return self._arms.get(track_id, False)

    def fetch_track_name(self, track_id: int, timeout_s: float) -> str:
        self._meta_event.clear()
        self._send("/live/track/get/name", track_id)
        self._wait_meta(timeout_s)
        with self._lock:
            return self._names.get(track_id, "")

    def fetch_selected_track(self, timeout_s: float) -> int:
        with self._lock:
            self._selected_track = None
        self._meta_event.clear()
        self._send("/live/view/get/selected_track")
        self._wait_meta(timeout_s)
        with self._lock:
            return self._selected_track if self._selected_track is not None else 0

    def start(self) -> None:
        dispatcher = Dispatcher()
        dispatcher.map("/live/song/get/record_mode", self._on_record_mode)
        dispatcher.map("/live/song/get/session_record_status", self._on_session_status)
        dispatcher.map("/live/song/get/is_counting_in", self._on_counting_in)
        dispatcher.map("/live/song/get/num_tracks", self._on_num_tracks)
        dispatcher.map("/live/track/get/arm", self._on_arm)
        dispatcher.map("/live/track/get/name", self._on_name)
        dispatcher.map("/live/view/get/selected_track", self._on_selected_track)
        dispatcher.map("/live/clip/get/is_recording", self._on_clip_is_recording)
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

    def inject(self, address: str, *args: int | str) -> None:
        """Test seam: simulate AbletonOSC reply."""
        if address == "/live/song/get/record_mode":
            self._on_record_mode(address, *[int(a) for a in args])
        elif address == "/live/song/get/session_record_status":
            self._on_session_status(address, *[int(a) for a in args])
        elif address == "/live/song/get/num_tracks":
            self._on_num_tracks(address, *[int(a) for a in args])
        elif address == "/live/track/get/arm":
            self._on_arm(address, *[int(a) for a in args])
        elif address == "/live/track/get/name":
            self._on_name(address, *args)
        elif address == "/live/view/get/selected_track":
            self._on_selected_track(address, *[int(a) for a in args])
        elif address == "/live/song/get/is_counting_in":
            self._on_counting_in(address, *[int(a) for a in args])
