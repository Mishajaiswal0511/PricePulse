"""Unit tests for the optional PricePulse Web UI server and backend integration."""

import json
import threading
import time
import unittest
import urllib.request
import urllib.error

from ui import execute_analysis, PricePulseHTTPHandler
import http.server


class TestWebUI(unittest.TestCase):
    """Test suite for ui.py analysis integration and HTTP endpoints."""

    def test_execute_analysis_valid(self):
        """execute_analysis produces exact alerts and statistics for valid input."""
        prices_csv = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1520.50\n"
            "2026-09-02,INFY,1498.00\n"
        )
        rules_json = json.dumps([
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ])

        result = execute_analysis(prices_csv, rules_json)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["alerts"]), 1)
        alert = result["alerts"][0]
        self.assertEqual(alert["rule_id"], "r1")
        self.assertEqual(alert["date"], "2026-09-02")
        self.assertEqual(alert["instrument"], "INFY")
        self.assertEqual(alert["type"], "level")
        self.assertEqual(alert["direction"], "below")
        self.assertIn("Price crossed below threshold 1500", alert["explanation"])

    def test_execute_analysis_validation_error(self):
        """execute_analysis returns success=False with clear message on invalid input."""
        bad_csv = "date,instrument\n2026-09-01,INFY\n"
        rules_json = json.dumps([
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ])
        result = execute_analysis(bad_csv, rules_json)
        self.assertFalse(result["success"])
        self.assertIn("Missing required CSV column", result["error"])

    def test_http_server_endpoints(self):
        """HTTP server serves HTML dashboard and responds to /api/analyze."""
        server = http.server.HTTPServer(("127.0.0.1", 0), PricePulseHTTPHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            # Test GET /
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("PricePulse Dashboard", html)

            # Test GET /api/health
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "healthy")

            # Test POST /api/analyze
            payload = json.dumps({
                "prices_content": "date,instrument,close\n2026-09-01,INFY,1520.50\n2026-09-02,INFY,1498.00\n",
                "rules_content": json.dumps([{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]),
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/analyze",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data["success"])
                self.assertEqual(len(data["alerts"]), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_presets_validity(self):
        """Regression test: All PRESETS defined in HTML_PAGE must have valid schema, newlines, and alerts."""
        from ui import HTML_PAGE
        import re

        # Find the PRESETS block in the JS code
        presets_idx = HTML_PAGE.find("const PRESETS = {")
        self.assertNotEqual(presets_idx, -1, "PRESETS object not found in HTML_PAGE")
        presets_block = HTML_PAGE[presets_idx : presets_idx + 6000]

        expected_alerts_map = {
            "standard": [
                ("2026-09-03", "r1", "INFY"),
                ("2026-09-24", "r2", "TCS"),
            ],
            "multi_asset": [
                ("2026-10-03", "alert_aapl_dip", "AAPL"),
                ("2026-10-06", "alert_aapl_rally", "AAPL"),
                ("2026-10-07", "alert_msft_cross", "MSFT"),
            ],
            "boundary": [
                ("2026-09-02", "exact_below", "INFY"),
                ("2026-09-04", "exact_above", "INFY"),
            ],
        }

        # Extract each preset and test execution
        for preset_name, expected_alerts in expected_alerts_map.items():
            # Match csv: `...` and json: `...`
            csv_pattern = re.compile(rf"{preset_name}:\s*\{{\s*csv:\s*`([^`]+)`", re.DOTALL)
            json_pattern = re.compile(rf"{preset_name}:\s*\{{[^}}]*?json:\s*`([^`]+)`", re.DOTALL)

            m_csv = csv_pattern.search(presets_block)
            m_json = json_pattern.search(presets_block)

            self.assertIsNotNone(m_csv, f"Preset '{preset_name}' csv string not found")
            self.assertIsNotNone(m_json, f"Preset '{preset_name}' json string not found")

            csv_text = m_csv.group(1).strip()
            json_text = m_json.group(1).strip()

            # Ensure the string actually has multiple lines and not literal \n characters
            self.assertIn("\n", csv_text, f"Preset '{preset_name}' CSV must contain real newlines")
            self.assertNotIn("\\n", csv_text, f"Preset '{preset_name}' CSV must not contain literal \\n")

            # Verify JSON schema: must NOT use 'threshold', must use 'level' for level rules
            parsed_rules = json.loads(json_text)
            for rule in parsed_rules:
                self.assertNotIn(
                    "threshold",
                    rule,
                    f"Preset '{preset_name}' rule '{rule.get('id')}' incorrectly uses 'threshold' instead of 'level'",
                )
                if rule.get("type") == "level":
                    self.assertIn(
                        "level",
                        rule,
                        f"Preset '{preset_name}' level rule '{rule.get('id')}' is missing required field 'level'",
                    )

            # Execute analysis directly
            res = execute_analysis(csv_text, json_text)
            self.assertTrue(res["success"], f"Preset '{preset_name}' analysis failed: {res.get('error')}")
            self.assertEqual(
                len(res["alerts"]),
                len(expected_alerts),
                f"Preset '{preset_name}' unexpected alert count",
            )

            actual_alert_tuples = [
                (a["date"], a["rule_id"], a["instrument"]) for a in res["alerts"]
            ]
            self.assertEqual(
                actual_alert_tuples,
                expected_alerts,
                f"Preset '{preset_name}' alert tuples did not match expected",
            )

    def test_threshold_field_rejected(self):
        """Regression test: Engine strictly rejects 'threshold' and requires 'level'."""
        prices_csv = (
            "date,instrument,close\n"
            "2026-09-01,INFY,1520.50\n"
            "2026-09-02,INFY,1498.00\n"
        )
        # Rule incorrectly using "threshold" instead of "level"
        bad_rules_json = json.dumps([
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "threshold": 100}
        ])

        result = execute_analysis(prices_csv, bad_rules_json)
        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "Rule 'r1' of type 'level' is missing required field 'level'.",
        )

    def test_ui_html_clears_stale_alert_count_on_error(self):
        """Regression test: HTML client code clears stale alert count badge on validation error."""
        from ui import HTML_PAGE

        # Ensure the client updates alertsCountBadge on validation failure
        self.assertIn("document.getElementById('alertsCountBadge').innerText = '0 alerts (validation error)'", HTML_PAGE)
        # Ensure the client clears old table data on validation failure
        self.assertIn("document.getElementById('alertsTableBody').innerHTML = ''", HTML_PAGE)
        # Ensure the client updates alertsCountBadge on missing input
        self.assertIn("document.getElementById('alertsCountBadge').innerText = '0 alerts (error)'", HTML_PAGE)
        # Ensure evaluating state is set immediately when runAnalysis begins
        self.assertIn("document.getElementById('alertsCountBadge').innerText = 'Evaluating...'", HTML_PAGE)


if __name__ == "__main__":
    unittest.main()

