"""
validate.py — play the chart perfectly for a long time and see where the money lands.

Two engines deal blackjack in this project. game.py deals one careful hand at a
time and scores every decision; sim.py deals a quarter of a million hands a second
and scores nothing. They are separate code, so they can disagree — and if they do,
one of them is wrong about the rules.

So this checks three things, and the third is the one that matters:

  1. playing the chart through game.py scores 100% accurate, which it must by
     definition, or the grader and the chart have drifted apart
  2. the two engines agree on the house edge
  3. that shared figure matches the published one

Any real mistake in dealing, settlement, blackjack payouts, doubling, splitting,
insurance or the dealer's drawing rules shows up in the edge. It is a slow test
for a reason: the thing being measured is half a percent and the noise is over a
hundred times that on a single hand.

    python3 validate.py            # the usual run
    python3 validate.py --quick    # a tenth of the hands, for a fast check
"""

import math
import random
import sys
import time

import engine as E
import rules as R
import sim
from game import Table

QUICK = "--quick" in sys.argv
ROUNDS = 3000 if QUICK else 30000
SIM_HANDS = 200_000 if QUICK else 2_000_000

random.seed(11)
checks = []


def result(name, ok, detail=""):
    checks.append(ok)
    print("  %-42s %s   %s" % (name, "PASS" if ok else "FAIL", detail))


# ---------------------------------------------------------------------------
# 1. the real game, one careful hand at a time
# ---------------------------------------------------------------------------

config = {"decks": 6, "others": 2, "table_min": 15, "penetration": 0.75}
t = Table(config=config, bankroll=1e9)      # deep enough never to be forced out
rules = t.rules

wagered = 0.0
decisions = correct = shoe_match = 0
splits = doubles = insurances = 0
start_money = t.bankroll
start = time.time()

for _ in range(ROUNDS):
    t.new_round()
    t.place_bet(t.config["table_min"])
    if t.phase == "insurance":
        t.insurance(False)
        insurances += 1
        decisions += 1
        correct += 1
        shoe_match += 1
    guard = 0
    while t.phase == "play":
        hand = t.hands[t.active]
        play = E.chart_play(hand["cards"], E.card_value(t.dealer[0]["rank"]),
                            t.can_double(hand), t.can_split(hand), rules)
        if play["move"] == "D":
            doubles += 1
        if play["move"] == "P":
            splits += 1
        a = t.act(play["move"])
        decisions += 1
        correct += 1 if a["correct"] else 0
        chosen = next((o for o in a["options"] if o["move"] == play["move"] and o["legal"]), None)
        if chosen and a["best_ev"] - chosen["ev"] <= 0.002:
            shoe_match += 1
        guard += 1
        assert guard < 60, "a hand never finished"
    assert t.phase == "settled", "a round never settled"
    wagered += t.round_result["wagered"]

net = t.bankroll - start_money
game_edge = net / wagered * 100
elapsed = time.time() - start

# one standard error on the edge, in percent: the swing of one hand, spread over
# every dollar that crossed the table
se = E.HAND_SD * math.sqrt(ROUNDS) * t.config["table_min"] / wagered * 100

print("\nthe real game, played by the chart")
print("  %d rounds in %.1fs  (%d decisions, %d splits, %d doubles, %d insurance offers)"
      % (ROUNDS, elapsed, decisions, splits, doubles, insurances))
print("  total wagered     $%.0f" % wagered)
print("  house edge        %+.3f%%  +/- %.3f%% (one standard error)" % (game_edge, se))

result("chart accuracy is exactly 100%", correct == decisions,
       "%.1f%%" % (correct / decisions * 100))
print("  matched the live shoe as well as the chart: %.1f%%" % (shoe_match / decisions * 100))
result("splits and doubles actually happened", splits > 0 and doubles > 0,
       "%d splits, %d doubles" % (splits, doubles))

# ---------------------------------------------------------------------------
# 2. the fast engine, over far more hands
# ---------------------------------------------------------------------------

print("\nthe fast engine, same rules, %s hands" % format(SIM_HANDS, ","))
start = time.time()
chunk = 50_000
sim_net = sim_wagered = 0.0
for i in range(SIM_HANDS // chunk):
    s = sim.run_session(rules, bankroll=1e12, table_min=15, hands=chunk,
                        decks=6, penetration=0.75, seed=4000 + i)
    sim_net += s["net"]
    sim_wagered += s["wagered"]
sim_edge = sim_net / sim_wagered * 100
sim_se = sim.HAND_SD / math.sqrt(SIM_HANDS) * 100
print("  %s hands in %.1fs  (%s hands/sec)"
      % (format(SIM_HANDS, ","), time.time() - start,
         format(int(SIM_HANDS / max(0.001, time.time() - start)), ",")))
print("  house edge        %+.3f%%  +/- %.3f%%" % (sim_edge, sim_se))

gap = abs(game_edge - sim_edge)
combined = math.sqrt(se ** 2 + sim_se ** 2)
result("the two engines agree with each other", gap < 2.5 * combined,
       "%.3f%% apart, %.1f standard errors" % (gap, gap / combined))

# ---------------------------------------------------------------------------
# 3. and they agree with the published figure
# ---------------------------------------------------------------------------

PUBLISHED = -0.43        # 6 decks, stand on soft 17, double after split, 3:2
off = abs(sim_edge - PUBLISHED) / sim_se
print("\nagainst the published figure")
print("  published         %+.2f%%  for 6 decks, stand on soft 17, double after split, 3:2" % PUBLISHED)
result("the edge matches", off < 3.0, "%.1f standard errors away" % off)

# ---------------------------------------------------------------------------
# 4. each rule change costs what it is supposed to cost
#
# Measured in pairs: the same seeds, so the same shuffles, played under both rule
# sets. Almost all the variance is the shoe rather than the rules, and dealing
# both hands from the same shoe cancels it. Without this, telling a 0.14% rule
# apart from noise would take tens of millions of hands.
# ---------------------------------------------------------------------------

def edge_for(rset, seed, hands):
    s = sim.run_session(rset, bankroll=1e12, table_min=15, hands=hands,
                        decks=rset["decks"], penetration=0.75, seed=seed)
    return s["net"] / s["wagered"] * 100


print("\nwhat each rule is worth, measured on matched shoes")
# The 6:5 figure is often quoted as 1.39%, but it is exactly computable and the
# round number is wrong: with 6 decks you are dealt a natural 4.749% of the time,
# the dealer matches it 4.562% of those (a push, paid nothing either way), and the
# rest are paid 0.3 of a bet short. 0.04749 x (1 - 0.04562) x 0.3 = 1.3597%.
VARIANTS = [
    ("dealer hits soft 17", {"hit_soft_17": True}, -0.22),
    ("no double after split", {"das": False}, -0.14),
    ("blackjack pays 6:5", {"blackjack_pays": 1.2}, -1.36),
    ("single deck", {"decks": 1}, +0.48),
]
PAIRS = 12 if QUICK else 24
PAIR_HANDS = 20_000 if QUICK else 40_000
base_rules = R.normalise(dict(R.DEFAULT_RULES))

for name, change, expected in VARIANTS:
    rset = R.normalise(dict(R.DEFAULT_RULES, **change))
    deltas = []
    for i in range(PAIRS):
        seed = 31_000 + i * 104_729
        deltas.append(edge_for(rset, seed, PAIR_HANDS) - edge_for(base_rules, seed, PAIR_HANDS))
    mean = sum(deltas) / len(deltas)
    var = sum((d - mean) ** 2 for d in deltas) / max(1, len(deltas) - 1)
    err = math.sqrt(var / len(deltas))
    # matched shoes can measure this more precisely than the published figures are
    # quoted, so allow the rounding of a two-decimal reference as well as the noise
    off = abs(mean - expected) / max(err, 1e-9)
    ok = abs(mean - expected) < max(3.0 * err, 0.02)
    checks.append(ok)
    print("  %-24s %+.3f%% +/- %.3f%%   (published %+.2f%%)  %.1f SE  %s"
          % (name, mean, err, expected, off, "ok" if ok else "MISMATCH"))
print("  (the single-deck row still plays the six-deck chart, so it understates the gain "
      "a single-deck chart would give)")

print("\n%s" % ("ALL CHECKS PASS" if all(checks) else "%d FAILURES" % checks.count(False)))
raise SystemExit(0 if all(checks) else 1)
