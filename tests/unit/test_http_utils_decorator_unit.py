import pytest


@pytest.mark.asyncio
async def test_log_exceptions_decorator_propagates():
    from app.http_utils import log_exceptions

    @log_exceptions("mod")
    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await boom()


