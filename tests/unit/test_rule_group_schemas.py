"""Unit tests for RuleGroup Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from src.api.schemas import ConditionCreate, RuleGroupCreate, RuleGroupUpdate


class TestRuleGroupCreate:
    def test_valid_and_group(self):
        group = RuleGroupCreate(
            latitude=-34.6037, longitude=-58.3816, logic="and",
            conditions=[
                ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
            ],
        )
        assert group.logic == "and"
        assert len(group.conditions) == 2

    def test_valid_or_group(self):
        group = RuleGroupCreate(
            latitude=0.0, longitude=0.0, logic="or",
            conditions=[
                ConditionCreate(metric_type="temperature", operator="gt", threshold_value=38.0),
                ConditionCreate(metric_type="wind_speed", operator="gte", threshold_value=60.0),
            ],
        )
        assert group.logic == "or"

    def test_min_two_conditions(self):
        with pytest.raises(ValidationError) as exc_info:
            RuleGroupCreate(
                latitude=0.0, longitude=0.0, logic="and",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                ],
            )
        assert "conditions" in str(exc_info.value)

    def test_empty_conditions_rejected(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=0.0, longitude=0.0, logic="and",
                conditions=[],
            )

    def test_max_ten_conditions(self):
        # 10 conditions should be fine
        group = RuleGroupCreate(
            latitude=0.0, longitude=0.0, logic="and",
            conditions=[
                ConditionCreate(metric_type="temperature", operator="gt", threshold_value=float(i))
                for i in range(10)
            ],
        )
        assert len(group.conditions) == 10

    def test_eleven_conditions_rejected(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=0.0, longitude=0.0, logic="and",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=float(i))
                    for i in range(11)
                ],
            )

    def test_invalid_logic_value(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=0.0, longitude=0.0, logic="xor",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                    ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
                ],
            )

    def test_invalid_latitude(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=91.0, longitude=0.0, logic="and",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                    ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
                ],
            )

    def test_invalid_longitude(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=0.0, longitude=181.0, logic="and",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                    ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
                ],
            )

    def test_condition_invalid_operator(self):
        with pytest.raises(ValidationError):
            RuleGroupCreate(
                latitude=0.0, longitude=0.0, logic="and",
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="bad", threshold_value=30.0),
                    ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
                ],
            )

    def test_default_logic_is_and(self):
        group = RuleGroupCreate(
            latitude=0.0, longitude=0.0,
            conditions=[
                ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                ConditionCreate(metric_type="humidity", operator="lt", threshold_value=20.0),
            ],
        )
        assert group.logic == "and"


class TestRuleGroupUpdate:
    def test_partial_update_logic_only(self):
        update = RuleGroupUpdate(logic="or")
        assert update.logic == "or"
        assert update.conditions is None
        assert update.latitude is None

    def test_partial_update_conditions_only(self):
        update = RuleGroupUpdate(
            conditions=[
                ConditionCreate(metric_type="temperature", operator="gt", threshold_value=40.0),
                ConditionCreate(metric_type="pressure", operator="lt", threshold_value=980.0),
            ],
        )
        assert len(update.conditions) == 2
        assert update.logic is None

    def test_empty_update_valid(self):
        update = RuleGroupUpdate()
        assert update.logic is None
        assert update.conditions is None

    def test_update_conditions_min_two(self):
        with pytest.raises(ValidationError):
            RuleGroupUpdate(
                conditions=[
                    ConditionCreate(metric_type="temperature", operator="gt", threshold_value=30.0),
                ],
            )

    def test_update_invalid_logic(self):
        with pytest.raises(ValidationError):
            RuleGroupUpdate(logic="nand")
