"""
db.py — local storage, one SQLite file next to the code.

Nothing leaves your machine. Delete blackjack.db and everything is gone.

The shape of it, in one paragraph: an *account* owns chips and a history. Sitting
down opens a *session*, which takes a buy-in out of the chips and hands it back
when you stand up; every session has its own hands, decisions and bets hanging
off it. Every movement of money in or out of the chip stack is written to the
*ledger*, so the all-time figure is a sum of recorded facts rather than a number
we keep updating and hope is right. Quizzes live alongside, because chips won
answering questions are chips.
"""

import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blackjack.db")

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    created       REAL NOT NULL,
    last_seen     REAL NOT NULL DEFAULT 0,
    chips         REAL NOT NULL DEFAULT 0,    -- money not currently on a table
    granted       REAL NOT NULL DEFAULT 0,    -- chips handed over for nothing, ever
    earned        REAL NOT NULL DEFAULT 0,    -- chips won answering questions, ever
    sessions_run  INTEGER NOT NULL DEFAULT 0,
    config        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    number        INTEGER NOT NULL,           -- 1, 2, 3 ... per account
    started       REAL NOT NULL,
    ended         REAL,
    buy_in        REAL NOT NULL,
    cash_out      REAL,
    hands         INTEGER NOT NULL DEFAULT 0,
    rounds        INTEGER NOT NULL DEFAULT 0,
    decisions     INTEGER NOT NULL DEFAULT 0,
    correct       INTEGER NOT NULL DEFAULT 0,
    wagered       REAL NOT NULL DEFAULT 0,
    net           REAL NOT NULL DEFAULT 0,
    peak          REAL NOT NULL DEFAULT 0,
    trough        REAL NOT NULL DEFAULT 0,
    blackjacks    INTEGER NOT NULL DEFAULT 0,
    busts         INTEGER NOT NULL DEFAULT 0,
    best_streak   INTEGER NOT NULL DEFAULT 0,
    ev_lost       REAL NOT NULL DEFAULT 0,
    busted        INTEGER NOT NULL DEFAULT 0, -- ran out of money rather than stood up
    config        TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    session_id    INTEGER,
    at            REAL NOT NULL,
    cell          TEXT NOT NULL,              -- e.g. "hard 16 vs 10"
    chose         TEXT NOT NULL,
    should        TEXT,                       -- what the chart wanted
    correct       INTEGER NOT NULL,           -- matched the chart
    ev_correct    INTEGER NOT NULL,           -- matched the live shoe
    cost          REAL NOT NULL,              -- expected value given up
    true_count    REAL NOT NULL,
    source        TEXT NOT NULL DEFAULT 'play',   -- 'play' or 'quiz'
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS bets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    session_id    INTEGER,
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
    session_id    INTEGER,
    at            REAL NOT NULL,
    wagered       REAL NOT NULL,
    net           REAL NOT NULL,
    bankroll      REAL NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    at            REAL NOT NULL,
    kind          TEXT NOT NULL,              -- grant | quiz | buyin | cashout
    amount        REAL NOT NULL,              -- signed, from the chip stack's point of view
    balance       REAL NOT NULL,              -- chips after this movement
    note          TEXT NOT NULL DEFAULT '',
    ref           INTEGER,                    -- session or quiz this belongs to
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS quizzes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    at            REAL NOT NULL,
    finished      REAL,
    mode          TEXT NOT NULL,
    config        TEXT NOT NULL DEFAULT '{}',
    length        INTEGER NOT NULL,
    answered      INTEGER NOT NULL DEFAULT 0,
    correct       INTEGER NOT NULL DEFAULT 0,
    chips_earned  REAL NOT NULL DEFAULT 0,
    for_chips     INTEGER NOT NULL DEFAULT 0,
    questions     TEXT NOT NULL DEFAULT '[]', -- the whole quiz, answers included
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_dec_acct ON decisions(account_id);
CREATE INDEX IF NOT EXISTS idx_dec_sess ON decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_bet_acct ON bets(account_id);
CREATE INDEX IF NOT EXISTS idx_rnd_acct ON rounds(account_id);
CREATE INDEX IF NOT EXISTS idx_ses_acct ON sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_led_acct ON ledger(account_id);
CREATE INDEX IF NOT EXISTS idx_qz_acct  ON quizzes(account_id);
"""


def _table_sql(name, next_name):
    return SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS " + name):
                  SCHEMA.index("CREATE TABLE IF NOT EXISTS " + next_name)]


ACCOUNTS_TABLE = _table_sql("accounts", "sessions")
ROUNDS_TABLE = _table_sql("rounds", "ledger")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # foreign keys stay declared but unenforced. Turning enforcement on would make
    # the accounts rebuild in _migrate_v1_to_v2 impossible: renaming a parent table
    # rewrites every child's reference to follow it, and then the old table cannot
    # be dropped. delete_account clears children itself.
    return conn


def _columns(conn, table):
    try:
        return {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)}
    except sqlite3.Error:
        return set()


def init():
    """
    Create the schema, and bring an older file up to date without losing anything.

    Version 1 kept a single bankroll on the account and topped it up by $100
    whenever it ran dry. Version 2 splits that into chips you hold and a session
    you buy into, so the migration reads the old bankroll as chips and the old
    deposits as chips you were given.
    """
    fresh = not os.path.exists(DB_PATH)
    with connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        legacy = (not fresh) and "bankroll" in _columns(conn, "accounts")

        # every table first: the migration writes ledger rows as it goes, and an
        # old file has no ledger to write them to
        conn.executescript(SCHEMA)
        if legacy:
            _migrate_v1_to_v2(conn)

        # version 1 hung a lifetime figure off every round. It is derived from the
        # ledger now, and the old column is NOT NULL with no default, so a table
        # left over from then has to be rebuilt rather than written around.
        if "lifetime" in _columns(conn, "rounds"):
            _rebuild_rounds(conn)

        # columns added to tables that already existed, before any index needs them
        for table, col, decl in (
            ("decisions", "session_id", "INTEGER"),
            ("decisions", "should", "TEXT"),
            ("decisions", "source", "TEXT NOT NULL DEFAULT 'play'"),
            ("bets", "session_id", "INTEGER"),
            ("rounds", "session_id", "INTEGER"),
        ):
            if col not in _columns(conn, table):
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))

        conn.executescript(INDEXES)
        if version < SCHEMA_VERSION:
            conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)


def _rebuild_rounds(conn):
    """Copy the rounds table onto the current schema, dropping the dead column."""
    conn.execute("DROP TABLE IF EXISTS rounds_old")
    conn.execute("ALTER TABLE rounds RENAME TO rounds_old")
    conn.executescript(ROUNDS_TABLE)
    conn.execute("INSERT INTO rounds (id, account_id, session_id, at, wagered, net, bankroll) "
                 "SELECT id, account_id, NULL, at, wagered, net, bankroll FROM rounds_old")
    conn.execute("DROP TABLE rounds_old")


def _migrate_v1_to_v2(conn):
    """Rebuild the accounts table, carrying the old money across as chips."""
    conn.execute("DROP TABLE IF EXISTS accounts_v1")   # leftover from a failed run
    old = conn.execute("SELECT * FROM accounts").fetchall()
    conn.execute("ALTER TABLE accounts RENAME TO accounts_v1")
    conn.executescript(ACCOUNTS_TABLE)
    now = time.time()
    for r in old:
        keys = r.keys()
        chips = float(r["bankroll"]) if "bankroll" in keys else 0.0
        granted = float(r["deposited"]) if "deposited" in keys else chips
        conn.execute(
            "INSERT INTO accounts (id, name, created, last_seen, chips, granted, "
            "earned, sessions_run, config) VALUES (?,?,?,?,?,?,0,?,?)",
            (r["id"], r["name"], r["created"], now, chips, granted,
             int(r["buy_ins"]) if "buy_ins" in keys else 1,
             r["config"] if "config" in keys else "{}"))
        # one ledger line so the history is not silently empty
        conn.execute(
            "INSERT INTO ledger (account_id, at, kind, amount, balance, note) "
            "VALUES (?,?,?,?,?,?)",
            (r["id"], r["created"], "grant", granted, chips,
             "Carried over from before sessions existed"))
    conn.execute("DROP TABLE accounts_v1")


# ---------------- accounts ----------------

def list_accounts():
    with connect() as conn:
        rows = conn.execute("""
            SELECT a.*,
                   (SELECT COUNT(*) FROM decisions d WHERE d.account_id = a.id) AS decisions,
                   (SELECT COUNT(*) FROM decisions d WHERE d.account_id = a.id AND d.correct = 1) AS correct,
                   (SELECT COUNT(*) FROM sessions s WHERE s.account_id = a.id) AS sessions,
                   (SELECT SUM(hands) FROM sessions s WHERE s.account_id = a.id) AS hands
            FROM accounts a ORDER BY a.last_seen DESC, a.created DESC
        """).fetchall()
    return [{
        "id": r["id"], "name": r["name"],
        "chips": round(r["chips"], 2),
        "lifetime": round(r["chips"] - r["granted"] - r["earned"], 2),
        "sessions": r["sessions"] or 0,
        "hands": r["hands"] or 0,
        "accuracy": round(r["correct"] / r["decisions"] * 100) if r["decisions"] else None,
    } for r in rows]


def create_account(name):
    """A new account starts with nothing. The first session is where money appears."""
    name = (name or "Player").strip()[:32] or "Player"
    now = time.time()
    with connect() as conn:
        base, n = name, 1
        while conn.execute("SELECT 1 FROM accounts WHERE name = ?", (name,)).fetchone():
            n += 1
            name = "%s %d" % (base, n)
        cur = conn.execute(
            "INSERT INTO accounts (name, created, last_seen, chips, granted, earned, "
            "sessions_run, config) VALUES (?,?,?,0,0,0,0,'{}')", (name, now, now))
        return cur.lastrowid


def get_account(account_id):
    with connect() as conn:
        r = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "name": r["name"], "created": r["created"],
            "last_seen": r["last_seen"], "chips": r["chips"],
            "granted": r["granted"], "earned": r["earned"],
            "sessions_run": r["sessions_run"],
            "config": json.loads(r["config"] or "{}")}


def touch(account_id):
    with connect() as conn:
        conn.execute("UPDATE accounts SET last_seen = ? WHERE id = ?",
                     (time.time(), account_id))


def save_config(account_id, config):
    with connect() as conn:
        conn.execute("UPDATE accounts SET config = ? WHERE id = ?",
                     (json.dumps(config), account_id))


def rename_account(account_id, name):
    name = (name or "").strip()[:32]
    if not name:
        return False
    with connect() as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE name = ? AND id != ?",
                        (name, account_id)).fetchone():
            return False
        conn.execute("UPDATE accounts SET name = ? WHERE id = ?", (name, account_id))
    return True


def delete_account(account_id):
    with connect() as conn:
        for t in ("decisions", "bets", "rounds", "ledger", "quizzes", "sessions"):
            conn.execute("DELETE FROM %s WHERE account_id = ?" % t, (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


# ---------------- chips ----------------

def move_chips(conn, account_id, amount, kind, note="", ref=None):
    """
    Change the chip stack and write the movement down, in one place.

    Every route in and out of the money goes through here, which is the only
    reason the ledger can be trusted to add up.
    """
    row = conn.execute("SELECT chips, granted, earned FROM accounts WHERE id = ?",
                       (account_id,)).fetchone()
    balance = round(float(row["chips"]) + float(amount), 2)
    granted = float(row["granted"]) + (amount if kind == "grant" else 0.0)
    earned = float(row["earned"]) + (amount if kind == "quiz" else 0.0)
    conn.execute("UPDATE accounts SET chips = ?, granted = ?, earned = ? WHERE id = ?",
                 (balance, round(granted, 2), round(earned, 2), account_id))
    conn.execute("INSERT INTO ledger (account_id, at, kind, amount, balance, note, ref) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (account_id, time.time(), kind, round(float(amount), 2), balance,
                  note, ref))
    return balance


def grant_chips(account_id, amount, note, kind="grant", ref=None):
    with connect() as conn:
        return move_chips(conn, account_id, amount, kind, note, ref)


def ledger(account_id, limit=200):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ledger WHERE account_id = ? ORDER BY id DESC LIMIT ?",
            (account_id, limit)).fetchall()
    return [{"at": r["at"], "kind": r["kind"], "amount": r["amount"],
             "balance": r["balance"], "note": r["note"], "ref": r["ref"]} for r in rows]


# ---------------- sessions ----------------

def open_session(account_id, buy_in, config):
    """Take the buy-in out of the chip stack and start a session with it."""
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM sessions WHERE account_id = ?",
                         (account_id,)).fetchone()["c"] + 1
        cur = conn.execute(
            "INSERT INTO sessions (account_id, number, started, buy_in, peak, trough, config) "
            "VALUES (?,?,?,?,?,?,?)",
            (account_id, n, time.time(), buy_in, buy_in, buy_in, json.dumps(config)))
        session_id = cur.lastrowid
        move_chips(conn, account_id, -buy_in, "buyin",
                   "Bought in to session %d" % n, session_id)
        conn.execute("UPDATE accounts SET sessions_run = sessions_run + 1 WHERE id = ?",
                     (account_id,))
        return {"id": session_id, "number": n, "buy_in": buy_in}


def update_session(session_id, stats):
    if not session_id:
        return
    with connect() as conn:
        conn.execute("""
            UPDATE sessions SET hands=?, rounds=?, decisions=?, correct=?, wagered=?,
                   net=?, peak=?, trough=?, blackjacks=?, busts=?, best_streak=?, ev_lost=?
            WHERE id = ?""",
            (stats["hands"], stats["rounds"], stats["decisions"], stats["correct"],
             round(stats["wagered"], 2), round(stats["net"], 2),
             round(stats["peak"], 2), round(stats["trough"], 2),
             stats["blackjacks"], stats["busts"], stats["best_streak"],
             round(stats["ev_lost"], 4), session_id))


def close_session(account_id, session_id, cash_out, stats, busted=False):
    """Stand up: whatever is left on the table goes back into the chip stack."""
    with connect() as conn:
        conn.execute("""
            UPDATE sessions SET ended=?, cash_out=?, busted=?, hands=?, rounds=?,
                   decisions=?, correct=?, wagered=?, net=?, peak=?, trough=?,
                   blackjacks=?, busts=?, best_streak=?, ev_lost=?
            WHERE id = ? AND account_id = ?""",
            (time.time(), round(cash_out, 2), int(bool(busted)),
             stats["hands"], stats["rounds"], stats["decisions"], stats["correct"],
             round(stats["wagered"], 2), round(stats["net"], 2),
             round(stats["peak"], 2), round(stats["trough"], 2),
             stats["blackjacks"], stats["busts"], stats["best_streak"],
             round(stats["ev_lost"], 4), session_id, account_id))
        row = conn.execute("SELECT number FROM sessions WHERE id = ?",
                           (session_id,)).fetchone()
        number = row["number"] if row else "?"
        if cash_out > 0:
            move_chips(conn, account_id, cash_out, "cashout",
                       "Cashed out of session %s" % number, session_id)
        else:
            conn.execute(
                "INSERT INTO ledger (account_id, at, kind, amount, balance, note, ref) "
                "VALUES (?,?,?,?,?,?,?)",
                (account_id, time.time(), "cashout", 0.0,
                 conn.execute("SELECT chips FROM accounts WHERE id = ?",
                              (account_id,)).fetchone()["chips"],
                 "Session %s ended with nothing left" % number, session_id))


def open_session_row(account_id):
    """A session that was started and never closed — the server restarting, usually."""
    with connect() as conn:
        r = conn.execute(
            "SELECT * FROM sessions WHERE account_id = ? AND ended IS NULL "
            "ORDER BY id DESC LIMIT 1", (account_id,)).fetchone()
    return dict(r) if r else None


def sessions(account_id, limit=60):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE account_id = ? ORDER BY number DESC LIMIT ?",
            (account_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["config"] = json.loads(d.get("config") or "{}")
        d["accuracy"] = (r["correct"] / r["decisions"]) if r["decisions"] else None
        d["live"] = r["ended"] is None
        out.append(d)
    return out


# ---------------- logging ----------------

def log_decision(account_id, session_id, cell, chose, should, correct, ev_correct,
                 cost, true_count, source="play"):
    with connect() as conn:
        conn.execute(
            "INSERT INTO decisions (account_id, session_id, at, cell, chose, should, "
            "correct, ev_correct, cost, true_count, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (account_id, session_id, time.time(), cell, chose, should, int(correct),
             int(ev_correct), float(cost), float(true_count), source))


def log_bet(account_id, session_id, check):
    with connect() as conn:
        conn.execute(
            "INSERT INTO bets (account_id, session_id, at, amount, suggested, sound, "
            "flags, true_count) VALUES (?,?,?,?,?,?,?,?)",
            (account_id, session_id, time.time(), check["amount"], check["suggested"],
             int(check["ok"]),
             json.dumps([f["key"] for f in check["flags"] if f["level"] != "info"]),
             check["true_count"]))


def log_round(account_id, session_id, wagered, net, bankroll):
    with connect() as conn:
        conn.execute(
            "INSERT INTO rounds (account_id, session_id, at, wagered, net, bankroll) "
            "VALUES (?,?,?,?,?,?)",
            (account_id, session_id, time.time(), wagered, net, bankroll))


# ---------------- quizzes ----------------

def start_quiz(account_id, mode, config, questions, for_chips):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO quizzes (account_id, at, mode, config, length, for_chips, questions) "
            "VALUES (?,?,?,?,?,?,?)",
            (account_id, time.time(), mode, json.dumps(config), len(questions),
             int(bool(for_chips)), json.dumps(questions)))
        return cur.lastrowid


def get_quiz(account_id, quiz_id):
    with connect() as conn:
        r = conn.execute("SELECT * FROM quizzes WHERE id = ? AND account_id = ?",
                         (quiz_id, account_id)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["questions"] = json.loads(d["questions"] or "[]")
    d["config"] = json.loads(d["config"] or "{}")
    return d


def save_quiz(quiz_id, questions, answered, correct):
    with connect() as conn:
        conn.execute(
            "UPDATE quizzes SET questions = ?, answered = ?, correct = ? WHERE id = ?",
            (json.dumps(questions), answered, correct, quiz_id))


def finish_quiz(account_id, quiz_id, correct, chips_earned):
    with connect() as conn:
        row = conn.execute("SELECT length FROM quizzes WHERE id = ? AND account_id = ?",
                           (quiz_id, account_id)).fetchone()
        asked = row["length"] if row else correct
        conn.execute("UPDATE quizzes SET finished = ?, correct = ?, chips_earned = ? "
                     "WHERE id = ? AND account_id = ?",
                     (time.time(), correct, chips_earned, quiz_id, account_id))
        if chips_earned > 0:
            return move_chips(conn, account_id, chips_earned, "quiz",
                              "Won %d of %d questions" % (correct, asked), quiz_id)
        r = conn.execute("SELECT chips FROM accounts WHERE id = ?",
                         (account_id,)).fetchone()
        return r["chips"] if r else 0.0


def quiz_history(account_id, limit=40):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, at, finished, mode, length, answered, correct, chips_earned, "
            "for_chips FROM quizzes WHERE account_id = ? ORDER BY id DESC LIMIT ?",
            (account_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ---------------- reading it back ----------------

def decision_rows(account_id, limit=6000):
    """Every decision, oldest first, which is the order mastery.py wants them in."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT cell, chose, should, correct, cost, at, source FROM decisions "
            "WHERE account_id = ? ORDER BY id DESC LIMIT ?", (account_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def recent_misses(account_id, limit=40):
    """Distinct cells you have got wrong lately, most recent first."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT cell, MAX(at) last_at, COUNT(*) n FROM decisions
            WHERE account_id = ? AND correct = 0
            GROUP BY cell ORDER BY last_at DESC LIMIT ?""",
            (account_id, limit)).fetchall()
    return [{"cell": r["cell"], "last_at": r["last_at"], "misses": r["n"]} for r in rows]


def money_curve(account_id, limit=400):
    """Chip balance over time, straight from the ledger."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT at, balance, kind FROM ledger WHERE account_id = ? "
            "ORDER BY id DESC LIMIT ?", (account_id, limit)).fetchall()
    return [{"at": r["at"], "balance": r["balance"], "kind": r["kind"]}
            for r in reversed(rows)]


def totals(account_id):
    """The all-time accounting. Everything here is a sum of recorded rows."""
    acct = get_account(account_id)
    if not acct:
        return None
    with connect() as conn:
        d = conn.execute("""
            SELECT COUNT(*) n, SUM(correct) c, SUM(ev_correct) e, SUM(cost) cost
            FROM decisions WHERE account_id = ?""", (account_id,)).fetchone()
        b = conn.execute(
            "SELECT COUNT(*) n, SUM(sound) s FROM bets WHERE account_id = ?",
            (account_id,)).fetchone()
        s = conn.execute("""
            SELECT COUNT(*) n, SUM(hands) hands, SUM(rounds) rounds, SUM(wagered) wagered,
                   SUM(net) net, SUM(buy_in) bought, SUM(busted) busted,
                   MAX(net) best, MIN(net) worst, MAX(peak) high
            FROM sessions WHERE account_id = ?""", (account_id,)).fetchone()
        closed = conn.execute(
            "SELECT COUNT(*) n FROM sessions WHERE account_id = ? AND ended IS NOT NULL",
            (account_id,)).fetchone()["n"]
        q = conn.execute("""
            SELECT COUNT(*) n, SUM(answered) answered, SUM(correct) correct,
                   SUM(chips_earned) earned
            FROM quizzes WHERE account_id = ?""", (account_id,)).fetchone()
        flags = conn.execute(
            "SELECT flags FROM bets WHERE account_id = ? AND sound = 0",
            (account_id,)).fetchall()

    flag_counts = {}
    for row in flags:
        for k in json.loads(row["flags"] or "[]"):
            flag_counts[k] = flag_counts.get(k, 0) + 1

    return {
        "chips": round(acct["chips"], 2),
        "granted": round(acct["granted"], 2),
        "earned": round(acct["earned"], 2),
        "put_in": round(acct["granted"] + acct["earned"], 2),
        "lifetime": round(acct["chips"] - acct["granted"] - acct["earned"], 2),
        "sessions": s["n"] or 0,
        "sessions_closed": closed,
        "sessions_live": (s["n"] or 0) - closed,
        "busted_out": s["busted"] or 0,
        "hands": s["hands"] or 0,
        "rounds": s["rounds"] or 0,
        "wagered": round(s["wagered"] or 0.0, 2),
        "table_net": round(s["net"] or 0.0, 2),
        "bought_in": round(s["bought"] or 0.0, 2),
        "best_session": round(s["best"], 2) if s["best"] is not None else None,
        "worst_session": round(s["worst"], 2) if s["worst"] is not None else None,
        "high_water": round(s["high"], 2) if s["high"] is not None else None,
        "return_per_dollar": ((s["net"] or 0.0) / s["wagered"]) if s["wagered"] else None,
        "decisions": d["n"] or 0,
        "correct": d["c"] or 0,
        "accuracy": (d["c"] / d["n"]) if d["n"] else None,
        "shoe_accuracy": (d["e"] / d["n"]) if d["n"] else None,
        "ev_given_up": round(d["cost"] or 0.0, 3),
        "bets": b["n"] or 0,
        "bet_accuracy": (b["s"] / b["n"]) if b["n"] else None,
        "bet_flags": flag_counts,
        "quizzes": q["n"] or 0,
        "quiz_answered": q["answered"] or 0,
        "quiz_correct": q["correct"] or 0,
        "quiz_chips": round(q["earned"] or 0.0, 2),
    }
