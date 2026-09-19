"""
test_game.py — the table deals the way a real one does.

These are the rules that are easy to get subtly wrong and impossible to notice
from the outside once they are. Every one of them was checked against how a
dealer actually behaves, not against what the old code happened to do.

    python3 test_game.py
"""

import random

import engine as E
import rules as R
from game import Table

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %-58s %s%s" % (name, "ok" if cond else "FAIL", ("  " + detail) if detail else ""))


def ranks(hand):
    return [c["rank"] for c in hand["cards"]]


def card(rank):
    return {"rank": rank, "suit": "♠", "red": False}


def stack(table, seq):
    """
    Force the next cards off the shoe.

    draw() pops from the end, so the sequence goes on reversed. The tail matters
    too: the table reshuffles rather than deal off the bottom, so the rigged
    cards sit on top of a deep pile of filler that no assertion depends on.
    """
    filler = [card(r) for r in ["4", "9", "3", "7", "2", "8", "5", "6"] * 8]
    table.shoe = filler + [card(r) for r in seq][::-1]


def rigged(seq, **cfg):
    """A table with no other players and a known shoe."""
    conf = {"others": 0, "table_min": 10, "decks": 6}
    conf.update(cfg)
    t = Table(config=conf, bankroll=1000.0)
    t.new_round()
    t.bet = 10.0
    t.bankroll -= 10.0
    stack(t, seq)
    t.deal()
    return t


print("\nsplitting")

# you: 8,8   dealer: 9 up, 7 hole.  Then 3 to the first half, 10 to the second.
t = rigged(["8", "9", "8", "7", "3", "10", "6"])
t.act("P")
check("split leaves the second hand face down with one card",
      len(t.hands) == 2 and len(t.hands[0]["cards"]) == 2 and len(t.hands[1]["cards"]) == 1)
check("the first hand is the one you are still playing",
      t.active == 0 and ranks(t.hands[0]) == ["8", "3"])
check("the second hand has not been dealt to yet", ranks(t.hands[1]) == ["8"])

t.act("S")   # stand on 11 -- bad play, but it ends hand one
check("standing on hand one deals hand two its second card",
      len(t.hands[1]["cards"]) == 2 and ranks(t.hands[1]) == ["8", "10"], str(ranks(t.hands[1])))
check("play moves to hand two", t.active == 1 and t.phase == "play")

print("\nre-splitting")

# 8,8 -> split -> another 8 arrives on hand one -> split again
t = rigged(["8", "9", "8", "7", "8", "4", "10", "10", "6"])
t.act("P")
check("a third eight on the first hand can be split again", t.can_split(t.hands[0]))
t.act("P")
check("re-split inserts the new hand next in line, not last",
      len(t.hands) == 3 and ranks(t.hands[1]) == ["8"] and ranks(t.hands[2]) == ["8"])
check("only the hand in play was dealt to",
      len(t.hands[0]["cards"]) == 2 and len(t.hands[1]["cards"]) == 1
      and len(t.hands[2]["cards"]) == 1)
t.act("S"); t.act("S"); t.act("S")
check("four hands is the limit", len(t.hands) <= 4)

print("\nsplit aces")

t = rigged(["A", "9", "A", "7", "5", "6", "8"])
t.act("P")
check("a split ace gets exactly one card and is finished",
      t.hands[0]["done"] and len(t.hands[0]["cards"]) == 2)
check("the second split ace is dealt only when its turn comes, then also finished",
      len(t.hands[1]["cards"]) == 2 and t.phase == "settled")
check("21 on a split ace is not a blackjack",
      all(h["result"] != "blackjack" for h in t.hands))

t = rigged(["A", "9", "A", "7", "A", "5", "6", "8"], resplit_aces=True)
t.act("P")
check("re-split aces is off by default and on when the house allows it",
      len(t.hands) == 2 and t.can_split(t.hands[0]))
check("but a split ace still cannot be drawn to", not t.can_hit(t.hands[0]))
check("and cannot be doubled either", not t.can_double(t.hands[0]))

t = rigged(["8", "9", "8", "7", "3", "10", "6"])
t.act("P")
check("an ordinary split hand can of course be hit", t.can_hit(t.hands[0]))

print("\ndoubling")

t = rigged(["5", "9", "6", "7", "9", "6"])
check("you may double your first two cards", t.can_double(t.hands[0]))
t.act("H")
check("you may not double after taking a card", not t.can_double(t.hands[0]))

t = rigged(["8", "9", "8", "7", "3", "10", "6"], das=True)
t.act("P")
check("double after split allowed when the house allows it", t.can_double(t.hands[0]))

t = rigged(["8", "9", "8", "7", "3", "10", "6"], das=False)
t.act("P")
check("double after split refused when the house forbids it", not t.can_double(t.hands[0]))
check("and the chart stops splitting low pairs when it does",
      R.chart_move({"hit_soft_17": False, "das": False}, "pair", 3, 2) == "H"
      and R.chart_move({"hit_soft_17": False, "das": True}, "pair", 3, 2) == "P")

t = rigged(["5", "9", "6", "7", "9", "6"])
t.bankroll = 5.0
check("you cannot double what you cannot cover", not t.can_double(t.hands[0]))

print("\nblackjack and the dealer's hole card")

t = rigged(["A", "9", "K", "7", "4"])
check("a natural is paid at once and the round is over", t.phase == "settled"
      and t.hands[0]["result"] == "blackjack")
check("3:2 pays one and a half", abs(t.hands[0]["net"] - 15.0) < 1e-9, str(t.hands[0]["net"]))

t = rigged(["A", "9", "K", "7", "4"], blackjack_pays=1.2)
check("a 6:5 table pays one and a fifth", abs(t.hands[0]["net"] - 12.0) < 1e-9,
      str(t.hands[0]["net"]))

t = rigged(["10", "10", "9", "A", "4"])
check("the dealer peeks under a ten and the hand ends there",
      t.phase == "settled" and t.hands[0]["result"] == "lose")

# dealer showing the ten, not the ace, so the hand is not interrupted by insurance
t = rigged(["A", "K", "K", "A", "4"])
check("two naturals push", t.phase == "settled" and t.hands[0]["result"] == "push")
check("and neither side is paid", abs(t.hands[0]["net"]) < 1e-9 and t.bankroll == 1000.0)

t = rigged(["A", "A", "K", "9", "4"])
check("an ace showing stops for insurance before anything is settled",
      t.phase == "insurance")
check("holding a natural against it, the offer is even money", t.even_money)
t.insurance(False)
check("declining pays the natural as normal", t.hands[0]["result"] == "blackjack")

print("\nthe dealer's own hand")

# dealer 6 up, ace in the hole -- a soft 17, and no insurance to get in the way
t = rigged(["10", "6", "6", "A", "4"], hit_soft_17=False)
t.act("S")
check("stands on soft 17 when the house says so", E.hand_value(t.dealer)[0] == 17
      and len(t.dealer) == 2, str(E.hand_value(t.dealer)))

t = rigged(["10", "6", "6", "A", "4"], hit_soft_17=True)
t.act("S")
check("hits soft 17 when the house says so", E.hand_value(t.dealer)[0] == 21
      and len(t.dealer) == 3, str(E.hand_value(t.dealer)))

t = rigged(["10", "9", "6", "7", "K"])
t.act("H")   # 16 + K = bust
check("the dealer does not draw when every hand you hold has busted",
      len(t.dealer) == 2 and t.phase == "settled")
check("but the hole card is still turned over", not t.hole_hidden)

print("\nthe shoe")

t = rigged(["5", "9", "6", "7", "9", "6"])
before = t.running_count
check("the hole card is not counted while it is face down",
      before == E.hilo(5) + E.hilo(6) + E.hilo(9))
t.act("S")
check("and is counted the moment it is revealed",
      t.running_count == before + E.hilo(7) + sum(
          E.hilo(E.card_value(c["rank"])) for c in t.dealer[2:]))

t = Table(config={"others": 0, "penetration": 0.5, "decks": 1}, bankroll=1000.0)
random.seed(5)
seen_shuffle = False
for _ in range(80):
    t.new_round()
    before_dealt = t.dealt
    t.bet = 10.0
    t.bankroll -= 10.0
    t.deal()
    if before_dealt == 0 and t.dealt > 0:
        seen_shuffle = True
    guard = 0
    while t.phase in ("play", "insurance"):
        if t.phase == "insurance":
            t.insurance(False)
            continue
        hand = t.hands[t.active]
        play = E.chart_play(hand["cards"], E.card_value(t.dealer[0]["rank"]),
                            t.can_double(hand), t.can_split(hand), t.rules)
        t.act(play["move"])
        guard += 1
        assert guard < 40, "a round never finished"
    assert t.dealt <= t.config["decks"] * 52, "dealt more cards than the shoe holds"
check("a round always reaches a settlement", True)
check("the shoe reshuffles at the cut card, never mid-round", seen_shuffle)

print("\nmoney")

t = rigged(["8", "9", "8", "7", "3", "10", "6"])
start = t.bankroll
t.act("P")
check("splitting takes a second bet off your stack", abs(t.bankroll - (start - 10.0)) < 1e-9)

# 5,6 = 11 doubled into a 9 for 20; dealer 9,7 draws a 6 and busts
t = rigged(["5", "9", "6", "7", "9", "6"])
t.act("D")
check("doubling risks a second bet and is paid on both",
      t.hands[0]["bet"] == 20.0 and abs(t.hands[0]["net"] - 20.0) < 1e-9,
      "bet %g net %g" % (t.hands[0]["bet"], t.hands[0]["net"]))
check("and the stack ends where that says it should", abs(t.bankroll - 1020.0) < 1e-9,
      str(t.bankroll))

t = Table(config={"others": 0, "table_min": 25}, bankroll=20.0)
check("below the table minimum you are out of the game", t.broke())
check("a bet is clamped to the minimum and to what you are holding",
      Table(config={"others": 0, "table_min": 25}, bankroll=200.0).clamp_bet(3) == 25)
check("and to the table maximum",
      Table(config={"others": 0, "table_min": 25, "table_max": 100},
            bankroll=5000.0).clamp_bet(9999) == 100)

print("\nevery hand has words to go with it")

# coach.py keys its passages by (hand kind, total or pair, upcard). game.py's
# analyse() is what fills that in, so the two have to agree about every square
# the chart can put in front of you -- under every rule set, and whether or not
# you are allowed to double.
import coach

broken, noted = [], []
for name, rset in (("S17+DAS", R.DEFAULT_RULES),
                   ("H17", R.normalise({"hit_soft_17": True})),
                   ("no-DAS", R.normalise({"das": False}))):
    for section, row, up, code in R.cells_for(rset):
        for can_double in (True, False):
            hand = [card(r) for r in R.cards_for_cell(section, row)]
            move, fell_back = R.resolve(code, can_double)
            total, soft = E.hand_value(hand)
            a = {"kind": "play", "cell": R.cell_name(section, row, up),
                 "hand_kind": section, "pair": row if section == "pair" else None,
                 "total": total, "soft": soft, "up": up,
                 "chart_move": move, "fallback": fell_back}
            try:
                out = coach.explain(a)
                if not ({"hook", "paragraphs", "picture", "remember", "terms"} <= set(out)
                        and out["hook"] and out["paragraphs"] and out["remember"]):
                    broken.append((name, a["cell"], can_double, "thin"))
            except Exception as exc:                      # noqa: BLE001 - reporting it
                broken.append((name, a["cell"], can_double, repr(exc)))
        if R.rule_note(rset, section, row, up):
            noted.append((name, R.cell_name(section, row, up)))

check("coach.py has a passage for all 300 squares, every rule set, doubled or not",
      not broken, "%d calls, %d broken %s" % (3 * 300 * 2, len(broken), broken[:2]))
check("insurance has one too",
      bool(coach.explain({"kind": "insurance"})["remember"]))
check("the squares the rules move are flagged, so the words cannot contradict the verdict",
      len(noted) == 10, "%d flagged" % len(noted))
check("and nothing is flagged on the standard table",
      not any(R.rule_note(R.DEFAULT_RULES, s, r, u)
              for s, r, u, _ in R.cells_for(R.DEFAULT_RULES)))

# ---------------------------------------------------------------------------
# The Chart tab collapses hard 17-21 into one row and 5-8 into another, which is
# only honest if those bands really are identical. If a rule set ever splits
# one of them, the chart would be drawing a lie and this fails.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Quiz questions are built from cards_for_cell, so if the cards do not add up to
# the row they belong to, the quiz shows one hand and grades another. Hard 20
# shipped as 9+J, which is a nineteen.
# ---------------------------------------------------------------------------

print("\nthe cards a quiz question is built from really make that hand")
wrong = []
for section in ("hard", "soft", "pair"):
    rows = sorted({r for s, r, u, c in R.cells_for(R.DEFAULT_RULES) if s == section})
    for row in rows:
        ranks = R.cards_for_cell(section, row)
        cards = [{"rank": r} for r in ranks]
        total, soft = E.hand_value(cards)
        if section == "hard":
            ok = total == row and not soft
        elif section == "soft":
            ok = total == row + 11 and soft
        else:
            ok = (len(cards) == 2
                  and E.card_value(ranks[0]) == E.card_value(ranks[1]) == row)
        if not ok:
            wrong.append("%s %s -> %s = %d%s" % (section, row, "+".join(ranks), total,
                                                 " soft" if soft else ""))
check("every cell's cards add up to that cell", not wrong, "; ".join(wrong))
check("a hard row is never dealt as a pair, which would be a split question",
      all(len(set(R.cards_for_cell("hard", r))) > 1 or len(R.cards_for_cell("hard", r)) > 2
          for r in range(5, 22)))
check("hard 21 takes three cards, so it is not a blackjack",
      len(R.cards_for_cell("hard", 21)) == 3)

print("\nthe bands the chart collapses really are flat")
import itertools
split = []
for h17, das, ra in itertools.product([False, True], repeat=3):
    rset = R.normalise({"hit_soft_17": h17, "das": das, "resplit_aces": ra})
    g = R.grid(rset)["hard"]
    label = ("H17" if h17 else "S17") + ("/DAS" if das else "/noDAS")
    for band, rows in (("17-21", range(17, 22)), ("5-8", range(5, 9))):
        distinct = {tuple(g[r]) for r in rows}
        if len(distinct) != 1:
            split.append("%s %s" % (label, band))
check("hard 17 through 21 is one row under every rule set",
      not [x for x in split if "17-21" in x], "; ".join(x for x in split if "17-21" in x))
check("hard 5 through 8 is one row under every rule set",
      not [x for x in split if "5-8" in x], "; ".join(x for x in split if "5-8" in x))
check("and 17+ is all stand, 8- is all hit",
      set("".join("".join(R.grid(R.DEFAULT_RULES)["hard"][r]) for r in range(17, 22))) == {"S"}
      and set("".join("".join(R.grid(R.DEFAULT_RULES)["hard"][r]) for r in range(5, 9))) == {"H"})

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    raise SystemExit(1)
