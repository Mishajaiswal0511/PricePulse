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
        """Regression test: All PRESETS defined in HTML_PAGE must have valid multiline formatting."""
        from ui import HTML_PAGE
        import re

        # Find the PRESETS block in the JS code
        presets_idx = HTML_PAGE.find("const PRESETS = {")
        self.assertNotEqual(presets_idx, -1, "PRESETS object not found in HTML_PAGE")
        presets_block = HTML_PAGE[presets_idx : presets_idx + 6000]

        # Extract each preset and test execution
        for preset_name, expected_count in [("standard", 2), ("multi_asset", 3), ("boundary", 2)]:
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

            # Execute analysis directly
            res = execute_analysis(csv_text, json_text)
            self.assertTrue(res["success"], f"Preset '{preset_name}' analysis failed: {res.get('error')}")
            self.assertEqual(len(res["alerts"]), expected_count, f"Preset '{preset_name}' unexpected alert count")



if __name__ == "__main__":
    unittest.main()
