"""
sim.py — playing thousands of hands in a hurry.

game.py deals one careful hand at a time and works out the exact odds of every
option from the cards actually left. That is the right thing for a trainer and
completely the wrong thing for a simulation — it is a few hundred hands a second
and the analysis tab wants a quarter of a million.

So this is a second, stripped table. Same rules, same chart, same shoe and
penetration, no explanation of anything. Cards are bare integers, decisions are a
dictionary lookup, and nothing is recorded except the money.

What it is for:
  * showing what a run of this game actually looks like, rather than what the
    average says it looks like
  * putting a number on how often a given bankroll does not survive a session
  * showing what your own error rate costs, by playing the same shoe with your
    mistakes in it and again without
"""

import math
import random

import rules as R

HAND_SD = 1.14        # standard deviation of one hand, in bets, flat-betting the chart

# The same figure once you spread your bet, in units of the table minimum.
#
# Spreading raises the swing much faster than it raises the average bet, because
# the big bets are the ones carrying the variance: "steep" averages 2.1 units a
# hand but swings 3.8 of them. Feeding the flat 1.14 into a ruin calculation for
# a spread bettor understates the swing threefold, and every bankroll answer
# that comes out the other side is too small — in the direction that empties it.
# Measured over three million hands each; test_sim.py re-measures and fails if
# these drift.
RAMP_SD = {"flat": 1.15, "mild": 2.01, "steep": 3.79}


def sd_for(ramp):
    """Per-hand standard deviation in units, for a named ramp."""
    return RAMP_SD.get(ramp, HAND_SD)


# What the game costs you a hand, flat-betting the chart, by rule set.
#
# The base is 40 million hands across ten independent shoes: -0.4231% with two
# standard errors of 0.0365, against a published -0.43% for six decks, stand on
# soft 17, double after split, 3:2 and no surrender. Every adjustment below is a
# paired measurement over four million hands on identical shuffles, so the shoe
# cancels and only the rule shows. test_sim.py re-measures them.
#
# There is no point hard-coding "the house edge is half a percent" anywhere: 6:5
# alone more than quadruples it, and that is a table this app lets you sit at.
BASE_EDGE = -0.0042

_RULE_COST = {
    "hit_soft_17": -0.0021,      # published -0.22%
    "no_das": -0.0013,           # published -0.14%
    "six_five": -0.0136,         # published -1.39%
    "resplit_aces": +0.0006,     # published +0.08%
}

# Fewer decks is better for the player. Measured while still playing the
# multi-deck chart, which is what this app deals at every deck count, so the
# single-deck figure understates what a proper single-deck chart would give.
_DECK_COST = {1: +0.0042, 2: +0.0006, 4: +0.0002, 6: 0.0, 8: -0.0014}


def house_edge(rules, decks=None):
    """
    Roughly what this rule set costs you a hand, before your own mistakes.

    An estimate assembled from measured pieces, not a fresh simulation — good to
    about a twentieth of a percent, which is far closer than any fixed constant
    can be once the rules are allowed to move.
    """
    n = int(decks if decks is not None else rules.get("decks", 6))
    edge = BASE_EDGE + _DECK_COST.get(n, -0.0014 if n > 8 else 0.0)
    if rules.get("hit_soft_17"):
        edge += _RULE_COST["hit_soft_17"]
    if not rules.get("das", True):
        edge += _RULE_COST["no_das"]
    if float(rules.get("blackjack_pays", 1.5)) < 1.5:
        edge += _RULE_COST["six_five"]
    if rules.get("resplit_aces"):
        edge += _RULE_COST["resplit_aces"]
    if int(rules.get("max_hands", 4)) < 4:
        edge += -0.0001 * (4 - int(rules.get("max_hands", 4)))
    return edge


# ---------------------------------------------------------------------------
# A shoe of plain integers: 11 is an ace, 10 covers all four ten-ranks.
# ---------------------------------------------------------------------------

def _deck_values(decks):
    out = []
    for _ in range(decks):
        for v in range(2, 10):
            out.extend([v] * 4)
        out.extend([10] * 16)
        out.extend([11] * 4)
    return out


_HILO = {v: (1 if 2 <= v <= 6 else (0 if 7 <= v <= 9 else -1)) for v in range(2, 12)}


def _total(cards):
    """(best total, is soft)."""
    t = sum(cards)
    aces = cards.count(11)
    while t > 21 and aces:
        t -= 10
        aces -= 1
    return t, aces > 0


def _flat_chart(rules):
    """The whole chart as one dict, so a decision is a single lookup."""
    return {(s, r, u): m for s, r, u, m in R.cells_for(rules)}


# the mistake a person actually makes, rather than a random other button
_TYPICAL_ERROR = {"S": "H", "H": "S", "D": "H", "Ds": "S", "P": "H"}


class Sim:
    def __init__(self, rules, decks=6, penetration=0.75, rng=None):
        self.rules = rules
        self.decks = decks
        self.penetration = penetration
        self.rng = rng or random.Random()
        self.chart = _flat_chart(rules)
        self.h17 = bool(rules["hit_soft_17"])
        self.bj = float(rules["blackjack_pays"])
        self.max_hands = int(rules["max_hands"])
        self.das = bool(rules["das"])
        self.resplit_aces = bool(rules["resplit_aces"])
        self.shuffle()

    def shuffle(self):
        self.shoe = _deck_values(self.decks)
        self.rng.shuffle(self.shoe)
        self.dealt = 0
        self.count = 0
        self.cut_at = self.place_cut_card()

    def place_cut_card(self):
        """
        Where the yellow card lands this shoe. Same rule as game.py.

        A dealer puts it in by eye, so it moves from shoe to shoe: the aim is
        the penetration setting, the spread is half a deck either way, and the
        result is that no two shoes run to the same depth. It matters here as
        well as at the table, because a ramp's value depends on how deep the
        count is allowed to run before the shuffle takes it away.
        """
        total = self.decks * 52
        aim = self.penetration * total
        if self.penetration < 0.2:
            return aim
        lo = max(total * 0.40, aim - 26.0)
        hi = min(total - 26.0, aim + 26.0)
        if lo >= hi:
            return max(1.0, min(aim, total - 1.0))
        return self.rng.triangular(lo, hi, min(max(aim, lo), hi))

    def draw(self):
        if not self.shoe:
            self.shuffle()
        v = self.shoe.pop()
        self.dealt += 1
        self.count += _HILO[v]
        return v

    def true_count(self):
        left = max(0.25, (self.decks * 52 - self.dealt) / 52.0)
        return self.count / left

    def cut_card(self):
        return self.dealt >= self.cut_at

    # ---------------- one decision ----------------
    def decide(self, cards, up, can_double, can_split, error_rate, miss_rates):
        total, soft = _total(cards)
        if can_split and len(cards) == 2 and cards[0] == cards[1]:
            section, row = "pair", cards[0]
        elif soft:
            section, row = "soft", max(2, min(9, total - 11))
        else:
            section, row = "hard", max(5, min(21, total))
        code = self.chart.get((section, row, up), "S")

        # does this player get it wrong here?
        rate = error_rate
        if miss_rates is not None:
            rate = miss_rates.get((section, row, up), error_rate)
        if rate and self.rng.random() < rate:
            code = _TYPICAL_ERROR.get(code, "H")

        if code == "D":
            return "D" if can_double else "H"
        if code == "Ds":
            return "D" if can_double else "S"
        return code

    # ---------------- one round ----------------
    def round(self, bet, error_rate=0.0, miss_rates=None, bankroll=None):
        """
        Play one round. Returns the net change to the stack, in money.

        `bankroll` caps how many extra bets you can put out — you cannot split
        or double money you do not have, which is exactly when it hurts most.
        """
        spare = (bankroll - bet) if bankroll is not None else float("inf")
        dealer = [self.draw(), self.draw()]
        hands = [[self.draw(), self.draw()]]
        bets = [bet]
        split_ace = [False]
        done = [False]

        d_total, _ = _total(dealer)
        p_total, _ = _total(hands[0])
        if d_total == 21 or p_total == 21:
            if p_total == 21 and d_total == 21:
                return 0.0
            if p_total == 21:
                return bet * self.bj
            return -bet

        i = 0
        guard = 0
        while i < len(hands):
            guard += 1
            if guard > 40:
                break
            if len(hands[i]) == 1:                 # a fresh half of a split
                hands[i].append(self.draw())
                if split_ace[i]:
                    done[i] = not (self.resplit_aces and hands[i][0] == hands[i][1]
                                   and len(hands) < self.max_hands and spare >= bets[i])
                elif _total(hands[i])[0] >= 21:
                    done[i] = True
            while not done[i]:
                cards = hands[i]
                total, _ = _total(cards)
                if total >= 21:
                    break
                first_two = len(cards) == 2
                can_double = (first_two and not split_ace[i] and spare >= bets[i]
                              and (self.das or len(hands) == 1))
                can_split = (first_two and cards[0] == cards[1]
                             and len(hands) < self.max_hands and spare >= bets[i]
                             and not (split_ace[i] and not self.resplit_aces))
                move = self.decide(cards, dealer[0], can_double, can_split,
                                   error_rate, miss_rates)
                if move == "S":
                    break
                if move == "D":
                    spare -= bets[i]
                    bets[i] *= 2
                    cards.append(self.draw())
                    break
                if move == "P":
                    spare -= bets[i]
                    moved = cards.pop()
                    is_ace = cards[0] == 11
                    split_ace[i] = is_ace
                    hands.insert(i + 1, [moved])
                    bets.insert(i + 1, bets[i])
                    split_ace.insert(i + 1, is_ace)
                    done.insert(i + 1, False)
                    cards.append(self.draw())
                    if is_ace and not (self.resplit_aces and cards[0] == cards[1]
                                       and len(hands) < self.max_hands):
                        break
                    continue
                cards.append(self.draw())          # hit
            done[i] = True
            i += 1

        # the dealer only plays if something of yours is still alive
        if any(_total(h)[0] <= 21 for h in hands):
            while True:
                t, s = _total(dealer)
                if t < 17 or (t == 17 and s and self.h17):
                    dealer.append(self.draw())
                else:
                    break

        d_total, _ = _total(dealer)
        net = 0.0
        for cards, stake in zip(hands, bets):
            t, _ = _total(cards)
            if t > 21:
                net -= stake
            elif d_total > 21 or t > d_total:
                net += stake
            elif t < d_total:
                net -= stake
        return net


# ---------------------------------------------------------------------------
# Bet ramps
# ---------------------------------------------------------------------------

RAMPS = {
    "flat": [(99, 1)],
    "mild": [(1, 1), (2, 2), (3, 3), (99, 4)],
    "steep": [(1, 1), (2, 2), (3, 4), (4, 8), (99, 12)],
}


def _units_for(ramp, tc):
    for threshold, units in RAMPS.get(ramp, RAMPS["flat"]):
        if tc <= threshold:
            return units
    return 1


# ---------------------------------------------------------------------------
# One session, and many
# ---------------------------------------------------------------------------

CURVE_POINTS = 160          # how many samples of the equity curve we keep


def run_session(rules, bankroll, table_min, hands, decks=6, penetration=0.75,
                ramp="flat", error_rate=0.0, miss_rates=None, seed=None,
                table_max=None):
    """
    Play one session until the hands run out or the money does.

    The curve is downsampled to a fixed number of points so a hundred thousand
    hands and a hundred hands both draw the same size of picture.
    """
    rng = random.Random(seed)
    sim = Sim(rules, decks, penetration, rng)
    stack = float(bankroll)
    ceiling = float(table_max or table_min * 100)

    peak = trough = stack
    max_dd = 0.0
    wagered = 0.0
    played = 0
    u_sum = u_sq = 0.0          # per-hand result in units, for the realised swing
    curve = []
    every = max(1, hands // CURVE_POINTS)

    for n in range(hands):
        if sim.cut_card():
            sim.shuffle()
        units = _units_for(ramp, sim.true_count())
        bet = min(table_min * units, ceiling, stack)
        if bet < table_min:
            break                                  # busted out
        wagered += bet
        delta = sim.round(bet, error_rate, miss_rates, bankroll=stack)
        stack += delta
        u = delta / table_min
        u_sum += u
        u_sq += u * u
        played += 1
        peak = max(peak, stack)
        trough = min(trough, stack)
        max_dd = max(max_dd, peak - stack)
        if n % every == 0:
            curve.append(round(stack, 2))

    curve.append(round(stack, 2))
    return {
        "final": round(stack, 2),
        "start": float(bankroll),
        "net": round(stack - bankroll, 2),
        "hands": played,
        "requested": hands,
        "busted": played < hands,
        "peak": round(peak, 2),
        "trough": round(trough, 2),
        "max_drawdown": round(max_dd, 2),
        "wagered": round(wagered, 2),
        "edge": ((stack - bankroll) / wagered) if wagered else None,
        "curve": curve,
        "u_sum": u_sum, "u_sq": u_sq,     # pooled by run_many, then dropped
    }


def _quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def run_many(runs=20, **kw):
    """
    Several independent sessions of the same game.

    Independent is the point. One run tells you nothing — it is a single sample
    from a distribution wide enough to contain both "up four hundred" and "lost
    the lot in an hour", and people generalise from whichever one they got.
    """
    runs = max(1, min(200, int(runs)))
    base = kw.pop("seed", None)
    seed0 = random.randrange(1 << 30) if base is None else int(base)

    sessions = [run_session(seed=seed0 + i * 7919, **kw) for i in range(runs)]

    finals = sorted(s["final"] for s in sessions)
    nets = sorted(s["net"] for s in sessions)
    dds = sorted(s["max_drawdown"] for s in sessions)
    busted = sum(1 for s in sessions if s["busted"])
    wagered = sum(s["wagered"] for s in sessions)
    net_total = sum(s["net"] for s in sessions)

    # a band across all the curves at each sample point
    width = max(len(s["curve"]) for s in sessions)
    bands = []
    for i in range(width):
        col = sorted(s["curve"][i] if i < len(s["curve"]) else s["curve"][-1]
                     for s in sessions)
        bands.append({
            "lo": round(_quantile(col, 0.10), 2),
            "mid": round(_quantile(col, 0.50), 2),
            "hi": round(_quantile(col, 0.90), 2),
        })

    # the swing this run actually produced, pooled across every hand dealt
    hands_played = sum(s["hands"] for s in sessions)
    u_sum = sum(s["u_sum"] for s in sessions)
    u_sq = sum(s["u_sq"] for s in sessions)
    sd_per_hand = (math.sqrt(max(0.0, u_sq / hands_played - (u_sum / hands_played) ** 2))
                   if hands_played > 1 else None)
    # Drift per hand, in units. NOT the same as `edge` below, which is per unit
    # wagered: spreading your bet averages about two units a hand, so the two
    # differ by that factor. ruin_within wants this one, in the same units as sd.
    edge_per_hand = (u_sum / hands_played) if hands_played else None

    drop = ("curve", "u_sum", "u_sq")
    start = sessions[0]["start"]
    return {
        "runs": runs,
        "start": start,
        "sd_per_hand": round(sd_per_hand, 4) if sd_per_hand else None,
        "edge_per_hand": round(edge_per_hand, 6) if edge_per_hand is not None else None,
        "sessions": [{k: v for k, v in s.items() if k not in drop} for s in sessions],
        "curves": [s["curve"] for s in sessions],
        "bands": bands,
        "busted": busted,
        "bust_rate": busted / runs,
        "median_final": round(_quantile(finals, 0.5), 2),
        "median_net": round(_quantile(nets, 0.5), 2),
        "mean_net": round(net_total / runs, 2),
        "best": round(finals[-1], 2),
        "worst": round(finals[0], 2),
        "p10": round(_quantile(finals, 0.10), 2),
        "p90": round(_quantile(finals, 0.90), 2),
        "median_drawdown": round(_quantile(dds, 0.5), 2),
        "worst_drawdown": round(dds[-1], 2),
        "up_sessions": sum(1 for s in sessions if s["net"] > 0),
        "edge": (net_total / wagered) if wagered else None,
        "wagered": round(wagered, 2),
        "histogram": _histogram(finals, start),
    }


def _histogram(finals, start, buckets=18):
    lo, hi = min(finals), max(finals)
    if hi - lo < 1e-9:
        return {"lo": lo, "hi": hi, "counts": [len(finals)], "start": start}
    step = (hi - lo) / buckets
    counts = [0] * buckets
    for v in finals:
        idx = min(buckets - 1, int((v - lo) / step))
        counts[idx] += 1
    return {"lo": round(lo, 2), "hi": round(hi, 2), "step": round(step, 2),
            "counts": counts, "start": start}


# ---------------------------------------------------------------------------
# The closed-form side: how much money do you need to last?
# ---------------------------------------------------------------------------

def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def ruin_within(units, hands, edge=-0.005, sd=HAND_SD):
    """
    Chance of going broke at some point during `hands` hands.

    First-passage probability for a random walk with drift, which is the usual
    approximation. Note it is the chance of touching zero at *any* point, not
    the chance of finishing below it — those are very different numbers and the
    first one is the one that ends your evening.
    """
    if units <= 0:
        return 1.0
    if hands <= 0:
        return 0.0
    mu = edge * hands
    sig = sd * math.sqrt(hands)
    if sig <= 0:
        return 0.0 if units > -mu else 1.0
    a = _phi((-units - mu) / sig)
    try:
        scale = math.exp(max(-700.0, min(700.0, -2.0 * edge * units / (sd * sd))))
    except OverflowError:
        scale = float("inf")
    b = scale * _phi((-units + mu) / sig)
    return max(0.0, min(1.0, a + b))


def bankroll_for(table_min, hands, ruin_target=0.05, edge=-0.005, sd=HAND_SD):
    """
    Smallest bankroll that survives `hands` hands with the given chance of ruin.

    Found by bisection on the formula above, because inverting it in closed form
    is not worth the algebra.
    """
    hands = max(1, int(hands))
    ruin_target = min(0.99, max(0.001, float(ruin_target)))
    lo, hi = 1.0, 10.0
    while ruin_within(hi, hands, edge, sd) > ruin_target and hi < 1e6:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        if ruin_within(mid, hands, edge, sd) > ruin_target:
            lo = mid
        else:
            hi = mid
    units = hi
    return {
        "units": round(units, 1),
        "bankroll": round(units * table_min, 2),
        "table_min": table_min,
        "hands": hands,
        "ruin_target": ruin_target,
        "edge": edge,
        "expected_loss": round(-edge * hands * table_min, 2),
        "swing": round(sd * math.sqrt(hands) * table_min, 2),
        "hours": round(hands / 80.0, 1),          # about 80 hands an hour at a full table
    }


def survival_table(table_min, bankroll, edge=-0.005, sd=HAND_SD,
                   marks=(50, 100, 200, 400, 800, 1600)):
    """
    Chance of still having money after this many hands.

    `edge` is the drift per hand in units, not the edge per unit wagered — for a
    spread bettor those differ by the average bet, which is about two.

    `sd` has to be the swing of the bet you are actually making. Pass the flat
    figure for a spread bettor and the table reads far too kindly: at a steep
    ramp the real swing is three times 1.14, and the answer stops being an
    estimate and becomes a wrong one.

    You are out when you cannot cover the minimum, not when you reach zero, so
    the barrier sits one unit up from the bottom.
    """
    units = (bankroll / table_min - 1.0) if table_min else 0
    return [{"hands": n, "hours": round(n / 80.0, 1),
             "survive": round(1.0 - ruin_within(units, n, edge, sd), 4),
             "expected": round(bankroll + edge * n * table_min, 2),
             "sd": round(sd, 3)}
            for n in marks]
