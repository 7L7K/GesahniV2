import json


def _get(client, path: str):
    return client.get(path, headers={"Authorization": "Bearer test"})


def _put(client, path: str, body: dict):
    return client.put(path, json=body, headers={"Authorization": "Bearer test"})


def test_tv_config_defaults_then_save_and_get(client):
    # Defaults when nothing saved
    res = _get(client, "/v1/tv/config?resident_id=r1")
    assert res.status_code == 200
    cfg = res.json()["config"]
    assert cfg["rail"] == "safe"
    # Save a config
    body = {
        "ambient_rotation": 60,
        "rail": "open",
        "quiet_hours": {"start": "22:00", "end": "06:00"},
        "default_vibe": "Turn Up",
    }
    res2 = _put(client, "/v1/tv/config?resident_id=r1", body)
    assert res2.status_code == 200
    # Get returns saved config
    res3 = _get(client, "/v1/tv/config?resident_id=r1")
    assert res3.status_code == 200
    assert res3.json()["config"]["ambient_rotation"] == 60
    assert res3.json()["config"]["rail"] == "open"


def test_tv_config_validation_rail_and_hhmm(client):
    # bad rail
    res = _put(
        client,
        "/v1/tv/config?resident_id=r2",
        {"ambient_rotation": 10, "rail": "danger", "default_vibe": "Calm Night"},
    )
    assert res.status_code == 400
    # bad hh:mm
    res2 = _put(
        client,
        "/v1/tv/config?resident_id=r2",
        {
            "ambient_rotation": 10,
            "rail": "safe",
            "quiet_hours": {"start": "25:00", "end": "00:00"},
            "default_vibe": "Calm Night",
        },
    )
    assert res2.status_code == 400


def test_tv_config_is_per_resident_isolated(client):
    # Save for r1
    _put(
        client,
        "/v1/tv/config?resident_id=r1",
        {"ambient_rotation": 15, "rail": "admin", "default_vibe": "Calm Night"},
    )
    # r2 should still see defaults
    res = _get(client, "/v1/tv/config?resident_id=r2")
    assert res.status_code == 200
    assert res.json()["config"]["rail"] == "safe"

