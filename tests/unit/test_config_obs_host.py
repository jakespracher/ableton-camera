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


def test_sync_offset_defaults_to_zero():
    data = {
        "osc": {
            "send_host": "127.0.0.1",
            "send_port": 11000,
            "listen_host": "127.0.0.1",
            "listen_port": 11001,
        },
        "obs": {"host": "127.0.0.1", "port": 4455},
        "paths": {"staging_dir": "/tmp/staging"},
    }

    config = AppConfig.from_dict(data)

    assert config.sync_offset_ms == 0


def test_sync_offset_reads_documented_config_value():
    data = {
        "osc": {
            "send_host": "127.0.0.1",
            "send_port": 11000,
            "listen_host": "127.0.0.1",
            "listen_port": 11001,
        },
        "obs": {"host": "127.0.0.1", "port": 4455},
        "paths": {"staging_dir": "/tmp/staging"},
        "sync": {"obs_source_sync_offset_ms": 120},
    }

    config = AppConfig.from_dict(data)

    assert config.sync_offset_ms == 120


def test_control_defaults_to_localhost():
    data = {
        "osc": {
            "send_host": "127.0.0.1",
            "send_port": 11000,
            "listen_host": "127.0.0.1",
            "listen_port": 11001,
        },
        "obs": {"host": "127.0.0.1", "port": 4455},
        "paths": {"staging_dir": "/tmp/staging"},
    }

    config = AppConfig.from_dict(data)

    assert config.control.host == "127.0.0.1"
    assert config.control.port == 11002


def test_control_reads_config_value():
    data = {
        "osc": {
            "send_host": "127.0.0.1",
            "send_port": 11000,
            "listen_host": "127.0.0.1",
            "listen_port": 11001,
        },
        "obs": {"host": "127.0.0.1", "port": 4455},
        "paths": {"staging_dir": "/tmp/staging"},
        "control": {"host": "127.0.0.1", "port": 11012},
    }

    config = AppConfig.from_dict(data)

    assert config.control.host == "127.0.0.1"
    assert config.control.port == 11012
