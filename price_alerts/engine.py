"""Alert evaluation engine for PricePulse.

Evaluates Level and Moving-Average Crossover rules independently across
instrument price series with deterministic sorting and rich diagnostic explanations.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from price_alerts.data_loader import PriceRecord
from price_alerts.rules import BaseRule, LevelRule, MACrossRule, format_decimal


@dataclass(frozen=True)
class Alert:
    """Represents a triggered price alert."""
    date: datetime.date
    rule_id: str
    instrument: str
    description: str
    explanation: str

    def format_line(self, rule_col_width: int = 6, inst_col_width: int = 9) -> str:
        """Format the alert into the mandatory fixed-width line format.

        Format:
            <date:18><rule_id:rule_col_width><instrument:inst_col_width><description>

        Matches example:
            2026-09-03        r1    INFY     level below 1500
            2026-09-24        r2    TCS      ma_cross 5/20 above
        """
        date_str = f"{self.date.isoformat():<18}"
        rule_str = f"{self.rule_id:<{rule_col_width}}"
        inst_str = f"{self.instrument:<{inst_col_width}}"
        return f"{date_str}{rule_str}{inst_str}{self.description}"


def evaluate_level_rule(rule: LevelRule, records: List[PriceRecord]) -> List[Alert]:
    """Evaluate a level threshold crossing rule against an instrument's chronological records.

    Semantics:
        - The first available observation has no previous close, so cannot trigger.
        - 'below': prev_close >= level and curr_close < level.
        - 'above': prev_close <= level and curr_close > level.
        - Fires only on the crossing day, not on days where the price merely remains beyond the level.
    """
    if len(records) < 2:
        return []

    alerts: List[Alert] = []
    threshold = rule.level

    for i in range(1, len(records)):
        prev_rec = records[i - 1]
        curr_rec = records[i]
        prev_close = prev_rec.close
        curr_close = curr_rec.close

        crossed = False
        if rule.direction == "below":
            if prev_close >= threshold and curr_close < threshold:
                crossed = True
        elif rule.direction == "above":
            if prev_close <= threshold and curr_close > threshold:
                crossed = True

        if crossed:
            desc = f"level {rule.direction} {rule.formatted_level}"
            comp_prev = ">=" if rule.direction == "below" else "<="
            comp_curr = "<" if rule.direction == "below" else ">"
            expl = (
                f"Price crossed {rule.direction} threshold {rule.formatted_level}. "
                f"Previous close on {prev_rec.date}: {format_decimal(prev_close)} ({comp_prev} {rule.formatted_level}), "
                f"Current close on {curr_rec.date}: {format_decimal(curr_close)} ({comp_curr} {rule.formatted_level})."
            )
            alerts.append(
                Alert(
                    date=curr_rec.date,
                    rule_id=rule.id,
                    instrument=rule.instrument,
                    description=desc,
                    explanation=expl,
                )
            )

    return alerts


def _compute_sma(closes: List[Decimal], window: int, end_idx: int) -> Decimal:
    """Compute Simple Moving Average for a complete window ending at end_idx."""
    window_sum = sum(closes[end_idx - window + 1 : end_idx + 1])
    return window_sum / Decimal(window)


def evaluate_ma_cross_rule(rule: MACrossRule, records: List[PriceRecord]) -> List[Alert]:
    """Evaluate an SMA crossover rule against an instrument's chronological records.

    Semantics:
        - Requires a full window for both short and long SMAs.
        - No partial-window averages are ever used.
        - Both previous and current observations must have valid short and long SMAs.
        - Earliest possible evaluation is at observation index `long` (the (long+1)-th record).
        - 'above': prev_short <= prev_long and curr_short > curr_long.
        - 'below': prev_short >= prev_long and curr_short < curr_long.
    """
    short_win = rule.short
    long_win = rule.long

    # We need at least long_win + 1 observations so that index long_win - 1
    # has a valid long SMA and index long_win has a valid long SMA.
    if len(records) < long_win + 1:
        return []

    closes = [r.close for r in records]
    alerts: List[Alert] = []

    # Iterate from observation index long_win onwards
    for i in range(long_win, len(records)):
        prev_idx = i - 1
        curr_idx = i

        prev_short = _compute_sma(closes, short_win, prev_idx)
        prev_long = _compute_sma(closes, long_win, prev_idx)
        curr_short = _compute_sma(closes, short_win, curr_idx)
        curr_long = _compute_sma(closes, long_win, curr_idx)

        crossover = False
        if rule.direction == "above":
            if prev_short <= prev_long and curr_short > curr_long:
                crossover = True
        elif rule.direction == "below":
            if prev_short >= prev_long and curr_short < curr_long:
                crossover = True

        if crossover:
            desc = f"ma_cross {short_win}/{long_win} {rule.direction}"
            comp_prev = "<=" if rule.direction == "above" else ">="
            comp_curr = ">" if rule.direction == "above" else "<"
            expl = (
                f"{short_win}-SMA crossed {rule.direction} {long_win}-SMA. "
                f"Previous on {records[prev_idx].date}: {short_win}-SMA={format_decimal(prev_short)} "
                f"({comp_prev} {long_win}-SMA={format_decimal(prev_long)}); "
                f"Current on {records[curr_idx].date}: {short_win}-SMA={format_decimal(curr_short)} "
                f"({comp_curr} {long_win}-SMA={format_decimal(curr_long)})."
            )
            alerts.append(
                Alert(
                    date=records[curr_idx].date,
                    rule_id=rule.id,
                    instrument=rule.instrument,
                    description=desc,
                    explanation=expl,
                )
            )

    return alerts


def evaluate_rule(rule: BaseRule, records: List[PriceRecord]) -> List[Alert]:
    """Dispatch evaluation to the appropriate rule handler."""
    if isinstance(rule, LevelRule):
        return evaluate_level_rule(rule, records)
    elif isinstance(rule, MACrossRule):
        return evaluate_ma_cross_rule(rule, records)
    else:
        raise ValueError(f"Unsupported rule type: {type(rule).__name__}")


def run_engine(
    records_by_instrument: Dict[str, List[PriceRecord]],
    rules: List[BaseRule],
) -> List[Alert]:
    """Run all rules against price records and return deterministically sorted alerts.

    Sorting:
        Alerts are sorted chronologically by date ascending, then by rule ID
        lexicographically ascending.
    """
    all_alerts: List[Alert] = []

    for rule in rules:
        instrument_records = records_by_instrument.get(rule.instrument, [])
        rule_alerts = evaluate_rule(rule, instrument_records)
        all_alerts.extend(rule_alerts)

    # Sort deterministically by date ascending, then rule ID ascending
    all_alerts.sort(key=lambda a: (a.date, a.rule_id))
    return all_alerts
