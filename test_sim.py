"""
test_sim.py — the fast table deals the same game as the careful one.

sim.py exists to play millions of hands quickly, and everything on the Analysis
tab is built on it: the equity curves, the bust rates, the bankroll advice. It
is also the one file nothing else checks closely — validate.py compares its
house edge to a published figure, but at the tolerance it uses that comparison
cannot fail. So this re-derives the numbers rather than trusting them.

It deals a few million hands and takes about a minute.

    python3 test_sim.py
"""

import collections
import math
import random

import engine as E
import rules as R
import sim as S

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %-60s %s%s" % (name, "ok" if cond else "FAIL", ("  " + detail) if detail else ""))


def full_shoe(decks=6):
    return [{"rank": r, "suit": s, "red": red}
            for _ in range(decks) for s, red in E.SUITS for r in E.RANKS]


def edge_of(rules, decks=6, hands=2000000, seed=777, ramp=None):
    """Mean result per hand, in units. Same seed means the same shuffles."""
    rng = random.Random(seed)
    s = S.Sim(rules, decks, 0.75, rng)
    tot = sq = 0.0
    for _ in range(hands):
        if s.cut_card():
            s.shuffle()
        u = S._units_for(ramp, s.true_count()) if ramp else 1
        r = s.round(1.0 * u)
        tot += r
        sq += r * r
    n = float(hands)
    return tot / n, math.sqrt(sq / n - (tot / n) ** 2)


# ---------------------------------------------------------------------------

def test_the_shoe():
    print("\nthe shoe is a shoe")
    d = S._deck_values(1)
    check("52 cards to a deck", len(d) == 52, str(len(d)))
    check("sixteen ten-value cards", d.count(10) == 16)
    check("four aces", d.count(11) == 4)
    check("four of each of 2 through 9",
          all(d.count(v) == 4 for v in range(2, 10)))
    check("six decks is six times that", len(S._deck_values(6)) == 312)
    check("Hi-Lo over a whole deck comes to zero",
          sum(S._HILO[v] for v in d) == 0, str(sum(S._HILO[v] for v in d)))
    check("2-6 count plus one", all(S._HILO[v] == 1 for v in range(2, 7)))
    check("7-9 count nothing", all(S._HILO[v] == 0 for v in range(7, 10)))
    check("tens and aces count minus one", S._HILO[10] == -1 and S._HILO[11] == -1)


def test_totals():
    print("\ntotalling a hand")
    for cards, want in (([11, 6], (17, True)), ([11, 6, 5], (12, False)),
                        ([11, 11], (12, True)), ([11, 11, 9], (21, True)),
                        ([10, 6], (16, False)), ([10, 6, 8], (24, False)),
                        ([11, 10], (21, True)), ([11, 11, 11], (13, True))):
        got = S._total(cards)
        check("%-16s -> %s" % (cards, want), got == want, str(got))


def test_chart_lookup_is_total():
    """A missed lookup silently stands, so no lookup may ever miss."""
    print("\nevery hand the table can deal has a square on the chart")
    chart = S._flat_chart(R.DEFAULT_RULES)
    missing = []
    for up in R.UPCARDS:
        missing += [("hard", r, up) for r in range(5, 22) if ("hard", r, up) not in chart]
        missing += [("soft", r, up) for r in range(2, 10) if ("soft", r, up) not in chart]
        missing += [("pair", r, up) for r in range(2, 12) if ("pair", r, up) not in chart]
    check("no key decide() can build is missing", not missing, str(missing[:4]))
    check("the chart is the whole grid", len(chart) == len(R.cells_for(R.DEFAULT_RULES)))


def test_dealer_matches_the_exact_engine():
    print("\nthe dealer draws like the exact engine says it should")
    shoe = full_shoe()
    rng = random.Random(7)
    s = S.Sim(R.DEFAULT_RULES, 6, 0.75, rng)
    tally = {u: collections.Counter() for u in R.UPCARDS}
    for _ in range(400000):
        if s.cut_card():
            s.shuffle()
        d = [s.draw(), s.draw()]
        if S._total(d)[0] == 21:
            continue                       # the engine conditions on no blackjack
        while True:
            t, soft = S._total(d)
            if t < 17 or (t == 17 and soft and s.h17):
                d.append(s.draw())
            else:
                break
        t = S._total(d)[0]
        tally[d[0]]["bust" if t > 21 else str(t)] += 1

    worst = (0.0, None)
    for up in R.UPCARDS:
        c = tally[up]
        n = sum(c.values())
        exact = E.Odds(shoe, up).dealer()
        for k in ("17", "18", "19", "20", "21", "bust"):
            got, want = c[k] / n, exact.get(k, 0.0)
            z = abs(got - want) / math.sqrt(max(want * (1 - want), 1e-9) / n)
            if z > worst[0]:
                worst = (z, "up %s, %s: %.4f vs %.4f" % (up, k, got, want))
    check("every dealer outcome is within 5 sigma of exact", worst[0] < 5.0,
          "worst %.1f sigma (%s)" % worst)
    for up in R.UPCARDS:
        c = tally[up]
        n = sum(c.values())
        want = E.Odds(shoe, up).dealer_bust()
        check("  bust rate on a %-2s  %.3f (exact %.3f)" % (up, c["bust"] / n, want),
              abs(c["bust"] / n - want) < 0.012)


def test_the_house_edge():
    """
    The number every figure on the Analysis tab is scaled by.

    Pinned at 40 million hands across ten independent shoes: -0.4231% +/- 0.0365
    at two standard errors, against a published -0.43% for these rules.
    """
    print("\nthe house edge, flat-betting the chart")
    hands = 6000000
    e, sd = edge_of(R.DEFAULT_RULES, hands=hands, seed=20260919)
    se = sd / math.sqrt(hands)
    check("edge is within a tenth of a percent of -0.42%",
          abs(e - (-0.0042)) < 0.0010,
          "%+.4f%% (2 s.e. = %.4f)" % (100 * e, 200 * se))
    check("and the swing per hand is the 1.14 everything quotes",
          abs(sd - S.HAND_SD) < 0.05, "%.4f" % sd)


def test_rule_changes_cost_what_they_should():
    """Paired on identical shuffles, so the shoe cancels and the rule shows."""
    print("\nwhat each rule change costs, against published figures")
    hands, seed = 1500000, 4242
    base, _ = edge_of(R.DEFAULT_RULES, hands=hands, seed=seed)
    for label, rules, published in (
            ("6:5 blackjack", dict(R.DEFAULT_RULES, blackjack_pays=1.2), -0.0139),
            ("dealer hits soft 17", dict(R.DEFAULT_RULES, hit_soft_17=True), -0.0022),
            ("no double after split", dict(R.DEFAULT_RULES, das=False), -0.0014)):
        got, _ = edge_of(rules, hands=hands, seed=seed)
        d = got - base
        check("%-22s costs %+.3f%% (published %+.3f%%)" % (label, 100 * d, 100 * published),
              abs(d - published) < 0.0008)
    better, _ = edge_of(dict(R.DEFAULT_RULES, resplit_aces=True), hands=hands, seed=seed)
    check("re-splitting aces helps the player", better > base,
          "%+.4f%% vs %+.4f%%" % (100 * better, 100 * base))


def test_the_ramp_swing():
    """
    RAMP_SD is what the bankroll advice is built on. Spreading a bet raises the
    swing far faster than it raises the average bet, and using the flat figure
    for a spread bettor understates ruin badly.
    """
    print("\nthe swing of each bet ramp")
    for ramp, pinned in sorted(S.RAMP_SD.items()):
        _, sd = edge_of(R.DEFAULT_RULES, hands=500000, seed=2024, ramp=ramp)
        check("%-6s swings %.2f bets a hand (pinned %.2f)" % (ramp, sd, pinned),
              abs(sd - pinned) / pinned < 0.06)
    check("a steeper ramp always swings wider",
          S.RAMP_SD["flat"] < S.RAMP_SD["mild"] < S.RAMP_SD["steep"])
    check("and sd_for falls back to the flat figure on an unknown ramp",
          S.sd_for("nonsense") == S.HAND_SD)
    check("spreading the bet turns the game positive",
          edge_of(R.DEFAULT_RULES, hands=500000, seed=2024, ramp="steep")[0] > 0,
          "%+.4f units a hand" % edge_of(R.DEFAULT_RULES, hands=400000,
                                         seed=2024, ramp="steep")[0])


def test_ruin_formula():
    print("\nthe ruin formula against cases with a known answer")
    # driftless: the reflection principle gives exactly 2 * Phi(-a / (sd*sqrt(T)))
    for units, hands in ((20, 400), (50, 1000), (10, 100)):
        want = 2 * S._phi(-units / (S.HAND_SD * math.sqrt(hands)))
        got = S.ruin_within(units, hands, edge=0.0)
        check("fair game, %d units over %d hands: %.4f" % (units, hands, got),
              abs(got - want) < 1e-9)
    # a positive edge over a very long run tends to exp(-2*mu*a/sd^2)
    edge, units = 0.01, 40
    want = math.exp(-2 * edge * units / S.HAND_SD ** 2)
    got = S.ruin_within(units, 4000000, edge=edge)
    check("winning game, long run, tends to the classic formula",
          abs(got - want) < 0.002, "%.4f vs %.4f" % (got, want))
    check("no bankroll is certain ruin", S.ruin_within(0, 500) == 1.0)
    check("no hands is no risk", S.ruin_within(10, 0) == 0.0)
    check("more money is never more risk",
          all(S.ruin_within(u, 500) >= S.ruin_within(u + 5, 500) for u in range(1, 60, 5)))
    check("a wider swing is never less risk",
          all(S.ruin_within(30, 500, sd=a) <= S.ruin_within(30, 500, sd=a + 0.5)
              for a in (1.0, 1.5, 2.0, 3.0)))
    check("a better edge is never more risk",
          all(S.ruin_within(30, 500, edge=x) >= S.ruin_within(30, 500, edge=x + 0.002)
              for x in (-0.01, -0.005, 0.0, 0.005)))


def test_bankroll_for_inverts_it():
    print("\nthe bankroll calculator inverts its own formula")
    for target in (0.20, 0.10, 0.05, 0.01):
        a = S.bankroll_for(15, 500, target)
        got = S.ruin_within(a["units"], 500)
        check("%d%% ruin target lands on %d%% ruin" % (target * 100, round(got * 100)),
              abs(got - target) < 0.005, "%.1f units" % a["units"])
    check("a tighter target always needs more money",
          all(S.bankroll_for(15, 500, a)["units"] <= S.bankroll_for(15, 500, b)["units"]
              for a, b in ((0.20, 0.10), (0.10, 0.05), (0.05, 0.01))))
    check("a wider swing always needs more money",
          S.bankroll_for(15, 500, 0.05, -0.0042, 3.79)["units"]
          > S.bankroll_for(15, 500, 0.05, -0.0042, 1.15)["units"])


def test_survival_matches_what_gets_dealt():
    """
    The Analysis tab prints the formula next to the dealt sessions. Two methods
    on one question is only a check if they actually agree.
    """
    print("\nthe formula against sessions actually dealt")
    for ramp in ("flat", "mild", "steep"):
        m = S.run_many(runs=150, rules=R.DEFAULT_RULES, bankroll=1500, table_min=15,
                       hands=800, decks=6, penetration=0.75, ramp=ramp, seed=5150)
        row = S.survival_table(15, 1500, edge=m["edge_per_hand"], sd=m["sd_per_hand"],
                               marks=(800,))[0]
        dealt = 1.0 - m["bust_rate"]
        check("%-6s: formula %.0f%%, dealt %.0f%%" % (ramp, 100 * row["survive"], 100 * dealt),
              abs(row["survive"] - dealt) < 0.08)
        check("  and it used the swing it measured (%.2f)" % m["sd_per_hand"],
              abs(m["sd_per_hand"] - S.RAMP_SD[ramp]) / S.RAMP_SD[ramp] < 0.10)
    # the two edge figures are in different units and only one of them belongs
    # in the ruin formula
    m = S.run_many(runs=20, rules=R.DEFAULT_RULES, bankroll=1000, table_min=25,
                   hands=500, decks=6, penetration=0.75, ramp="steep", seed=11)
    check("drift per hand is the wagered edge times the average bet",
          abs(m["edge_per_hand"] / m["edge"] - 2.08) < 0.25,
          "%.2f units a hand" % (m["edge_per_hand"] / m["edge"]))
    flat = S.run_many(runs=20, rules=R.DEFAULT_RULES, bankroll=1000, table_min=25,
                      hands=500, decks=6, penetration=0.75, ramp="flat", seed=11)
    check("and flat betting makes the two the same",
          abs(flat["edge_per_hand"] / flat["edge"] - 1.0) < 0.02,
          "%.3f" % (flat["edge_per_hand"] / flat["edge"]))
    check("the flat figure alone would have been far too kind",
          S.survival_table(15, 1500, edge=0.011, sd=S.HAND_SD, marks=(800,))[0]["survive"]
          - S.survival_table(15, 1500, edge=0.011, sd=S.RAMP_SD["steep"], marks=(800,))[0]["survive"]
          > 0.2)


def test_run_plumbing():
    print("\nthe run reports what it did")
    m = S.run_many(runs=8, rules=R.DEFAULT_RULES, bankroll=2000, table_min=25,
                   hands=300, decks=6, penetration=0.75, seed=1)
    check("no raw moment fields leak into the payload",
          all("u_sum" not in s and "u_sq" not in s for s in m["sessions"]))
    check("a measured swing comes back", m["sd_per_hand"] > 0)
    check("every band is ordered lo <= mid <= hi",
          all(b["lo"] <= b["mid"] <= b["hi"] for b in m["bands"]))
    check("the histogram counts every session",
          sum(m["histogram"]["counts"]) == m["runs"])
    check("the same seed gives the same run",
          S.run_many(runs=4, rules=R.DEFAULT_RULES, bankroll=2000, table_min=25,
                     hands=200, decks=6, seed=3)["median_final"]
          == S.run_many(runs=4, rules=R.DEFAULT_RULES, bankroll=2000, table_min=25,
                        hands=200, decks=6, seed=3)["median_final"])
    broke = S.run_session(R.DEFAULT_RULES, bankroll=25, table_min=25, hands=500, seed=9)
    check("a session that cannot make the minimum stops and says so",
          broke["busted"] and broke["hands"] < 500, "%d hands" % broke["hands"])
    check("you can never lose more than you sat down with", broke["final"] >= 0)


if __name__ == "__main__":
    test_the_shoe()
    test_totals()
    test_chart_lookup_is_total()
    test_dealer_matches_the_exact_engine()
    test_the_house_edge()
    test_rule_changes_cost_what_they_should()
    test_the_ramp_swing()
    test_ruin_formula()
    test_bankroll_for_inverts_it()
    test_survival_matches_what_gets_dealt()
    test_run_plumbing()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        raise SystemExit(1)
