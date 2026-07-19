from pathlib import Path

from bridge import __main__ as main_module
from bridge.capture import CaptureRequest, CaptureResponse


def _write_config(path: Path) -> None:
    path.write_text(
        """
osc:
  send_host: 127.0.0.1
  send_port: 11000
  listen_host: 127.0.0.1
  listen_port: 11001
obs:
  host: 127.0.0.1
  port: 4455
paths:
  staging_dir: /tmp/staging
control:
  host: 127.0.0.1
  port: 11012
""".strip(),
        encoding="utf-8",
    )


def test_capture_cli_sends_control_request(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    sent: list[tuple[str, int, CaptureRequest]] = []

    def fake_send_capture_request(
        host: str,
        port: int,
        request: CaptureRequest,
        *,
        timeout_s: float,
    ) -> CaptureResponse:
        sent.append((host, port, request))
        return CaptureResponse(
            ok=True,
            message="Captured",
            video_path=Path("/tmp/video.mov"),
            sidecar_path=Path("/tmp/last_take.json"),
        )

    monkeypatch.setattr(
        main_module,
        "send_capture_request",
        fake_send_capture_request,
        raising=False,
    )

    result = main_module.main(
        [
            "capture",
            "--config",
            str(config_path),
            "--bars",
            "2",
            "--destination",
            "session",
        ]
    )

    assert result == 0
    assert sent == [("127.0.0.1", 11012, CaptureRequest(bars=2, destination="session"))]
    assert "/tmp/video.mov" in capsys.readouterr().out


def test_capture_cli_returns_nonzero_on_capture_error(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    def fake_send_capture_request(
        host: str,
        port: int,
        request: CaptureRequest,
        *,
        timeout_s: float,
    ) -> CaptureResponse:
        return CaptureResponse(
            ok=False,
            message="OBS Replay Buffer was started; run capture again after it has history.",
            error="replay_buffer_started",
        )

    monkeypatch.setattr(
        main_module,
        "send_capture_request",
        fake_send_capture_request,
        raising=False,
    )

    result = main_module.main(["capture", "--config", str(config_path)])

    assert result == 1
    assert "Replay Buffer was started" in capsys.readouterr().err
