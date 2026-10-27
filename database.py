# database.py
import sqlite3
import pandas as pd

DB_FILE = "scenarios.db"


def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_name TEXT UNIQUE,
            rev_growth REAL,
            cogs_pct REAL,
            sga_pct REAL,
            tax_rate REAL,
            capex_pct REAL,
            da_pct REAL,
            ar_days REAL,
            inv_days REAL,
            ap_days REAL,
            wacc REAL,
            perp_growth REAL,
            interest_rate REAL,
            base_rev REAL,
            base_cash REAL,
            base_ppe REAL,
            base_debt REAL,
            base_equity REAL,
            shares_outstanding REAL
        )
    """)
  conn.commit()
  conn.close()


def save_scenario_to_db(name, params):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO saved_scenarios (
            scenario_name, rev_growth, cogs_pct, sga_pct, tax_rate,
            capex_pct, da_pct, ar_days, inv_days, ap_days,
            wacc, perp_growth, interest_rate,
            base_rev, base_cash, base_ppe, base_debt, base_equity, shares_outstanding
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (name, *params),
  )
  conn.commit()
  conn.close()


def load_scenario_from_db(name):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT * FROM saved_scenarios WHERE scenario_name = ?", (name,)
  )
  row = cursor.fetchone()
  conn.close()
  if row:
    # id(0)とscenario_name(1)をスキップし、数値パラメータ(2~)のみを返す
    return row[2:]
  return None


def get_all_scenario_names():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT scenario_name FROM saved_scenarios")
  rows = cursor.fetchall()
  conn.close()
  return [row[0] for row in rows]