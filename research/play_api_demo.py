"""Play one real session through the running trainer's HTTP API.

Usage: python3 server.py --no-browser   (in another terminal)
       python3 research/play_api_demo.py [repo-path] [http://localhost:8000]

$300 buy-in, $15 flat bets, basic strategy from engine.chart_play, up to 100 hands.
Prints the bankroll after every hand so you can see where the peak was.
"""
import json
import sys
import urllib.request

import os
REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
sys.path.insert(0, REPO)
import engine as E  # noqa: E402
import rules as R   # noqa: E402


def post(route, data):
    req = urllib.request.Request(BASE + route, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


acct = post("/api/accounts", {"name": "Claude stop-solver demo"})["id"]
# first sit-down must pick one of the grant sizes; grant 500, stand up, re-sit with exactly 300
post("/api/session/start", {"account": acct, "buy_in": 500})
post("/api/session/end", {"account": acct})
p = post("/api/session/start", {"account": acct, "buy_in": 300})
rset = R.normalise(p.get("config") or {})
print("session opened, bankroll $%.2f, table min $%d, rules %s" % (
    p["bankroll"], p["config"]["table_min"],
    {k: rset[k] for k in ("decks", "hit_soft_17", "das", "blackjack_pays")}))

start = p["bankroll"]
peak, peak_hand = 0.0, 0
log = []
for hand in range(1, 101):
    p = post("/api/bet", {"account": acct, "amount": 15})
    if "error" in p:
        print("hand %d: %s" % (hand, p["error"]))
        break
    while p["phase"] == "insurance":
        p = post("/api/insurance", {"account": acct, "take": False})
    while p["phase"] == "play":
        h = p["hands"][p["active"]]
        play = E.chart_play(h["cards"], p["dealer"]["showing"],
                            p["can_double"], p["can_split"], rset)
        p = post("/api/action", {"account": acct, "move": play["move"]})
    net = p["bankroll"] - start
    desc = " | ".join("%s=%d%s" % ("".join(c["rank"] for c in hh["cards"]), hh["total"],
                                   " " + str(hh["result"]) if hh.get("result") else "")
                      for hh in p["hands"])
    dealer = "".join(c["rank"] for c in p["dealer"]["cards"])
    log.append((hand, net))
    if net > peak:
        peak, peak_hand = net, hand
    print("hand %3d  you %-28s dealer %-6s=%-3s  bankroll $%7.2f  (%+.2f)" % (
        hand, desc, dealer, p["dealer"]["total"], p["bankroll"], net))
    if p.get("broke") or p.get("out_of_money"):
        print("out of money after hand", hand)
        break
    p = post("/api/next", {"account": acct})

closed = post("/api/session/end", {"account": acct})["closed"]
print()
print("closed: hands=%d cash_out=$%.2f net=%+.2f accuracy=%s" % (
    closed["hands"], closed["cash_out"], closed["net"],
    "%.0f%%" % (100 * closed["accuracy"]) if closed["accuracy"] is not None else "n/a"))
print("hindsight best stop: after hand %d at %+.2f" % (peak_hand, peak))
