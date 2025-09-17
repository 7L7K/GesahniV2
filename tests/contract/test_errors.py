def _assert_envelope(resp, code):
    body = resp.json()
    # This application uses {code, message, details} format
    assert set(body.keys()) == {"code", "message", "details"}
    assert body["code"] == code
    assert isinstance(body["details"], dict)


def test_not_found_envelope(client):
    """Test that 404 errors return the proper envelope format.

    This test codifies the error response format to prevent backsliding.
    The application should consistently return errors in the format:
    {"code": "...", "message": "...", "details": {...}}
    """
    # Test the not found endpoint that actually exists
    r = client.get("/test-errors/test/not-found")
    assert r.status_code == 404
    _assert_envelope(r, "not_found")
