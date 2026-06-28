"""Redis-backed sliding window rate limiter."""
import time, sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "gateway.db"

def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS rate_windows(team TEXT, window_start REAL, count INT, tokens INT);
    CREATE TABLE IF NOT EXISTS budget_usage(team TEXT PRIMARY KEY, spent_usd REAL DEFAULT 0, month TEXT);
    CREATE TABLE IF NOT EXISTS requests(
        id INTEGER PRIMARY KEY, ts TEXT, team TEXT, model TEXT,
        in_tok INT, out_tok INT, cost_usd REAL, latency_ms REAL,
        provider TEXT, was_fallback INT DEFAULT 0, status TEXT);
    """)
    c.commit(); c.close()
init_db()

WINDOW_SECS = 60

def check_rate_limit(team: str, config: dict) -> tuple[bool, str]:
    now = time.time()
    window_start = now - WINDOW_SECS
    c = sqlite3.connect(DB)
    # Count requests in sliding window
    row = c.execute("SELECT SUM(count) FROM rate_windows WHERE team=? AND window_start > ?",
                    (team, window_start)).fetchone()
    current_rpm = row[0] or 0
    c.close()
    limit = config.get("rate_limit", {}).get("rpm", 60)
    if current_rpm >= limit:
        return False, f"Rate limit exceeded ({current_rpm}/{limit} RPM)"
    return True, "OK"

def record_request(team: str, in_tok: int, out_tok: int, cost_usd: float,
                   model: str, latency_ms: float, provider: str, was_fallback: bool = False):
    now = time.time()
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO rate_windows VALUES(?,?,1,?)", (team, now, in_tok+out_tok))
    # Update budget
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    c.execute("INSERT INTO budget_usage(team,spent_usd,month) VALUES(?,?,?) ON CONFLICT(team) DO UPDATE SET spent_usd=spent_usd+?, month=?",
              (team, cost_usd, month, cost_usd, month))
    c.execute("INSERT INTO requests(ts,team,model,in_tok,out_tok,cost_usd,latency_ms,provider,was_fallback,status) VALUES(datetime('now'),?,?,?,?,?,?,?,?,'ok')",
              (team, model, in_tok, out_tok, cost_usd, latency_ms, provider, 1 if was_fallback else 0))
    c.commit(); c.close()

def check_budget(team: str, config: dict) -> tuple[bool, str]:
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    c = sqlite3.connect(DB)
    row = c.execute("SELECT spent_usd FROM budget_usage WHERE team=? AND month=?", (team, month)).fetchone()
    c.close()
    spent = row[0] if row else 0
    limit = config.get("monthly_budget_usd", float("inf"))
    if spent >= limit:
        return False, f"Budget exceeded (${spent:.2f}/${limit:.2f})"
    return True, f"${spent:.4f} / ${limit:.2f}"
