import logging

from bridge.__main__ import configure_logging


def test_configure_logging_suppresses_obs_client_connection_details():
    obs_logger = logging.getLogger("obsws_python.baseclient")
    obs_logger.setLevel(logging.NOTSET)

    configure_logging(verbose=False)

    assert obs_logger.level == logging.WARNING
