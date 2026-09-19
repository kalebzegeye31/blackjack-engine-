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
        # The UI works out which side is the deviation by asking which one is
        # NOT the chart. That only works if the two sides differ, and it cannot
        # be inferred from the sign of the index: 16 v 10 and 12 v 4 both have
        # an index of 0 and deviate in opposite directions.
        if p["at_or_above"] == p["below"]:
            bad.append("%s: both sides are %s, so neither is the deviation"
                       % (p["key"], p["at_or_above"]))
    check("no index contradicts basic strategy on both sides", not bad,
          "; ".join(bad))
    check("every index has two different sides, so the deviating one is identifiable",
          all(q["at_or_above"] != q["below"] for q in C.ILLUSTRIOUS_18))

    zero = [q["key"] for q in C.ILLUSTRIOUS_18 if q["index"] == 0]
    check("the index-zero plays deviate in opposite directions, so the sign cannot be used",
          len(zero) >= 2, ", ".join(zero))


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



def test_a_pair_is_not_its_total():
    """
    A hand you are going to split is not a hard total.

    This shipped broken: lookup() fell through to the hard-total indices for any
    pair that was not tens, so a pair of 8s matched 16 v 10 and the app told a
    player to hit 8,8 against a ten at a true count of -0.9. Nothing ever
    justifies that. A pair of 6s had the same fault against the whole 12 row.

    A pair of 5s is the case that has to keep working: the chart never splits
    it, so it really is a hard 10 and the hard 10 indices belong to it.
    """
    print("\na pair is not its total")
    rules = R.normalise({})

    for pair, total, label in ((8, 16, "8,8"), (6, 12, "6,6")):
        wrong = []
        for up in R.UPCARDS:
            code = R.chart_move(rules, "pair", pair, up)
            chart = R.resolve(code, True)[0]
            if chart != "P":
                continue                     # not a split cell; the total governs
            for tc in (-8, -5, -3, -1, 0, 1, 3, 5, 8, 12):
                mv, entry, dev = C.correct_move(chart, "pair", total, pair, up, tc,
                                                can_split=True, can_double=True)
                if mv != "P" or entry is not None:
                    wrong.append((up, tc, mv, entry["key"] if entry else None))
        check("%s is split at every count the chart splits it" % label,
              not wrong, str(wrong[:3]))

    # the reported hand, exactly
    mv, entry, dev = C.correct_move("P", "pair", 16, 8, 10, -0.9,
                                    can_split=True, can_double=True)
    check("8,8 v 10 at true count -0.9 splits", mv == "P" and entry is None and not dev)

    # ...but an 8,8 you are not allowed to split arrives as a hard 16 and keeps
    # its index, which is the whole reason the hard lookup exists
    mv, entry, dev = C.correct_move("H", "hard", 16, None, 10, 1.0)
    check("a hard 16 v 10 you cannot split still stands at +1",
          mv == "S" and entry is not None and dev)

    # 5,5 is never split, so it really is a hard 10
    mv, entry, dev = C.correct_move("H", "pair", 10, 5, 10, 5.0,
                                    can_split=True, can_double=True)
    check("5,5 v 10 still doubles at +5, as a hard ten",
          mv == "D" and entry is not None and entry["key"] == "h10v10")

    # and tens keep their own index rather than borrowing hard 20's (there isn't one)
    mv, entry, dev = C.correct_move("S", "pair", 20, 10, 5, 5.0,
                                    can_split=True, can_double=True)
    check("T,T v 5 splits at +5 on its own index",
          mv == "P" and entry is not None and entry["key"] == "pTTv5")


def test_verdict_is_count_aware():
    """
    The headline a player reads has to be graded on the count.

    This is the bug that shipped: the index grading went into the analysis but
    the verdict still came from the chart, so correctly hitting 12 v 5 at a
    true count of -3.7 was reported as "you should have stood". A trainer that
    marks a correct deviation wrong teaches the opposite of what it is for.
    """
    from game import Table
    print("\nthe verdict a player actually reads")

    def card(r):
        return {"rank": r, "suit": "S", "red": False}

    def rigged(player, up, running):
        t = Table(config={"decks": 6, "others": 0, "table_min": 10})
        t.bankroll = 500.0
        t.bet = 10.0
        t.dealer = [card(up), card("7")]
        t.hole_hidden = True
        t.hands = [t._new_hand([card(c) for c in player], 10.0)]
        t.active = 0
        t.phase = "play"
        t.running_count = running
        t.dealt = 312 - 170          # ~3.27 decks left, as in the reported hand
        return t

    t = rigged(["7", "5"], "5", -12)
    tc = t.true_count()
    check("the reported hand reproduces a true count near -3.7",
          -4.0 < tc < -3.3, "%+.2f" % tc)

    a = t.analyse(t.hands[0], "H")
    check("basic strategy still says stand", a["chart_move"] == "S")
    check("the count says hit", a["count_move"] == "H")
    check("and it is flagged as a deviation", a["index_deviation"])

    t.act("H")
    v = t.verdict
    check("hitting is marked CORRECT in the verdict", v["count_correct"] is True)
    check("the verdict's 'should' is the count's move", v["count_should"] == "H")
    check("the chart move is still carried, for the explanation", v["should"] == "S")
    check("and the chart-only flag still says wrong, for the history",
          v["correct"] is False)

    # the other direction: playing the chart when the count says otherwise
    t2 = rigged(["7", "5"], "5", -12)
    t2.act("S")
    check("standing there is marked WRONG", t2.verdict["count_correct"] is False)

    # and a square with no index is unaffected
    t3 = rigged(["7", "6"], "6", -12)
    t3.act("S")
    check("13 v 6 has no index, so the chart still rules",
          t3.verdict["count_correct"] is True and not t3.verdict["index_deviation"])

    # insurance carries the same fields
    t4 = rigged(["10", "9"], "A", 30)
    t4.dealt = 312 - 170
    t4.phase = "insurance"
    t4.insurance(True)
    check("insurance taken at a high count is marked correct",
          t4.verdict["count_correct"] is True)
    t5 = rigged(["10", "9"], "A", 30)
    t5.dealt = 312 - 170
    t5.phase = "insurance"
    t5.insurance(False)
    check("and declining it there is marked wrong",
          t5.verdict["count_correct"] is False)


def test_the_chart_never_contradicts_its_own_index():
    """
    Every square the count moves, checked from both sides.

    Two ways a player gets whipsawed here. The flag that says "the chart has
    been overruled" has to be exactly that and nothing else, or the warning the
    app prints sits on the wrong hands. And the passage on a square the count
    moves must not hand the player an absolute rule to memorise that the index
    table then marks them wrong for following.
    """
    import coach
    import re

    print("\nno square is told one thing by the chart and another by the count")
    absolute = re.compile(r"\b(never|always|no upcard|every card|not one)\b", re.I)
    qualifier = re.compile(r"count|index|on the chart|without a count", re.I)

    wrong_flag, unqualified, one_sided = [], [], []
    for p in C._I18:
        key = p["key"]
        if key == "insurance":
            e = coach.explain({"kind": "insurance"})
            sides = set()
            for tc in (-4, 0, 2, 2.9, 3, 5, 8):
                take, _ = C.insurance_play(tc)
                # game.py sets index_deviation from this, and basic strategy declines
                if take != (("take" if take else "decline") != "decline"):
                    wrong_flag.append((key, tc))
                sides.add(take)
        else:
            kind = p["kind"]
            section = "pair" if kind == "pair" else "hard"
            row = p.get("pair") if kind == "pair" else p.get("total")
            chart = R.chart_move(R.DEFAULT_RULES, section, row, p["up"])
            e = coach.explain({"kind": "play", "hand_kind": kind,
                               "total": p.get("total") or (p.get("pair") or 0) * 2,
                               "pair": p.get("pair"), "up": p["up"]})
            sides = set()
            for tc in range(-6, 9):
                want, _, dev = C.correct_move(chart, kind, p.get("total"), p.get("pair"),
                                              p["up"], tc, can_split=(kind == "pair"))
                if dev != (want != chart):
                    wrong_flag.append((key, tc, dev, want, chart))
                sides.add(dev)
        if sides != {True, False}:
            one_sided.append((key, sides))
        for field in ("hook", "remember"):
            text = e[field]
            if absolute.search(text) and not qualifier.search(text):
                unqualified.append((key, field, text[:70]))

    check("the deviation flag means exactly 'the move has changed'",
          not wrong_flag, str(wrong_flag[:2]))
    check("every index flags on one side of itself and not the other",
          not one_sided, str(one_sided[:2]))
    check("no square memorises an absolute its own index contradicts",
          not unqualified, str(unqualified[:2]))
    check("all %d index squares were checked" % len(C._I18), len(C._I18) == 18)

    # the eight tens upcards with no index keep their flat "never", which is true
    flat = [u for u in range(2, 12)
            if "until the count" not in
            coach.explain({"kind": "play", "hand_kind": "pair", "total": 20,
                           "pair": 10, "up": u})["hook"]]
    check("and the eight upcards with no index keep the unqualified rule",
          sorted(flat) == [2, 3, 4, 7, 8, 9, 10, 11], str(sorted(flat)))


if __name__ == "__main__":
    test_tags()
    test_true_count()
    test_lookup()
    test_moves()
    test_agrees_with_the_chart()
    test_ramp()
    test_deck_estimates()
    test_grading()
    test_a_pair_is_not_its_total()
    test_verdict_is_count_aware()
    test_the_chart_never_contradicts_its_own_index()
    test_indices_against_the_engine()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        raise SystemExit(1)
