#!/usr/bin/env python3
"""
server.py — run this.

    python3 server.py

Then open http://localhost:8000 in a browser. No pip install, no internet,
no accounts anywhere but the SQLite file sitting next to this script.

Standard library only, so it works on any Python 3.8+.
"""

import argparse
import json
import mimetypes
import os
import random
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import coach
import db
import mastery as M
import quiz as Q
import rules as R
import sim
from game import Table

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

BUY_IN_CHOICES = [100, 250, 500, 1000]
MAX_SIM_WORK = 400_000          # runs x hands, so nobody can hang the server

# live tables, one per account, kept in memory only while a session is open
TABLES = {}
LOCK = threading.Lock()


class Live:
    """One open session: the table it is being played on, and its database row."""

    def __init__(self, table, session_id, number):
        self.table = table
        self.session_id = session_id
        self.number = number
        self.last_bet = None
        self.last_outcome = None


def live_for(account_id):
    return TABLES.get(account_id)


def reconcile(account_id):
    """
    Close a session the server was restarted in the middle of.

    The table itself only ever lived in memory, so it is gone. What survives is
    the session row, which carries the buy-in and the running net — enough to
    hand the right amount of money back rather than quietly lose or invent it.
    """
    row = db.open_session_row(account_id)
    if not row or account_id in TABLES:
        return
    left = max(0.0, round(row["buy_in"] + row["net"], 2))
    stats = {k: row[k] for k in ("hands", "rounds", "decisions", "correct", "wagered",
                                 "net", "peak", "trough", "blackjacks", "busts",
                                 "best_streak", "ev_lost")}
    db.close_session(account_id, row["id"], left, stats, busted=left <= 0)


# ---------------------------------------------------------------------------
# What the browser gets
# ---------------------------------------------------------------------------

def account_block(account_id):
    acct = db.get_account(account_id)
    if not acct:
        return None
    return {
        "id": acct["id"], "name": acct["name"], "created": acct["created"],
        "chips": round(acct["chips"], 2),
        "granted": round(acct["granted"], 2),
        "earned": round(acct["earned"], 2),
        "sessions_run": acct["sessions_run"],
        "first_time": acct["sessions_run"] == 0,
        "config": acct["config"],
    }


def payload(account_id, extra=None):
    """
    The whole state of the world for the Table tab.

    With no session open this is deliberately thin: the account, the settings,
    and enough for the browser to draw the sit-down screen.
    """
    acct = account_block(account_id)
    live = live_for(account_id)
    out = {"account": acct, "buy_in_choices": BUY_IN_CHOICES}

    if not live:
        cfg = dict(Table(config=acct["config"]).config)
        out.update({"phase": "idle", "session": None, "config": cfg,
                    "rules": R.normalise(cfg),
                    "all_time": all_time_marks(account_id),
                    "can_sit": acct["first_time"] or acct["chips"] >= cfg["table_min"],
                    "min_buy_in": cfg["table_min"]})
        return dict(out, **(extra or {}))

    snap = live.table.snapshot()
    snap.update(out)
    snap["session"] = dict(snap["session"], id=live.session_id, number=live.number)
    snap["all_time"] = all_time_marks(account_id)
    if snap.get("analysis"):
        snap["explanation"] = coach.explain(snap["analysis"])
    if extra:
        snap.update(extra)
    return snap


def all_time_marks(account_id):
    """
    The handful of records the Table tab shows next to this session.

    Lifetime counts the money still sitting in front of you on the table. Leaving
    it out would show every open session as a total loss until you stood up.
    """
    t = db.totals(account_id) or {}
    live = live_for(account_id)
    on_table = live.table.bankroll if live else 0.0
    worth = t.get("chips", 0.0) + on_table
    return {
        "sessions": t.get("sessions", 0),
        "hands": t.get("hands", 0),
        "best_session": t.get("best_session"),
        "worst_session": t.get("worst_session"),
        "high_water": t.get("high_water"),
        "lifetime": round(worth - t.get("put_in", 0.0), 2),
        "accuracy": t.get("accuracy"),
        "worth": round(worth, 2),
        "chips": t.get("chips", 0.0),
        "on_table": round(on_table, 2),
    }


def profile_for(account_id, rules=None):
    return M.Profile(rules).feed(db.decision_rows(account_id))


def full_stats(account_id):
    """Everything the Account and Analysis tabs read."""
    acct = db.get_account(account_id)
    if not acct:
        return None
    cfg = dict(Table(config=acct["config"]).config)
    rset = R.normalise(cfg)
    prof = profile_for(account_id, rset)
    totals = db.totals(account_id)
    live = live_for(account_id)

    on_table = live.table.bankroll if live else 0.0
    return {
        "account": account_block(account_id),
        "config": cfg,
        "rules": rset,
        "totals": dict(totals,
                       lifetime=round(totals["chips"] + on_table - totals["put_in"], 2)),
        "worth": round(totals["chips"] + on_table, 2),
        "on_table": round(on_table, 2),
        "sessions": db.sessions(account_id),
        "ledger": db.ledger(account_id, 120),
        "money_curve": db.money_curve(account_id),
        "quizzes": db.quiz_history(account_id, 20),
        "skill": {
            "accuracy": prof.accuracy,
            "sharpness": prof.sharpness,
            "weighted": prof.weighted,
            "confidence": prof.confidence,
            "band": M.band(prof.sharpness),
            "decisions": prof.total,
            "ramp": M.RAMP,
            "trend": prof.trend(),
            "coverage": prof.coverage(),
            "by_section": prof.by_section(),
            "by_upcard": prof.by_upcard(),
            "cost_per_hand": M.expected_cost_per_hand(prof, rset),
        },
        "drill": prof.drill(14),
        "leaks": prof.leaks(),
        "misses": db.recent_misses(account_id, 20),
    }


# ---------------------------------------------------------------------------
# The quiz, which needs the server to hold the answers
# ---------------------------------------------------------------------------

def start_quiz(account_id, data):
    acct = db.get_account(account_id)
    cfg = dict(Table(config=acct["config"]).config)
    rset = R.normalise(cfg)
    mode = str(data.get("mode") or "weak")
    if mode not in Q.MODES:
        mode = "weak"
    for_chips = mode == "chips"
    length = Q.CHIPS_QUESTIONS if for_chips else max(5, min(30, int(data.get("length") or 10)))

    prof = profile_for(account_id, rset)
    missed = [m["cell"] for m in db.recent_misses(account_id, 40)]
    rng = random.Random()
    cells = Q.select_cells(mode, length, rset, prof, data.get("filters"), rng, missed)
    questions = [Q.build(s, r, u, rset, rng, i) for i, (s, r, u) in enumerate(cells)]
    if not questions:
        return {"error": "nothing to ask about"}

    quiz_id = db.start_quiz(account_id, mode, data.get("filters") or {}, questions, for_chips)
    title, blurb = Q.describe(mode)
    return {
        "quiz": quiz_id, "mode": mode, "title": title, "blurb": blurb,
        "length": len(questions), "for_chips": for_chips,
        "reward": Q.CHIPS_PER_CORRECT if for_chips else 0,
        "index": 0, "answered": 0, "correct": 0,
        "question": Q.public(questions[0]),
        "legal": Q.legal_moves(questions[0]),
    }


def answer_quiz(account_id, data):
    quiz_id = int(data.get("quiz") or 0)
    row = db.get_quiz(account_id, quiz_id)
    if not row:
        return {"error": "no such quiz"}
    if row["finished"]:
        return {"error": "that quiz is already over"}

    questions = row["questions"]
    idx = row["answered"]
    if idx >= len(questions):
        return {"error": "no question waiting"}

    acct = db.get_account(account_id)
    cfg = dict(Table(config=acct["config"]).config)
    rset = R.normalise(cfg)
    question = questions[idx]
    move = str(data.get("move", "")).upper()
    if move not in Q.legal_moves(question):
        return {"error": "that is not one of the options"}

    result = Q.grade(question, move, rset, cfg["decks"])
    question["chose"] = move
    question["correct"] = bool(result["correct"])
    question["cost"] = result["cost"]

    answered = idx + 1
    correct = row["correct"] + (1 if result["correct"] else 0)
    db.save_quiz(quiz_id, questions, answered, correct)
    # quiz answers count towards how well you know the chart, same as real hands
    db.log_decision(account_id, None, question["cell"], move, result["answer"],
                    result["correct"], result["correct"], result["cost"], 0.0,
                    source="quiz")

    out = {
        "quiz": quiz_id, "mode": row["mode"], "length": len(questions),
        "answered": answered, "correct": correct,
        "for_chips": bool(row["for_chips"]),
        "reward": Q.CHIPS_PER_CORRECT if row["for_chips"] else 0,
        "result": result,
    }
    if answered < len(questions):
        nxt = questions[answered]
        out["question"] = Q.public(nxt)
        out["legal"] = Q.legal_moves(nxt)
        out["index"] = answered
    else:
        earned = correct * Q.CHIPS_PER_CORRECT if row["for_chips"] else 0.0
        balance = db.finish_quiz(account_id, quiz_id, correct, earned)
        out["done"] = True
        out["earned"] = earned
        out["chips"] = round(balance, 2)
        out["review"] = [{"cell": q["cell"], "chose": q.get("chose"),
                          "answer": q["answer"], "correct": q.get("correct"),
                          "cost": q.get("cost", 0)} for q in questions]
    return out


# ---------------------------------------------------------------------------
# Simulation, with a ceiling on how much work one request can ask for
# ---------------------------------------------------------------------------

def run_simulation(account_id, data):
    acct = db.get_account(account_id)
    base = dict(Table(config=acct["config"]).config)

    def num(key, default, lo, hi):
        try:
            return max(lo, min(hi, type(default)(data.get(key, default))))
        except (TypeError, ValueError):
            return default

    runs = num("runs", 20, 1, 100)
    hands = num("hands", 500, 20, 20000)
    if runs * hands > MAX_SIM_WORK:
        runs = max(1, MAX_SIM_WORK // hands)

    table_min = num("table_min", int(base["table_min"]), 1, 10000)
    bankroll = num("bankroll", float(table_min * 40), float(table_min), 1e7)
    decks = num("decks", int(base["decks"]), 1, 8)
    penetration = num("penetration", float(base["penetration"]), 0.05, 0.95)
    ramp = str(data.get("ramp") or "flat")
    if ramp not in sim.RAMPS:
        ramp = "flat"

    rset = R.normalise({
        "hit_soft_17": data.get("hit_soft_17", base["hit_soft_17"]),
        "das": data.get("das", base["das"]),
        "blackjack_pays": data.get("blackjack_pays", base["blackjack_pays"]),
        "resplit_aces": base["resplit_aces"],
        "max_hands": base["max_hands"],
        "decks": decks,
    })

    # "play like me" replays your own error rate, cell by cell
    skill = str(data.get("skill") or "perfect")
    error_rate, miss_rates = 0.0, None
    if skill == "mine":
        prof = profile_for(account_id, rset)
        miss_rates = {}
        for cell in prof.cells.values():
            if cell.section and cell.n:
                miss_rates[(cell.section, cell.row, cell.up)] = 1.0 - cell.mastery
        error_rate = 1.0 - (prof.accuracy or 1.0)
    elif skill == "custom":
        error_rate = num("error_rate", 0.05, 0.0, 0.5)

    out = sim.run_many(
        runs=runs, rules=rset, bankroll=bankroll, table_min=table_min, hands=hands,
        decks=decks, penetration=penetration, ramp=ramp,
        error_rate=error_rate, miss_rates=miss_rates,
        table_max=int(base.get("table_max") or table_min * 100))
    out["settings"] = {
        "runs": runs, "hands": hands, "table_min": table_min, "bankroll": bankroll,
        "decks": decks, "penetration": penetration, "ramp": ramp, "skill": skill,
        "error_rate": round(error_rate, 4), "rules": rset,
    }
    out["theory"] = sim.survival_table(table_min, bankroll, edge=out["edge"] or -0.005)
    return out


def run_calculator(account_id, data):
    acct = db.get_account(account_id)
    base = dict(Table(config=acct["config"]).config)

    def num(key, default, lo, hi):
        try:
            return max(lo, min(hi, type(default)(data.get(key, default))))
        except (TypeError, ValueError):
            return default

    table_min = num("table_min", int(base["table_min"]), 1, 10000)
    hands = num("hands", 500, 10, 100000)
    risk = num("ruin_target", 0.05, 0.005, 0.5)
    edge = num("edge", -0.005, -0.05, 0.02)

    answer = sim.bankroll_for(table_min, hands, risk, edge)
    answer["alternatives"] = [
        dict(sim.bankroll_for(table_min, hands, r, edge), ruin_target=r)
        for r in (0.20, 0.10, 0.05, 0.01)
    ]
    answer["by_hands"] = [
        {"hands": h, "bankroll": sim.bankroll_for(table_min, h, risk, edge)["bankroll"]}
        for h in (100, 200, 400, 800, 1600, 3200)
    ]
    return answer


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

ROUTE_NAME = re.compile(r"^/api/([a-z]+(?:/[a-z]+)?)$")


def route(no_lock=False):
    """Mark a method as reachable from the network. Nothing else is."""
    def wrap(fn):
        fn.is_route = True
        fn.no_lock = no_lock
        return fn
    return wrap


class Handler(BaseHTTPRequestHandler):
    server_version = "BlackjackTrainer/2.0"

    # ---------- plumbing ----------
    def log_message(self, fmt, *args):
        if os.environ.get("BJ_VERBOSE"):
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not os.path.isfile(path):
            self.send_json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def account_from(self, data=None, query=None):
        raw = (data or {}).get("account") or (query or {}).get("account", [None])[0]
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    # ---------- GET ----------
    def do_GET(self):
        url = urlparse(self.path)
        route, query = url.path, parse_qs(url.query)

        if route == "/":
            return self.send_file(os.path.join(STATIC, "index.html"))
        if route.startswith("/static/"):
            safe = os.path.normpath(route[len("/static/"):]).lstrip("./\\")
            return self.send_file(os.path.join(STATIC, safe))

        if route == "/api/glossary":
            return self.send_json({"terms": coach.GLOSSARY})
        if route == "/api/accounts":
            return self.send_json({"accounts": db.list_accounts()})

        account_id = self.account_from(query=query)
        if not db.get_account(account_id):
            return self.send_json({"error": "no such account"}, 404)

        if route == "/api/state":
            with LOCK:
                reconcile(account_id)
                db.touch(account_id)
                return self.send_json(payload(account_id))

        if route == "/api/stats":
            with LOCK:
                return self.send_json(full_stats(account_id))

        if route == "/api/chart":
            with LOCK:
                acct = db.get_account(account_id)
                cfg = dict(Table(config=acct["config"]).config)
                rset = R.normalise(cfg)
                prof = profile_for(account_id, rset)
                g = R.grid(rset)
                return self.send_json({
                    "rules": rset,
                    "upcards": R.UPCARDS,
                    "grid": {section: {str(row): g[section][row] for row in g[section]}
                             for section in ("hard", "soft", "pair")},
                    "heatmap": prof.heatmap(),
                })

        return self.send_json({"error": "not found"}, 404)

    # ---------- POST ----------
    def do_POST(self):
        route = urlparse(self.path).path
        data = self.body_json()

        if route == "/api/accounts":
            return self.send_json({"id": db.create_account(data.get("name"))})

        account_id = self.account_from(data)
        if not db.get_account(account_id):
            return self.send_json({"error": "no such account"}, 404)

        if route == "/api/accounts/delete":
            TABLES.pop(account_id, None)
            db.delete_account(account_id)
            return self.send_json({"ok": True})

        if route == "/api/accounts/rename":
            ok = db.rename_account(account_id, data.get("name"))
            return self.send_json({"ok": ok, "account": account_block(account_id)})

        name = ROUTE_NAME.match(route)
        handler = getattr(self, "post_" + name.group(1).replace("/", "_"), None) if name else None
        if not callable(handler) or not getattr(handler, "is_route", False):
            return self.send_json({"error": "not found"}, 404)

        # the simulator can churn for a second or two and touches no live table,
        # so it must not sit on the lock the rest of the app needs to deal a card
        if getattr(handler, "no_lock", False):
            return handler(account_id, data)
        with LOCK:
            return handler(account_id, data)

    # ---------- sitting down and standing up ----------
    @route()
    def post_session_start(self, account_id, data):
        if live_for(account_id):
            return self.send_json(payload(account_id))
        reconcile(account_id)
        acct = db.get_account(account_id)
        cfg = dict(Table(config=acct["config"]).config)

        try:
            buy_in = round(float(data.get("buy_in") or 0), 2)
        except (TypeError, ValueError):
            buy_in = 0.0

        first_time = acct["sessions_run"] == 0
        if first_time and buy_in not in BUY_IN_CHOICES:
            buy_in = float(BUY_IN_CHOICES[0])

        if buy_in < cfg["table_min"]:
            return self.send_json({"error": "A buy-in has to cover at least one bet of $%d."
                                   % cfg["table_min"]}, 400)
        if first_time:
            # the one free ride: pick what you want to be carrying, and it appears
            db.grant_chips(account_id, buy_in, "Starting chips, first session")
            acct = db.get_account(account_id)
        if buy_in > acct["chips"] + 0.001:
            return self.send_json({"error": "You only have $%.2f in chips. Win more on "
                                   "the Quiz tab." % acct["chips"]}, 400)

        row = db.open_session(account_id, buy_in, cfg)
        TABLES[account_id] = Live(Table(config=cfg, bankroll=buy_in),
                                  row["id"], row["number"])
        db.touch(account_id)
        return self.send_json(payload(account_id, {"opened": row}))

    @route()
    def post_session_end(self, account_id, data):
        live = live_for(account_id)
        if not live:
            return self.send_json(payload(account_id))
        if live.table.phase not in ("bet", "settled"):
            return self.send_json({"error": "Finish the hand you are in first."}, 400)

        table = live.table
        cash = round(max(0.0, table.bankroll), 2)
        db.close_session(account_id, live.session_id, cash, table.session,
                         busted=table.broke())
        TABLES.pop(account_id, None)
        return self.send_json(payload(account_id, {"closed": {
            "number": live.number, "cash_out": cash,
            "net": round(table.session["net"], 2),
            "hands": table.session["hands"],
            "accuracy": (table.session["correct"] / table.session["decisions"])
                        if table.session["decisions"] else None,
        }}))

    @route()
    def post_config(self, account_id, data):
        """Table settings. Changing them mid-session would rewrite the game you are in."""
        if live_for(account_id):
            return self.send_json({"error": "Stand up from the table before changing "
                                   "the rules."}, 400)
        acct = db.get_account(account_id)
        cfg = dict(acct["config"])
        for key in ("decks", "others", "table_min", "table_max", "penetration",
                    "hit_soft_17", "das", "resplit_aces", "max_hands", "blackjack_pays"):
            if key in data:
                cfg[key] = data[key]
        clean = dict(Table(config=cfg).config)     # one place decides what is legal
        db.save_config(account_id, clean)
        return self.send_json(payload(account_id))

    # ---------- playing ----------
    def _need_table(self, account_id):
        live = live_for(account_id)
        if not live:
            self.send_json({"error": "no session"}, 409)
            return None
        return live

    @route()
    def post_next(self, account_id, data):
        live = self._need_table(account_id)
        if not live:
            return
        live.table.new_round()
        return self.send_json(payload(account_id))

    @route()
    def post_bet(self, account_id, data):
        live = self._need_table(account_id)
        if not live:
            return
        table = live.table
        if table.phase != "bet":
            return self.send_json(payload(account_id))
        if table.broke():
            return self.send_json({"error": "You are below the table minimum. "
                                   "Stand up and buy in again."}, 400)

        check = table.place_bet(data.get("amount"), live.last_bet, live.last_outcome)
        live.last_bet = check["amount"]
        db.log_bet(account_id, live.session_id, check)
        extra = self.finish_round(account_id, live) if table.phase == "settled" else None
        return self.send_json(payload(account_id, extra))

    @route()
    def post_insurance(self, account_id, data):
        live = self._need_table(account_id)
        if not live:
            return
        table = live.table
        if table.phase != "insurance":
            return self.send_json(payload(account_id))
        a = table.insurance(bool(data.get("take")))
        db.log_decision(account_id, live.session_id, "insurance vs A",
                        "take" if a["took"] else "decline", "decline",
                        not a["took"], a["correct"],
                        0.0 if not a["took"] else max(0.0, -a["ev"]) / 2,
                        a["true_count"])
        extra = self.finish_round(account_id, live) if table.phase == "settled" else None
        return self.send_json(payload(account_id, extra))

    @route()
    def post_action(self, account_id, data):
        live = self._need_table(account_id)
        if not live:
            return
        table = live.table
        if table.phase != "play":
            return self.send_json(payload(account_id))
        move = str(data.get("move", "")).upper()
        if move not in ("H", "S", "D", "P"):
            return self.send_json({"error": "bad move"}, 400)
        hand = table.hands[table.active]
        if move == "H" and not table.can_hit(hand):
            return self.send_json({"error": "a split ace gets one card only"}, 400)
        if move == "D" and not table.can_double(hand):
            return self.send_json({"error": "cannot double"}, 400)
        if move == "P" and not table.can_split(hand):
            return self.send_json({"error": "cannot split"}, 400)

        a = table.act(move)
        chosen = next((o for o in a["options"] if o["move"] == move and o["legal"]), None)
        # credit "matched the shoe" when the pick is within rounding noise of best
        ev_ok = bool(chosen and a["best_ev"] - chosen["ev"] <= 0.002)
        db.log_decision(account_id, live.session_id, a["cell"], move, a["chart_move"],
                        a["correct"], ev_ok, a["cost"], a["true_count"])
        extra = self.finish_round(account_id, live) if table.phase == "settled" else None
        return self.send_json(payload(account_id, extra))

    def finish_round(self, account_id, live):
        """A round settled: write it down. No more silent top-ups when you run dry."""
        table = live.table
        result = table.round_result
        if not result:
            return None
        live.last_outcome = result["outcome"]
        db.log_round(account_id, live.session_id, result["wagered"], result["net"],
                     table.bankroll)
        db.update_session(live.session_id, table.session)
        return {"out_of_money": table.broke()}

    # ---------- quiz ----------
    @route()
    def post_quiz_start(self, account_id, data):
        out = start_quiz(account_id, data)
        return self.send_json(out, 400 if out.get("error") else 200)

    @route()
    def post_quiz_answer(self, account_id, data):
        out = answer_quiz(account_id, data)
        return self.send_json(out, 400 if out.get("error") else 200)

    # ---------- analysis ----------
    @route(no_lock=True)
    def post_simulate(self, account_id, data):
        return self.send_json(run_simulation(account_id, data))

    @route(no_lock=True)
    def post_calculator(self, account_id, data):
        return self.send_json(run_calculator(account_id, data))


def main():
    ap = argparse.ArgumentParser(description="Blackjack basic strategy trainer")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    db.init()
    for acct in db.list_accounts():
        reconcile(acct["id"])

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = "http://%s:%d" % ("localhost" if args.host == "127.0.0.1" else args.host, args.port)
    print("\n  Blackjack trainer running at  %s" % url)
    print("  Data stored in                %s" % db.DB_PATH)
    print("  Stop with Ctrl-C\n")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")


if __name__ == "__main__":
    main()
