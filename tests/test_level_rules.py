"""Unit tests for Level crossing alert rules in PricePulse."""

import datetime
from decimal import Decimal
import unittest

from price_alerts.data_loader import PriceRecord
from price_alerts.engine import evaluate_level_rule
from price_alerts.rules import LevelRule


def _make_record(date_str: str, instrument: str, price: str) -> PriceRecord:
    return PriceRecord(
        date=datetime.date.fromisoformat(date_str),
        instrument=instrument,
        close=Decimal(price),
    )


class TestLevelRules(unittest.TestCase):
    """Test suite covering all level rule semantics and edge cases."""

    def test_01_level_crossing_below(self):
        """1. Level crossing below a threshold triggers an alert on the transition day."""
        rule = LevelRule(
            id="r_below",
            instrument="INFY",
            type="level",
            direction="below",
            level=Decimal("1500"),
        )
        records = [
            _make_record("2026-09-01", "INFY", "1520.00"),
            _make_record("2026-09-02", "INFY", "1490.00"),
        ]
        alerts = evaluate_level_rule(rule, records)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.date, datetime.date(2026, 9, 2))
        self.assertEqual(alert.rule_id, "r_below")
        self.assertEqual(alert.instrument, "INFY")
        self.assertEqual(alert.description, "level below 1500")
        self.assertIn("Price crossed below threshold 1500", alert.explanation)

    def test_02_level_crossing_above(self):
        """2. Level crossing above a threshold triggers an alert on the transition day."""
        rule = LevelRule(
            id="r_above",
            instrument="TCS",
            type="level",
            direction="above",
            level=Decimal("3500"),
        )
        records = [
            _make_record("2026-09-01", "TCS", "3450.00"),
            _make_record("2026-09-02", "TCS", "3510.00"),
        ]
        alerts = evaluate_level_rule(rule, records)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.date, datetime.date(2026, 9, 2))
        self.assertEqual(alert.rule_id, "r_above")
        self.assertEqual(alert.instrument, "TCS")
        self.assertEqual(alert.description, "level above 3500")
        self.assertIn("Price crossed above threshold 3500", alert.explanation)

    def test_03_price_remaining_beyond_does_not_retrigger(self):
        """3. A price remaining beyond a threshold must not retrigger the alert on subsequent days."""
        rule = LevelRule(
            id="r_below",
            instrument="INFY",
            type="level",
            direction="below",
            level=Decimal("1500"),
        )
        records = [
            _make_record("2026-09-01", "INFY", "1520.00"),  # initial: above
            _make_record("2026-09-02", "INFY", "1490.00"),  # day 2: crosses below -> alert
            _make_record("2026-09-03", "INFY", "1480.00"),  # day 3: stays below -> no alert
            _make_record("2026-09-04", "INFY", "1450.00"),  # day 4: stays below -> no alert
        ]
        alerts = evaluate_level_rule(rule, records)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].date, datetime.date(2026, 9, 2))

    def test_04_crossing_back_and_crossing_again(self):
        """4. Crossing back and crossing again must produce a new alert."""
        rule = LevelRule(
            id="r_cycle",
            instrument="INFY",
            type="level",
            direction="below",
            level=Decimal("1500"),
        )
        records = [
            _make_record("2026-09-01", "INFY", "1520.00"),
            _make_record("2026-09-02", "INFY", "1490.00"),  # Alert 1
            _make_record("2026-09-03", "INFY", "1510.00"),  # Crosses back above
            _make_record("2026-09-04", "INFY", "1495.00"),  # Alert 2
            _make_record("2026-09-05", "INFY", "1490.00"),  # Stays below -> no alert
        ]
        alerts = evaluate_level_rule(rule, records)
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].date, datetime.date(2026, 9, 2))
        self.assertEqual(alerts[1].date, datetime.date(2026, 9, 4))

    def test_05_exact_threshold_boundary_behavior(self):
        """5. Exact-threshold boundary behavior must be strictly consistent.

        'below': prev >= level and curr < level.
        'above': prev <= level and curr > level.
        """
        threshold = Decimal("1500.00")
        rule_below = LevelRule(id="rb", instrument="INFY", type="level", direction="below", level=threshold)
        rule_above = LevelRule(id="ra", instrument="INFY", type="level", direction="above", level=threshold)

        # Case A: Exactly on threshold transitioning to below (1500.00 -> 1499.99)
        # 1500.00 is >= 1500.00, so it qualifies as prev. curr < 1500.00. Should fire 'below'.
        records_a = [
            _make_record("2026-09-01", "INFY", "1500.00"),
            _make_record("2026-09-02", "INFY", "1499.99"),
        ]
        alerts_a = evaluate_level_rule(rule_below, records_a)
        self.assertEqual(len(alerts_a), 1)
        self.assertEqual(alerts_a[0].date, datetime.date(2026, 9, 2))

        # Case B: Exactly on threshold transitioning to above (1500.00 -> 1500.01)
        # 1500.00 is <= 1500.00, so it qualifies as prev. curr > 1500.00. Should fire 'above'.
        records_b = [
            _make_record("2026-09-01", "INFY", "1500.00"),
            _make_record("2026-09-02", "INFY", "1500.01"),
        ]
        alerts_b = evaluate_level_rule(rule_above, records_b)
        self.assertEqual(len(alerts_b), 1)
        self.assertEqual(alerts_b[0].date, datetime.date(2026, 9, 2))

        # Case C: Below threshold touching exact threshold (1490.00 -> 1500.00)
        # For 'above': curr is 1500.00 which is NOT strictly > 1500.00. Must NOT fire.
        # For 'below': curr is 1500.00 which is NOT < 1500.00. Must NOT fire.
        records_c = [
            _make_record("2026-09-01", "INFY", "1490.00"),
            _make_record("2026-09-02", "INFY", "1500.00"),
        ]
        self.assertEqual(len(evaluate_level_rule(rule_above, records_c)), 0)
        self.assertEqual(len(evaluate_level_rule(rule_below, records_c)), 0)

        # Case D: Staying exactly on threshold (1500.00 -> 1500.00)
        # Must not fire either rule.
        records_d = [
            _make_record("2026-09-01", "INFY", "1500.00"),
            _make_record("2026-09-02", "INFY", "1500.00"),
        ]
        self.assertEqual(len(evaluate_level_rule(rule_above, records_d)), 0)
        self.assertEqual(len(evaluate_level_rule(rule_below, records_d)), 0)

    def test_06_no_alert_on_first_observation(self):
        """6. The first available observation for an instrument has no previous close, so cannot alert."""
        rule_below = LevelRule(id="rb", instrument="INFY", type="level", direction="below", level=Decimal("1500"))
        rule_above = LevelRule(id="ra", instrument="INFY", type="level", direction="above", level=Decimal("1500"))

        # Single record even if far below threshold
        records_single = [_make_record("2026-09-01", "INFY", "1200.00")]
        self.assertEqual(len(evaluate_level_rule(rule_below, records_single)), 0)
        self.assertEqual(len(evaluate_level_rule(rule_above, records_single)), 0)

        # Empty records
        self.assertEqual(len(evaluate_level_rule(rule_below, [])), 0)


if __name__ == "__main__":
    unittest.main()
