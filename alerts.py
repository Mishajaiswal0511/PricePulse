"""PricePulse: Reliable Price Alert Engine CLI.

CLI entry point for evaluating price series against alert rules.
Usage:
    python alerts.py prices.csv rules.json [--explain]
"""

import argparse
import sys
from typing import List

from price_alerts.data_loader import ValidationError, load_prices
from price_alerts.engine import Alert, run_engine
from price_alerts.rules import load_rules


def parse_arguments(args: List[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="alerts.py",
        description="PricePulse: Reliable Price Alert Engine CLI",
        add_help=True,
    )
    parser.add_argument(
        "prices",
        help="Path to CSV price file with columns: date,instrument,close",
    )
    parser.add_argument(
        "rules",
        help="Path to JSON alert rules file",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Enable diagnostic mode showing why alerts triggered",
    )
    return parser.parse_args(args)


def format_and_print_alerts(alerts: List[Alert], explain: bool = False) -> None:
    """Format and print alerts to stdout adhering strictly to format specifications."""
    if not alerts:
        if explain:
            sys.stderr.write("Diagnostics: No alerts triggered.\n")
        return

    # Dynamic column widths ensure alignment even for long rule IDs or tickers,
    # while guaranteeing the exact standard spacing (18, 6, 9) for standard inputs.
    max_rule_len = max(len(a.rule_id) for a in alerts)
    max_inst_len = max(len(a.instrument) for a in alerts)
    rule_col_width = max(6, max_rule_len + 2)
    inst_col_width = max(9, max_inst_len + 2)

    for alert in alerts:
        line = alert.format_line(rule_col_width=rule_col_width, inst_col_width=inst_col_width)
        sys.stdout.write(f"{line}\n")
        if explain:
            sys.stdout.write(f"  [EXPLAIN] {alert.explanation}\n")


def main(argv: List[str] = None) -> int:
    """Application main entry point."""
    if argv is None:
        argv = sys.argv[1:]

    try:
        args = parse_arguments(argv)
    except SystemExit as exc:
        # argparse exited (e.g. --help or invalid usage)
        return exc.code

    try:
        prices_by_instrument = load_prices(args.prices)
        rules = load_rules(args.rules)
        alerts = run_engine(prices_by_instrument, rules)
        format_and_print_alerts(alerts, explain=args.explain)
        return 0
    except ValidationError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        # Catch unexpected fatal errors cleanly without a raw traceback in standard runs
        sys.stderr.write(f"Fatal error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
