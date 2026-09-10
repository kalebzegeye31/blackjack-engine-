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
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import coach
import db
from game import Table

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
RELOAD_AMOUNT = 100.0     # what you get topped up with when you run out

# live tables, one per account, kept in memory
TABLES = {}
LOCK = threading.Lock()


def table_for(account_id):
    """Get the live table for an account, restoring bankroll and settings from disk."""
    if account_id not in TABLES:
        acct = db.get_account(account_id)
        if not acct:
            return None
        TABLES[account_id] = Table(config=acct["config"], bankroll=acct["bankroll"])
    return TABLES[account_id]


def persist(account_id, table):
    acct = db.get_account(account_id)
    db.save_account(account_id, table.bankroll, acct["deposited"], acct["buy_ins"], table.config)


def payload(account_id, table, extra=None):
    snap = table.snapshot()
    acct = db.get_account(account_id)
    snap["account"] = {"id": acct["id"], "name": acct["name"]}
    snap["deposited"] = acct["deposited"]
    snap["buy_ins"] = acct["buy_ins"]
    snap["lifetime"] = round(table.bankroll - acct["deposited"], 2)
    if snap.get("analysis"):
        snap["explanation"] = coach.explain(snap["analysis"])
    if extra:
        snap.update(extra)
    return snap


def finish_round(account_id, table):
    """Called once a round settles: write it down, and top up if they're broke."""
    result = table.round_result
    if not result:
        return None
    acct = db.get_account(account_id)
    wagered = sum(h["bet"] for h in table.hands)
    lifetime = table.bankroll - acct["deposited"]
    db.log_round(account_id, wagered, result["net"], table.bankroll, lifetime)

    reloaded = False
    deposited, buy_ins = acct["deposited"], acct["buy_ins"]
    if table.bankroll < table.config["table_min"]:
        table.bankroll += RELOAD_AMOUNT
        deposited += RELOAD_AMOUNT
        buy_ins += 1
        reloaded = True
    db.save_account(account_id, table.bankroll, deposited, buy_ins, table.config)
    return {"reloaded": reloaded, "reload_amount": RELOAD_AMOUNT if reloaded else 0}


class Handler(BaseHTTPRequestHandler):
    server_version = "BlackjackTrainer/1.0"

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

    # ---------- routing ----------
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

        if route == "/api/state":
            account_id = self.account_from(query=query)
            with LOCK:
                table = table_for(account_id)
                if not table:
                    return self.send_json({"error": "no such account"}, 404)
                return self.send_json(payload(account_id, table))

        if route == "/api/stats":
            account_id = self.account_from(query=query)
            s = db.stats(account_id)
            return self.send_json(s or {"error": "no such account"}, 200 if s else 404)

        return self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        route = urlparse(self.path).path
        data = self.body_json()

        if route == "/api/accounts":
            new_id = db.create_account(data.get("name"))
            return self.send_json({"id": new_id})

        if route == "/api/accounts/delete":
            account_id = self.account_from(data)
            TABLES.pop(account_id, None)
            db.delete_account(account_id)
            return self.send_json({"ok": True})

        account_id = self.account_from(data)
        with LOCK:
            table = table_for(account_id)
            if not table:
                return self.send_json({"error": "no such account"}, 404)

            if route == "/api/config":
                for key in ("decks", "others", "table_min", "penetration"):
                    if key in data:
                        table.config[key] = type(table.config[key])(data[key])
                table.shuffle()
                table.new_round()
                persist(account_id, table)
                return self.send_json(payload(account_id, table))

            if route == "/api/next":
                table.new_round()
                return self.send_json(payload(account_id, table))

            if route == "/api/bet":
                if table.phase != "bet":
                    return self.send_json(payload(account_id, table))
                last = data.get("last_bet")
                last_outcome = data.get("last_outcome")
                amount = float(data.get("amount") or table.config["table_min"])
                amount = max(table.config["table_min"], min(amount, table.bankroll))
                check = table.judge_bet(amount, last, last_outcome)
                table.bet = amount
                table.last_bet_check = check
                table.bankroll -= amount
                table.deal()
                db.log_bet(account_id, check)
                extra = finish_round(account_id, table) if table.phase == "settled" else None
                persist(account_id, table)
                return self.send_json(payload(account_id, table, extra))

            if route == "/api/insurance":
                if table.phase != "insurance":
                    return self.send_json(payload(account_id, table))
                analysis = table.insurance(bool(data.get("take")))
                db.log_decision(account_id, "insurance vs A",
                                "take" if analysis["took"] else "decline",
                                not analysis["took"], analysis["correct"],
                                0.0 if not analysis["took"] else max(0.0, -analysis["ev"]) / 2,
                                analysis["true_count"])
                extra = finish_round(account_id, table) if table.phase == "settled" else None
                persist(account_id, table)
                return self.send_json(payload(account_id, table, extra))

            if route == "/api/action":
                if table.phase != "play":
                    return self.send_json(payload(account_id, table))
                move = str(data.get("move", "")).upper()
                if move not in ("H", "S", "D", "P"):
                    return self.send_json({"error": "bad move"}, 400)
                hand = table.hands[table.active]
                if move == "D" and not table.can_double(hand):
                    return self.send_json({"error": "cannot double"}, 400)
                if move == "P" and not table.can_split(hand):
                    return self.send_json({"error": "cannot split"}, 400)

                analysis = table.act(move)
                cell = "%s vs %s" % (analysis["row"],
                                     "A" if analysis["up"] == 11 else analysis["up"])
                chosen = next((o for o in analysis["options"]
                               if o["move"] == move and o["legal"]), None)
                # credit "matched the shoe" when the pick is within rounding noise of best
                ev_ok = bool(chosen and analysis["best_ev"] - chosen["ev"] <= 0.002)
                db.log_decision(account_id, cell, move, analysis["correct"], ev_ok,
                                analysis["cost"], analysis["true_count"])
                extra = finish_round(account_id, table) if table.phase == "settled" else None
                persist(account_id, table)
                return self.send_json(payload(account_id, table, extra))

        return self.send_json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser(description="Blackjack basic strategy trainer")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    db.init()
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
