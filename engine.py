"""
engine.py — the maths.

Everything in here is pure: no database, no web server, no game state.
Give it a set of cards and it tells you what the odds are.

The important idea: we never look anything up in a printed table. Every
probability is computed from the cards that are actually still unseen,
so the answers shift as the shoe gets used up.
"""

from functools import lru_cache

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

    def __init__(self, unseen_cards, up):
        self.counts = composition(unseen_cards)
        self.total = sum(self.counts[2:12])
        self.up = up
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
        elif total >= 17:
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
# Basic strategy (6 decks, dealer stands on all 17s, double after split)
# Columns are dealer 2,3,4,5,6,7,8,9,10,A
# ---------------------------------------------------------------------------

HARD = {
    8:  "HHHHHHHHHH",
    9:  "HDDDDHHHHH",
    10: "DDDDDDDDHH",
    11: "DDDDDDDDDH",
    12: "HHSSSHHHHH",
    16: "SSSSSHHHHH",
    21: "SSSSSSSSSS",
}
SOFT = {
    "2-3": "HHHDDHHHHH",
    "4-5": "HHDDDHHHHH",
    "6":   "HDDDDHHHHH",
    "7":   "SDDDDSSHHH",
    "8+":  "SSSSSSSSSS",
}
PAIRS = {
    11: "PPPPPPPPPP",
    2:  "PPPPPPHHHH",
    3:  "PPPPPPHHHH",
    4:  "HHHPPHHHHH",
    5:  "DDDDDDDDHH",
    6:  "PPPPPHHHHH",
    7:  "PPPPPPHHHH",
    8:  "PPPPPPPPPP",
    9:  "PPPPPSPPSS",
    10: "SSSSSSSSSS",
}

ACTION_NAME = {"H": "hit", "S": "stand", "D": "double", "P": "split"}


def up_index(up):
    return 9 if up == 11 else up - 2


def chart_play(cards, up, can_double, can_split):
    """
    What the printed chart says to do.

    Returns a dict with the move plus a human label for the row, so the UI
    can show you which line of the chart you were on.
    """
    i = up_index(up)
    first_two = len(cards) == 2

    if can_split and first_two and card_value(cards[0]["rank"]) == card_value(cards[1]["rank"]):
        pair = card_value(cards[0]["rank"])
        move = PAIRS[pair][i]
        label = "pair of " + ("aces" if pair == 11 else str(pair) + "s")
        if move == "P":
            return {"move": "P", "row": label, "kind": "pair", "pair": pair, "fallback": False}
        if move == "D":
            return {"move": "D" if can_double else "H", "row": "pair of 5s (played as a hard 10)",
                    "kind": "pair", "pair": pair, "fallback": not can_double}
        return {"move": move, "row": label, "kind": "pair", "pair": pair, "fallback": False}

    total, soft = hand_value(cards)

    if soft and total <= 12:
        return {"move": "H", "row": "soft " + str(total), "kind": "soft",
                "total": total, "fallback": False}

    if soft:
        other = total - 11
        key = "2-3" if other <= 3 else "4-5" if other <= 5 else "6" if other == 6 else "7" if other == 7 else "8+"
        move = SOFT[key][i]
        fallback = False
        if move == "D" and not can_double:
            move = "S" if other == 7 else "H"
            fallback = True
        return {"move": move, "row": "soft %d (A,%d)" % (total, other), "kind": "soft",
                "total": total, "fallback": fallback}

    key = 8 if total <= 8 else total if total <= 11 else 12 if total == 12 else 16 if total <= 16 else 21
    move = HARD[key][i]
    fallback = False
    if move == "D" and not can_double:
        move = "H"
        fallback = True
    return {"move": move, "row": "hard " + str(total), "kind": "hard",
            "total": total, "fallback": fallback}


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
