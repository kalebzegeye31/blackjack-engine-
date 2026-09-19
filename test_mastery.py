"""
test_mastery.py — the score means what the file says it means.

mastery.py computes the number a player judges themselves by, and it had no
tests. Every property asserted here is one its docstring promises: that mastered
cells stop holding the score up, that expensive mistakes weigh more than cheap
ones, that the number is held back until there is evidence behind it, and that
none of it falls over on an empty or odd profile.

    python3 test_mastery.py
"""

import engine as E
import mastery as M
import rules as R

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %-62s %s%s" % (name, "ok" if cond else "FAIL", ("  " + detail) if detail else ""))


H20v10 = R.cell_name("hard", 20, 10)
H16v10 = R.cell_name("hard", 16, 10)
H11v6 = R.cell_name("hard", 11, 6)
INS = "insurance vs A"          # deliberately not a chart square


def prof(rows):
    return M.Profile(R.DEFAULT_RULES).feed(rows)


def run(cell, n, correct, cost=0.0, chose="S", start=0):
    return [{"cell": cell, "correct": 1 if correct else 0, "cost": cost,
             "at": start + i, "chose": chose} for i in range(n)]


# ---------------------------------------------------------------------------

def test_cost_claim():
    """The docstring names two cells to make its point. They have to be true."""
    print("\nthe two cells the docstring uses as its example")
    shoe = [{"rank": r, "suit": s, "red": red}
            for _ in range(6) for s, red in E.SUITS for r in E.RANKS]
    o10, o6 = E.Odds(shoe, 10), E.Odds(shoe, 6)
    cheap = abs(o10.ev_stand(16) - o10.ev_hit(16, False))
    dear = o6.ev_double(11, False) - o6.ev_hit(11, False)
    check("misplaying 16 v 10 really does cost almost nothing", cheap < 0.005,
          "%.4f" % cheap)
    check("missing the double on 11 v 6 really does cost a lot", dear > 0.2,
          "%.4f" % dear)
    check("and the expensive one is at least a hundred times the cheap one",
          dear / cheap > 100, "%.0fx" % (dear / cheap))


def test_mastered_cells_stop_counting():
    print("\na cell you have mastered stops holding the score up")
    p = prof(run(H20v10, 200, True))
    c = p.cells[H20v10]
    check("its weight decays towards the floor", c.difficulty < M.FLOOR + 0.05,
          "difficulty %.3f, floor %.2f" % (c.difficulty, M.FLOOR))
    check("but never all the way to zero", c.weight > 0,
          "weight %.3f" % c.weight)

    # the same easy cell, plus a hard one being missed
    p2 = prof(run(H20v10, 200, True) + run(H16v10, 20, False, 0.0006, "S", 300))
    check("sharpness falls well below plain accuracy when a hard cell is missed",
          p2.sharpness < p2.accuracy - 0.2,
          "accuracy %.3f vs sharpness %.3f" % (p2.accuracy, p2.sharpness))
    check("plain accuracy stays flattered by the easy cell", p2.accuracy > 0.85,
          "%.3f" % p2.accuracy)


def test_expensive_mistakes_weigh_more():
    print("\nan expensive mistake weighs more than a cheap one")
    cheap = prof(run(H16v10, 40, False, 0.0006, "S"))
    dear = prof(run(H11v6, 40, False, 0.3337, "H"))
    wc = cheap.cells[H16v10].weight
    wd = dear.cells[H11v6].weight
    check("the costly cell carries more weight", wd > wc, "%.3f vs %.3f" % (wd, wc))
    check("and the cost multiplier is capped at doubling",
          dear.cells[H11v6].cost_mult <= 2.0,
          "%.2f" % dear.cells[H11v6].cost_mult)


def test_recency():
    print("\nrecent results count for more than old ones")
    improving = prof(run(H16v10, 30, False, 0.001, "S")
                     + run(H16v10, 30, True, 0.0, "H", 100))
    slipping = prof(run(H16v10, 30, True, 0.0, "H")
                    + run(H16v10, 30, False, 0.001, "S", 100))
    a = improving.cells[H16v10]
    b = slipping.cells[H16v10]
    check("same record, opposite order, very different mastery",
          a.mastery > b.mastery + 0.5, "%.3f vs %.3f" % (a.mastery, b.mastery))
    check("plain accuracy cannot tell them apart",
          abs(a.raw - b.raw) < 1e-9, "%.3f vs %.3f" % (a.raw, b.raw))


def test_the_confidence_ramp():
    print("\nthe score is held back until there is evidence behind it")
    rows = [dict(cell=H16v10, correct=i % 2, cost=0.001, at=i, chose="H")
            for i in range(M.RAMP * 2)]
    low = prof(rows[:10])
    full = prof(rows)
    check("confidence starts near zero", low.confidence < 0.1, "%.2f" % low.confidence)
    check("and reaches one at RAMP decisions", full.confidence == 1.0)
    check("early on, the number sits close to plain accuracy",
          abs(low.sharpness - low.accuracy) < 0.02,
          "%.3f vs %.3f" % (low.sharpness, low.accuracy))
    check("later it is the weighted figure outright",
          abs(full.sharpness - full.weighted) < 1e-9)


def test_leaks_and_drill():
    print("\npatterns and the drill list")
    rows = []
    for up in (2, 3, 4, 5, 6):
        rows += run(R.cell_name("hard", 15, up), 4, False, 0.02, "H", up * 10)
    p = prof(rows)
    keys = [l["key"] for l in p.leaks()]
    check("standing errors on stiff hands v weak cards are named as a pattern",
          "stiff_low" in keys, str(keys))
    check("the drill list is ordered worst first",
          all(a["leak"] >= b["leak"] for a, b in zip(p.drill(), p.drill()[1:])))
    check("a cell you always get right drops off the drill list",
          H20v10 not in [d["cell"] for d in
                         prof(rows + run(H20v10, 50, True, 0.0, "S", 200)).drill()])


def test_the_mastered_cutoff_is_reachable():
    """
    The drill list drops cells you have mastered. It used to compare against
    0.95, but mastery tops out below that, so the filter could never fire and a
    perfect record still showed up as something to practise.
    """
    print("\nthe cutoff for 'you have this one' is a number a cell can reach")
    p = prof(run(H20v10, 500, True))
    top = p.cells[H20v10].mastery
    check("mastery really does stop short of 1.0", top < 0.99, "%.4f" % top)
    check("CEILING predicts where it stops", abs(top - M.CEILING) < 1e-6,
          "%.6f vs %.6f" % (top, M.CEILING))
    check("the mastered cutoff sits below that ceiling", M.MASTERED < M.CEILING,
          "%.4f < %.4f" % (M.MASTERED, M.CEILING))
    check("so a spotless record clears it", top >= M.MASTERED)
    check("the coverage 'solid' mark is reachable too", 0.8 < M.CEILING)
    nine = prof([{"cell": H16v10, "correct": i % 10 != 0, "cost": 0.001,
                  "at": i, "chose": "H"} for i in range(200)])
    check("but nine right out of ten is still worth drilling",
          nine.cells[H16v10].mastery < M.MASTERED,
          "%.4f" % nine.cells[H16v10].mastery)


def test_cell_names_round_trip():
    """A name that does not parse is counted but never lands on the chart."""
    print("\nevery cell name the app writes can be read back")
    bad = [R.cell_name(s, r, u) for s, r, u, _ in R.cells_for(R.DEFAULT_RULES)
           if R.parse_cell(R.cell_name(s, r, u)) != (s, r, u)]
    check("all %d of them" % len(R.cells_for(R.DEFAULT_RULES)), not bad, str(bad[:3]))
    fed = prof([{"cell": R.cell_name(s, r, u), "correct": 0, "cost": 0.01,
                 "at": i, "chose": "H"}
                for i, (s, r, u, _) in enumerate(R.cells_for(R.DEFAULT_RULES))])
    check("and a decision on every square reaches the chart",
          len(fed.cells) == fed.total, "%d of %d" % (len(fed.cells), fed.total))
    check("soft hands among them", any(c.section == "soft" for c in fed.cells.values()))
    check("pairs among them", any(c.section == "pair" for c in fed.cells.values()))


def test_patterns_match_the_chart():
    """
    A named pattern tells the player what to do differently. If it sweeps in a
    cell where the chart says the opposite, it is telling them to break the
    chart — so each predicate is checked against the chart it is describing.
    """
    print("\nthe named patterns do not contradict the chart")
    rules = R.DEFAULT_RULES
    cells = []
    for sec, row, up, _ in R.cells_for(rules):
        c = M.Cell(R.cell_name(sec, row, up))
        c.chose = {"H": 1}       # the doubles pattern reads what you chose, not the chart
        cells.append(c)
    by = {name: [c for c in cells if c.section and test(c, rules)]
          for name, test, _ in M._PATTERNS}

    stand_only = [c.cell for c in by["stiff_low"]
                  if R.chart_move(rules, c.section, c.row, c.up) != "S"]
    check("'stand on your stiff' only covers cells the chart stands on",
          not stand_only, str(stand_only))
    check("and the hard 12s it leaves out are the ones the chart hits",
          all(R.chart_move(rules, "hard", 12, u) == "H" for u in (2, 3)))
    check("it still covers the bulk of the stiff squares",
          len(by["stiff_low"]) >= 20, "%d cells" % len(by["stiff_low"]))

    hit_only = [c.cell for c in by["stiff_high"]
                if R.chart_move(rules, c.section, c.row, c.up) != "H"]
    check("'stiff against a strong dealer' only covers cells the chart hits",
          not hit_only, str(hit_only))

    check("'pairs you did not split' only covers cells the chart splits",
          all(R.chart_move(rules, c.section, c.row, c.up) == "P"
              for c in by["splits"]))
    check("'pairs you split anyway' covers no cell the chart splits",
          all(R.chart_move(rules, c.section, c.row, c.up) != "P"
              for c in by["oversplit"]))
    check("the two pair patterns between them cover every pair, once",
          len(by["splits"]) + len(by["oversplit"])
          == len([c for c in cells if c.section == "pair"]))

    check("'soft hands' covers soft 13 through soft 17",
          sorted({c.row + 11 for c in by["soft"]}) == [13, 14, 15, 16, 17],
          str(sorted({c.row + 11 for c in by["soft"]})))
    check("and drawing really does beat standing on every soft 17",
          _draw_beats_stand(17))
    check("'doubles you skipped' only covers cells the chart doubles",
          all(R.chart_move(rules, c.section, c.row, c.up) in ("D", "Ds")
              for c in by["doubles"]))
    check("and it does not fire on a player who never hit a doubling hand",
          not [c for c in cells if (setattr(c, "chose", {"D": 1}) or
                                    M._missed_double(c, rules))])
    check("every pattern still fires on some cell",
          all(by[name] for name in by), str([n for n in by if not by[n]]))


def _draw_beats_stand(soft_total):
    import engine as E
    shoe = [{"rank": r, "suit": s, "red": red}
            for _ in range(6) for s, red in E.SUITS for r in E.RANKS]
    return all(E.Odds(shoe, up).ev_hit(soft_total, True)
               >= E.Odds(shoe, up).ev_stand(soft_total) for up in R.UPCARDS)


def test_survives_odd_input():
    print("\nnothing falls over on an empty or odd profile")
    e = prof([])
    check("an empty profile has no score rather than a wrong one",
          e.accuracy is None and e.sharpness is None)
    check("and is banded 'unrated'", M.band(e.sharpness) == "unrated")
    check("cost per hand on an empty profile is None",
          M.expected_cost_per_hand(e, R.DEFAULT_RULES) is None)
    off = prof([{"cell": INS, "correct": 1, "cost": 0.0, "at": 1,
                 "chose": "decline"}])
    check("a row that is not a chart square still counts in the totals",
          off.total == 1)
    check("but is not placed on the chart", len(off.cells) == 0)
    junk = prof([{"cell": "not a real cell", "correct": 0, "cost": None, "at": None}])
    check("an unparseable cell and a missing cost do not raise", junk.total == 1)
    check("coverage reports the whole playable grid",
          prof([]).coverage()["total"] > 200,
          str(prof([]).coverage()))


def test_band_thresholds():
    print("\nthe word attached to a score")
    for score, want in ((0.99, "sharp"), (0.90, "solid"), (0.75, "patchy"),
                        (0.55, "shaky"), (0.30, "learning"), (None, "unrated")):
        check("%-6s -> %s" % (score, want), M.band(score) == want)


if __name__ == "__main__":
    test_cost_claim()
    test_mastered_cells_stop_counting()
    test_expensive_mistakes_weigh_more()
    test_recency()
    test_the_confidence_ramp()
    test_leaks_and_drill()
    test_the_mastered_cutoff_is_reachable()
    test_cell_names_round_trip()
    test_patterns_match_the_chart()
    test_survives_odd_input()
    test_band_thresholds()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        raise SystemExit(1)
