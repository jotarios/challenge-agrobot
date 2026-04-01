"""Unit tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from src.api.schemas import RuleCreate, RuleUpdate, UserRegister


class TestUserRegister:
    def test_valid_registration(self):
        user = UserRegister(email="test@example.com", password="password123")
        assert user.email == "test@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserRegister(email="not-an-email", password="password123")

    def test_short_password(self):
        with pytest.raises(ValidationError):
            UserRegister(email="test@example.com", password="short")

    def test_empty_password(self):
        with pytest.raises(ValidationError):
            UserRegister(email="test@example.com", password="")


class TestRuleCreate:
    def test_valid_rule(self):
        rule = RuleCreate(
            latitude=-34.6037,
            longitude=-58.3816,
            metric_type="temperature",
            operator="gt",
            threshold_value=35.0,
        )
        assert rule.operator.value == "gt"

    def test_invalid_latitude(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                latitude=91.0, longitude=0.0, metric_type="temperature",
                operator="gt", threshold_value=35.0,
            )

    def test_invalid_longitude(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                latitude=0.0, longitude=181.0, metric_type="temperature",
                operator="gt", threshold_value=35.0,
            )

    def test_invalid_operator(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                latitude=0.0, longitude=0.0, metric_type="temperature",
                operator="invalid", threshold_value=35.0,
            )

    def test_metric_type_accepted_at_schema_level(self):
        # metric_type validation is now at the route level (DB check), not schema
        # Schema only validates format (non-empty, max length)
        rule = RuleCreate(
            latitude=0.0, longitude=0.0, metric_type="any_string",
            operator="gt", threshold_value=35.0,
        )
        assert rule.metric_type == "any_string"

    def test_all_valid_operators(self):
        for op in ["gt", "gte", "lt", "lte", "eq"]:
            rule = RuleCreate(
                latitude=0.0, longitude=0.0, metric_type="temperature",
                operator=op, threshold_value=35.0,
            )
            assert rule.operator.value == op


class TestRuleUpdate:
    def test_partial_update(self):
        update = RuleUpdate(threshold_value=40.0)
        assert update.threshold_value == 40.0
        assert update.latitude is None

    def test_empty_update_valid(self):
        update = RuleUpdate()
        assert update.latitude is None
        assert update.operator is None
