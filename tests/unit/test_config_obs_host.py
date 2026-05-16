from bridge.config import AppConfig


def test_obs_host_defaults_when_null_or_empty():
    for obs in ({"host": None, "port": 4455}, {"port": 4455}, {"host": "", "port": 4455}):
        data = {
            "osc": {
                "send_host": "127.0.0.1",
                "send_port": 11000,
                "listen_host": "127.0.0.1",
                "listen_port": 11001,
            },
            "obs": obs,
            "paths": {"staging_dir": "/tmp/staging"},
        }
        config = AppConfig.from_dict(data)
        assert config.obs.host == "127.0.0.1"
