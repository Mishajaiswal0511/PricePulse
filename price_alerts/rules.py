"""Alert rule definitions and schema validation for PricePulse.

Supports 'level' and 'ma_cross' rules with strict type checking,
range validation, and duplicate ID detection.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Union

from price_alerts.data_loader import ValidationError


def format_decimal(val: Decimal) -> str:
    """Format a Decimal cleanly without scientific notation or unnecessary trailing zeros.
    
    Examples:
        Decimal('1500') -> '1500'
        Decimal('1500.00') -> '1500'
        Decimal('1500.50') -> '1500.5'
        Decimal('1500.25') -> '1500.25'
    """
    if val.is_nan() or val.is_infinite():
        return str(val)
    # If it's an integer value, display as integer
    normalized = val.normalize()
    # Check if normalized has an exponent in scientific notation, or is whole
    sign, digits, exponent = normalized.as_tuple()
    if exponent >= 0:
        return str(int(val))
    # Otherwise format normally with sign
    return f"{normalized:f}".rstrip("0").rstrip(".") if "." in f"{normalized:f}" else f"{normalized:f}"


@dataclass(frozen=True)
class BaseRule:
    """Base class for all alert rules."""
    id: str
    instrument: str
    type: str
    direction: str


@dataclass(frozen=True)
class LevelRule(BaseRule):
    """Rule monitoring threshold level crossings for an instrument."""
    level: Decimal

    @property
    def formatted_level(self) -> str:
        """Clean string representation of threshold level."""
        return format_decimal(self.level)


@dataclass(frozen=True)
class MACrossRule(BaseRule):
    """Rule monitoring moving-average crossovers (short SMA vs long SMA)."""
    short: int
    long: int


def _validate_common_fields(rule_dict: Dict[str, Any], index: int) -> None:
    """Validate presence and basic types of common rule fields."""
    if not isinstance(rule_dict, dict):
        raise ValidationError(f"Rule at index {index} must be a JSON object, got {type(rule_dict).__name__}.")

    for field in ("id", "instrument", "type", "direction"):
        if field not in rule_dict:
            rule_id = rule_dict.get("id", f"index_{index}")
            raise ValidationError(f"Rule '{rule_id}' is missing required field '{field}'.")

    rule_id = rule_dict["id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValidationError(f"Rule at index {index} has an empty or non-string 'id'.")

    instrument = rule_dict["instrument"]
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValidationError(f"Rule '{rule_id}' has an empty or non-string 'instrument'.")

    direction = rule_dict["direction"]
    if direction not in ("above", "below"):
        raise ValidationError(
            f"Rule '{rule_id}' has unsupported direction '{direction}'. "
            f"Supported directions are 'above' and 'below'."
        )


def _normalize_level_dict(rule_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate fields for a 'level' rule.

    Accepts canonical 'level' and documented alias 'threshold'.
    Normalizes to 'level'. Rejects unknown fields and conflicting alias values.
    """
    rule_id = rule_dict.get("id", "unknown")
    allowed_fields = {"id", "instrument", "type", "direction", "level", "threshold"}

    # Reject unknown fields
    for field in rule_dict:
        if field not in allowed_fields:
            raise ValidationError(
                f"Rule '{rule_id}' of type 'level' contains unknown field '{field}'. "
                f"Supported fields: 'id', 'instrument', 'type', 'direction', 'level' (or alias 'threshold')."
            )

    has_level = "level" in rule_dict
    has_threshold = "threshold" in rule_dict

    if has_level and has_threshold:
        v_level = rule_dict["level"]
        v_thresh = rule_dict["threshold"]

        identical = False
        if v_level == v_thresh:
            identical = True
        elif not isinstance(v_level, bool) and not isinstance(v_thresh, bool):
            try:
                identical = (Decimal(str(v_level).strip()) == Decimal(str(v_thresh).strip()))
            except (InvalidOperation, ValueError, TypeError):
                identical = False

        if not identical:
            raise ValidationError(
                f"Rule '{rule_id}': Conflicting values provided for 'level' ({v_level}) "
                f"and alias 'threshold' ({v_thresh})."
            )

        normalized = dict(rule_dict)
        del normalized["threshold"]
        return normalized

    if has_threshold:
        normalized = dict(rule_dict)
        normalized["level"] = normalized.pop("threshold")
        return normalized

    return dict(rule_dict)


def _normalize_ma_cross_dict(rule_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate fields for an 'ma_cross' rule.

    Accepts canonical 'short' / 'long' and documented aliases 'short_window' / 'long_window'.
    Normalizes to 'short' and 'long'. Rejects unknown fields and conflicting alias values.
    """
    rule_id = rule_dict.get("id", "unknown")
    allowed_fields = {
        "id", "instrument", "type", "direction",
        "short", "long", "short_window", "long_window",
    }

    # Reject unknown fields
    for field in rule_dict:
        if field not in allowed_fields:
            raise ValidationError(
                f"Rule '{rule_id}' of type 'ma_cross' contains unknown field '{field}'. "
                f"Supported fields: 'id', 'instrument', 'type', 'direction', "
                f"'short' (or 'short_window'), 'long' (or 'long_window')."
            )

    normalized = dict(rule_dict)

    # Check short / short_window
    has_short = "short" in rule_dict
    has_short_win = "short_window" in rule_dict
    if has_short and has_short_win:
        v_short = rule_dict["short"]
        v_short_w = rule_dict["short_window"]
        if v_short != v_short_w or type(v_short) is not type(v_short_w):
            raise ValidationError(
                f"Rule '{rule_id}': Conflicting values provided for 'short' ({v_short}) "
                f"and alias 'short_window' ({v_short_w})."
            )
        del normalized["short_window"]
    elif has_short_win:
        normalized["short"] = normalized.pop("short_window")

    # Check long / long_window
    has_long = "long" in rule_dict
    has_long_win = "long_window" in rule_dict
    if has_long and has_long_win:
        v_long = rule_dict["long"]
        v_long_w = rule_dict["long_window"]
        if v_long != v_long_w or type(v_long) is not type(v_long_w):
            raise ValidationError(
                f"Rule '{rule_id}': Conflicting values provided for 'long' ({v_long}) "
                f"and alias 'long_window' ({v_long_w})."
            )
        del normalized["long_window"]
    elif has_long_win:
        normalized["long"] = normalized.pop("long_window")

    return normalized


def _parse_level_rule(rule_dict: Dict[str, Any]) -> LevelRule:
    """Parse and validate a 'level' rule."""
    rule_dict = _normalize_level_dict(rule_dict)
    rule_id = rule_dict["id"]
    if "level" not in rule_dict:
        raise ValidationError(f"Rule '{rule_id}' of type 'level' is missing required field 'level'.")

    raw_level = rule_dict["level"]
    if isinstance(raw_level, bool):
        raise ValidationError(f"Rule '{rule_id}': 'level' cannot be a boolean.")

    try:
        level = Decimal(str(raw_level).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(
            f"Rule '{rule_id}': Invalid numeric level '{raw_level}'."
        ) from exc

    if level.is_nan() or level.is_infinite():
        raise ValidationError(f"Rule '{rule_id}': 'level' must be a finite number.")

    if level <= Decimal("0"):
        raise ValidationError(f"Rule '{rule_id}': 'level' must be strictly positive, got {level}.")

    return LevelRule(
        id=rule_dict["id"].strip(),
        instrument=rule_dict["instrument"].strip(),
        type="level",
        direction=rule_dict["direction"],
        level=level,
    )


def _parse_ma_cross_rule(rule_dict: Dict[str, Any]) -> MACrossRule:
    """Parse and validate an 'ma_cross' rule."""
    rule_dict = _normalize_ma_cross_dict(rule_dict)
    rule_id = rule_dict["id"]

    for window in ("short", "long"):
        if window not in rule_dict:
            raise ValidationError(
                f"Rule '{rule_id}' of type 'ma_cross' is missing required field '{window}'."
            )
        val = rule_dict[window]
        if type(val) is not int or isinstance(val, bool):
            raise ValidationError(
                f"Rule '{rule_id}': '{window}' window must be an integer, got {type(val).__name__} ({val})."
            )
        if val <= 0:
            raise ValidationError(
                f"Rule '{rule_id}': '{window}' window must be a positive integer greater than zero, got {val}."
            )

    short_win = rule_dict["short"]
    long_win = rule_dict["long"]

    if short_win >= long_win:
        raise ValidationError(
            f"Rule '{rule_id}': 'short' window ({short_win}) must be strictly less than 'long' window ({long_win})."
        )

    return MACrossRule(
        id=rule_dict["id"].strip(),
        instrument=rule_dict["instrument"].strip(),
        type="ma_cross",
        direction=rule_dict["direction"],
        short=short_win,
        long=long_win,
    )


def load_rules(file_path: Union[str, Path]) -> List[BaseRule]:
    """Load and strictly validate alert rules from a JSON file.

    Parameters:
        file_path: Path to the JSON rules file.

    Returns:
        List of validated BaseRule (LevelRule or MACrossRule) instances.

    Raises:
        ValidationError: If the file is missing, JSON is invalid, schema is violated,
                         or duplicate rule IDs are found.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValidationError(f"Rules file not found: '{file_path}'")
    if path.is_dir():
        raise ValidationError(f"Rules path is a directory, not a file: '{file_path}'")

    try:
        with open(path, mode="r", encoding="utf-8") as f:
            raw_content = f.read().strip()
            if not raw_content:
                raise ValidationError("Rules JSON file is empty.")
            data = json.loads(raw_content)
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"Rules file '{file_path}' is not valid UTF-8 text: {exc}."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Malformed JSON in rules file '{file_path}': {exc}."
        ) from exc
    except OSError as exc:
        raise ValidationError(
            f"Cannot read rules file '{file_path}': {exc}."
        ) from exc

    if not isinstance(data, list):
        raise ValidationError("Rules file must contain a JSON array (list) of rule objects.")

    if len(data) == 0:
        raise ValidationError("Rules file must contain at least one rule.")

    rules: List[BaseRule] = []
    seen_ids: Set[str] = set()

    for idx, item in enumerate(data):
        _validate_common_fields(item, idx)
        rule_id = item["id"].strip()
        if rule_id in seen_ids:
            raise ValidationError(f"Duplicate rule ID '{rule_id}' found in rules file.")
        seen_ids.add(rule_id)

        rule_type = item["type"]
        if rule_type == "level":
            rules.append(_parse_level_rule(item))
        elif rule_type == "ma_cross":
            rules.append(_parse_ma_cross_rule(item))
        else:
            raise ValidationError(
                f"Unknown rule type '{rule_type}' for rule '{rule_id}'. "
                f"Supported types: 'level', 'ma_cross'."
            )

    return rules
