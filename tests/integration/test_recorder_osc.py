import pytest

from bridge.osc_client import OscListener
from bridge.recorder import Recorder
from tests.fakes.fake_obs import FakeObsClient
from tests.fakes.fake_osc_query import FakeOscQuery


@pytest.mark.integration
def test_osc_inject_drives_recorder(output_dir, staging_dir):
    obs = FakeObsClient(staging_dir)
    metadata = FakeOscQuery(num_tracks=1, armed={0: True}, names={0: "Bass"})
    recorder = Recorder(obs, metadata, output_dir, staging_dir)

    listener = OscListener(
        "127.0.0.1",
        11000,
        "127.0.0.1",
        11001,
        recorder.on_edge,
    )
    staged = staging_dir / "clip.mkv"
    staged.write_bytes(b"v")
    obs.set_staged_file(staged)

    listener.inject("/live/song/get/record_mode", 1)
    listener.inject("/live/song/get/record_mode", 0)

    assert obs.calls == ["start", "stop"]
    assert list(output_dir.glob("Bass_*.mkv"))
