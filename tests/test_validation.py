"""Validation and error handling tests for PricePulse."""

import os
from pathlib import Path
import tempfile
import unittest

from price_alerts.data_loader import ValidationError, load_prices
from price_alerts.rules import load_rules


class TestValidation(unittest.TestCase):
    """Test suite covering data validation, schema enforcement, and edge cases."""

    def _write_temp_file(self, content: str, suffix: str) -> str:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=suffix) as f:
            f.write(content)
            temp_path = f.name
        self.addCleanup(lambda: os.path.exists(temp_path) and os.unlink(temp_path))
        return temp_path

    def test_18_malformed_csv_and_json(self):
        """18. Reject malformed CSV rows and invalid JSON syntax with clear ValidationError."""
        # Malformed CSV: inconsistent column count
        bad_csv = self._write_temp_file(
            "date,instrument,close\n2026-09-01,INFY\n",
            suffix=".csv",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_prices(bad_csv)
        self.assertIn("Expected 3 columns", str(ctx.exception))

        # Malformed JSON: syntax error
        bad_json = self._write_temp_file(
            "[{'id': 'r1', 'invalid': json}]",
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_json)
        self.assertIn("Malformed JSON", str(ctx.exception))

    def test_19_missing_required_columns_or_rule_fields(self):
        """19. Reject missing CSV headers and missing required rule fields."""
        # Missing 'close' header
        bad_csv = self._write_temp_file(
            "date,instrument\n2026-09-01,INFY\n",
            suffix=".csv",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_prices(bad_csv)
        self.assertIn("Missing required CSV column", str(ctx.exception))

        # Missing rule field 'level' in level rule
        bad_rule_json = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below"}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_rule_json)
        self.assertIn("missing required field 'level'", str(ctx.exception))

        # Missing rule field 'long' in ma_cross rule
        bad_ma_rule_json = self._write_temp_file(
            '[{"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_ma_rule_json)
        self.assertIn("missing required field 'long'", str(ctx.exception))

    def test_20_duplicate_observations_and_duplicate_rule_ids(self):
        """20. Reject duplicate (instrument, date) price rows and duplicate rule IDs."""
        # Duplicate price record
        dup_csv = self._write_temp_file(
            "date,instrument,close\n"
            "2026-09-01,INFY,1500.00\n"
            "2026-09-01,INFY,1510.00\n",
            suffix=".csv",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_prices(dup_csv)
        self.assertIn("Duplicate price observation for instrument 'INFY'", str(ctx.exception))

        # Duplicate rule ID
        dup_rules = self._write_temp_file(
            '['
            '  {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500},'
            '  {"id": "r1", "instrument": "TCS", "type": "level", "direction": "above", "level": 3000}'
            ']',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(dup_rules)
        self.assertIn("Duplicate rule ID 'r1'", str(ctx.exception))

    def test_21_invalid_moving_average_windows(self):
        """21. Reject zero, negative, non-integer, and short >= long moving average windows."""
        # Zero window
        zero_win = self._write_temp_file(
            '[{"id": "r1", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 0, "long": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(zero_win)
        self.assertIn("must be a positive integer greater than zero", str(ctx.exception))

        # Negative window
        neg_win = self._write_temp_file(
            '[{"id": "r1", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": -5, "long": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(neg_win)
        self.assertIn("must be a positive integer greater than zero", str(ctx.exception))

        # Short >= Long
        short_ge_long = self._write_temp_file(
            '[{"id": "r1", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 20, "long": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(short_ge_long)
        self.assertIn("must be strictly less than 'long' window", str(ctx.exception))

        # Float window
        float_win = self._write_temp_file(
            '[{"id": "r1", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5.5, "long": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(float_win)
        self.assertIn("must be an integer", str(ctx.exception))

    def test_22_missing_files_and_invalid_dates(self):
        """22. Reject missing files, directory paths, and malformed/non-existent dates."""
        # Missing file
        with self.assertRaises(ValidationError) as ctx:
            load_prices("non_existent_file_xyz.csv")
        self.assertIn("Prices file not found", str(ctx.exception))

        # Directory path passed
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.rmdir(temp_dir))
        with self.assertRaises(ValidationError) as ctx:
            load_prices(temp_dir)
        self.assertIn("is a directory", str(ctx.exception))

        # Invalid calendar date (Feb 31)
        bad_date_csv = self._write_temp_file(
            "date,instrument,close\n2026-02-31,INFY,1500.00\n",
            suffix=".csv",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_prices(bad_date_csv)
        self.assertIn("Invalid calendar date", str(ctx.exception))

        # Invalid date format (DD/MM/YYYY)
        bad_format_csv = self._write_temp_file(
            "date,instrument,close\n01-09-2026,INFY,1500.00\n",
            suffix=".csv",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_prices(bad_format_csv)
        self.assertIn("Invalid date format", str(ctx.exception))

    def test_23_non_finite_or_invalid_prices(self):
        """23. Reject NaN, Inf, negative, zero, and text close prices."""
        for bad_price in ("nan", "inf", "-inf", "Infinity", "-100.5", "0.0", "abc"):
            bad_price_csv = self._write_temp_file(
                f"date,instrument,close\n2026-09-01,INFY,{bad_price}\n",
                suffix=".csv",
            )
            with self.assertRaises(ValidationError):
                load_prices(bad_price_csv)

    def test_empty_files_and_lists(self):
        """Reject completely empty CSV files, header-only CSVs, and empty rule lists."""
        empty_csv = self._write_temp_file("", suffix=".csv")
        with self.assertRaises(ValidationError) as ctx:
            load_prices(empty_csv)
        self.assertIn("Prices CSV file is empty", str(ctx.exception))

        header_only_csv = self._write_temp_file("date,instrument,close\n", suffix=".csv")
        with self.assertRaises(ValidationError) as ctx:
            load_prices(header_only_csv)
        self.assertIn("contains no data rows", str(ctx.exception))

        empty_rules = self._write_temp_file("[]", suffix=".json")
        with self.assertRaises(ValidationError) as ctx:
            load_rules(empty_rules)
        self.assertIn("must contain at least one rule", str(ctx.exception))

    def test_unknown_rule_type_and_unsupported_direction(self):
        """Reject unknown rule types and unsupported directions."""
        unknown_type = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "rsi", "direction": "above", "level": 70}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(unknown_type)
        self.assertIn("Unknown rule type 'rsi'", str(ctx.exception))

        unsupported_dir = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "UP", "level": 1500}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(unsupported_dir)
        self.assertIn("unsupported direction 'UP'", str(ctx.exception))

    def test_alternate_field_names_accepted(self):
        """Documented alternate field names normalize cleanly to canonical schema."""
        from decimal import Decimal
        from price_alerts.rules import LevelRule, MACrossRule

        rules_json = self._write_temp_file(
            '['
            '  {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": 1500},'
            '  {"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short_window": 5, "long_window": 20}'
            ']',
            suffix=".json",
        )
        rules = load_rules(rules_json)
        self.assertEqual(len(rules), 2)

        # Rule 1 normalized to canonical LevelRule with .level
        self.assertIsInstance(rules[0], LevelRule)
        self.assertEqual(rules[0].id, "r1")
        self.assertEqual(rules[0].level, Decimal("1500"))
        self.assertTrue(hasattr(rules[0], "level"))
        self.assertFalse(hasattr(rules[0], "threshold"))

        # Rule 2 normalized to canonical MACrossRule with .short and .long
        self.assertIsInstance(rules[1], MACrossRule)
        self.assertEqual(rules[1].id, "r2")
        self.assertEqual(rules[1].short, 5)
        self.assertEqual(rules[1].long, 20)
        self.assertTrue(hasattr(rules[1], "short"))
        self.assertTrue(hasattr(rules[1], "long"))

    def test_conflicting_aliases_rejected(self):
        """Reject conflicting values between canonical fields and their aliases."""
        # Level rule: level != threshold
        conflicting_level = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500, "threshold": 1600}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(conflicting_level)
        self.assertIn("Conflicting values provided for 'level'", str(ctx.exception))
        self.assertIn("threshold", str(ctx.exception))

        # MA rule: short != short_window
        conflicting_short = self._write_temp_file(
            '[{"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5, "short_window": 10, "long": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(conflicting_short)
        self.assertIn("Conflicting values provided for 'short'", str(ctx.exception))

        # MA rule: long != long_window
        conflicting_long = self._write_temp_file(
            '[{"id": "r3", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5, "long": 20, "long_window": 30}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(conflicting_long)
        self.assertIn("Conflicting values provided for 'long'", str(ctx.exception))

    def test_identical_aliases_accepted(self):
        """Accept identical values between canonical and alias fields without error."""
        from decimal import Decimal

        identical_rules = self._write_temp_file(
            '['
            '  {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500, "threshold": 1500.0},'
            '  {"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5, "short_window": 5, "long": 20, "long_window": 20}'
            ']',
            suffix=".json",
        )
        rules = load_rules(identical_rules)
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].level, Decimal("1500"))
        self.assertEqual(rules[1].short, 5)
        self.assertEqual(rules[1].long, 20)

    def test_unknown_fields_rejected(self):
        """Strictly reject arbitrary unknown fields on rules."""
        unknown_level = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500, "extra_field": 123}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(unknown_level)
        self.assertIn("contains unknown field 'extra_field'", str(ctx.exception))

        unknown_ma = self._write_temp_file(
            '[{"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short": 5, "long": 20, "window_type": "ema"}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(unknown_ma)
        self.assertIn("contains unknown field 'window_type'", str(ctx.exception))

    def test_invalid_alias_values_rejected(self):
        """Reject invalid values provided via alternate alias fields."""
        # Non-numeric threshold
        bad_thresh_text = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": "invalid"}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_thresh_text)
        self.assertIn("Invalid numeric level", str(ctx.exception))

        # Negative threshold
        bad_thresh_neg = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": -100}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_thresh_neg)
        self.assertIn("must be strictly positive", str(ctx.exception))

        # Boolean threshold
        bad_thresh_bool = self._write_temp_file(
            '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": true}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_thresh_bool)
        self.assertIn("'level' cannot be a boolean", str(ctx.exception))

        # Non-integer short_window
        bad_short_float = self._write_temp_file(
            '[{"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short_window": 5.5, "long_window": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_short_float)
        self.assertIn("'short' window must be an integer", str(ctx.exception))

        # short_window >= long_window
        bad_window_order = self._write_temp_file(
            '[{"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short_window": 25, "long_window": 20}]',
            suffix=".json",
        )
        with self.assertRaises(ValidationError) as ctx:
            load_rules(bad_window_order)
        self.assertIn("must be strictly less than", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

