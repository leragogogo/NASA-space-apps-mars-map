import pytest

from app.core.config import Settings
from app.layers.contracts import GraphInputs, LayerDataError
from app.layers.inputs.load import load_all
from app.layers.validate import validate_inputs


def test_load_all_builds_validated_inputs_on_one_grid(fixture_settings):
    inputs = load_all(fixture_settings)
    assert isinstance(inputs, GraphInputs)
    validate_inputs(inputs)
    assert inputs.relief.grid == inputs.weather.grid == inputs.grid
    assert len(inputs.poi.features) == 7


def test_load_all_raises_layer_data_error_when_data_is_missing(tmp_path):
    with pytest.raises(LayerDataError):
        load_all(Settings(data_dir=tmp_path))
