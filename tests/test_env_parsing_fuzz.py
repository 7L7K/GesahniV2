import os
import random

from app.memory.env_utils import _get_sim_threshold, _get_mem_top_k


def test_env_parsing_fuzz(monkeypatch):
    # Fuzz SIM_THRESHOLD and MEM_TOP_K with weird values
    for raw in ["", " ", "-1", "2", "abc", "0.3", "1", "0", "0.9999"]:
        os.environ["SIM_THRESHOLD"] = raw
        val = _get_sim_threshold()
        assert 0.0 <= val <= 1.0

    for raw in ["-5", "100", "x", "3", "10", "1"]:
        os.environ["MEM_TOP_K"] = raw
        k = _get_mem_top_k()
        assert 1 <= k <= 10


