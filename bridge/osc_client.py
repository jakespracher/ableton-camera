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


class OscListener:
    """Listens for AbletonOSC record property changes; emits STARTED/STOPPED edges."""

    def __init__(
        self,
        send_host: str,
        send_port: int,
        listen_host: str,
        listen_port: int,
        on_edge: RecordingHandler,
    ) -> None:
        self._send_host = send_host
        self._send_port = send_port
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._on_edge = on_edge
        self._client = SimpleUDPClient(send_host, send_port)
        self._state = RecordingStateMachine()
        self._arrangement = 0
        self._session_status = 0
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
        return RecordingSignals(self._arrangement, self._session_status)

    def subscribe(self) -> None:
        self._send("/live/song/start_listen/record_mode")
        self._send("/live/song/start_listen/session_record_status")
        self._query_initial_state()

    def _query_initial_state(self) -> None:
        self._send("/live/song/get/record_mode")
        self._send("/live/song/get/session_record_status")

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
        self.handle_session_status(address, *args)
        self._dispatch_edges()

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
        dispatcher.map("/live/song/get/num_tracks", self._on_num_tracks)
        dispatcher.map("/live/track/get/arm", self._on_arm)
        dispatcher.map("/live/track/get/name", self._on_name)
        dispatcher.map("/live/view/get/selected_track", self._on_selected_track)
        self._server = BlockingOSCUDPServer((self._listen_host, self._listen_port), dispatcher)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.subscribe()
        for edge in self.apply_boot_sync():
            self._on_edge(edge, self.signals)

    def stop(self) -> None:
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
