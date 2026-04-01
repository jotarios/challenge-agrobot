"""Unit tests for threshold comparison logic."""

import pytest

from src.shared.threshold import evaluate_threshold


class TestEvaluateThreshold:
    # ── GT (greater than) ────────────────────────────────────
    def test_gt_above(self):
        assert evaluate_threshold("gt", 36.0, 35.0) is True

    def test_gt_equal(self):
        assert evaluate_threshold("gt", 35.0, 35.0) is False

    def test_gt_below(self):
        assert evaluate_threshold("gt", 34.0, 35.0) is False

    # ── GTE (greater than or equal) ──────────────────────────
    def test_gte_above(self):
        assert evaluate_threshold("gte", 36.0, 35.0) is True

    def test_gte_equal(self):
        assert evaluate_threshold("gte", 35.0, 35.0) is True

    def test_gte_below(self):
        assert evaluate_threshold("gte", 34.0, 35.0) is False

    # ── LT (less than) ──────────────────────────────────────
    def test_lt_below(self):
        assert evaluate_threshold("lt", -6.0, -5.0) is True

    def test_lt_equal(self):
        assert evaluate_threshold("lt", -5.0, -5.0) is False

    def test_lt_above(self):
        assert evaluate_threshold("lt", -4.0, -5.0) is False

    # ── LTE (less than or equal) ─────────────────────────────
    def test_lte_below(self):
        assert evaluate_threshold("lte", -6.0, -5.0) is True

    def test_lte_equal(self):
        assert evaluate_threshold("lte", -5.0, -5.0) is True

    def test_lte_above(self):
        assert evaluate_threshold("lte", -4.0, -5.0) is False

    # ── EQ (equal) ───────────────────────────────────────────
    def test_eq_match(self):
        assert evaluate_threshold("eq", 35.0, 35.0) is True

    def test_eq_no_match(self):
        assert evaluate_threshold("eq", 35.1, 35.0) is False

    # ── Float precision ──────────────────────────────────────
    def test_float_precision_gt(self):
        # 35.00001 > 35.0 should be True
        assert evaluate_threshold("gt", 35.00001, 35.0) is True

    def test_float_precision_eq(self):
        # Decimal comparison from same-precision floats
        assert evaluate_threshold("eq", 35.0000, 35.0) is True
        # Known: 0.1 + 0.2 != 0.3 in float, and Decimal(str()) preserves that
        assert evaluate_threshold("eq", 0.1 + 0.2, 0.3) is False

    # ── Unknown operator ─────────────────────────────────────
    def test_unknown_operator_returns_false(self):
        assert evaluate_threshold("invalid", 36.0, 35.0) is False

    def test_empty_operator_returns_false(self):
        assert evaluate_threshold("", 36.0, 35.0) is False
