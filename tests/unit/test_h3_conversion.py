"""Unit tests for H3 coordinate conversion."""

import h3

from src.shared.constants import H3_RESOLUTION


class TestH3Conversion:
    def test_valid_coordinates(self):
        # Buenos Aires
        idx = h3.latlng_to_cell(-34.6037, -58.3816, H3_RESOLUTION)
        assert isinstance(idx, str)
        assert len(idx) > 0

    def test_different_cities_different_cells(self):
        ba = h3.latlng_to_cell(-34.6037, -58.3816, H3_RESOLUTION)
        sp = h3.latlng_to_cell(-23.5505, -46.6333, H3_RESOLUTION)
        assert ba != sp

    def test_nearby_coords_same_cell(self):
        # Two points very close together should be in the same H3 cell
        a = h3.latlng_to_cell(-34.6037, -58.3816, H3_RESOLUTION)
        b = h3.latlng_to_cell(-34.6038, -58.3817, H3_RESOLUTION)
        assert a == b

    def test_resolution_7(self):
        idx = h3.latlng_to_cell(-34.6037, -58.3816, H3_RESOLUTION)
        assert h3.get_resolution(idx) == 7

    def test_boundary_coordinates(self):
        # North pole
        idx = h3.latlng_to_cell(89.99, 0.0, H3_RESOLUTION)
        assert isinstance(idx, str)

        # South pole
        idx = h3.latlng_to_cell(-89.99, 0.0, H3_RESOLUTION)
        assert isinstance(idx, str)

    def test_dateline_coordinates(self):
        # Near international date line
        idx = h3.latlng_to_cell(0.0, 179.99, H3_RESOLUTION)
        assert isinstance(idx, str)

    def test_zero_coordinates(self):
        # Null Island (0, 0)
        idx = h3.latlng_to_cell(0.0, 0.0, H3_RESOLUTION)
        assert isinstance(idx, str)
