"""End-to-end and CLI integration tests for PricePulse."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from price_alerts.data_loader import load_prices
from price_alerts.engine import run_engine
from price_alerts.rules import load_rules


class TestCLI(unittest.TestCase):
    """End-to-end test suite testing CLI invocation, exit codes, sorting, and output formats."""

    def setUp(self):
        self.python_exe = sys.executable
        self.script_path = str(Path(__file__).resolve().parent.parent / "alerts.py")

    def _write_temp_file(self, content: str, suffix: str) -> str:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=suffix) as f:
            f.write(content)
            temp_path = f.name
        self.addCleanup(lambda: os.path.exists(temp_path) and os.unlink(temp_path))
        return temp_path

    def _run_cli(self, args: list) -> subprocess.CompletedProcess:
        cmd = [self.python_exe, self.script_path] + args
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_12_multiple_instruments_independent_histories(self):
        """12. Multiple instruments with independent histories do not interfere with each other."""
        csv_content = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1550.00\n"
            "2026-09-01,TCS,3800.00\n"
            "2026-09-02,INFY,1490.00\n"  # INFY crosses below 1500
            "2026-09-02,TCS,3810.00\n"   # TCS does not cross 3900
            "2026-09-03,INFY,1495.00\n"  # INFY stays below
            "2026-09-03,TCS,3950.00\n"   # TCS crosses above 3900
        )
        rules_content = (
            "[\n"
            '  {"id": "r_infy", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500},\n'
            '  {"id": "r_tcs", "instrument": "TCS", "type": "level", "direction": "above", "level": 3900}\n'
            "]"
        )
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 0)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("r_infy", lines[0])
        self.assertIn("2026-09-02", lines[0])
        self.assertIn("r_tcs", lines[1])
        self.assertIn("2026-09-03", lines[1])

    def test_13_unsorted_csv_dates(self):
        """13. Unsorted CSV dates are processed chronologically and produce deterministic output."""
        # Intentionally out-of-order dates in CSV
        csv_content = (
            "date,instrument,close\n"
            "2026-09-03,INFY,1480.00\n"
            "2026-09-01,INFY,1550.00\n"
            "2026-09-02,INFY,1495.00\n"
        )
        rules_content = '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]'
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        # Alert should trigger on 2026-09-02 (the first chronological drop below 1500)
        self.assertEqual(len(lines), 1)
        self.assertIn("2026-09-02", lines[0])
        self.assertIn("r1", lines[0])

    def test_14_and_15_multiple_rules_same_date_and_sorting(self):
        """14 & 15. Multiple rules firing on the same date are sorted by date, then rule ID."""
        csv_content = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1600.00\n"
            "2026-09-02,INFY,1300.00\n"
        )
        # Both rules trigger on 2026-09-02 for INFY.
        # r_beta and r_alpha: r_alpha must appear before r_beta.
        rules_content = (
            "[\n"
            '  {"id": "r_beta", "instrument": "INFY", "type": "level", "direction": "below", "level": 1400},\n'
            '  {"id": "r_alpha", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}\n'
            "]"
        )
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        # Both on 2026-09-02
        self.assertIn("2026-09-02", lines[0])
        self.assertIn("r_alpha", lines[0])
        self.assertIn("2026-09-02", lines[1])
        self.assertIn("r_beta", lines[1])

    def test_17_no_alerts_for_valid_input(self):
        """17. Valid input that produces no alerts exits 0 and prints nothing to stdout."""
        csv_content = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1600.00\n"
            "2026-09-02,INFY,1620.00\n"
            "2026-09-03,INFY,1610.00\n"
        )
        rules_content = '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]'
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertEqual(proc.stderr.strip(), "")

    def test_24_diagnostic_mode_explains_alert(self):
        """24. Diagnostic mode (--explain) explains why an alert fired."""
        csv_content = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1520.00\n"
            "2026-09-02,INFY,1490.00\n"
        )
        rules_content = '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]'
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path, "--explain"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("level below 1500", proc.stdout)
        self.assertIn("[EXPLAIN]", proc.stdout)
        self.assertIn("Previous close on 2026-09-01: 1520", proc.stdout)
        self.assertIn("Current close on 2026-09-02: 1490", proc.stdout)

    def test_25_normal_mode_free_of_diagnostics(self):
        """25. Normal mode output remains completely free of diagnostics and banners."""
        csv_content = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1520.00\n"
            "2026-09-02,INFY,1490.00\n"
        )
        rules_content = '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]'
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("[EXPLAIN]", proc.stdout)
        self.assertNotIn("Diagnostics", proc.stdout)
        self.assertEqual(proc.stderr.strip(), "")
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "2026-09-02        r1    INFY     level below 1500")

    def test_cli_validation_failure_exit_code_and_stderr(self):
        """CLI returns exit code 1 with clean error on stderr without traceback."""
        csv_content = "date,instrument\n2026-09-01,INFY\n"
        rules_content = '[{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]'
        csv_path = self._write_temp_file(csv_content, suffix=".csv")
        rules_path = self._write_temp_file(rules_content, suffix=".json")

        proc = self._run_cli([csv_path, rules_path])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertTrue(proc.stderr.startswith("Error:"))
        self.assertNotIn("Traceback", proc.stderr)

    def test_cli_usage_error_on_missing_args(self):
        """CLI returns exit code 2 when required positional arguments are missing."""
        proc = self._run_cli([])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage: alerts.py", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
