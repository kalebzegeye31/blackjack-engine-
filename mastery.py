"""
mastery.py — how well you actually know the chart.

Raw accuracy is a bad measure of a card player. Most of the hands you are dealt
are trivial — a hard 20, a hard 8 — and getting those right forever will hold a
number in the nineties while the six cells you keep fluffing quietly cost you
money. Worse, the number only goes up, so it stops telling you anything.

So there are two numbers here.

  Accuracy   plain and unweighted: decisions you got right, out of all of them.
             Useful, honest, and easy to game by playing a lot of easy hands.

  Sharpness  what this file computes. Each cell of the chart carries a weight
             that falls as you master it and stays high while you don't, so
             once you can play a hand in your sleep it stops holding the number
             up. What is left is a score that only moves when you learn
             something you did not already know.

Three things set a cell's weight:

  difficulty  driven by your recent record on that cell. Get it right a few
              times running and the weight decays towards a floor; miss it and
              it springs straight back up. Recent results count for much more
              than old ones, so improvement shows up quickly.
  cost        how much expected value your mistakes on that cell actually give
              away. Misplaying a 16 against a 10 costs almost nothing; missing
              a double on 11 costs a lot. The expensive ones weigh more.
  exposure    a cell you have seen twice cannot swing the score. Weight ramps
              in as evidence accumulates.

And the whole thing is held back until there is enough evidence to mean
anything: below RAMP decisions the score is blended towards plain accuracy, so
it does not lurch about while you are still finding your feet.
"""

import rules as R

RAMP = 250          # decisions before sharpness is shown on its own
HALF_LIFE = 10      # sightings of a cell before an old result counts half
FLOOR = 0.20        # weight a fully mastered cell keeps
SHAPE = 1.4         # how sharply weight falls away as a cell is mastered
PRIOR_N = 2.0       # pseudo-counts pulling an unseen cell towards a coin flip
COST_SCALE = 0.08   # EV given up, in bets, at which a cell counts double

_DECAY = 0.5 ** (1.0 / HALF_LIFE)


class Cell:
    """One square of the chart, and your record on it."""

    __slots__ = ("cell", "section", "row", "up", "n", "hits", "w_sum", "w_hits",
                 "cost", "misses", "last_at", "chose")

    def __init__(self, cell):
        self.cell = cell
        parsed = R.parse_cell(cell)
        self.section, self.row, self.up = parsed if parsed else (None, None, None)
        self.n = self.hits = self.misses = 0
        self.w_sum = self.w_hits = 0.0
        self.cost = 0.0
        self.last_at = 0.0
        self.chose = {}

    # -- the recency-weighted view of your record on this cell
    def observe(self, correct, cost, at, chose=None):
        """Fold in one more sighting. Everything already here ages by one step."""
        self.w_sum = self.w_sum * _DECAY + 1.0
        self.w_hits = self.w_hits * _DECAY + (1.0 if correct else 0.0)
        self.n += 1
        if correct:
            self.hits += 1
        else:
            self.misses += 1
            self.cost += max(0.0, cost)
        self.last_at = max(self.last_at, at or 0.0)
        if chose:
            self.chose[chose] = self.chose.get(chose, 0) + 1

    @property
    def mastery(self):
        """Recent correctness, smoothed towards a coin flip while evidence is thin."""
        return (self.w_hits + PRIOR_N * 0.5) / (self.w_sum + PRIOR_N)

    @property
    def raw(self):
        return self.hits / self.n if self.n else None

    @property
    def avg_cost(self):
        """EV given up per mistake, in units of the bet."""
        return self.cost / self.misses if self.misses else 0.0

    @property
    def exposure(self):
        return self.n / (self.n + 2.0)

    @property
    def difficulty(self):
        return FLOOR + (1.0 - FLOOR) * (1.0 - self.mastery) ** SHAPE

    @property
    def cost_mult(self):
        return 1.0 + min(1.0, self.avg_cost / COST_SCALE)

    @property
    def weight(self):
        return self.difficulty * self.cost_mult * self.exposure

    @property
    def leak(self):
        """
        How much of your score this one cell is holding down.

        This is the drill order: fixing the cell at the top of this list moves
        the number more than fixing anything else.
        """
        return self.weight * (1.0 - self.mastery)

    def as_dict(self, rules=None):
        out = {
            "cell": self.cell, "section": self.section, "row": self.row, "up": self.up,
            "seen": self.n, "correct": self.hits, "missed": self.misses,
            "accuracy": self.raw, "mastery": round(self.mastery, 4),
            "weight": round(self.weight, 4), "leak": round(self.leak, 4),
            "avg_cost": round(self.avg_cost, 4), "total_cost": round(self.cost, 3),
            "last_at": self.last_at,
            "chose": self.chose,
        }
        if rules and self.section:
            try:
                out["should"] = R.chart_move(rules, self.section, self.row, self.up)
            except KeyError:
                out["should"] = None
        return out


class Profile:
    """Everything the app knows about how well one person plays."""

    def __init__(self, rules=None):
        self.rules = rules or R.DEFAULT_RULES
        self.cells = {}
        self.total = 0
        self.correct = 0
        self.cost = 0.0
        self.recent = []           # newest last, 1 or 0

    def feed(self, rows):
        """
        Take decision rows oldest first.

        Each row needs `cell`, `correct` and `cost`; `at` and `chose` are used
        where they exist. Rows whose cell name no longer parses are counted in
        the totals but cannot be placed on the chart, so they are skipped here.
        """
        for row in rows:
            cell = row["cell"]
            correct = bool(row["correct"])
            self.total += 1
            self.correct += 1 if correct else 0
            self.cost += max(0.0, float(row.get("cost") or 0.0))
            self.recent.append(1 if correct else 0)
            if R.parse_cell(cell) is None:
                continue           # insurance and anything else off the grid
            if cell not in self.cells:
                self.cells[cell] = Cell(cell)
            self.cells[cell].observe(correct, float(row.get("cost") or 0.0),
                                     float(row.get("at") or 0.0), row.get("chose"))
        return self

    # ---------------- the headline numbers ----------------
    @property
    def accuracy(self):
        return self.correct / self.total if self.total else None

    @property
    def confidence(self):
        """0 while you have barely played, 1 once the weighting can be trusted."""
        return min(1.0, self.total / float(RAMP))

    @property
    def weighted(self):
        """Sharpness before the confidence ramp is applied."""
        live = [c for c in self.cells.values() if c.n]
        if not live:
            return None
        num = sum(c.weight * c.mastery for c in live)
        den = sum(c.weight for c in live)
        return num / den if den else None

    @property
    def sharpness(self):
        """The number to show. Blended towards plain accuracy while evidence is thin."""
        w = self.weighted
        if w is None or self.accuracy is None:
            return None
        conf = self.confidence
        return self.accuracy * (1 - conf) + w * conf

    def trend(self, window=50):
        """Plain accuracy over the last `window` decisions, and the one before it."""
        if len(self.recent) < 10:
            return None
        tail = self.recent[-window:]
        prev = self.recent[-2 * window:-window]
        return {
            "recent": sum(tail) / len(tail),
            "previous": (sum(prev) / len(prev)) if len(prev) >= 10 else None,
            "window": len(tail),
        }

    # ---------------- what to work on ----------------
    def drill(self, limit=12, min_seen=1):
        """The cells costing you the most, worst first."""
        live = [c for c in self.cells.values() if c.n >= min_seen and c.mastery < 0.95]
        live.sort(key=lambda c: c.leak, reverse=True)
        return [c.as_dict(self.rules) for c in live[:limit]]

    def coverage(self):
        """How much of the chart you have actually been tested on."""
        grid_cells = R.cells_for(self.rules)
        playable = [(s, r, u) for s, r, u, _ in grid_cells if not (s == "hard" and r >= 17)]
        seen = sum(1 for s, r, u in playable if R.cell_name(s, r, u) in self.cells)
        solid = sum(1 for s, r, u in playable
                    if (R.cell_name(s, r, u) in self.cells
                        and self.cells[R.cell_name(s, r, u)].mastery >= 0.8))
        return {"total": len(playable), "seen": seen, "solid": solid,
                "unseen": len(playable) - seen}

    def by_section(self):
        out = {}
        for section in ("hard", "soft", "pair"):
            live = [c for c in self.cells.values() if c.section == section and c.n]
            if not live:
                out[section] = None
                continue
            n = sum(c.n for c in live)
            out[section] = {
                "seen": n,
                "accuracy": sum(c.hits for c in live) / n,
                "mastery": sum(c.weight * c.mastery for c in live) / (sum(c.weight for c in live) or 1),
                "cells": len(live),
            }
        return out

    def by_upcard(self):
        out = {}
        for up in R.UPCARDS:
            live = [c for c in self.cells.values() if c.up == up and c.n]
            n = sum(c.n for c in live)
            out[R.up_label(up)] = {"seen": n,
                                   "accuracy": (sum(c.hits for c in live) / n) if n else None}
        return out

    def heatmap(self):
        """Every cell of the chart with your record on it, for drawing over the chart."""
        out = {}
        for cell, c in self.cells.items():
            if c.section is None:
                continue
            out[cell] = {"seen": c.n, "correct": c.hits,
                         "accuracy": c.raw, "mastery": round(c.mastery, 3)}
        return out

    # ---------------- patterns, not just cells ----------------
    def leaks(self):
        """
        Named habits, rather than a list of squares.

        A cell tells you what you got wrong. A pattern tells you why, and it is
        the difference between memorising 40 corrections and fixing one idea.
        """
        found = []
        for name, test, text in _PATTERNS:
            hit = [c for c in self.cells.values() if c.section and test(c, self.rules)]
            misses = sum(c.misses for c in hit)
            seen = sum(c.n for c in hit)
            if seen >= 8 and misses >= 3 and misses / seen >= 0.2:
                found.append({
                    "key": name, "text": text, "misses": misses, "seen": seen,
                    "rate": round(misses / seen, 3),
                    "cells": sorted((c.cell for c in hit if c.misses),
                                    key=lambda x: -self.cells[x].misses)[:6],
                })
        found.sort(key=lambda f: -f["misses"])
        return found


def _should(cell, rules):
    try:
        return R.chart_move(rules, cell.section, cell.row, cell.up)
    except KeyError:
        return None


def _stiff_low(c, rules):
    return c.section == "hard" and 12 <= c.row <= 16 and c.up <= 6


def _stiff_high(c, rules):
    return c.section == "hard" and 12 <= c.row <= 16 and c.up >= 7


def _missed_double(c, rules):
    return _should(c, rules) in ("D", "Ds") and c.chose.get("H", 0) + c.chose.get("S", 0) > 0


def _should_split(c, rules):
    return c.section == "pair" and _should(c, rules) == "P"


def _should_not_split(c, rules):
    return c.section == "pair" and _should(c, rules) != "P"


def _soft_hand(c, rules):
    return c.section == "soft" and c.row <= 6


_PATTERNS = [
    ("stiff_low", _stiff_low,
     "Stiff hands against a weak dealer. On 12 to 16 against a 2 to 6 the dealer is the "
     "one in trouble, so you stand and let them break. Taking a card here is the single "
     "most common way people give the game away."),
    ("stiff_high", _stiff_high,
     "Stiff hands against a strong dealer. On 12 to 16 against a 7 or better, standing "
     "loses slowly and hitting loses slightly less slowly. Both are bad; take the less bad one."),
    ("doubles", _missed_double,
     "Doubles you did not take. Doubling is the only time the house lets you put more money "
     "out after seeing a card. Skipping it is a pure giveaway, not a safe choice."),
    ("splits", _should_split,
     "Pairs you did not split. Splitting turns one bad hand into two live ones — the whole "
     "point of splitting 8s against a 10 is that 16 is hopeless and two 8s are not."),
    ("oversplit", _should_not_split,
     "Pairs you split that you should have kept together. Two tens is a 20 and two fives is "
     "an 11 you should double — splitting either one throws away a made hand."),
    ("soft", _soft_hand,
     "Soft hands. With an ace counting as eleven you cannot break with one card, so the "
     "cautious play is the wrong one. Soft 17 is not a 17; it is a hand that cannot lose by drawing."),
]


# ---------------------------------------------------------------------------
# Picking what to ask next. The quiz uses this so the questions you get are the
# questions you need, rather than a shuffle of the whole chart.
# ---------------------------------------------------------------------------

def study_weights(profile, rules, pool=None, include_unseen=True, unseen_weight=0.5,
                  leak_gain=4.0):
    """
    A weight per chart cell for drawing quiz questions.

    Cells you keep missing come up most. Cells you have never been dealt come up
    next, because an untested cell is not a mastered one. Cells you can play in
    your sleep come up rarely, but never quite never.

    `unseen_weight` is the dial between the two. High, and the quiz explores the
    chart; low, and it drills the handful of squares you actually get wrong.
    """
    out = []
    for section, row, up, _ in R.cells_for(rules):
        if section == "hard" and row >= 17:
            continue
        if pool and (section, row, up) not in pool:
            continue
        name = R.cell_name(section, row, up)
        cell = profile.cells.get(name) if profile else None
        if cell and cell.n:
            w = cell.leak * leak_gain + 0.05
        elif include_unseen:
            w = unseen_weight
        else:
            continue
        out.append((section, row, up, w))
    return out


def pick(weights, count, rng):
    """Sample without replacement, proportional to weight."""
    pool = list(weights)
    chosen = []
    while pool and len(chosen) < count:
        total = sum(w for _, _, _, w in pool)
        if total <= 0:
            chosen.extend(pool[:count - len(chosen)])
            break
        r = rng.random() * total
        acc = 0.0
        for i, item in enumerate(pool):
            acc += item[3]
            if acc >= r:
                chosen.append(pool.pop(i))
                break
        else:
            chosen.append(pool.pop())
    return chosen


def expected_cost_per_hand(profile, rules):
    """
    Roughly what your mistakes cost, per hand, in units of your bet.

    Each cell's miss rate times what a miss on it costs, weighted by how often
    that cell actually turns up at a table. This is the number that turns
    "94% accurate" into money.
    """
    if not profile or not profile.cells:
        return None
    total = 0.0
    for c in profile.cells.values():
        if not c.section or not c.n:
            continue
        freq = R.cell_frequency(c.section, c.row, c.up)
        miss_rate = 1.0 - c.mastery
        total += freq * miss_rate * c.avg_cost
    return total


def band(score):
    """A word for a score, so the UI doesn't have to invent one."""
    if score is None:
        return "unrated"
    if score >= 0.95:
        return "sharp"
    if score >= 0.85:
        return "solid"
    if score >= 0.70:
        return "patchy"
    if score >= 0.50:
        return "shaky"
    return "learning"
