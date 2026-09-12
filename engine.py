"""
engine.py — the maths.

Everything in here is pure: no database, no web server, no game state.
Give it a set of cards and it tells you what the odds are.

The important idea: we never look anything up in a printed table. Every
probability is computed from the cards that are actually still unseen,
so the answers shift as the shoe gets used up.
"""

import rules as R

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = [("\u2660", False), ("\u2665", True), ("\u2666", True), ("\u2663", False)]

TENS = {"10", "J", "Q", "K"}


def card_value(rank):
    """An ace counts as 11 here; we drop it to 1 later if the hand would bust."""
    if rank == "A":
        return 11
    if rank in TENS:
        return 10
    return int(rank)


def hilo(value):
    """Hi-Lo counting tag: low cards +1, middles 0, high cards -1."""
    if 2 <= value <= 6:
        return 1
    if 7 <= value <= 9:
        return 0
    return -1


def add_card(total, soft, value):
    """
    Add one card to a running total.

    `soft` means an ace is currently being counted as 11. If adding the card
    would bust, the ace silently drops to 1 and the hand carries on.
    """
    if value == 11:
        if total + 11 <= 21:
            new_total, new_soft = total + 11, True
        else:
            new_total, new_soft = total + 1, soft
    else:
        new_total, new_soft = total + value, soft
    if new_total > 21 and new_soft:
        new_total -= 10
        new_soft = False
    return new_total, new_soft


def hand_value(cards):
    """Return (best total, is_soft) for a list of card dicts."""
    total = aces = 0
    for c in cards:
        v = card_value(c["rank"])
        total += v
        if c["rank"] == "A":
            aces += 1
    soft_aces = aces
    while total > 21 and soft_aces:
        total -= 10
        soft_aces -= 1
    return total, soft_aces > 0


def composition(cards):
    """Count how many of each value are in a pile. Index 2..11; 10 holds T/J/Q/K."""
    counts = [0] * 12
    for c in cards:
        counts[card_value(c["rank"])] += 1
    return counts


# ---------------------------------------------------------------------------
# The analysis context: built fresh for every decision.
# ---------------------------------------------------------------------------

class Odds:
    """
    Odds for one specific decision.

    `unseen` is every card the player cannot see: the rest of the shoe plus
    the dealer's face-down card. `up` is the dealer's face-up value.
    """

    def __init__(self, unseen_cards, up, hit_soft_17=False):
        self.counts = composition(unseen_cards)
        self.total = sum(self.counts[2:12])
        self.up = up
        self.h17 = bool(hit_soft_17)
        self.probs = [
            (v, self.counts[v] / self.total)
            for v in range(2, 12)
            if self.counts[v] > 0
        ]
        self._dealer_memo = {}
        self._hit_memo = {}
        self._dealer_dist = None

    # -- probability of drawing a particular value right now
    def p(self, value):
        return self.counts[value] / self.total if self.total else 0.0

    # -- where a dealer hand ends up, drawing to 17
    def _from(self, total, soft):
        key = (total, soft)
        if key in self._dealer_memo:
            return self._dealer_memo[key]
        if total > 21:
            out = {"bust": 1.0}
        elif total > 17 or (total == 17 and not (soft and self.h17)):
            out = {str(total): 1.0}
        else:
            out = {}
            for v, prob in self.probs:
                nt, ns = add_card(total, soft, v)
                for end, sub in self._from(nt, ns).items():
                    out[end] = out.get(end, 0.0) + prob * sub
        self._dealer_memo[key] = out
        return out

    def dealer(self):
        """
        Full distribution of dealer outcomes from the upcard.

        Conditioned on the dealer NOT already having blackjack, because if
        they did the hand would already be over and you'd never be deciding.
        """
        if self._dealer_dist is not None:
            return self._dealer_dist
        start = (11, True) if self.up == 11 else (self.up, False)
        natural = 10 if self.up == 11 else (11 if self.up == 10 else 0)
        norm = 1.0 - self.p(natural) if natural else 1.0
        out = {}
        for v, prob in self.probs:
            if v == natural:
                continue
            nt, ns = add_card(start[0], start[1], v)
            for end, sub in self._from(nt, ns).items():
                out[end] = out.get(end, 0.0) + (prob / norm) * sub
        self._dealer_dist = out
        return out

    def dealer_bust(self):
        return self.dealer().get("bust", 0.0)

    # -- expected value of each option, in units of your original bet
    def ev_stand(self, total):
        ev = 0.0
        for end, prob in self.dealer().items():
            if end == "bust":
                ev += prob
            else:
                d = int(end)
                if d < total:
                    ev += prob
                elif d > total:
                    ev -= prob
        return ev

    def ev_hit(self, total, soft):
        key = (total, soft)
        if key in self._hit_memo:
            return self._hit_memo[key]
        ev = 0.0
        for v, prob in self.probs:
            nt, ns = add_card(total, soft, v)
            if nt > 21:
                ev += prob * -1.0
            else:
                ev += prob * max(self.ev_stand(nt), self.ev_hit(nt, ns))
        self._hit_memo[key] = ev
        return ev

    def ev_double(self, total, soft):
        ev = 0.0
        for v, prob in self.probs:
            nt, ns = add_card(total, soft, v)
            ev += prob * (-1.0 if nt > 21 else self.ev_stand(nt))
        return 2 * ev

    def ev_split(self, pair_value):
        """
        Approximate: value one fresh hand starting from the pair card, then
        double it. Ignores re-splitting, so it slightly understates 8s and aces.
        Split aces get exactly one card, so they can only stand.
        """
        start = (11, True) if pair_value == 11 else (pair_value, False)
        ev = 0.0
        for v, prob in self.probs:
            nt, ns = add_card(start[0], start[1], v)
            if pair_value == 11:
                ev += prob * self.ev_stand(nt)
            else:
                ev += prob * max(
                    self.ev_stand(nt), self.ev_hit(nt, ns), self.ev_double(nt, ns)
                )
        return 2 * ev

    def bust_chance(self, total, soft):
        """Chance the very next card breaks this hand."""
        out = 0.0
        for v, prob in self.probs:
            nt, _ = add_card(total, soft, v)
            if nt > 21:
                out += prob
        return out


# ---------------------------------------------------------------------------
# Basic strategy. The grid itself lives in rules.py so it can vary with the
# table rules and be drawn on screen; this is the part that reads a real hand.
# ---------------------------------------------------------------------------

def classify(cards, can_split):
    """
    Which row of the chart this hand sits on.

    Returns (section, row). A pair only counts as a pair while you can still
    split it \u2014 once you can't, 8,8 is just a hard 16 and the chart agrees.
    """
    if can_split and len(cards) == 2 and card_value(cards[0]["rank"]) == card_value(cards[1]["rank"]):
        return ("pair", card_value(cards[0]["rank"]))
    total, soft = hand_value(cards)
    if soft:
        if total <= 12:
            # A,A that can no longer be split, or a soft total that dropped: treat
            # as the soft row it is, clamped to the lowest row the chart holds
            return ("soft", max(2, total - 11))
        return ("soft", min(9, total - 11))
    return ("hard", max(5, min(21, total)))


def chart_play(cards, up, can_double, can_split, rules=None):
    """
    What the chart says to do.

    Returns the move plus a human label for the row, so the UI can show you
    which line of the chart you were on, and `fallback` when the chart wanted a
    double the table wouldn't let you make.
    """
    rset = rules or R.DEFAULT_RULES
    section, row = classify(cards, can_split)
    code = R.chart_move(rset, section, row, up)
    move, fell_back = R.resolve(code, can_double)

    if section == "pair":
        label = "pair of " + ("aces" if row == 11 else str(row) + "s")
        if row == 5 and move != "P":
            label = "pair of 5s (played as a hard 10)"
        return {"move": move, "row": label, "kind": "pair", "pair": row,
                "code": code, "cell": R.cell_name(section, row, up), "fallback": fell_back}
    if section == "soft":
        total = row + 11
        return {"move": move, "row": "soft %d (A,%d)" % (total, row), "kind": "soft",
                "total": total, "code": code, "cell": R.cell_name(section, row, up),
                "fallback": fell_back}
    return {"move": move, "row": "hard %d" % row, "kind": "hard", "total": row,
            "code": code, "cell": R.cell_name(section, row, up), "fallback": fell_back}


# Kept so test_engine.py can still walk the chart cell by cell.
HARD = {k: "".join(m[0] for m in v) for k, v in R.grid(R.DEFAULT_RULES)["hard"].items()}
SOFT = {str(k): "".join(m[0] for m in v) for k, v in R.grid(R.DEFAULT_RULES)["soft"].items()}
PAIRS = {k: "".join(m[0] for m in v) for k, v in R.grid(R.DEFAULT_RULES)["pair"].items()}


# ---------------------------------------------------------------------------
# Bankroll maths
# ---------------------------------------------------------------------------

HAND_SD = 1.14  # standard deviation of one hand, in bets, for basic strategy


def edge_at(true_count):
    """
    Rough Hi-Lo conversion: you start about half a percent behind, and each
    point of true count above +1 hands you back about half a percent.
    """
    return -0.005 + 0.005 * max(0.0, true_count - 1)


def reach_before_ruin(units, target_units, drift, sd=HAND_SD):
    """
    Chance of growing a bankroll to `target_units` before losing it all.
    Standard random-walk-with-drift approximation.
    """
    import math
    if units <= 0:
        return 0.0
    if target_units <= units:
        return 1.0
    if abs(drift) < 1e-12:
        return units / target_units
    k = -2 * drift / (sd * sd)
    try:
        a = math.exp(min(700, k * units))
        b = math.exp(min(700, k * target_units))
    except OverflowError:
        return 0.0
    return (a - 1) / (b - 1) if b != 1 else units / target_units


def risk_of_ruin(units, drift, sd=HAND_SD):
    """With no edge, ruin is certain given enough hands. With an edge it isn't."""
    import math
    if drift <= 0:
        return 1.0
    return math.exp(-2 * drift * units / (sd * sd))
