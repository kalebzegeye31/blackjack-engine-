"""
test_count.py — the counting is right, and the index numbers are not made up.

The important test here is the last one. Every index number in count.py is
re-derived from engine.py by dealing real shoes, so the table cannot quietly
drift away from the maths it claims to be based on.

    python3 test_count.py
"""

import collections
import random

import count as C
import engine as E
import rules as R

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %-58s %s%s" % (name, "ok" if cond else "FAIL", ("  " + detail) if detail else ""))


# ---------------------------------------------------------------------------

def test_tags():
    print("\nthe Hi-Lo tags")
    check("2 through 6 are +1", all(C.tag(v) == 1 for v in range(2, 7)))
    check("7, 8 and 9 are 0", all(C.tag(v) == 0 for v in (7, 8, 9)))
    check("tens and aces are -1", C.tag(10) == -1 and C.tag(11) == -1)
    total = sum(C.tag(E.card_value(r)) * 4 for r in E.RANKS)
    check("a full deck counts to zero", total == 0, "sum %+d" % total)


def test_true_count():
    print("\nrunning count into true count")
    check("+6 with three decks left is +2", C.true_count(6, 3) == 2)
    check("+6 with one deck left is +6", C.true_count(6, 1) == 6)
    check("negative counts divide too", C.true_count(-4, 2) == -2)
    check("no decks left does not explode", C.true_count(5, 0) == 0.0)
    check("decks left rounds to quarters", C.decks_left(130) == 2.5, str(C.decks_left(130)))
    check("and never reports less than a quarter", C.decks_left(2) == 0.25)


def test_lookup():
    print("\nfinding the index play for a hand")
    check("16 v 10 is on the list", C.lookup("hard", 16, None, 10) is not None)
    check("16 v 7 is not", C.lookup("hard", 16, None, 7) is None)
    check("soft hands never are", C.lookup("soft", 18, None, 3) is None)
    p = C.lookup("pair", 20, 10, 5, can_split=True)
    check("a splittable pair of tens v 5 is", p is not None and p["key"] == "pTTv5")
    check("the same pair is not, if you cannot split",
          C.lookup("pair", 20, 10, 5, can_split=False) is None)
    fives = C.lookup("pair", 10, 5, 10, can_split=True)
    check("a pair of 5s is looked up as a hard 10",
          fives is not None and fives["key"] == "h10v10")


def test_moves():
    print("\nwhat the count says to do")
    m, e, dev = C.correct_move("H", "hard", 16, None, 10, tc=1.0)
    check("16 v 10 stands at +1", m == "S" and dev)
    m, e, dev = C.correct_move("H", "hard", 16, None, 10, tc=-1.0)
    check("and hits at -1", m == "H" and not dev)
    m, e, dev = C.correct_move("H", "hard", 16, None, 10, tc=0.0)
    check("the index is inclusive: +0 already stands", m == "S" and dev)

    m, e, dev = C.correct_move("S", "hard", 13, None, 2, tc=-3.0)
    check("13 v 2 is a negative index, so -3 hits", m == "H" and dev)
    m, e, dev = C.correct_move("S", "hard", 13, None, 2, tc=0.0)
    check("and 0 still stands", m == "S" and not dev)

    m, e, dev = C.correct_move("H", "hard", 11, None, 11, tc=5.0, can_double=False)
    check("an index that wants a double you cannot make is not a play",
          m == "H" and not dev)
    m, e, dev = C.correct_move("H", "hard", 11, None, 11, tc=5.0, can_double=True)
    check("but it is when you can", m == "D" and dev)

    m, e, dev = C.correct_move("S", "hard", 19, None, 6, tc=8.0)
    check("a hand with no index is left alone at any count", m == "S" and not dev)

    take, p = C.insurance_play(3.0)
    check("insurance goes on at +3", take and p["index"] == 3)
    check("and stays off at +2.9", not C.insurance_play(2.9)[0])


def test_agrees_with_the_chart():
    """
    Each index has two sides, and one of them has to be what basic strategy
    already says. If neither is, the index table has drifted away from rules.py
    and the app would be marking a player wrong for playing the chart correctly.
    """
    print("\nevery index still lines up with the chart in rules.py")
    rules = R.normalise({})          # 6 decks, S17, DAS: the table these were derived for
    bad = []
    for p in C.ILLUSTRIOUS_18:
        if p["key"] == "insurance":
            continue
        if p["kind"] == "pair":
            section, row = "pair", p["pair"]
        else:
            section, row = "hard", p["total"]
        code = R.chart_move(rules, section, row, p["up"])
        chart = R.resolve(code, True)[0]      # as played when doubling is allowed
        sides = {p["at_or_above"], p["below"]}
        ok = chart in sides
        if not ok:
            bad.append("%s: chart says %s, index offers %s" % (p["key"], chart, sorted(sides)))
        check("%-12s chart move %-2s is one of its two sides" % (p["key"], chart), ok)
    check("no index contradicts basic strategy on both sides", not bad,
          "; ".join(bad))


def test_ramp():
    print("\nthe bet ramp")
    check("no edge means one unit", C.bet_units(-3) == 1 and C.bet_units(0) == 1)
    check("+1 is still one unit", C.bet_units(1) == 1)
    check("+3 is about three", C.bet_units(3) == 3)
    check("the spread caps it", C.bet_units(20, spread=8) == 8)
    check("a bet one unit off the ramp is not nagged about",
          C.judge_ramp(3, 3.0)["level"] == "ok")
    check("flat betting a high count is flagged",
          C.judge_ramp(1, 6.0)["level"] == "warn")
    check("so is overbetting a dead count",
          C.judge_ramp(8, 0.0)["level"] == "warn")


def test_deck_estimates():
    print("\njudging the discard tray")
    e = C.grade_estimate(3.0, 3.0, 6)
    check("a spot-on estimate passes", e["ok"] and e["tc_off"] == 0)
    check("and gives the true count it implies", e["tc_said"] == 2.0)
    check("half a deck out is still fine", C.grade_estimate(2.5, 3.0, 6)["ok"])
    check("and so is half a deck the other way", C.grade_estimate(3.5, 3.0, 6)["ok"])
    bad = C.grade_estimate(2.0, 4.0, 8)
    check("two decks out does not pass", not bad["ok"])
    check("and it reports the true count it would have produced",
          bad["tc_said"] == 4.0 and bad["tc_actual"] == 2.0, "said +4.0 vs real +2.0")
    check("the error is signed", bad["off"] == -2.0)
    check("a nonsense estimate does not crash",
          C.grade_estimate("half", 3.0, 6)["ok"] is False)
    check("nor does nothing at all", C.grade_estimate(None, 3.0, 6)["ok"] is False)
    check("zero decks is floored rather than dividing by zero",
          C.grade_estimate(0, 1.0, 4)["tc_said"] == 16.0)

    print("\n  the point of it: a perfect count divided by a bad estimate")
    # Running count +6 is correct. The shoe really has 3 decks left, so the true
    # count is +2 and 12 v 2 is a hit. Misjudge the tray as one deck and you
    # believe it is +6, which stands. The arithmetic was never wrong.
    e = C.grade_estimate(1.0, 3.0, 6)
    tc_real, tc_thought = e["tc_actual"], e["tc_said"]
    move_real = C.correct_move("H", "hard", 12, None, 2, tc_real)[0]
    move_thought = C.correct_move("H", "hard", 12, None, 2, tc_thought)[0]
    check("a right count and a wrong tray misplays 12 v 2",
          move_real == "H" and move_thought == "S",
          "real %+.1f -> %s, believed %+.1f -> %s" % (tc_real, move_real, tc_thought, move_thought))
    check("and the estimate is marked as the thing that failed", not e["ok"])


def test_grading():
    print("\ngrading a count you were asked for")
    check("right is right", C.grade_count(5, 5)["ok"])
    check("close is still wrong", not C.grade_count(4, 5)["ok"])
    check("and it says by how much", C.grade_count(4, 5)["off"] == -1)
    check("a negative count reads back correctly", C.grade_count(-3, -3)["ok"])
    check("nonsense does not crash", C.grade_count("banana", 3)["ok"] is False)
    check("nor does nothing at all", C.grade_count(None, 3)["ok"] is False)


# ---------------------------------------------------------------------------
# The one that matters: derive every index from the engine and check the table.
# ---------------------------------------------------------------------------

def test_indices_against_the_engine(shoes=1200, tolerance=1.0):
    print("\nevery index number, re-derived from engine.py")
    print("  dealing %d shoes to find where each decision actually flips..." % shoes)

    random.seed(11)
    base = [r for _ in range(6) for _s in E.SUITS for r in E.RANKS]
    buckets = collections.defaultdict(lambda: [0.0] * 12)
    hits = collections.Counter()

    for _ in range(shoes):
        shoe = base[:]
        random.shuffle(shoe)
        rc = 0
        for i in range(len(shoe)):
            left = len(shoe) - i
            dl = left / 52.0
            if dl <= 0.5:
                break
            if dl >= 1.0:
                tc = rc / dl
                if -6 <= tc <= 10:
                    b = int(round(tc))
                    hits[b] += 1
                    acc = buckets[b]
                    for r in shoe[i:]:
                        acc[E.card_value(r)] += 1
                    acc[0] += left
            rc += E.hilo(E.card_value(shoe[i]))

    def odds_at(tc, up):
        acc = buckets[tc]
        cards = []
        for v in range(2, 12):
            n = int(round(acc[v] / acc[0] * 3120))
            rank = {11: "A", 10: "10"}.get(v, str(v))
            cards += [{"rank": rank, "suit": "S", "red": False}] * n
        return E.Odds(cards, up)

    def crossing(gap):
        pts = [(t, gap(t)) for t in range(-6, 11) if hits.get(t, 0) >= 300]
        for (t0, g0), (t1, g1) in zip(pts, pts[1:]):
            if g0 <= 0 < g1:
                return t0 + (0 - g0) / (g1 - g0) * (t1 - t0)
        return None

    def gap_for(p):
        up, t = p["up"], p.get("total")
        if p["key"] == "insurance":
            return lambda tc: 3 * odds_at(tc, 11).p(10) - 1
        if p["at_or_above"] == "S":
            return lambda tc: (lambda o: o.ev_stand(t) - o.ev_hit(t, False))(odds_at(tc, up))
        if p["at_or_above"] == "D":
            return lambda tc: (lambda o: o.ev_double(t, False) - o.ev_hit(t, False))(odds_at(tc, up))
        if p["at_or_above"] == "P":
            return lambda tc: (lambda o: o.ev_split(10) - o.ev_stand(20))(odds_at(tc, up))
        return None

    worst = 0.0
    for p in C.ILLUSTRIOUS_18:
        x = crossing(gap_for(p))
        if x is None:
            check("%-12s derived" % p["key"], False, "no crossing found")
            continue
        off = abs(x - p["crossing"])
        worst = max(worst, off)
        check("%-12s index %+d" % (p["key"], p["index"]),
              off <= tolerance,
              "engine crosses %+.2f, table says %+.2f" % (x, p["crossing"]))

    check("every index is within %.1f of its stored crossing" % tolerance,
          worst <= tolerance, "worst %.2f" % worst)

    for p in C.ILLUSTRIOUS_18:
        near = abs(p["crossing"] - p["index"]) <= 1.0
        if not near:
            check("%s index sits near its crossing" % p["key"], False,
                  "index %+d vs crossing %+.2f" % (p["index"], p["crossing"]))
    check("every published index is within 1.0 of where the maths puts it",
          all(abs(p["crossing"] - p["index"]) <= 1.0 for p in C.ILLUSTRIOUS_18))


if __name__ == "__main__":
    test_tags()
    test_true_count()
    test_lookup()
    test_moves()
    test_agrees_with_the_chart()
    test_ramp()
    test_deck_estimates()
    test_grading()
    test_indices_against_the_engine()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        raise SystemExit(1)
