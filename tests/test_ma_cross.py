"""Unit tests for Moving-Average Crossover alert rules in PricePulse."""

import datetime
from decimal import Decimal
import unittest

from price_alerts.data_loader import PriceRecord
from price_alerts.engine import evaluate_ma_cross_rule
from price_alerts.rules import MACrossRule


def _make_series(prices: list, start_day: int = 1, instrument: str = "TCS") -> list:
    """Helper to generate a daily PriceRecord list for testing."""
    records = []
    for idx, p in enumerate(prices):
        day = start_day + idx
        date_str = f"2026-09-{day:02d}"
        records.append(
            PriceRecord(
                date=datetime.date.fromisoformat(date_str),
                instrument=instrument,
                close=Decimal(str(p)),
            )
        )
    return records


class TestMACrossRules(unittest.TestCase):
    """Test suite covering moving average crossover rules and window constraints."""

    def test_07_correct_ma_crossover_above(self):
        """7. Short MA crosses from at-or-below long MA to strictly above it."""
        # short = 2, long = 4
        # Need at least 5 observations (index 4 is first possible crossover)
        rule = MACrossRule(id="ma1", instrument="TCS", type="ma_cross", short=2, long=4, direction="above")
        # Indices:
        # 0: 10
        # 1: 10
        # 2: 10
        # 3: 10 -> at t=3: 2-SMA=(10+10)/2=10, 4-SMA=(10+10+10+10)/4=10. prev_short <= prev_long (10 <= 10)
        # 4: 20 -> at t=4: 2-SMA=(10+20)/2=15, 4-SMA=(10+10+10+20)/4=12.5. curr_short > curr_long (15 > 12.5)
        # Crosses above at index 4!
        records = _make_series([10, 10, 10, 10, 20])
        alerts = evaluate_ma_cross_rule(rule, records)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].date, datetime.date(2026, 9, 5))
        self.assertEqual(alerts[0].rule_id, "ma1")
        self.assertEqual(alerts[0].instrument, "TCS")
        self.assertEqual(alerts[0].description, "ma_cross 2/4 above")
        self.assertIn("2-SMA crossed above 4-SMA", alerts[0].explanation)

    def test_08_correct_ma_crossover_below(self):
        """8. Short MA crosses from at-or-above long MA to strictly below it."""
        # short = 2, long = 4
        rule = MACrossRule(id="ma2", instrument="TCS", type="ma_cross", short=2, long=4, direction="below")
        # Indices:
        # 0: 20
        # 1: 20
        # 2: 20
        # 3: 20 -> at t=3: 2-SMA=20, 4-SMA=20. prev_short >= prev_long (20 >= 20)
        # 4: 10 -> at t=4: 2-SMA=15, 4-SMA=17.5. curr_short < curr_long (15 < 17.5)
        # Crosses below at index 4!
        records = _make_series([20, 20, 20, 20, 10])
        alerts = evaluate_ma_cross_rule(rule, records)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].date, datetime.date(2026, 9, 5))
        self.assertEqual(alerts[0].rule_id, "ma2")
        self.assertEqual(alerts[0].description, "ma_cross 2/4 below")
        self.assertIn("2-SMA crossed below 4-SMA", alerts[0].explanation)

    def test_09_full_window_warmup_behavior(self):
        """9. Full-window warm-up behavior: never substitute partial windows.

        With short=3, long=5:
        Long window requires 5 observations.
        Index 4 (5th observation) is the first day long MA exists.
        Index 5 (6th observation) is the earliest day where BOTH previous (index 4)
        and current (index 5) have valid full windows.
        No alert can occur prior to index 5.
        """
        rule = MACrossRule(id="ma_warmup", instrument="TCS", type="ma_cross", short=3, long=5, direction="above")
        # 5 observations only: index 4 has valid MA, but index 3 did NOT have a valid long MA.
        # Therefore, cannot evaluate a crossover transition yet!
        records_5 = _make_series([10, 10, 10, 10, 30])
        self.assertEqual(len(evaluate_ma_cross_rule(rule, records_5)), 0)

        # 6 observations: index 4 has valid short/long, index 5 has valid short/long.
        # Now a crossover can be evaluated!
        # At index 4: 3-SMA=(10+10+10)/3=10, 5-SMA=(10+10+10+10+10)/5=10 -> prev_short <= prev_long
        # At index 5: price=30 -> 3-SMA=(10+10+30)/3=16.67, 5-SMA=(10+10+10+10+30)/5=14 -> curr_short > curr_long
        records_6 = _make_series([10, 10, 10, 10, 10, 30])
        alerts_6 = evaluate_ma_cross_rule(rule, records_6)
        self.assertEqual(len(alerts_6), 1)
        self.assertEqual(alerts_6[0].date, datetime.date(2026, 9, 6))

    def test_10_no_crossover_while_mas_remain_on_same_side(self):
        """10. No crossover while moving averages remain on the same side."""
        rule_above = MACrossRule(id="m1", instrument="TCS", type="ma_cross", short=2, long=3, direction="above")
        rule_below = MACrossRule(id="m2", instrument="TCS", type="ma_cross", short=2, long=3, direction="below")

        # Consistently rising series: short MA is always strictly above long MA
        # Prices: 10, 20, 30, 40, 50
        # t=2: 2-SMA=25, 3-SMA=20 (short > long)
        # t=3: 2-SMA=35, 3-SMA=30 (short > long)
        # t=4: 2-SMA=45, 3-SMA=40 (short > long)
        # No crossover occurs!
        records_rising = _make_series([10, 20, 30, 40, 50])
        self.assertEqual(len(evaluate_ma_cross_rule(rule_above, records_rising)), 0)
        self.assertEqual(len(evaluate_ma_cross_rule(rule_below, records_rising)), 0)

    def test_11_equal_moving_averages_and_subsequent_crossing(self):
        """11. Equal moving averages (prev_short == prev_long) and subsequent crossing."""
        # short = 2, long = 3
        # Start with flat prices so 2-SMA == 3-SMA
        # Prices: 100, 100, 100, 110
        # t=2 (Sep 3): 2-SMA=100, 3-SMA=100 (equal!)
        # t=3 (Sep 4): 2-SMA=(100+110)/2=105, 3-SMA=(100+100+110)/3=103.33 -> short > long
        # Since prev_short <= prev_long (100 <= 100 is True) and curr_short > curr_long,
        # it MUST trigger 'above'!
        rule_above = MACrossRule(id="eq_cross", instrument="TCS", type="ma_cross", short=2, long=3, direction="above")
        records = _make_series([100, 100, 100, 110])
        alerts = evaluate_ma_cross_rule(rule_above, records)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].date, datetime.date(2026, 9, 4))

        # And if it moves down to 90 instead:
        # t=3: 2-SMA=95, 3-SMA=96.67 -> short < long
        # Since prev_short >= prev_long (100 >= 100 is True) and curr_short < curr_long,
        # it MUST trigger 'below'!
        rule_below = MACrossRule(id="eq_below", instrument="TCS", type="ma_cross", short=2, long=3, direction="below")
        records_down = _make_series([100, 100, 100, 90])
        alerts_down = evaluate_ma_cross_rule(rule_below, records_down)
        self.assertEqual(len(alerts_down), 1)
        self.assertEqual(alerts_down[0].date, datetime.date(2026, 9, 4))

    def test_16_insufficient_history_for_ma_rule(self):
        """16. Instruments with insufficient history produce 0 alerts without error."""
        rule = MACrossRule(id="m_long", instrument="TCS", type="ma_cross", short=5, long=20, direction="above")
        # Only 10 observations, when 21 are required
        records = _make_series([3000 + i for i in range(10)])
        alerts = evaluate_ma_cross_rule(rule, records)
        self.assertEqual(len(alerts), 0)


if __name__ == "__main__":
    unittest.main()
