def test_bucket_rate_limit_and_retry_after():
    from app.security import _bucket_rate_limit, _bucket_retry_after

    bucket = {}
    # allow first 3 in period 60
    assert _bucket_rate_limit("u", bucket, 3, 60.0)
    assert _bucket_rate_limit("u", bucket, 3, 60.0)
    assert _bucket_rate_limit("u", bucket, 3, 60.0)
    assert not _bucket_rate_limit("u", bucket, 3, 60.0)
    ra = _bucket_retry_after(bucket, 60.0)
    assert isinstance(ra, int) and ra >= 0


