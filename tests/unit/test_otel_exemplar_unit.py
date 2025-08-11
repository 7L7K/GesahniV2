def test_observe_with_exemplar_fallbacks():
    from app import otel_utils

    class Hist:
        def __init__(self):
            self.values = []

        def observe(self, value, **kwargs):
            # simulate older client rejecting exemplar kw
            if "exemplar" in kwargs:
                raise TypeError("no exemplar")
            self.values.append(value)

    h = Hist()
    otel_utils.observe_with_exemplar(h, 1.23, exemplar_labels={"a": "b"})
    assert h.values == [1.23]


