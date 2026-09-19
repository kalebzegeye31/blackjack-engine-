"""
count.py — Hi-Lo counting: the count itself, the index plays, and the bet ramp.

Three jobs, and one thing this module deliberately does not do.

  1. Keep a Hi-Lo running count and turn it into a true count.
  2. Hold the index plays — the handful of hands where a big count changes the
     right move — and say which move the count actually calls for.
  3. Say how much to bet at a given count.

What it does not do is decide anything about a hand on its own. engine.py still
computes every expected value from the cards actually left, and rules.py still
holds basic strategy. This module only says "at this count, the book departs
from the chart here, and this is what it says instead".

Where the numbers came from
---------------------------
The index numbers below are the published Illustrious 18 for six decks, dealer
standing on all 17s. They are not copied on trust: each one was re-derived from
this repository's own engine by Monte Carlo. Six thousand shoes were dealt card
by card; every point where the true count sat near an integer, the composition
of what remained was recorded; those compositions were averaged per count and
fed to engine.Odds to find the exact true count at which each decision flips.

That crossing point is stored next to each index as `crossing`, so the app can
show its working rather than asserting a number. Sixteen of the eighteen came
out on the published value. Two did not:

    12 v 3    crossing +1.41, published index 2
    11 v A    crossing +1.53, published index 1

Both sit within half a point of the boundary, which is to say the expected value
either side is nearly identical and the rounding could fall either way. The
published value is used for both, because the point of an index is that you can
remember it at a table, and disagreeing with every book to chase a hundredth of
a percent is not worth the confusion.

Surrender indices (the Fab 4) are not here, because this game has no surrender.
"""

import engine as E
import rules as R


# ---------------------------------------------------------------------------
# The count
# ---------------------------------------------------------------------------

def tag(card_value):
    """Hi-Lo tag for a card: 2-6 are +1, 7-9 are 0, tens and aces are -1."""
    return E.hilo(card_value)


def true_count(running, decks_left):
    """
    Running count divided by decks remaining.

    A running count of +6 means something very different with one deck left than
    with five. Dividing is what makes the number comparable, and every index
    below is expressed in these units.
    """
    if decks_left <= 0:
        return 0.0
    return running / float(decks_left)


def decks_left(cards_unseen):
    """Decks still to come, to the nearest quarter — how a real player estimates."""
    raw = cards_unseen / 52.0
    return max(0.25, round(raw * 4) / 4.0)


# ---------------------------------------------------------------------------
# The Illustrious 18
#
# `at_or_above` is what to do when the true count reaches `index`; `below` is
# what the basic strategy chart already says, repeated here so a wrong answer
# can be explained in both directions. `crossing` is where this engine puts the
# actual flip, kept for showing the working.
# ---------------------------------------------------------------------------

_I18 = [
    # the single most valuable one, and the only one that is not a playing decision
    dict(key="insurance", kind="insurance", up=11, index=3, crossing=3.45,
         at_or_above="take", below="decline", rank=1,
         why="Insurance is a bet that the hole card is a ten. It needs to come in "
             "more than a third of the time to pay, and a high count is exactly the "
             "condition where the shoe is rich enough in tens for that to be true."),

    dict(key="h16v10", kind="hard", total=16, up=10, index=0, crossing=0.09, rank=2,
         at_or_above="S", below="H",
         why="One of the hands you face most often against a ten, and the closest "
             "call on the whole chart — standing and hitting are within a thousandth "
             "of a bet on a fresh shoe, which is why the smallest push tips it. Once "
             "the shoe is even slightly ten-rich, the extra chance of breaking "
             "outweighs the extra chance of improving."),

    dict(key="h15v10", kind="hard", total=15, up=10, index=4, crossing=4.31, rank=3,
         at_or_above="S", below="H",
         why="Same logic as 16 against a ten, but 15 has one more safe card to "
             "catch, so it takes a much richer shoe before standing wins."),

    dict(key="pTTv5", kind="pair", pair=10, up=5, index=5, crossing=4.93, rank=4,
         at_or_above="P", below="S",
         why="Breaking a twenty is almost always wrong. At a count this high the "
             "dealer busts often enough, and your split hands catch tens often "
             "enough, that two hands beat one. Conspicuous at a real table."),

    dict(key="pTTv6", kind="pair", pair=10, up=6, index=4, crossing=4.40, rank=5,
         at_or_above="P", below="S",
         why="As with a 5 up, but the 6 is the dealer's worst card, so it takes "
             "slightly less of a count to justify it."),

    dict(key="h10v10", kind="hard", total=10, up=10, index=4, crossing=3.91, rank=6,
         at_or_above="D", below="H",
         why="The whole case is the card you are buying: a shoe rich enough that a "
             "ten is likely, turning this into twenty. It is not that the dealer "
             "starts breaking — from a ten they break slightly LESS as the count "
             "climbs, because they are likelier to hold twenty outright than a stiff "
             "hand they have to draw to."),

    dict(key="h12v3", kind="hard", total=12, up=3, index=2, crossing=1.41, rank=7,
         at_or_above="S", below="H",
         why="Twelve against the small cards is the block of the chart the count "
             "moves most. As tens pile up, drawing to a 12 gets more dangerous and "
             "the dealer's 3 gets more fragile."),

    dict(key="h12v2", kind="hard", total=12, up=2, index=3, crossing=3.15, rank=8,
         at_or_above="S", below="H",
         why="The same flip as against a 3, but a 2 is the strongest of the dealer's "
             "weak cards, so it takes a bigger count."),

    dict(key="h11vA", kind="hard", total=11, up=11, index=1, crossing=1.53, rank=9,
         at_or_above="D", below="H",
         why="Against an ace the chart hits an 11 at this table. A positive count "
             "tips it back to doubling, because the ten you want is more likely."),

    dict(key="h9v2", kind="hard", total=9, up=2, index=1, crossing=0.97, rank=10,
         at_or_above="D", below="H",
         why="Nine against a 2 is the cell just outside the doubling row. A small "
             "positive count is enough to pull it in."),

    dict(key="h10vA", kind="hard", total=10, up=11, index=4, crossing=3.83, rank=11,
         at_or_above="D", below="H",
         why="Doubling into an ace is the most aggressive thing on this list and "
             "needs a genuinely rich shoe behind it."),

    dict(key="h9v7", kind="hard", total=9, up=7, index=3, crossing=3.48, rank=12,
         at_or_above="D", below="H",
         why="A 7 is not a weak card. It takes a strong count before buying one "
             "card on a 9 against it is worth a second bet."),

    dict(key="h16v9", kind="hard", total=16, up=9, index=5, crossing=4.72, rank=13,
         at_or_above="S", below="H",
         why="The third of the 16s. A 9 is weaker than a ten, so it takes much more "
             "of a count before standing becomes right."),

    dict(key="h13v2", kind="hard", total=13, up=2, index=-1, crossing=-1.06, rank=14,
         at_or_above="S", below="H",
         why="A negative index: this one tells you when to STOP standing. In a "
             "ten-poor shoe a 13 is safer to draw to and the dealer's 2 is less "
             "likely to break."),

    dict(key="h12v4", kind="hard", total=12, up=4, index=0, crossing=-0.18, rank=15,
         at_or_above="S", below="H",
         why="Basic strategy already stands here. Below zero it stops being right, "
             "because the dealer's 4 breaks less often in a low shoe."),

    dict(key="h12v5", kind="hard", total=12, up=5, index=-2, crossing=-1.73, rank=16,
         at_or_above="S", below="H",
         why="Another negative index. It takes a fairly low count before giving up "
             "on the dealer's 5 breaking."),

    dict(key="h12v6", kind="hard", total=12, up=6, index=-1, crossing=-1.34, rank=17,
         at_or_above="S", below="H",
         why="You hold on to standing well below zero here, because a 6 is the card "
             "the dealer breaks from most. Note it gives up marginally sooner than "
             "the 5 does, not later, which looks the wrong way round — the two are "
             "close enough that this is simply where the numbers fall."),

    dict(key="h13v3", kind="hard", total=13, up=3, index=-2, crossing=-2.44, rank=18,
         at_or_above="S", below="H",
         why="The last of the eighteen and the least valuable. It only matters in a "
             "shoe that has gone properly cold."),
]

BY_KEY = {p["key"]: p for p in _I18}
ILLUSTRIOUS_18 = sorted(_I18, key=lambda p: p["rank"])


def lookup(hand_kind, total, pair, up, can_split=False, chart_move=None):
    """
    The index play for this situation, or None if the count never changes it.

    `hand_kind` is what rules/engine decided the hand is: "hard", "soft" or
    "pair". Soft hands have no index plays in this set.

    `chart_move` is what decides it for pairs, and getting this wrong is not
    cosmetic. A hand you are going to split is not a hard total: a pair of 8s
    is never played as a 16, so the 16 v 10 index does not belong to it — that
    index is for a hard 16 you cannot break up. Without this the app told a
    player to hit 8,8 against a ten, which no count ever justifies.

    A pair of 5s is the opposite case. The chart never splits it, so it really
    is a hard 10 and the hard 10 indices apply to it properly. Same for a pair
    you are not allowed to split, which arrives here as a hard total anyway.
    """
    if hand_kind == "pair" and can_split:
        if pair == 10:
            # tens are their own index: whether a count is high enough to break
            # a twenty, which is the reverse question from the hard totals
            for p in _I18:
                if p["kind"] == "pair" and p["pair"] == 10 and p["up"] == up:
                    return p
            return None
        if chart_move == "P":
            return None
    if hand_kind == "soft":
        return None
    # everything else is judged on the total, which covers pairs the chart plays
    # as a hard total (5,5 is a ten) and hands that grew past two cards
    for p in _I18:
        if p["kind"] == "hard" and p["total"] == total and p["up"] == up:
            return p
    return None


def insurance_play(tc):
    """Whether to take insurance at this true count, and the entry behind it."""
    p = BY_KEY["insurance"]
    return (tc >= p["index"]), p


def correct_move(chart_move, hand_kind, total, pair, up, tc, can_split=False,
                 can_double=True):
    """
    What a counter should actually do here.

    Returns (move, entry, deviated). `entry` is the index play if one applies,
    so a wrong answer can be explained with the number behind it. `deviated` is
    True only when the count genuinely pulls the move off the chart.

    If the index calls for a move the table won't allow — doubling a hand you
    cannot afford to double — the chart move stands, because an index play you
    cannot make is not a play.
    """
    entry = lookup(hand_kind, total, pair, up, can_split, chart_move)
    if entry is None:
        return chart_move, None, False

    want = entry["at_or_above"] if tc >= entry["index"] else entry["below"]
    if want == "D" and not can_double:
        return chart_move, entry, False
    if want == "P" and not can_split:
        return chart_move, entry, False

    # Which side of the index is the deviation depends on the sign of it. For
    # 16 v 10 the chart hits and a high count makes you stand; for 13 v 2 the
    # chart stands and a low count makes you hit. So the branch is compared
    # against the chart rather than assumed to be one or the other.
    return want, entry, (want != chart_move)


# ---------------------------------------------------------------------------
# Betting
#
# A counter makes money by betting more when the count is high, not by playing
# the index plays — those are worth a fraction of a percent. The spread is the
# whole game, and it is also the thing that gets you noticed.
# ---------------------------------------------------------------------------

DEFAULT_SPREAD = 8      # top bet, in units, at a high count


def bet_units(tc, spread=DEFAULT_SPREAD):
    """
    Units to bet at this true count, on the standard ramp.

    One unit until the count is genuinely positive, then roughly (true count − 1)
    units, capped at the spread. Below +1 you have no edge and the only correct
    bet is the smallest one you are allowed to make.
    """
    if tc < 1:
        return 1
    return max(1, min(int(spread), int(tc - 1) + 1))


def edge_at(tc):
    """Rough player edge at a given true count. Half a percent per point above +1."""
    return E.edge_at(tc)


def judge_ramp(units_bet, tc, spread=DEFAULT_SPREAD):
    """
    Grade a bet against the ramp.

    Deliberately banded rather than exact: betting three units when the ramp
    wants four is not a mistake worth flagging, and a trainer that nags about
    one unit teaches you to ignore it. What matters is the shape — small when
    the count is dead, big when it is live — and, above all, not spreading so
    wide you get backed off.
    """
    want = bet_units(tc, spread)
    off = units_bet - want
    if abs(off) <= 1:
        return {"want": want, "off": off, "level": "ok",
                "text": "About right for a true count of %+.1f." % tc}
    if off < 0:
        return {"want": want, "off": off, "level": "warn",
                "text": "The count is %+.1f, which wants about %d units. You bet %d. "
                        "Playing the indices perfectly and betting flat earns almost "
                        "nothing — the spread is where a counter's money comes from."
                        % (tc, want, units_bet)}
    return {"want": want, "off": off, "level": "warn",
            "text": "You bet %d units at a true count of %+.1f, which wants about %d. "
                    "Overbetting a small edge is how bankrolls die, and a wild spread "
                    "is the single easiest thing for a pit to spot."
                    % (units_bet, tc, want)}


# ---------------------------------------------------------------------------
# Grading the count itself
# ---------------------------------------------------------------------------

def _decks(n):
    """'1 deck', '2.5 decks' — the singular only when it really is one."""
    txt = ("%.2f" % float(n)).rstrip("0").rstrip(".")
    return txt + (" deck" if float(n) == 1 else " decks")


#: how far out a deck estimate can be before it starts moving decisions
DECK_TOLERANCE = 0.5


def grade_estimate(said_decks, actual_decks, running):
    """
    Mark an estimate of how many decks are left, and the true count that falls
    out of it.

    This is the half of counting that nobody practises. Keeping a running count
    is arithmetic and you either can or cannot do it; judging the discard tray
    is a physical guess made across a table, and it is where most true counts go
    wrong. An estimate half a deck out is fine. A whole deck out will flip index
    plays and mis-size bets, and it does it silently, because the running count
    it is dividing was perfectly correct.
    """
    try:
        said_decks = float(said_decks)
    except (TypeError, ValueError):
        return {"ok": False, "said": None, "actual": actual_decks, "off": None,
                "tc_said": None, "tc_actual": true_count(running, actual_decks),
                "tc_off": None, "text": "That wasn't a number of decks."}
    if said_decks <= 0:
        said_decks = 0.25

    off = said_decks - actual_decks
    tc_said = true_count(running, said_decks)
    tc_actual = true_count(running, actual_decks)
    tc_off = tc_said - tc_actual
    close = abs(off) <= DECK_TOLERANCE

    if close:
        text = ("Deck estimate good: you said %s, it was %s."
                % (_decks(said_decks), _decks(actual_decks)))
    else:
        text = ("You put the shoe at %s and it was %s. That is %s out, "
                "which turns a running count of %+d into a true count of %+.1f when it "
                "is really %+.1f — enough to move an index play."
                % (_decks(said_decks), _decks(actual_decks), _decks(abs(off)),
                   running, tc_said, tc_actual))
    return {"ok": close, "said": said_decks, "actual": actual_decks, "off": round(off, 2),
            "tc_said": round(tc_said, 2), "tc_actual": round(tc_actual, 2),
            "tc_off": round(tc_off, 2), "text": text}


def grade_count(said, actual):
    """
    Mark an answer to "what is the running count?".

    Exact or nothing. A count that is close is still a wrong count: the error
    does not wash out, it rides with you for the rest of the shoe and quietly
    corrupts every true count you derive from it.
    """
    try:
        said = int(said)
    except (TypeError, ValueError):
        return {"ok": False, "said": None, "actual": actual, "off": None,
                "text": "That wasn't a number."}
    off = said - actual
    if off == 0:
        return {"ok": True, "said": said, "actual": actual, "off": 0,
                "text": "Correct. Running count %+d." % actual}
    return {"ok": False, "said": said, "actual": actual, "off": off,
            "text": "You said %+d. It is %+d, so you are %+d out. An error in the "
                    "running count does not average away — it follows you to the "
                    "shuffle and skews every true count you work out from here."
                    % (said, actual, off)}
