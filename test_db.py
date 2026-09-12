"""
test_db.py — the money adds up, and an old file survives the upgrade.

The migration is the part worth testing properly. A database that opens without
complaining but then refuses the first write is worse than one that fails loudly,
so this builds a version-1 file by hand, upgrades it, and then actually plays
hands through every logging path on the result.

    python3 test_db.py
"""

import os
import sqlite3
import tempfile
import time

import db
import engine as E
from game import Table

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %-58s %s%s" % (name, "ok" if cond else "FAIL", ("  " + detail) if detail else ""))


def temp_db():
    db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
    return db.DB_PATH


def columns(table):
    """connect() is a context manager, so borrow one properly."""
    with db.connect() as conn:
        return db._columns(conn, table)


def row(sql, args=()):
    with db.connect() as conn:
        return tuple(conn.execute(sql, args).fetchone())


def open_handles():
    """
    How many file descriptors this process is holding.

    /dev/fd on macOS, /proc/self/fd on Linux. Both list one entry per open
    descriptor, which is all this needs.
    """
    path = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
    try:
        return len(os.listdir(path))
    except OSError:
        return None


V1_SCHEMA = """
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created REAL NOT NULL,
    bankroll REAL NOT NULL DEFAULT 100, deposited REAL NOT NULL DEFAULT 100,
    buy_ins INTEGER NOT NULL DEFAULT 1, config TEXT NOT NULL DEFAULT '{}');
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, at REAL NOT NULL,
    cell TEXT NOT NULL, chose TEXT NOT NULL, correct INTEGER NOT NULL,
    ev_correct INTEGER NOT NULL, cost REAL NOT NULL, true_count REAL NOT NULL);
CREATE TABLE bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, at REAL NOT NULL,
    amount REAL NOT NULL, suggested REAL NOT NULL, sound INTEGER NOT NULL,
    flags TEXT NOT NULL DEFAULT '[]', true_count REAL NOT NULL);
CREATE TABLE rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, at REAL NOT NULL,
    wagered REAL NOT NULL, net REAL NOT NULL, bankroll REAL NOT NULL, lifetime REAL NOT NULL);
"""


def build_v1(path):
    """A version-1 file with a bit of history in it, exactly as the old code left them."""
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    now = time.time()
    conn.execute("INSERT INTO accounts (name, created, bankroll, deposited, buy_ins, config) "
                 "VALUES ('Old Hand', ?, 122.5, 200, 2, '{\"decks\": 6}')", (now,))
    for i in range(30):
        conn.execute("INSERT INTO decisions (account_id, at, cell, chose, correct, ev_correct, "
                     "cost, true_count) VALUES (1,?,?,?,?,?,?,0)",
                     (now + i, "hard 16 vs 10", "H", i % 3 != 0, 1, 0.01))
        conn.execute("INSERT INTO rounds (account_id, at, wagered, net, bankroll, lifetime) "
                     "VALUES (1,?,15,-15,?,?)", (now + i, 100 - i, -i))
        conn.execute("INSERT INTO bets (account_id, at, amount, suggested, sound, flags, "
                     "true_count) VALUES (1,?,15,15,1,'[]',0)", (now + i,))
    conn.commit()
    conn.close()


print("\nupgrading a version 1 file")

path = temp_db()
build_v1(path)
db.init()

cols = columns("accounts")
check("the account grows chips, grants and earnings",
      {"chips", "granted", "earned", "sessions_run"} <= cols)
check("and loses the single bankroll it used to carry", "bankroll" not in cols)
check("the dead lifetime column is gone from rounds",
      "lifetime" not in columns("rounds"))
check("rounds gains a session to belong to", "session_id" in columns("rounds"))
check("decisions gains what the chart wanted and where it came from",
      {"should", "source", "session_id"} <= columns("decisions"))

kept = row("SELECT (SELECT COUNT(*) FROM decisions), (SELECT COUNT(*) FROM rounds), "
           "(SELECT COUNT(*) FROM bets)")
check("every row of history survives", kept == (30, 30, 30), str(kept))

acct = db.get_account(1)
check("the old bankroll becomes chips", acct["chips"] == 122.5)
check("the old deposits become chips you were given", acct["granted"] == 200.0)
check("and a ledger line explains where they came from",
      len(db.ledger(1)) == 1 and db.ledger(1)[0]["kind"] == "grant")
check("so the all-time figure carries over", db.totals(1)["lifetime"] == -77.5,
      str(db.totals(1)["lifetime"]))

db.init()
check("running the upgrade twice changes nothing",
      db.get_account(1)["chips"] == 122.5 and
      row("SELECT COUNT(*) FROM decisions")[0] == 30)

print("\nplaying real hands through the upgraded file")

session = db.open_session(1, 100, {"table_min": 15})
t = Table(config={"others": 0, "table_min": 15}, bankroll=100.0)
rounds = 0
for _ in range(25):
    t.new_round()
    if t.broke():
        break
    t.place_bet(15)
    if t.phase == "insurance":
        t.insurance(False)
    guard = 0
    while t.phase == "play":
        hand = t.hands[t.active]
        play = E.chart_play(hand["cards"], E.card_value(t.dealer[0]["rank"]),
                            t.can_double(hand), t.can_split(hand), t.rules)
        a = t.act(play["move"])
        db.log_decision(1, session["id"], a["cell"], play["move"], a["chart_move"],
                        a["correct"], True, a["cost"], a["true_count"])
        guard += 1
        assert guard < 40
    db.log_bet(1, session["id"], t.last_bet_check)
    db.log_round(1, session["id"], t.round_result["wagered"], t.round_result["net"], t.bankroll)
    db.update_session(session["id"], t.session)
    rounds += 1
check("every logging path writes without complaint", rounds >= 1, "%d rounds" % rounds)

db.close_session(1, session["id"], t.bankroll, t.session)
check("standing up returns the table money to the chips",
      abs(db.get_account(1)["chips"] - (22.5 + t.bankroll)) < 0.01,
      str(db.get_account(1)["chips"]))

print("\nthe chip ledger is self-consistent")

path = temp_db()
db.init()
acct = db.create_account("Fresh")
check("a new account starts with nothing", db.get_account(acct)["chips"] == 0.0)
check("and cannot show a profit it has not made", db.totals(acct)["lifetime"] == 0.0)

db.grant_chips(acct, 500, "Starting chips")
s1 = db.open_session(acct, 300, {})
check("buying in moves chips onto the table", db.get_account(acct)["chips"] == 200.0)
stats = {"hands": 40, "rounds": 38, "decisions": 45, "correct": 40, "wagered": 600,
         "net": 60, "peak": 380, "trough": 250, "blackjacks": 2, "busts": 9,
         "best_streak": 4, "ev_lost": 0.3}
db.close_session(acct, s1["id"], 360, stats)
check("cashing out brings it back", db.get_account(acct)["chips"] == 560.0)
check("a winning session shows as profit", db.totals(acct)["lifetime"] == 60.0)

db.finish_quiz(acct, db.start_quiz(acct, "chips", {}, [{"a": 1}], True), 7, 70)
check("quiz winnings are chips", db.get_account(acct)["chips"] == 630.0)
check("but they are not profit — they were given, not won at the table",
      db.totals(acct)["lifetime"] == 60.0, str(db.totals(acct)["lifetime"]))

rows = db.ledger(acct)
check("every movement is on the ledger", len(rows) == 4,
      " ".join(r["kind"] for r in rows))
check("and each line's balance is the running total",
      rows[0]["balance"] == db.get_account(acct)["chips"])
moved = sum(r["amount"] for r in rows)
check("the ledger sums to the chips actually held",
      abs(moved - db.get_account(acct)["chips"]) < 0.01, "%.2f" % moved)

s2 = db.open_session(acct, 100, {})
check("a busted session returns nothing", True)
db.close_session(acct, s2["id"], 0, dict(stats, net=-100), busted=True)
check("and is recorded as busted", db.totals(acct)["busted_out"] == 1)
check("chips reflect the loss", db.get_account(acct)["chips"] == 530.0,
      str(db.get_account(acct)["chips"]))

print("\nconnections are handed back")

# The point of connect() being a context manager. Every call site uses `with`,
# which on a raw sqlite3 connection only opens a transaction -- it commits and
# leaves the connection open. In WAL mode each leaked connection pins three file
# handles, and a few dozen hands was enough to exhaust the process limit and take
# the server down with "unable to open database file".
path = temp_db()
db.init()
acct = db.create_account("Busy")
db.grant_chips(acct, 1000, "chips")
session = db.open_session(acct, 500, {})

before = open_handles()
for i in range(300):
    db.log_decision(acct, session["id"], "hard 16 vs 10", "H", "H", 1, 1, 0.0, 0.0)
    db.log_round(acct, session["id"], 15, -15, 500 - i)
    db.get_account(acct)
    db.totals(acct)
    db.decision_rows(acct, 50)
after = open_handles()
check("1500 database operations leak no file handles",
      before is None or after <= before + 2, "%s -> %s" % (before, after))

# and a failure inside the block must not leave one behind either
before = open_handles()
for _ in range(50):
    try:
        with db.connect() as conn:
            conn.execute("INSERT INTO accounts (name, created) VALUES ('Busy', 0)")
    except sqlite3.IntegrityError:
        pass
after = open_handles()
check("nor does an operation that raises", before is None or after <= before + 2,
      "%s -> %s" % (before, after))
check("and the failed write rolled back",
      row("SELECT COUNT(*) FROM accounts WHERE name = 'Busy'")[0] == 1)

print("\ndeleting an account takes everything with it")
db.delete_account(acct)
left = row("SELECT (SELECT COUNT(*) FROM sessions WHERE account_id=?), "
           "(SELECT COUNT(*) FROM ledger WHERE account_id=?), "
           "(SELECT COUNT(*) FROM quizzes WHERE account_id=?)", (acct, acct, acct))
check("no rows are left behind", left == (0, 0, 0), str(left))

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    raise SystemExit(1)
