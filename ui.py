"""PricePulse: Optional Local Web UI Server.

A zero-dependency local web dashboard for PricePulse using Python's standard library.
Preserves all core business logic and modules without duplicating calculations.

Usage:
    python ui.py [--port 8000]
"""

import argparse
import datetime
from decimal import Decimal
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Tuple
import urllib.parse
import webbrowser

from price_alerts.data_loader import ValidationError, load_prices
from price_alerts.engine import Alert, run_engine
from price_alerts.rules import LevelRule, MACrossRule, load_rules

# Root directory of the PricePulse project
PROJECT_ROOT = Path(__file__).resolve().parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def execute_analysis(prices_content: str, rules_content: str) -> Dict[str, Any]:
    """Execute alert analysis safely through existing PricePulse core modules.

    Uses temporary files to feed the exact load_prices and load_rules validation
    pipelines, ensuring 100% parity with the CLI without duplicating logic.
    """
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f_prices:
        f_prices.write(prices_content)
        prices_temp_path = f_prices.name

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json") as f_rules:
        f_rules.write(rules_content)
        rules_temp_path = f_rules.name

    try:
        prices_by_inst = load_prices(prices_temp_path)
        rules = load_rules(rules_temp_path)
        alerts = run_engine(prices_by_inst, rules)

        total_obs = sum(len(records) for records in prices_by_inst.values())
        rule_map = {r.id: r for r in rules}

        serialized_alerts: List[Dict[str, Any]] = []
        for a in alerts:
            rule_obj = rule_map.get(a.rule_id)
            rule_type = rule_obj.type if rule_obj else "unknown"
            rule_dir = rule_obj.direction if rule_obj else "unknown"
            serialized_alerts.append(
                {
                    "date": a.date.isoformat(),
                    "rule_id": a.rule_id,
                    "instrument": a.instrument,
                    "type": rule_type,
                    "direction": rule_dir,
                    "description": a.description,
                    "explanation": a.explanation,
                    "formatted_line": a.format_line(),
                }
            )

        return {
            "success": True,
            "alerts": serialized_alerts,
            "stats": {
                "total_alerts": len(alerts),
                "instruments_count": len(prices_by_inst),
                "total_observations": total_obs,
                "rules_evaluated": len(rules),
            },
        }
    except ValidationError as exc:
        return {
            "success": False,
            "error": str(exc),
        }
    except Exception as exc:  # pylint: disable=broad-except
        return {
            "success": False,
            "error": f"Unexpected execution error: {exc}",
        }
    finally:
        for path in (prices_temp_path, rules_temp_path):
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PricePulse — Reliable Price Alert Engine</title>
  <style>
    :root {
      --bg: #090d16;
      --surface: #111827;
      --surface-hover: #1f2937;
      --card-bg: #151e2e;
      --border: #243247;
      --text: #f3f4f6;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.12);
      --danger: #f43f5e;
      --danger-bg: rgba(244, 63, 94, 0.12);
      --accent: #38bdf8;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      line-height: 1.5;
      padding: 1.5rem;
      min-height: 100vh;
    }

    .container {
      max-width: 1200px;
      margin: 0 auto;
    }

    /* Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2rem;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .brand-icon {
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, #6366f1, #38bdf8);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      font-weight: bold;
      color: white;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
    }
    .brand-title h1 {
      font-size: 1.4rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .brand-title p {
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .badge-status {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.35rem 0.75rem;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-radius: 9999px;
      color: var(--success);
      font-size: 0.8rem;
      font-weight: 500;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--success);
    }

    /* Preset bar */
    .presets-bar {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      margin-bottom: 1.5rem;
      background: var(--surface);
      padding: 0.75rem 1rem;
      border-radius: 10px;
      border: 1px solid var(--border);
    }
    .presets-label {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .btn-preset {
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 0.4rem 0.85rem;
      border-radius: 6px;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .btn-preset:hover {
      background: var(--surface-hover);
      border-color: var(--primary);
      color: white;
    }

    /* Grid for Inputs */
    .grid-inputs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 860px) {
      .grid-inputs { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }
    .card-title {
      font-size: 1rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .file-input-wrapper {
      position: relative;
      display: inline-block;
    }
    .file-input-wrapper input[type="file"] {
      display: none;
    }
    .btn-upload {
      background: rgba(99, 102, 241, 0.12);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: var(--primary);
      padding: 0.35rem 0.75rem;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn-upload:hover {
      background: rgba(99, 102, 241, 0.25);
    }

    textarea {
      width: 100%;
      height: 180px;
      background: #0b111e;
      color: #e2e8f0;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.75rem;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      resize: vertical;
      line-height: 1.4;
    }
    textarea:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
    }

    /* Actions Bar */
    .actions-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2rem;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary), #4338ca);
      color: white;
      border: none;
      padding: 0.75rem 1.75rem;
      font-size: 0.95rem;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s ease;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    }
    .btn-primary:hover {
      background: linear-gradient(135deg, var(--primary-hover), #3730a3);
      transform: translateY(-1px);
    }
    .btn-primary:active {
      transform: translateY(1px);
    }

    /* Stats Bar */
    .stats-bar {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 768px) {
      .stats-bar { grid-template-columns: repeat(2, 1fr); }
    }
    .stat-card {
      background: var(--surface);
      border: 1px solid var(--border);
      padding: 1rem;
      border-radius: 10px;
      text-align: center;
    }
    .stat-value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text);
    }
    .stat-label {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 0.2rem;
    }

    /* Alerts Table */
    .table-container {
      width: 100%;
      overflow-x: auto;
      border-radius: 8px;
      border: 1px solid var(--border);
      margin-top: 1rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.9rem;
    }
    th {
      background: #0f172a;
      padding: 0.75rem 1rem;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.05em;
    }
    td {
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover { background: rgba(255, 255, 255, 0.02); }

    /* Badges */
    .badge {
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-rule { background: rgba(56, 189, 248, 0.12); color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.3); font-family: var(--font-mono); }
    .badge-ticker { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; font-weight: 700; }
    .badge-level { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); }
    .badge-ma { background: rgba(6, 182, 212, 0.15); color: #22d3ee; border: 1px solid rgba(6, 182, 212, 0.3); }
    .badge-above { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-below { background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.3); }

    .btn-explain {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 0.3rem 0.6rem;
      border-radius: 4px;
      font-size: 0.75rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn-explain:hover {
      border-color: var(--primary);
      color: var(--text);
    }

    /* Explanation drawer */
    .explanation-row td {
      background: #0d1424;
      padding: 0.75rem 1.25rem;
      border-bottom: 1px solid var(--border);
    }
    .explanation-box {
      border-left: 3px solid var(--primary);
      padding-left: 0.75rem;
      font-size: 0.85rem;
      color: #cbd5e1;
      font-family: var(--font-sans);
    }

    /* Error Message */
    .error-box {
      background: rgba(244, 63, 94, 0.12);
      border: 1px solid rgba(244, 63, 94, 0.3);
      color: #fda4af;
      padding: 1rem 1.25rem;
      border-radius: 8px;
      margin-bottom: 1.5rem;
      display: none;
      align-items: flex-start;
      gap: 0.75rem;
    }
    .error-box.active { display: flex; }

    /* Empty state */
    .empty-state {
      text-align: center;
      padding: 3rem 1rem;
      color: var(--text-muted);
    }
    .empty-icon { font-size: 2.5rem; margin-bottom: 0.5rem; opacity: 0.6; }

    /* Terminal Output Preview */
    .terminal-card {
      margin-top: 1.5rem;
      background: #080c14;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
    }
    .terminal-title {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .terminal-code {
      font-family: var(--font-mono);
      font-size: 0.85rem;
      color: #38bdf8;
      white-space: pre-wrap;
      overflow-x: auto;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">⚡</div>
        <div class="brand-title">
          <h1>PricePulse Dashboard</h1>
          <p>Reliable Financial Price Alert Engine • Interactive Visual Interface</p>
        </div>
      </div>
      <div class="badge-status">
        <span class="status-dot"></span>
        <span>Local Backend Connected</span>
      </div>
    </header>

    <!-- Preset Fixtures -->
    <div class="presets-bar">
      <span class="presets-label">Load Fixture:</span>
      <button class="btn-preset" onclick="loadFixture('standard')">
        📋 Assessment Example (INFY & TCS)
      </button>
      <button class="btn-preset" onclick="loadFixture('multi_asset')">
        🌐 Multi-Asset Market (AAPL, MSFT, GOOGL)
      </button>
      <button class="btn-preset" onclick="loadFixture('boundary')">
        🎯 Exact-Boundary Edge Case
      </button>
    </div>

    <!-- Error Banner -->
    <div id="errorBanner" class="error-box">
      <span style="font-size: 1.2rem;">⚠️</span>
      <div>
        <strong id="errorTitle">Validation Error</strong>
        <p id="errorMessage" style="margin-top: 0.25rem; font-size: 0.85rem;"></p>
      </div>
    </div>

    <!-- Input Editors -->
    <div class="grid-inputs">
      <div class="card">
        <div class="card-header">
          <span class="card-title">📄 Prices CSV (date,instrument,close)</span>
          <div class="file-input-wrapper">
            <button class="btn-upload" onclick="document.getElementById('csvFileInput').click()">Upload CSV</button>
            <input type="file" id="csvFileInput" accept=".csv,.txt" onchange="handleFileUpload(event, 'csvText')">
          </div>
        </div>
        <textarea id="csvText" spellcheck="false" placeholder="date,instrument,close&#10;2026-09-01,INFY,1520.50&#10;2026-09-02,INFY,1498.00"></textarea>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">⚙️ Rules JSON Array</span>
          <div class="file-input-wrapper">
            <button class="btn-upload" onclick="document.getElementById('jsonFileInput').click()">Upload JSON</button>
            <input type="file" id="jsonFileInput" accept=".json,.txt" onchange="handleFileUpload(event, 'jsonText')">
          </div>
        </div>
        <textarea id="jsonText" spellcheck="false" placeholder='[&#10;  {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}&#10;]'></textarea>
      </div>
    </div>

    <!-- Execution Row -->
    <div class="actions-bar">
      <button class="btn-primary" onclick="runAnalysis()">
        <span>⚡ Run Analysis</span>
      </button>
      <span style="font-size: 0.85rem; color: var(--text-muted);">
        Runs pure Python engine with exact Decimal precision.
      </span>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar" id="statsBar" style="display: none;">
      <div class="stat-card">
        <div class="stat-value" id="statAlerts" style="color: var(--primary);">0</div>
        <div class="stat-label">Alerts Triggered</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" id="statInstruments">0</div>
        <div class="stat-label">Instruments Analyzed</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" id="statObservations">0</div>
        <div class="stat-label">Daily Observations</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" id="statRules">0</div>
        <div class="stat-label">Rules Evaluated</div>
      </div>
    </div>

    <!-- Results Card -->
    <div class="card" id="resultsCard">
      <div class="card-header">
        <span class="card-title">🔔 Triggered Alerts</span>
        <span id="alertsCountBadge" style="font-size: 0.85rem; color: var(--text-muted);">Ready to run</span>
      </div>

      <div id="emptyState" class="empty-state">
        <div class="empty-icon">📊</div>
        <p>No analysis run yet.</p>
        <p style="font-size: 0.8rem; margin-top: 0.25rem;">Select a preset above or input data and click <strong>Run Analysis</strong>.</p>
      </div>

      <div class="table-container" id="tableContainer" style="display: none;">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Rule ID</th>
              <th>Instrument</th>
              <th>Rule Type</th>
              <th>Direction</th>
              <th>Summary</th>
              <th>Diagnostic</th>
            </tr>
          </thead>
          <tbody id="alertsTableBody"></tbody>
        </table>
      </div>

      <!-- Terminal Output Equivalent -->
      <div class="terminal-card" id="terminalCard" style="display: none;">
        <div class="terminal-title">
          <span>Standard CLI Output (python alerts.py prices.csv rules.json)</span>
          <button class="btn-explain" onclick="copyTerminalOutput()">Copy</button>
        </div>
        <div class="terminal-code" id="terminalOutput"></div>
      </div>
    </div>
  </div>

  <script>
    const PRESETS = {
      standard: {
        csv: `date,instrument,close
2026-09-01,INFY,1520.50
2026-09-01,TCS,3890.00
2026-09-02,INFY,1534.10
2026-09-02,TCS,3902.25
2026-09-03,INFY,1498.00
2026-09-03,TCS,3910.00
2026-09-04,TCS,3910.00
2026-09-05,TCS,3910.00
2026-09-06,TCS,3910.00
2026-09-07,TCS,3910.00
2026-09-08,TCS,3910.00
2026-09-09,TCS,3910.00
2026-09-10,TCS,3910.00
2026-09-11,TCS,3910.00
2026-09-12,TCS,3910.00
2026-09-13,TCS,3910.00
2026-09-14,TCS,3910.00
2026-09-15,TCS,3910.00
2026-09-16,TCS,3890.00
2026-09-17,TCS,3890.00
2026-09-18,TCS,3890.00
2026-09-19,TCS,3890.00
2026-09-20,TCS,3890.00
2026-09-21,TCS,3890.00
2026-09-22,TCS,3890.00
2026-09-23,TCS,3890.00
2026-09-24,TCS,4050.00`,
        json: `[
  {
    "id": "r1",
    "instrument": "INFY",
    "type": "level",
    "direction": "below",
    "level": 1500
  },
  {
    "id": "r2",
    "instrument": "TCS",
    "type": "ma_cross",
    "short": 5,
    "long": 20,
    "direction": "above"
  }
]`
      },
      multi_asset: {
        csv: `date,instrument,close
2026-10-03,AAPL,198.50
2026-10-01,GOOGL,175.00
2026-10-05,MSFT,400.00
2026-10-01,AAPL,202.00
2026-10-02,AAPL,201.00
2026-10-04,AAPL,197.00
2026-10-06,AAPL,206.50
2026-10-05,AAPL,204.00
2026-10-01,MSFT,400.00
2026-10-07,MSFT,370.00
2026-10-02,MSFT,400.00
2026-10-06,MSFT,400.00
2026-10-03,MSFT,400.00
2026-10-04,MSFT,400.00
2026-10-02,GOOGL,176.00
2026-10-07,GOOGL,179.00
2026-10-05,GOOGL,178.00
2026-10-03,GOOGL,174.50
2026-10-04,GOOGL,177.00
2026-10-06,GOOGL,176.50`,
        json: `[
  {
    "id": "alert_aapl_dip",
    "instrument": "AAPL",
    "type": "level",
    "direction": "below",
    "level": 200
  },
  {
    "id": "alert_aapl_rally",
    "instrument": "AAPL",
    "type": "level",
    "direction": "above",
    "level": 205
  },
  {
    "id": "alert_msft_cross",
    "instrument": "MSFT",
    "type": "ma_cross",
    "short": 3,
    "long": 6,
    "direction": "below"
  },
  {
    "id": "alert_googl_dip",
    "instrument": "GOOGL",
    "type": "level",
    "direction": "below",
    "level": 150
  }
]`
      },
      boundary: {
        csv: `date,instrument,close
2026-09-01,INFY,1500.00
2026-09-02,INFY,1499.99
2026-09-03,INFY,1500.00
2026-09-04,INFY,1500.01`,
        json: `[
  {
    "id": "exact_below",
    "instrument": "INFY",
    "type": "level",
    "direction": "below",
    "level": 1500
  },
  {
    "id": "exact_above",
    "instrument": "INFY",
    "type": "level",
    "direction": "above",
    "level": 1500
  }
]`
      }
    };

    function loadFixture(key) {
      if (PRESETS[key]) {
        document.getElementById('csvText').value = PRESETS[key].csv;
        document.getElementById('jsonText').value = PRESETS[key].json;
        hideError();
        runAnalysis();
      }
    }

    function handleFileUpload(event, targetId) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(e) {
        document.getElementById(targetId).value = e.target.result;
      };
      reader.readAsText(file);
    }

    function showError(msg) {
      const banner = document.getElementById('errorBanner');
      document.getElementById('errorMessage').innerText = msg;
      banner.classList.add('active');
    }

    function hideError() {
      document.getElementById('errorBanner').classList.remove('active');
    }

    async function runAnalysis() {
      hideError();
      const prices = document.getElementById('csvText').value.trim();
      const rules = document.getElementById('jsonText').value.trim();

      if (!prices || !rules) {
        showError('Please supply both CSV prices and JSON alert rules.');
        return;
      }

      try {
        const resp = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prices_content: prices, rules_content: rules })
        });
        const data = await resp.json();

        if (!data.success) {
          showError(data.error);
          document.getElementById('statsBar').style.display = 'none';
          document.getElementById('tableContainer').style.display = 'none';
          document.getElementById('terminalCard').style.display = 'none';
          document.getElementById('emptyState').style.display = 'block';
          document.getElementById('emptyState').innerHTML = `
            <div class="empty-icon">❌</div>
            <p style="color: #fda4af;">Analysis could not be evaluated due to validation errors.</p>
          `;
          return;
        }

        renderResults(data);
      } catch (err) {
        showError('Failed to communicate with local PricePulse server: ' + err.message);
      }
    }

    function renderResults(data) {
      const alerts = data.alerts;
      const stats = data.stats;

      // Stats Bar
      document.getElementById('statsBar').style.display = 'grid';
      document.getElementById('statAlerts').innerText = stats.total_alerts;
      document.getElementById('statInstruments').innerText = stats.instruments_count;
      document.getElementById('statObservations').innerText = stats.total_observations;
      document.getElementById('statRules').innerText = stats.rules_evaluated;

      document.getElementById('alertsCountBadge').innerText = `${alerts.length} alert${alerts.length === 1 ? '' : 's'} triggered`;

      if (alerts.length === 0) {
        document.getElementById('tableContainer').style.display = 'none';
        document.getElementById('terminalCard').style.display = 'none';
        document.getElementById('emptyState').style.display = 'block';
        document.getElementById('emptyState').innerHTML = `
          <div class="empty-icon">✅</div>
          <p>No alerts triggered.</p>
          <p style="font-size: 0.85rem; margin-top: 0.25rem;">Evaluated ${stats.rules_evaluated} rules across ${stats.instruments_count} instruments. Price series remained within thresholds.</p>
        `;
        return;
      }

      document.getElementById('emptyState').style.display = 'none';
      document.getElementById('tableContainer').style.display = 'block';

      // Table body
      const tbody = document.getElementById('alertsTableBody');
      tbody.innerHTML = '';
      let terminalLines = [];

      alerts.forEach((alert, idx) => {
        terminalLines.push(alert.formatted_line);

        const typeBadge = alert.type === 'level'
          ? '<span class="badge badge-level">LEVEL</span>'
          : '<span class="badge badge-ma">MA_CROSS</span>';

        const dirBadge = alert.direction === 'above'
          ? '<span class="badge badge-above">▲ ABOVE</span>'
          : '<span class="badge badge-below">▼ BELOW</span>';

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family: var(--font-mono); font-weight: 600;">${alert.date}</td>
          <td><span class="badge badge-rule">${alert.rule_id}</span></td>
          <td><span class="badge badge-ticker">${alert.instrument}</span></td>
          <td>${typeBadge}</td>
          <td>${dirBadge}</td>
          <td style="font-family: var(--font-mono); font-size: 0.85rem;">${alert.description}</td>
          <td><button class="btn-explain" onclick="toggleExplanation(${idx})">Explain</button></td>
        `;
        tbody.appendChild(tr);

        // Explanation row (hidden by default)
        const trExpl = document.createElement('tr');
        trExpl.id = `expl-row-${idx}`;
        trExpl.className = 'explanation-row';
        trExpl.style.display = 'none';
        trExpl.innerHTML = `
          <td colspan="7">
            <div class="explanation-box">
              <strong>Diagnostic Reason:</strong> ${alert.explanation}
            </div>
          </td>
        `;
        tbody.appendChild(trExpl);
      });

      // Terminal Output
      document.getElementById('terminalCard').style.display = 'block';
      document.getElementById('terminalOutput').innerText = terminalLines.join('\\n');
    }

    function toggleExplanation(idx) {
      const row = document.getElementById(`expl-row-${idx}`);
      if (row.style.display === 'none') {
        row.style.display = 'table-row';
      } else {
        row.style.display = 'none';
      }
    }

    function copyTerminalOutput() {
      const text = document.getElementById('terminalOutput').innerText;
      navigator.clipboard.writeText(text);
    }

    // Auto load assessment example on startup
    window.addEventListener('DOMContentLoaded', () => {
      loadFixture('standard');
    });
  </script>
</body>
</html>
"""


class PricePulseHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler for PricePulse local web dashboard."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP access logs in normal server run."""
        # Clean terminal output: only write errors if needed
        pass

    def do_GET(self) -> None:
        """Serve HTML dashboard or static API endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            content = HTML_PAGE.encode("utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed.path == "/api/health":
            self._send_json({"status": "healthy", "service": "PricePulse UI"})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Process analysis requests using the Python core engine."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/analyze":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 10 * 1024 * 1024:  # 10MB limit
                    self._send_json({"success": False, "error": "Payload exceeds 10MB limit."})
                    return

                raw_body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(raw_body)
                prices_content = payload.get("prices_content", "")
                rules_content = payload.get("rules_content", "")

                result = execute_analysis(prices_content, rules_content)
                self._send_json(result)
            except json.JSONDecodeError:
                self._send_json({"success": False, "error": "Invalid JSON request payload."})
            except Exception as exc:  # pylint: disable=broad-except
                self._send_json({"success": False, "error": f"Server processing error: {exc}"})
        else:
            self.send_error(404, "Endpoint Not Found")

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        """Helper to send JSON response."""
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def start_server(port: int = 8000, open_browser: bool = True) -> None:
    """Start the PricePulse local web server."""
    server_address = ("127.0.0.1", port)
    try:
        httpd = http.server.HTTPServer(server_address, PricePulseHTTPHandler)
    except OSError as exc:
        sys.stderr.write(f"Error starting server on port {port}: {exc}\n")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    sys.stdout.write(f"\n===================================================\n")
    sys.stdout.write(f" PricePulse Local Web Dashboard Running\n")
    sys.stdout.write(f" URL: {url}\n")
    sys.stdout.write(f" Press Ctrl+C in terminal to stop server\n")
    sys.stdout.write(f"===================================================\n\n")
    sys.stdout.flush()

    if open_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nShutting down PricePulse UI server gracefully...\n")
        httpd.server_close()


def main() -> None:
    """CLI entry point for ui.py."""
    parser = argparse.ArgumentParser(
        prog="ui.py",
        description="Optional PricePulse Local Web Dashboard",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run local web server on (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically launch default web browser",
    )
    args = parser.parse_args()
    start_server(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
