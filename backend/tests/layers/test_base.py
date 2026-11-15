from app.layers.base import LayerUnavailable


def test_layer_unavailable_carries_fix():
    ex = LayerUnavailable("missing", "python scripts/download_data.py")
    assert ex.detail == "missing" and ex.fix == "python scripts/download_data.py"
    assert isinstance(ex, Exception)
    assert str(ex) == "missing"
