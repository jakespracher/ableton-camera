from __future__ import annotations

import json
import logging
import socket
import socketserver
import threading
from collections.abc import Callable

from bridge.capture import CaptureRequest, CaptureResponse

logger = logging.getLogger(__name__)

CaptureHandler = Callable[[CaptureRequest], CaptureResponse]


class CaptureControlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    capture_handler: CaptureHandler
    thread: threading.Thread


class _CaptureControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            raw = self.rfile.readline()
            request = CaptureRequest.from_json_dict(json.loads(raw.decode("utf-8")))
            response = self.server.capture_handler(request)
        except Exception as exc:
            logger.exception("Capture control request failed")
            response = CaptureResponse(
                ok=False,
                message=f"Capture control request failed: {exc}",
                error="control_error",
            )
        payload = json.dumps(response.to_json_dict()).encode("utf-8") + b"\n"
        self.wfile.write(payload)


def start_control_server(
    host: str,
    port: int,
    handler: CaptureHandler,
) -> CaptureControlServer:
    server = CaptureControlServer((host, port), _CaptureControlHandler)
    server.capture_handler = handler
    server.thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="capture-control-server",
    )
    server.thread.start()
    return server


def send_capture_request(
    host: str,
    port: int,
    request: CaptureRequest,
    *,
    timeout_s: float = 5.0,
) -> CaptureResponse:
    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        sock.settimeout(timeout_s)
        file = sock.makefile("rwb")
        try:
            payload = json.dumps(request.to_json_dict()).encode("utf-8") + b"\n"
            file.write(payload)
            file.flush()
            raw = file.readline()
        finally:
            file.close()
    if not raw:
        raise RuntimeError("capture control server closed without a response")
    return CaptureResponse.from_json_dict(json.loads(raw.decode("utf-8")))
