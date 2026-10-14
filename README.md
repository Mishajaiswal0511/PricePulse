# PricePulse — Reliable Price Alert Engine

A robust, dependency-free Python CLI alert engine that detects price level crossings and moving-average crossovers from CSV price series against JSON rule sets.

## Requirements & Installation
- **Python**: 3.9+ (Standard Library only; zero external packages required).
- **Setup**: Clone or unzip into any directory. No virtual environment, API keys, or database required.

## Quick Start (CLI)
Run from the repository root:
```bash
python alerts.py prices.csv rules.json
```
For diagnostic explanations showing previous/current values and thresholds:
```bash
python alerts.py prices.csv rules.json --explain
```

### Optional Local Web Dashboard
For interactive live presentations:
```bash
python ui.py
```
*Opens `http://127.0.0.1:8000` in your browser. Uses Python's standard library with zero external dependencies.*

## Input Formats
- **Prices CSV** (`date,instrument,close`):
  ```csv
  date,instrument,close
  2026-09-01,INFY,1520.50
  2026-09-02,INFY,1498.00
  ```
  *Dates must be `YYYY-MM-DD`. Rows need not be sorted. Ambiguous duplicate `(instrument, date)` rows are rejected.*
- **Rules JSON**:
  ```json
  [
    {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500},
    {"id": "r2", "instrument": "TCS", "type": "ma_cross", "short": 5, "long": 20, "direction": "above"}
  ]
  ```

### Documented Schema & Alternate Field Aliases
PricePulse normalizes input rules into internal canonical objects (`LevelRule` and `MACrossRule`). To accommodate common naming conventions without breaking canonical requirements, the parser supports explicitly documented field aliases:

| Rule Type | Canonical Field | Supported Alias | Description & Constraint |
| :--- | :--- | :--- | :--- |
| `level` | `level` | `threshold` | Strictly positive numeric threshold (e.g. `1500` or `"1500.50"`). |
| `ma_cross` | `short` | `short_window` | Positive integer window for the fast SMA. |
| `ma_cross` | `long` | `long_window` | Positive integer window for the slow SMA (`short < long`). |

**Alias Normalization Rules:**
- **Single field used**: Either the canonical field or its alias is accepted and normalized to the canonical field name.
- **Both fields present**: If both canonical and alias fields are provided (e.g. `{"level": 1500, "threshold": 1500}`), their values must be identical. If values conflict (e.g. `{"level": 1500, "threshold": 1600}`), a clear `ValidationError` is raised.
- **Strict schema**: Arbitrary or unknown fields outside the documented schema are strictly rejected.
- **Internal execution**: Internal alert evaluation and diagnostic explanations consistently use canonical names (`rule.level`, `rule.short`, `rule.long`).

**Example with Alternate Aliases:**
```json
[
  {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": 1500},
  {"id": "r2", "instrument": "TCS", "type": "ma_cross", "direction": "above", "short_window": 5, "long_window": 20}
]
```

## Crossing Semantics
- **Level Crossing (`level`)**:
  - `below`: Previous close $\ge$ threshold and current close $<$ threshold.
  - `above`: Previous close $\le$ threshold and current close $>$ threshold.
  - Fires only on the first crossing day; does not re-fire while price remains beyond the level.
  - The first observation has no prior close and never triggers.
- **Moving-Average Crossover (`ma_cross`)**:
  - Uses Simple Moving Averages (`SMA`). Partial windows are never substituted.
  - Both previous ($t-1$) and current ($t$) observations must have complete windows for both `short` and `long` MAs.
  - Earliest possible evaluation requires at least $long + 1$ observations ($t \ge long$).
  - `above`: $SMA_{short}(t-1) \le SMA_{long}(t-1)$ and $SMA_{short}(t) > SMA_{long}(t)$.
  - `below`: $SMA_{short}(t-1) \ge SMA_{long}(t-1)$ and $SMA_{short}(t) < SMA_{long}(t)$.

## Output Format
Deterministic output sorted by `date` (ascending), then `rule_id` (ascending):
```text
2026-09-03        r1    INFY     level below 1500
2026-09-24        r2    TCS      ma_cross 5/20 above
```

## Architecture
Separation of concerns across four focused modules:
1. `alerts.py`: CLI interface, argument parsing, error formatting, clean stderr reporting.
2. `price_alerts/data_loader.py`: CSV ingestion, strict schema/date/price validation, duplicate rejection, and chronological grouping.
3. `price_alerts/rules.py`: JSON schema validation, rule instantiation (`LevelRule`, `MACrossRule`), duplicate ID rejection.
4. `price_alerts/engine.py`: Pure rule evaluation, exact `Decimal` arithmetic, deterministic alert sorting.

## Running Tests
Run the automated test suite (built-in `unittest`):
```bash
python -m unittest discover tests -v
```

## AI Assistance & Discovered Edge Case
- **AI Assistance**: An LLM (Google Antigravity) generated the initial boilerplate, test scaffolds, and documentation based on prompt specifications.
- **Genuine Edge Case & Resolution**: During warm-up analysis for `ma_cross`, a naive loop indexing from observation $long - 1$ was identified as flawed. At $t = long - 1$, the current observation has a valid long window, but the *previous* observation ($t - 1 = long - 2$) only has $long - 1$ points and lacks a complete long window. Attempting to evaluate crossover at $long - 1$ would either violate the "never substitute partial windows" rule or crash. The engine was explicitly designed to require $N \ge long + 1$ records and evaluate starting strictly at $t = long$. Covered in `test_09_full_window_warmup_behavior`.
