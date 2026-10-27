# database.py
import json
import sqlite3
 
DB_FILE = "scenarios.db"
 
# 設定項目が増えても壊れないよう、1シナリオ=名前+JSON文字列で保存する。
# (以前の saved_scenarios テーブルはそのまま残し、使わない)
 
 
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_scenarios_v2 (
            scenario_name TEXT PRIMARY KEY,
            params_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
 
 
def save_scenario_to_db(name, params):
    """params は {項目名: 値} の辞書"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO saved_scenarios_v2 (scenario_name, params_json)"
        " VALUES (?, ?)",
        (name, json.dumps(params, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
 
 
def load_scenario_from_db(name):
    """保存した辞書を返す。なければ None"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT params_json FROM saved_scenarios_v2 WHERE scenario_name = ?",
        (name,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None
 
 
def get_all_scenario_names():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT scenario_name FROM saved_scenarios_v2 ORDER BY rowid")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]
 