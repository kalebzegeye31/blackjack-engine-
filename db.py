"""
db.py — local storage, one SQLite file next to the code.

Nothing leaves your machine. Delete blackjack.db and everything is gone.
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blackjack.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    created       REAL NOT NULL,
    bankroll      REAL NOT NULL DEFAULT 100,
    deposited     REAL NOT NULL DEFAULT 100,
    buy_ins       INTEGER NOT NULL DEFAULT 1,
    config        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    at            REAL NOT NULL,
    cell          TEXT NOT NULL,       -- e.g. "hard 16 vs 10"
    chose         TEXT NOT NULL,
    correct       INTEGER NOT NULL,    -- matched the chart
    ev_correct    INTEGER NOT NULL,    -- matched the live shoe
    cost          REAL NOT NULL,       -- expected value given up
    true_count    REAL NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS bets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    at            REAL NOT NULL,
    amount        REAL NOT NULL,
    suggested     REAL NOT NULL,
    sound         INTEGER NOT NULL,
    flags         TEXT NOT NULL DEFAULT '[]',
    true_count    REAL NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    at            REAL NOT NULL,
    wagered       REAL NOT NULL,
    net           REAL NOT NULL,
    bankroll      REAL NOT NULL,
    lifetime      REAL NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_dec_acct ON decisions(account_id);
CREATE INDEX IF NOT EXISTS idx_bet_acct ON bets(account_id);
CREATE INDEX IF NOT EXISTS idx_rnd_acct ON rounds(account_id);
"""


@contextmanager
def connect():
    """
    One connection per operation, committed and then closed.

    `with sqlite3_connection:` only opens a transaction - it commits or rolls
    back and leaves the connection open. Every caller here uses `with`, so
    without the close() below each request leaked a connection, and in WAL
    mode each of those pins three file handles. A few dozen hands was enough
    to exhaust the process file limit and take the server down with
    "unable to open database file".
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        with conn:          # commit on success, roll back on error
            yield conn
    finally:
        conn.close()


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------------- accounts ----------------

def list_accounts():
    with connect() as conn:
        rows = conn.execute("""
            SELECT a.id, a.name, a.bankroll, a.deposited, a.buy_ins,
                   (SELECT COUNT(*) FROM decisions d WHERE d.account_id = a.id) AS decisions,
                   (SELECT COUNT(*) FROM decisions d WHERE d.account_id = a.id AND d.correct = 1) AS correct,
                   (SELECT COUNT(*) FROM rounds r WHERE r.account_id = a.id) AS rounds
            FROM accounts a ORDER BY a.created DESC
        """).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "name": r["name"],
            "bankroll": r["bankroll"],
            "lifetime": round(r["bankroll"] - r["deposited"], 2),
            "rounds": r["rounds"],
            "accuracy": round(r["correct"] / r["decisions"] * 100) if r["decisions"] else None,
        })
    return out


def create_account(name):
    name = (name or "Player").strip()[:32] or "Player"
    with connect() as conn:
        base, n = name, 1
        while conn.execute("SELECT 1 FROM accounts WHERE name = ?", (name,)).fetchone():
            n += 1
            name = "%s %d" % (base, n)
        cur = conn.execute(
            "INSERT INTO accounts (name, created, bankroll, deposited, buy_ins, config) "
            "VALUES (?, ?, 100, 100, 1, '{}')", (name, time.time()))
        return cur.lastrowid


def get_account(account_id):
    with connect() as conn:
        r = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "name": r["name"], "created": r["created"],
            "bankroll": r["bankroll"], "deposited": r["deposited"],
            "buy_ins": r["buy_ins"], "config": json.loads(r["config"] or "{}")}


def save_account(account_id, bankroll, deposited, buy_ins, config):
    with connect() as conn:
        conn.execute(
            "UPDATE accounts SET bankroll = ?, deposited = ?, buy_ins = ?, config = ? WHERE id = ?",
            (bankroll, deposited, buy_ins, json.dumps(config), account_id))


def delete_account(account_id):
    with connect() as conn:
        for t in ("decisions", "bets", "rounds"):
            conn.execute("DELETE FROM %s WHERE account_id = ?" % t, (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


# ---------------- logging ----------------

def log_decision(account_id, cell, chose, correct, ev_correct, cost, true_count):
    with connect() as conn:
        conn.execute(
            "INSERT INTO decisions (account_id, at, cell, chose, correct, ev_correct, cost, true_count) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (account_id, time.time(), cell, chose, int(correct), int(ev_correct),
             float(cost), float(true_count)))


def log_bet(account_id, check):
    with connect() as conn:
        conn.execute(
            "INSERT INTO bets (account_id, at, amount, suggested, sound, flags, true_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (account_id, time.time(), check["amount"], check["suggested"], int(check["ok"]),
             json.dumps([f["key"] for f in check["flags"] if f["level"] != "info"]),
             check["true_count"]))


def log_round(account_id, wagered, net, bankroll, lifetime):
    with connect() as conn:
        conn.execute(
            "INSERT INTO rounds (account_id, at, wagered, net, bankroll, lifetime) "
            "VALUES (?,?,?,?,?,?)",
            (account_id, time.time(), wagered, net, bankroll, lifetime))


# ---------------- reading it back ----------------

def stats(account_id):
    acct = get_account(account_id)
    if not acct:
        return None
    with connect() as conn:
        d = conn.execute("""
            SELECT COUNT(*) n, SUM(correct) c, SUM(ev_correct) e, SUM(cost) cost
            FROM decisions WHERE account_id = ?""", (account_id,)).fetchone()
        b = conn.execute("""
            SELECT COUNT(*) n, SUM(sound) s FROM bets WHERE account_id = ?""",
            (account_id,)).fetchone()
        r = conn.execute("""
            SELECT COUNT(*) n, SUM(wagered) w, SUM(net) net FROM rounds WHERE account_id = ?""",
            (account_id,)).fetchone()
        weak = conn.execute("""
            SELECT cell, COUNT(*) n, SUM(cost) cost FROM decisions
            WHERE account_id = ? AND correct = 0
            GROUP BY cell ORDER BY n DESC LIMIT 12""", (account_id,)).fetchall()
        flags = conn.execute(
            "SELECT flags FROM bets WHERE account_id = ? AND sound = 0", (account_id,)).fetchall()
        curve = conn.execute("""
            SELECT lifetime FROM rounds WHERE account_id = ?
            ORDER BY id DESC LIMIT 300""", (account_id,)).fetchall()
        recent = conn.execute("""
            SELECT correct FROM decisions WHERE account_id = ?
            ORDER BY id DESC LIMIT 50""", (account_id,)).fetchall()

    flag_counts = {}
    for row in flags:
        for k in json.loads(row["flags"] or "[]"):
            flag_counts[k] = flag_counts.get(k, 0) + 1

    n_dec = d["n"] or 0
    n_bet = b["n"] or 0
    wagered = r["w"] or 0.0
    recent_list = [row["correct"] for row in recent]

    return {
        "account": {"id": acct["id"], "name": acct["name"], "created": acct["created"]},
        "bankroll": round(acct["bankroll"], 2),
        "deposited": acct["deposited"],
        "buy_ins": acct["buy_ins"],
        "lifetime": round(acct["bankroll"] - acct["deposited"], 2),
        "rounds": r["n"] or 0,
        "wagered": round(wagered, 2),
        "return_per_dollar": ((acct["bankroll"] - acct["deposited"]) / wagered) if wagered else None,
        "decisions": n_dec,
        "accuracy": (d["c"] or 0) / n_dec if n_dec else None,
        "shoe_accuracy": (d["e"] or 0) / n_dec if n_dec else None,
        "recent_accuracy": (sum(recent_list) / len(recent_list)) if recent_list else None,
        "ev_given_up": round(d["cost"] or 0.0, 3),
        "bets": n_bet,
        "bet_accuracy": (b["s"] or 0) / n_bet if n_bet else None,
        "bet_flags": flag_counts,
        "weak_spots": [{"cell": w["cell"], "misses": w["n"], "cost": round(w["cost"] or 0, 3)}
                       for w in weak],
        "curve": [row["lifetime"] for row in reversed(curve)],
    }
