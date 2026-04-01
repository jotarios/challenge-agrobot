"""Unit tests for DMS record parsing in the Matching Engine."""

import json
import pytest

from src.lambdas.matching.parser import parse_dms_record


class TestParseDmsRecord:
    def test_dms_envelope_insert(self):
        record = json.dumps({
            "data": {
                "location_lat": -34.6037,
                "location_lon": -58.3816,
                "metric_type": "temperature",
                "value": 36.5,
                "recorded_at": "2026-03-31T12:00:00Z",
            },
            "metadata": {
                "operation": "insert",
                "table-name": "weather_data",
            },
        })
        result = parse_dms_record(record)
        assert result is not None
        assert result["location_lat"] == -34.6037
        assert result["metric_type"] == "temperature"

    def test_dms_envelope_load(self):
        record = json.dumps({
            "data": {"location_lat": 0.0, "location_lon": 0.0, "metric_type": "humidity", "value": 50.0},
            "metadata": {"operation": "load", "table-name": "weather_data"},
        })
        result = parse_dms_record(record)
        assert result is not None

    def test_dms_envelope_update_ignored(self):
        record = json.dumps({
            "data": {"location_lat": 0.0},
            "metadata": {"operation": "update", "table-name": "weather_data"},
        })
        result = parse_dms_record(record)
        assert result is None

    def test_dms_envelope_wrong_table(self):
        record = json.dumps({
            "data": {"something": "else"},
            "metadata": {"operation": "insert", "table-name": "other_table"},
        })
        result = parse_dms_record(record)
        assert result is None

    def test_direct_format(self):
        record = json.dumps({
            "location_lat": -34.6037,
            "location_lon": -58.3816,
            "metric_type": "temperature",
            "value": 36.5,
        })
        result = parse_dms_record(record)
        assert result is not None
        assert result["location_lat"] == -34.6037

    def test_malformed_json(self):
        result = parse_dms_record("not json at all")
        assert result is None

    def test_empty_json(self):
        result = parse_dms_record("{}")
        assert result is None

    def test_unrecognized_format(self):
        record = json.dumps({"random_key": "random_value"})
        result = parse_dms_record(record)
        assert result is None
