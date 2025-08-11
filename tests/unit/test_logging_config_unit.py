import logging


def test_configure_logging_and_error_buffer(monkeypatch, capsys):
    from app import logging_config as lc

    monkeypatch.setenv("LOG_LEVEL", "INFO")
    lc.configure_logging()

    logger = logging.getLogger("test")
    logger.error("boom")

    errors = lc.get_last_errors(1)
    assert errors and errors[-1]["msg"] == "boom"


