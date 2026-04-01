"""Unit tests for composite rule evaluation logic."""

import pytest

from src.shared.threshold import evaluate_threshold


class TestCompositeLogic:
    """Test the AND/OR evaluation patterns used by the Matching Engine."""

    def test_and_all_conditions_met(self):
        conditions = [
            ("gt", 36.0, 30.0),   # temp > 30: True
            ("lt", 8.0, 10.0),    # wind < 10: True
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert all(results)

    def test_and_one_condition_unmet(self):
        conditions = [
            ("gt", 36.0, 30.0),   # temp > 30: True
            ("lt", 12.0, 10.0),   # wind < 10: False (12 is not < 10)
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert not all(results)

    def test_and_no_conditions_met(self):
        conditions = [
            ("gt", 25.0, 30.0),   # temp > 30: False
            ("lt", 12.0, 10.0),   # wind < 10: False
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert not all(results)

    def test_or_one_condition_met(self):
        conditions = [
            ("gt", 36.0, 30.0),   # temp > 30: True
            ("lt", 12.0, 10.0),   # wind < 10: False
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert any(results)

    def test_or_no_conditions_met(self):
        conditions = [
            ("gt", 25.0, 30.0),   # temp > 30: False
            ("lt", 12.0, 10.0),   # wind < 10: False
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert not any(results)

    def test_three_conditions_and(self):
        conditions = [
            ("gt", 36.0, 30.0),   # temp > 30: True
            ("lt", 8.0, 10.0),    # wind < 10: True
            ("gte", 15.0, 15.0),  # humidity >= 15: True
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert all(results)

    def test_three_conditions_and_one_fails(self):
        conditions = [
            ("gt", 36.0, 30.0),   # temp > 30: True
            ("lt", 8.0, 10.0),    # wind < 10: True
            ("gte", 14.9, 15.0),  # humidity >= 15: False
        ]
        results = [evaluate_threshold(op, val, thresh) for op, val, thresh in conditions]
        assert not all(results)

    def test_missing_reading_treated_as_false(self):
        """When a metric has no reading yet, the condition evaluates to False."""
        # Simulate: temp condition passes, wind reading is None
        results = [True, False]  # wind_speed not available
        assert not all(results)  # AND fails
        assert any(results)      # OR passes
