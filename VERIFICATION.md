# Verification & Quality Assurance Report: PricePulse

This document records the actual verification runs, test outputs, commands executed, and behavior audits performed on the PricePulse alert engine.

---

## 1. Automated Test Suite Execution

Ran the complete test suite using Python's built-in `unittest` runner:

```bash
python -m unittest discover tests -v
```

### Actual Output
```text
test_12_multiple_instruments_independent_histories (test_cli.TestCLI.test_12_multiple_instruments_independent_histories) ... ok
test_13_unsorted_csv_dates (test_cli.TestCLI.test_13_unsorted_csv_dates) ... ok
test_14_and_15_multiple_rules_same_date_and_sorting (test_cli.TestCLI.test_14_and_15_multiple_rules_same_date_and_sorting) ... ok
test_17_no_alerts_for_valid_input (test_cli.TestCLI.test_17_no_alerts_for_valid_input) ... ok
test_24_diagnostic_mode_explains_alert (test_cli.TestCLI.test_24_diagnostic_mode_explains_alert) ... ok
test_25_normal_mode_free_of_diagnostics (test_cli.TestCLI.test_25_normal_mode_free_of_diagnostics) ... ok
test_cli_usage_error_on_missing_args (test_cli.TestCLI.test_cli_usage_error_on_missing_args) ... ok
test_cli_validation_failure_exit_code_and_stderr (test_cli.TestCLI.test_cli_validation_failure_exit_code_and_stderr) ... ok
test_01_level_crossing_below (test_level_rules.TestLevelRules.test_01_level_crossing_below) ... ok
test_02_level_crossing_above (test_level_rules.TestLevelRules.test_02_level_crossing_above) ... ok
test_03_price_remaining_beyond_does_not_retrigger (test_level_rules.TestLevelRules.test_03_price_remaining_beyond_does_not_retrigger) ... ok
test_04_crossing_back_and_crossing_again (test_level_rules.TestLevelRules.test_04_crossing_back_and_crossing_again) ... ok
test_05_exact_threshold_boundary_behavior (test_level_rules.TestLevelRules.test_05_exact_threshold_boundary_behavior) ... ok
test_06_no_alert_on_first_observation (test_level_rules.TestLevelRules.test_06_no_alert_on_first_observation) ... ok
test_07_correct_ma_crossover_above (test_ma_cross.TestMACrossRules.test_07_correct_ma_crossover_above) ... ok
test_08_correct_ma_crossover_below (test_ma_cross.TestMACrossRules.test_08_correct_ma_crossover_below) ... ok
test_09_full_window_warmup_behavior (test_ma_cross.TestMACrossRules.test_09_full_window_warmup_behavior) ... ok
test_10_no_crossover_while_mas_remain_on_same_side (test_ma_cross.TestMACrossRules.test_10_no_crossover_while_mas_remain_on_same_side) ... ok
test_11_equal_moving_averages_and_subsequent_crossing (test_ma_cross.TestMACrossRules.test_11_equal_moving_averages_and_subsequent_crossing) ... ok
test_16_insufficient_history_for_ma_rule (test_ma_cross.TestMACrossRules.test_16_insufficient_history_for_ma_rule) ... ok
test_18_malformed_csv_and_json (test_validation.TestValidation.test_18_malformed_csv_and_json) ... ok
test_19_missing_required_columns_or_rule_fields (test_validation.TestValidation.test_19_missing_required_columns_or_rule_fields) ... ok
test_20_duplicate_observations_and_duplicate_rule_ids (test_validation.TestValidation.test_20_duplicate_observations_and_duplicate_rule_ids) ... ok
test_21_invalid_moving_average_windows (test_validation.TestValidation.test_21_invalid_moving_average_windows) ... ok
test_22_missing_files_and_invalid_dates (test_validation.TestValidation.test_22_missing_files_and_invalid_dates) ... ok
test_23_non_finite_or_invalid_prices (test_validation.TestValidation.test_23_non_finite_or_invalid_prices) ... ok
test_empty_files_and_lists (test_validation.TestValidation.test_empty_files_and_lists) ... ok
test_unknown_rule_type_and_unsupported_direction (test_validation.TestValidation.test_unknown_rule_type_and_unsupported_direction) ... ok

----------------------------------------------------------------------
Ran 28 tests in 2.057s

OK
```

All 28 tests passed. Zero failures, zero errors.

---

## 2. Mandatory Assessment Command Verification

### Command
```bash
python alerts.py examples/prices.csv examples/rules.json
```

### Actual Output
```text
2026-09-03        r1    INFY     level below 1500
2026-09-24        r2    TCS      ma_cross 5/20 above
```
- Character-for-character exact match with the required specification format.
- Exit code: `0`.
- Standard error: empty.

---

## 3. Diagnostic Mode (`--explain`) Verification

### Command
```bash
python alerts.py examples/prices.csv examples/rules.json --explain
```

### Actual Output
```text
2026-09-03        r1    INFY     level below 1500
  [EXPLAIN] Price crossed below threshold 1500. Previous close on 2026-09-02: 1534.1 (>= 1500), Current close on 2026-09-03: 1498 (< 1500).
2026-09-24        r2    TCS      ma_cross 5/20 above
  [EXPLAIN] 5-SMA crossed above 20-SMA. Previous on 2026-09-23: 5-SMA=3890 (<= 20-SMA=3902); Current on 2026-09-24: 5-SMA=3922 (> 20-SMA=3909).
```
- Accurately details why each alert fired, showing both previous and current values against thresholds.
- Exit code: `0`.

---

## 4. Secondary Test Fixture (Out-of-Order CSV & Multiple Assets)

### Command
```bash
python alerts.py examples/sample_market.csv examples/sample_rules.json
```

### Actual Output
```text
2026-10-03        alert_aapl_dip    AAPL     level below 200
2026-10-06        alert_aapl_rally  AAPL     level above 205
2026-10-07        alert_msft_cross  MSFT     ma_cross 3/6 below
```
- Verifies deterministic sorting even when input CSV rows are shuffled out of order.
- Demonstrates clean column alignment with dynamic column expansion for longer rule IDs.

---

## 5. Input Validation & Error Handling Audit

| Scenario | Input Tested | Expected Behavior | Actual Behavior | Exit Code |
| :--- | :--- | :--- | :--- | :--- |
| Missing Prices File | `non_existent.csv` | Error to stderr | `Error: Prices file not found: 'non_existent.csv'` | 1 |
| Missing Rules File | `non_existent.json` | Error to stderr | `Error: Rules file not found: 'non_existent.json'` | 1 |
| Missing Header Column | CSV without `close` column | Error to stderr | `Error: Missing required CSV column(s): close. Header must include 'date,instrument,close'.` | 1 |
| Duplicate Rows | Two INFY rows on same date | Error to stderr | `Error: Row 3: Duplicate price observation for instrument 'INFY' on date '2026-09-01'.` | 1 |
| Duplicate Rule IDs | Two rules with id `"r1"` | Error to stderr | `Error: Duplicate rule ID 'r1' found in rules file.` | 1 |
| Invalid Date Format | Date `2026-02-31` | Error to stderr | `Error: Row 2: Invalid calendar date '2026-02-31': day is out of range for month.` | 1 |
| Non-finite Price | Price `nan` or `inf` | Error to stderr | `Error: Row 2: Non-finite close price 'nan' is not allowed.` | 1 |
| Negative Price | Price `-100.50` | Error to stderr | `Error: Row 2: Price '-100.50' must be strictly positive.` | 1 |
| Invalid Window | `short: 20, long: 20` | Error to stderr | `Error: Rule 'r1': 'short' window (20) must be strictly less than 'long' window (20).` | 1 |
| Zero / Neg Window | `short: 0` or `-5` | Error to stderr | `Error: Rule 'r1': 'short' window must be a positive integer greater than zero...` | 1 |
| Unknown Rule Type | `type: "rsi"` | Error to stderr | `Error: Unknown rule type 'rsi' for rule 'r1'. Supported types: 'level', 'ma_cross'.` | 1 |
| Unsupported Direction | `direction: "sideways"`| Error to stderr | `Error: Rule 'r1' has unsupported direction 'sideways'. Supported directions are 'above' and 'below'.` | 1 |
| Empty CSV | Empty 0-byte file | Error to stderr | `Error: Prices CSV file is empty.` | 1 |
| Empty Rule List | `[]` | Error to stderr | `Error: Rules file must contain at least one rule.` | 1 |

In all failure scenarios, no Python tracebacks were leaked to stdout or stderr.

---

## 6. Architecture & Quality Audit

- **Floating-point safety**: All close prices, levels, and moving averages are computed with Python's built-in `decimal.Decimal` module, eliminating precision artifacts.
- **Portability**: Uses exclusively Python Standard Library (`csv`, `json`, `datetime`, `decimal`, `argparse`, `unittest`, `dataclasses`, `pathlib`).
- **Memory efficiency**: Processes instruments independently and maintains rolling windows. Complexity is $O(N \log N)$ for initial date sorting and $O(N)$ for alert evaluation.
- **Identified Limitations**:
  - The tool is designed for daily close price batches; high-frequency intra-day tick data with microsecond timestamps is outside the scope of `datetime.date`.
  - Memory consumption scales with the total number of historical price points loaded in a batch. For multi-gigabyte historical archives, chunked streaming or SQLite indexing would be recommended.
