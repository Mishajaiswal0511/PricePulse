"""Data loading and validation module for PricePulse.

Parses price records from CSV files, validates schemas, formats, values,
rejects duplicates and malformed records, and groups observations by instrument
in chronological order.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
from typing import Dict, List, Set, Tuple, Union


class ValidationError(Exception):
    """Raised when input files, data rows, or configurations fail validation."""
    pass


@dataclass(frozen=True)
class PriceRecord:
    """Represents a validated daily price observation for a single instrument."""
    date: datetime.date
    instrument: str
    close: Decimal


_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NON_FINITE_VALUES = frozenset({"nan", "inf", "-inf", "+inf", "infinity", "-infinity"})


def parse_date(date_str: str, row_num: int) -> datetime.date:
    """Parse and strictly validate a date string in YYYY-MM-DD format."""
    clean_date = date_str.strip()
    if not clean_date or not _DATE_REGEX.match(clean_date):
        raise ValidationError(
            f"Row {row_num}: Invalid date format '{date_str}'. Expected strictly YYYY-MM-DD."
        )
    try:
        parsed = datetime.date.fromisoformat(clean_date)
        return parsed
    except ValueError as exc:
        raise ValidationError(
            f"Row {row_num}: Invalid calendar date '{date_str}': {exc}."
        ) from exc


def parse_price(price_str: str, row_num: int) -> Decimal:
    """Parse and validate a numeric close price into an exact Decimal."""
    clean_price = price_str.strip()
    if not clean_price:
        raise ValidationError(f"Row {row_num}: Close price cannot be empty.")
    
    if clean_price.lower() in _NON_FINITE_VALUES:
        raise ValidationError(
            f"Row {row_num}: Non-finite close price '{price_str}' is not allowed."
        )

    try:
        price = Decimal(clean_price)
    except InvalidOperation as exc:
        raise ValidationError(
            f"Row {row_num}: Malformed numeric price '{price_str}'."
        ) from exc

    if price.is_nan() or price.is_infinite():
        raise ValidationError(
            f"Row {row_num}: Non-finite close price '{price_str}' is not allowed."
        )

    if price <= Decimal("0"):
        raise ValidationError(
            f"Row {row_num}: Price '{price_str}' must be strictly positive."
        )

    return price


def load_prices(file_path: Union[str, Path]) -> Dict[str, List[PriceRecord]]:
    """Load, validate, and group prices from a CSV file.

    Parameters:
        file_path: Path to the CSV file.

    Returns:
        Dictionary mapping each instrument symbol to its chronologically sorted
        list of PriceRecord objects.

    Raises:
        ValidationError: If the file cannot be read, headers are missing,
                         values are invalid, duplicates exist, or file is empty.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValidationError(f"Prices file not found: '{file_path}'")
    if path.is_dir():
        raise ValidationError(f"Prices path is a directory, not a file: '{file_path}'")

    try:
        with open(path, mode="r", encoding="utf-8") as f:
            lines = [line.strip() for line in f]
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"Prices file '{file_path}' is not valid UTF-8 text: {exc}."
        ) from exc
    except OSError as exc:
        raise ValidationError(
            f"Cannot read prices file '{file_path}': {exc}."
        ) from exc

    # Filter out empty blank lines
    non_empty_lines = [line for line in lines if line]
    if not non_empty_lines:
        raise ValidationError("Prices CSV file is empty.")

    header_line = non_empty_lines[0]
    headers = [col.strip().lower() for col in header_line.split(",")]
    required_cols = {"date", "instrument", "close"}
    missing = required_cols - set(headers)
    if missing:
        raise ValidationError(
            f"Missing required CSV column(s): {', '.join(sorted(missing))}. "
            f"Header must include 'date,instrument,close'."
        )

    date_idx = headers.index("date")
    instrument_idx = headers.index("instrument")
    close_idx = headers.index("close")
    expected_col_count = len(headers)

    records_by_instrument: Dict[str, List[PriceRecord]] = {}
    seen_observations: Set[Tuple[str, datetime.date]] = set()

    data_lines = non_empty_lines[1:]
    if not data_lines:
        raise ValidationError("Prices CSV contains no data rows.")

    for i, line in enumerate(data_lines, start=2):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != expected_col_count:
            raise ValidationError(
                f"Row {i}: Expected {expected_col_count} columns matching header, got {len(parts)}."
            )

        date_val = parse_date(parts[date_idx], i)
        instrument = parts[instrument_idx]
        if not instrument:
            raise ValidationError(f"Row {i}: Instrument name cannot be empty.")

        close_val = parse_price(parts[close_idx], i)

        obs_key = (instrument, date_val)
        if obs_key in seen_observations:
            raise ValidationError(
                f"Row {i}: Duplicate price observation for instrument '{instrument}' "
                f"on date '{date_val.isoformat()}'. Ambiguous records are rejected."
            )
        seen_observations.add(obs_key)

        record = PriceRecord(date=date_val, instrument=instrument, close=close_val)
        if instrument not in records_by_instrument:
            records_by_instrument[instrument] = []
        records_by_instrument[instrument].append(record)

    # Sort each instrument's observations chronologically
    for instrument in records_by_instrument:
        records_by_instrument[instrument].sort(key=lambda rec: rec.date)

    return records_by_instrument
