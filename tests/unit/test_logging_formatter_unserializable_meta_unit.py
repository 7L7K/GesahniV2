import logging


def test_json_formatter_unserializable_meta_fallback():
    from app.logging_config import JsonFormatter

    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="comp",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="plain",
        args=(),
        exc_info=None,
    )

    # set an unserialisable object
    class X: ...

    rec.meta = {"x": X()}
    s = fmt.format(rec)
    # fallback returns plain message
    assert s == "plain"
