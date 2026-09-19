"""
coach.py \u2014 the words, not the maths.

Two jobs:
  1. Turn a scored decision into an explanation a person can actually keep.
  2. Define every piece of jargon the app uses, in plain language.

The rule for everything in this file: if a sentence needs a term the reader
might not know, that term goes in GLOSSARY and gets underlined in the UI.

How the explanations are built
------------------------------
Every cell of the chart is written out by hand: each player total against
each dealer upcard gets its own words. Nothing is shared between cells that
would make a sentence true for one hand and false for another.

Two deliberate choices:

  * This is pure basic strategy. No counting, no true count, no deviations.
    The chart assumes you are not tracking the cards, because almost nobody
    is, and because you have to own the chart before anything else is worth
    learning.

  * Every number quoted is a fixed, canonical figure for a full six-deck
    shoe, not a live reading off the current one. Basic strategy is a fixed
    chart, so the same hand has to read the same way every single time. That
    repetition is the whole point: the numbers are there to be memorised,
    and a figure that drifts by a point every hand cannot be.

The chart is the S17 chart: this table's dealer stands on all 17s, soft ones
included. Three cells would change at a table where the dealer hits soft 17,
and those three say so in their own words.
"""

# ---------------------------------------------------------------------------
# Canonical numbers. Full six-deck shoe, dealer stands on all 17s, and the
# dealer is known not to already have blackjack \u2014 which is always true at the
# moment you are actually being asked to decide something.
# ---------------------------------------------------------------------------

# How often the dealer busts, by upcard.
DEALER_BUST = {2: "35%", 3: "37%", 4: "39%", 5: "42%", 6: "42%",
               7: "26%", 8: "24%", 9: "23%", 10: "23%", 11: "17%"}

# Where the dealer most often ends up, by upcard, and how often.
DEALER_LIKELY = {
    2:  "bust, 35% of the time",
    3:  "bust, 37% of the time",
    4:  "bust, 39% of the time",
    5:  "bust, 42% of the time",
    6:  "bust, 42% of the time",
    7:  "seventeen, 37% of the time",
    8:  "eighteen, 36% of the time",
    9:  "nineteen, 35% of the time",
    10: "twenty, 37% of the time",
    11: "any of 17 through 20, about 19% each",
}

# Chance the very next card busts a hard total.
PLAYER_BUST = {12: "31%", 13: "38%", 14: "46%", 15: "54%", 16: "62%",
               17: "69%", 18: "77%", 19: "85%", 20: "92%", 21: "100%"}

# Nearly a third of a shoe is worth ten: 10, J, Q and K.
TEN_DENSITY = "31%"

# The three cells that change if the dealer hits soft 17 instead of standing.
H17 = ("At a table where the dealer hits soft 17, this one flips to a double "
       "\u2014 this table stands on all 17s, so here it doesn't.")


def _pct(x, places=0):
    return ("%." + str(places) + "f%%") % (x * 100)


def _card(up):
    return "an ace" if up == 11 else "a " + str(up)


def _Card(up):
    return "An ace" if up == 11 else "A " + str(up)


# ---------------------------------------------------------------------------
# explain() \u2014 look the situation up and hand back the words for it.
# ---------------------------------------------------------------------------

def explain(a):
    """
    Build the plain-language explanation for one scored decision.

    `a` is the analysis dict from game.Table.analyse().
    Returns hook / paragraphs / picture / remember / terms.
    """
    if a["kind"] == "insurance":
        return dict(INSURANCE, paragraphs=list(INSURANCE["paragraphs"]),
                    terms=list(INSURANCE["terms"]))

    up = a["up"]
    total = a["total"]

    if a["hand_kind"] == "pair":
        cell = PAIRS[a["pair"]][up]
    elif a["hand_kind"] == "soft":
        cell = SOFT[min(max(total, 12), 21)][up]
    else:
        cell = HARD[8 if total <= 8 else min(total, 21)][up]

    out = dict(cell, paragraphs=list(cell["paragraphs"]), terms=list(cell["terms"]))

    # The chart wanted a double and the table won't allow one. Say so, rather
    # than quietly explaining a move nobody is being offered.
    if a.get("fallback"):
        instead = "stand" if a["chart_move"] == "S" else "take one card and carry on"
        out["hook"] = "A doubling hand you aren't allowed to double. So: " + instead + "."
        out["paragraphs"] = [
            "Doubling is only on the table for your first two cards, and only when you "
            "can cover a second bet the same size as the first. One of those isn't true "
            "here \u2014 either this hand has already been hit, or the money isn't there \u2014 "
            "so the chart falls back to the best move you can actually make, which is to %s. "
            "Everything below is still why this is a doubling hand; you just can't collect "
            "on it this time." % instead,
        ] + out["paragraphs"]
        out["remember"] = ("A double you can't afford or aren't offered becomes a hit. "
                           "The single exception is soft 18 against 3 through 6, which "
                           "becomes a stand.")
    return out


# ---------------------------------------------------------------------------
# Insurance. Its own thing: a side bet, settled before your hand is played.
# ---------------------------------------------------------------------------

INSURANCE = {
    "hook": "It's a bet on the dealer's face-down card. Your own hand isn't invited.",
    "paragraphs": [
        "Insurance sounds like protection. It isn't. It's a completely separate bet "
        "that the dealer's hidden card is worth ten, and it gets settled before your "
        "hand is even played. You could be holding a 7 and a 4 and the maths would be "
        "exactly the same.",
        "It pays two to one, so it only makes money if the hidden card is a ten more "
        "than a third of the time. Four ranks out of thirteen are worth ten, so it comes "
        "in about " + TEN_DENSITY + " of the time. Short, every time, forever.",
    ],
    "picture": "Someone is offering you 2-to-1 on a coin that only lands your way three "
               "times in ten. If a friend offered you that in a pub you'd spot it instantly. "
               "The felt just makes it feel like a service being provided.",
    "remember": "Never take insurance. Not on a twenty, and especially not on a blackjack.",
    "terms": ["insurance", "hole card", "expected value"],
}


# ---------------------------------------------------------------------------
# Hard totals. Keyed by total, then by dealer upcard.
# Totals of 8 and under all live in row 8: the answer is the same for all of
# them and so is the reason.
# ---------------------------------------------------------------------------

HARD = {

    # --- 8 or less: always hit ------------------------------------------
    8: {
        2: {
            "hook": "Eight or less. There is no such thing as a wrong card here.",
            "paragraphs": [
                "At eight or under, every card in the shoe leaves you at 21 or below. Even "
                "an ace: it counts as 11 only when that fits, and quietly becomes a 1 when it "
                "doesn't. A hand that cannot be damaged always takes another card.",
                "A 2 is the weakest thing the dealer can show that still isn't genuinely weak "
                "\u2014 they bust 35% of the time, the least of the five small cards. But none of "
                "that helps you at 8. You can only cash in a dealer bust by having a total "
                "worth keeping, and this isn't one yet.",
            ],
            "picture": "Eight isn't a hand. It's the first two letters of one.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        3: {
            "hook": "Eight or less. Take the card; it's free.",
            "paragraphs": [
                "No card in the shoe busts a total of eight or under, so drawing costs you "
                "nothing at all. There is no risk to weigh up, which makes this one of the few "
                "spots in blackjack with no decision in it.",
                "A 3 busts 37% of the time, so the dealer is in mild trouble. Standing here "
                "wouldn't let you profit from that \u2014 a total this small loses to every hand "
                "they can finish on. Build something first.",
            ],
            "picture": "You can't wait out a weak dealer with a hand that loses to all of "
                       "their good outcomes and all of their bad ones.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        4: {
            "hook": "Eight or less. Nothing can break you, so nothing is a mistake.",
            "paragraphs": [
                "Every card leaves this hand alive. Aces drop to 1 rather than busting you, "
                "tens take you to 18 at worst. Drawing is pure upside.",
                "A 4 busts 39% of the time and this is the part of the chart where that starts "
                "to matter \u2014 but only once you have a total that can survive to the end of the "
                "hand. Eight isn't it.",
            ],
            "picture": "A free card is a free card. Take every one you're offered.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        5: {
            "hook": "Eight or less against the dealer's worst card. Still just hit.",
            "paragraphs": [
                "A 5 is the second-worst card a dealer can be showing \u2014 they bust 42% of the "
                "time. It's tempting to do something clever with that. There isn't anything "
                "clever to do: at eight or under you have no total to protect and no double "
                "worth making.",
                "The chart only starts doubling at 9, and for a good reason. Doubling buys you "
                "exactly one card and then stops you. From 8 that leaves you parked on a bad "
                "number with your bet doubled.",
            ],
            "picture": "The dealer being in trouble is worth a lot \u2014 but only to a hand that "
                       "is still standing at the end. Get one of those first.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "double down", "bust"],
        },
        6: {
            "hook": "Eight or less against a 6. Draw, and don't get fancy.",
            "paragraphs": [
                "A 6 is the single worst card the dealer can show: they bust 42% of the time, "
                "more than with any other upcard. You want to be in this hand at the end to "
                "collect on that, and you cannot be with a total of eight.",
                "And there's no risk on the other side of the ledger. Not one card in the shoe "
                "busts a hand this small, so the draw is free.",
            ],
            "picture": "The dealer showing a 6 is the shop putting up a sale sign. You still "
                       "have to walk in and pick something up.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        7: {
            "hook": "Eight or less against a 7. Obviously draw.",
            "paragraphs": [
                "A 7 is where the dealer stops being weak. Their most likely finish is "
                "seventeen, 37% of the time, and they only bust 26% of the time. You need a "
                "real total to beat that.",
                "Luckily this one is free. At eight or under nothing in the shoe can bust you, "
                "so there is no cost to drawing and no argument for stopping.",
            ],
            "picture": "Seventeen is a low bar, but it is still a bar. Eight does not clear it.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        8: {
            "hook": "Eight or less against an 8. Draw.",
            "paragraphs": [
                "The dealer's most likely finish is eighteen, 36% of the time, and they bust "
                "only 24% of the time. Standing on a small total against that is just handing "
                "the hand over.",
                "There is no downside to consider. At eight or under, every card in the shoe "
                "leaves you under 21.",
            ],
            "picture": "You are not choosing between two risks here. You are choosing between "
                       "a free card and nothing.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        9: {
            "hook": "Eight or less against a 9. Draw, and keep drawing.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts only 23% of the time. You "
                "will need a genuinely good hand to win this, which means several more cards, "
                "which is fine.",
                "None of them can hurt you from here. A total of eight or less cannot be busted "
                "by anything.",
            ],
            "picture": "Against a strong upcard the only losing move is to stop early. From "
                       "eight, stopping isn't even on the menu.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        10: {
            "hook": "Eight or less against a 10. Draw without thinking about it.",
            "paragraphs": [
                "A 10 is the most common upcard there is, and the dealer's most likely finish "
                "from it is twenty, 37% of the time. They bust just 23% of the time. Small "
                "totals lose this hand every way round.",
                "And the draw is free: nothing in the shoe busts a hand of eight or under.",
            ],
            "picture": "Against a ten you are climbing towards twenty. You cannot start the "
                       "climb by standing still.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
        11: {
            "hook": "Eight or less against an ace. Draw.",
            "paragraphs": [
                "An ace is the strongest card the dealer can show. Once they've checked for "
                "blackjack and haven't got it, they still bust only 17% of the time \u2014 the "
                "lowest of any upcard \u2014 and land on 17, 18, 19 or 20 about 19% each.",
                "You need a real hand against that, and getting one costs you nothing: no card "
                "can bust a total of eight or under.",
            ],
            "picture": "An ace almost never breaks. You have to beat it, not outlast it.",
            "remember": "Eight or less: always hit. Nothing in the shoe can hurt you.",
            "terms": ["hit", "bust", "upcard"],
        },
    },

    # --- 9: double against 3, 4, 5, 6 -----------------------------------
    9: {
        2: {
            "hook": "Nine doubles against the small cards \u2014 but not against a 2. Hit.",
            "paragraphs": [
                "This is where the 9 row starts, and it starts at 3 rather than 2 for one "
                "reason: a 2 busts 35% of the time, the least of the small cards. The dealer "
                "has the most room to recover from it, so the reward for committing a second "
                "bet isn't quite there.",
                "Doubling buys exactly one card and then stops you. About 31% of the time that "
                "card is a ten and you have 19, which is good \u2014 but the rest of the time you "
                "are frozen on a middling total against a dealer who isn't in enough trouble. "
                "Hit instead and keep the right to draw again.",
            ],
            "picture": "The 2 looks like a small card and behaves like a medium one. It is the "
                       "reason this row starts one column to the right of where you'd guess.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        3: {
            "hook": "The 9 row opens here. Double.",
            "paragraphs": [
                "A 3 busts 37% of the time, and that is the point where a second bet on a 9 "
                "starts paying. You are putting money down while already holding the better "
                "position \u2014 the dealer has to draw from a weak start and you don't.",
                "One card takes this to 19 about 31% of the time, and to 17 or better far more "
                "often than not. You are not trying to make 21. You are trying to make a total "
                "the dealer has to beat from a bad starting point.",
            ],
            "picture": "Doubling is the only bet in the building you get to place after seeing "
                       "some of the cards. This is one of the moments it's offered.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        4: {
            "hook": "Nine against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time. That's nearly two hands in five where you win "
                "without your total ever being tested \u2014 and you've just doubled how much you "
                "collect when it happens.",
                "The single card you're buying lands you on 19 about 31% of the time and on a "
                "perfectly playable total most of the rest. Against a dealer this weak, the "
                "risk of being frozen on 15 matters much less than the extra bet does.",
            ],
            "picture": "You are buying more of something while it's cheap. The dealer's 4 is "
                       "what makes it cheap.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        5: {
            "hook": "Nine against a 5. Double, and don't hesitate.",
            "paragraphs": [
                "A 5 busts 42% of the time. This is one of the two worst cards the dealer can "
                "be holding, and you have a total that can only improve on the next card.",
                "That combination \u2014 no made hand to protect, a dealer likely to break \u2014 is "
                "exactly what the double is for. Getting a second bet down here is worth more "
                "than the flexibility you give up by being stopped after one card.",
            ],
            "picture": "Weak dealer, improvable hand, extra bet. All three arrive at once and "
                       "then the moment is gone.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        6: {
            "hook": "Nine against a 6. The best cell in the row.",
            "paragraphs": [
                "A 6 is the worst card a dealer can show: they bust 42% of the time, more than "
                "from anything else. Nine against a 6 is the strongest version of this row and "
                "the clearest double in it.",
                "Your one card makes 19 about 31% of the time. Their hand breaks entirely more "
                "than four times in ten. You have doubled your stake on both of those.",
            ],
            "picture": "The dealer has to draw and you don't. That is the whole edge, and you "
                       "have just bought twice as much of it.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        7: {
            "hook": "Nine against a 7. The row closes. Hit.",
            "paragraphs": [
                "The 9 row runs 3 through 6 and stops. A 7 busts only 26% of the time and "
                "lands on seventeen 37% of the time, so the dealer is no longer the one in "
                "trouble.",
                "Doubling would buy one card and then freeze you. Against a 7 you might well "
                "need two or three more to build something that beats seventeen, so keep the "
                "right to draw and hit.",
            ],
            "picture": "Doubling is a bet that one card will be enough. Against a 7, one card "
                       "often isn't.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "hit", "upcard"],
        },
        8: {
            "hook": "Nine against an 8. Hit.",
            "paragraphs": [
                "The dealer's most likely finish is eighteen, 36% of the time, and they bust "
                "only 24% of the time. A 9 doubled into one card gives you 19 about 31% of the "
                "time and something short of eighteen far more often.",
                "Hitting keeps every option open: draw, look at what you've got, draw again. "
                "That flexibility is worth more than the second bet when the dealer is this solid.",
            ],
            "picture": "You need to get past eighteen, not merely to improve. That usually "
                       "takes more than one card.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "hit", "upcard"],
        },
        9: {
            "hook": "Nine against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts only 23% of the time. To "
                "win this hand you will usually need 20, and there is no version of one card "
                "on a 9 that reliably gets you there.",
                "So don't buy one card. Buy as many as you need: hit, and keep hitting until "
                "you have a total worth standing on.",
            ],
            "picture": "Against a 9, nineteen is the price of entry. Doubling stops you a "
                       "card short of paying it.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "hit", "upcard"],
        },
        10: {
            "hook": "Nine against a 10. Hit.",
            "paragraphs": [
                "The dealer's most likely finish is twenty, 37% of the time, and they bust "
                "only 23% of the time. Doubling into a single card leaves you on 19 at best "
                "about 31% of the time \u2014 and 19 loses to twenty.",
                "Hit, and be willing to keep going. This hand needs to end up high, and the "
                "only way there is more than one card.",
            ],
            "picture": "Committing a second bet only makes sense when one card is likely to be "
                       "enough. Against a ten it very much isn't.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "hit", "upcard"],
        },
        11: {
            "hook": "Nine against an ace. Hit.",
            "paragraphs": [
                "An ace is the strongest upcard on the table. The dealer busts only 17% of the "
                "time from it and spreads fairly evenly across 17 to 20. There is no weakness "
                "here to buy into.",
                "Doubling a 9 against the best card the dealer can hold is paying extra for the "
                "right to stop drawing early. Just hit.",
            ],
            "picture": "You double when the dealer is in trouble. An ace is the opposite of "
                       "trouble.",
            "remember": "Nine doubles against 3, 4, 5 and 6. Everything else, a 2 included, is a hit.",
            "terms": ["double down", "hit", "upcard"],
        },
    },

    # --- 10: double against 2 through 9 ---------------------------------
    10: {
        2: {
            "hook": "Ten against a 2. Double.",
            "paragraphs": [
                "Ten doubles against everything except a ten and an ace, and that includes the "
                "2. Unlike the 9 row, which has to wait for a 3, ten is strong enough that the "
                "dealer only has to be ordinary for the second bet to be worth it.",
                "About 31% of the shoe is worth ten, so one card makes 20 roughly a third of "
                "the time, and 17 or better most of the rest. You are the favourite the moment "
                "the money goes down, which is the only time you should ever be adding to a bet.",
            ],
            "picture": "Nine needs the dealer to be weak. Ten only needs them not to be strong.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        3: {
            "hook": "Ten against a 3. Double.",
            "paragraphs": [
                "A 3 busts 37% of the time, and you are holding the best two-card total in the "
                "game that isn't an 11. One card makes 20 about 31% of the time.",
                "Doubling and splitting are the only two ways you will ever increase a wager "
                "after seeing cards. Skipping them is how a 0.5% game quietly turns into a 2% one.",
            ],
            "picture": "This is the informed half of your bet \u2014 the part you place already "
                       "knowing you're ahead.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "house edge", "upcard"],
        },
        4: {
            "hook": "Ten against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time. Nearly two hands in five you win without your own "
                "total mattering at all, and you have just doubled what you collect on those.",
                "The other three, one card gives you 20 about 31% of the time and a solid total "
                "most of the rest. There is very little that can go wrong here.",
            ],
            "picture": "Strong hand, weak dealer, extra bet. The chart is not subtle about "
                       "this one.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        5: {
            "hook": "Ten against a 5. Double.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5. You are holding a total that turns "
                "into 20 about 31% of the time on a single card. Both halves of the hand are "
                "pointing the same way.",
                "This is as close to a free roll as blackjack offers. Put the second bet out.",
            ],
            "picture": "Two good things at once: you are likely to end up high, and they are "
                       "likely to end up nowhere.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        6: {
            "hook": "Ten against a 6. Double.",
            "paragraphs": [
                "A 6 is the dealer's worst card \u2014 42% bust, the highest on the board. A ten is "
                "your second-best starting total. There is no better time to have more money "
                "on the table.",
                "One card makes 20 about 31% of the time. And when they break, which is close "
                "to half the time, your total never even gets looked at.",
            ],
            "picture": "The sale sign is up and you are holding the best thing on the shelf. "
                       "Buy two.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard", "bust"],
        },
        7: {
            "hook": "Ten against a 7. Still double.",
            "paragraphs": [
                "This is the cell people flinch at, because a 7 doesn't look weak. It doesn't "
                "have to be. The dealer's most likely finish from a 7 is seventeen, 37% of the "
                "time \u2014 and a ten turns into 18, 19 or 20 far more often than it fails to.",
                "You are not doubling because they are in trouble. You are doubling because you "
                "are ahead, and seventeen is a low number to be chasing.",
            ],
            "picture": "Seventeen is the dealer's headline outcome here, and you beat it with "
                       "any ten, nine or eight. That is most of the shoe.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard"],
        },
        8: {
            "hook": "Ten against an 8. Double.",
            "paragraphs": [
                "The dealer's likeliest finish is eighteen, 36% of the time. One card on a ten "
                "beats that outright about 31% of the time with a ten alone, and ties or beats "
                "it far more often than not.",
                "The row runs all the way to 9 for a reason: a ten is strong enough that you "
                "only need the dealer to be beatable, not broken.",
            ],
            "picture": "You are trading the right to draw again for twice the money, at a "
                       "moment when one card is usually enough.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard"],
        },
        9: {
            "hook": "Ten against a 9. The last cell in the row. Double.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time, so you genuinely need a big card "
                "here. You will get one about 31% of the time, and that is still enough to "
                "make the second bet pay.",
                "This is where the row ends. One column further right and the dealer's likely "
                "finish moves to twenty, and the whole calculation turns over.",
            ],
            "picture": "The edge of the row is worth knowing as an edge. Nine is in, ten is out.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "upcard"],
        },
        10: {
            "hook": "Ten against a 10. Hit \u2014 don't double.",
            "paragraphs": [
                "The dealer's most likely finish from a ten is twenty, 37% of the time, and "
                "they only bust 23% of the time. Your one bought card makes 20 about 31% of the "
                "time \u2014 and 20 against 20 is a push, not a win.",
                "So keep your options. Hit, see what turns up, and draw again if you need to. "
                "The second bet isn't earning here.",
            ],
            "picture": "You'd be doubling to reach a total that only ties their most likely "
                       "hand. That's paying extra for a push.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "hit", "push"],
        },
        11: {
            "hook": "Ten against an ace. Hit.",
            "paragraphs": [
                "An ace is the dealer's strongest card. They bust just 17% of the time from it "
                "and land evenly across 17 through 20. There is no soft spot here to put extra "
                "money into.",
                "Hit instead. A ten is a fine hand to build from, and against an ace you want "
                "the freedom to keep building.",
            ],
            "picture": "Ten is strong and an ace is stronger. Strength meets strength, and the "
                       "extra bet stays in your pocket.",
            "remember": "Ten doubles against 2 through 9. Against a ten or an ace, just hit.",
            "terms": ["double down", "hit", "upcard"],
        },
    },

    # --- 11: double against everything except an ace --------------------
    11: {
        2: {
            "hook": "Eleven is the best two cards you'll ever be dealt. Double.",
            "paragraphs": [
                "Eleven cannot be busted by a single card and turns into 21 about 31% of the "
                "time, because that is how much of the shoe is worth ten. No other total in the "
                "game does both of those things.",
                "The 2 is the weakest thing the dealer can show while still not being weak, and "
                "it doesn't matter. Eleven is strong enough on its own that the dealer barely "
                "gets a vote.",
            ],
            "picture": "Eleven is the one hand where more money is right before you know "
                       "anything else at all.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        3: {
            "hook": "Eleven against a 3. Double.",
            "paragraphs": [
                "One card makes 21 about 31% of the time and 18 or better most of the rest. "
                "You cannot bust. There is no downside card in the shoe.",
                "A 3 busts 37% of the time on top of that. Best hand, weak dealer, second bet. "
                "Nothing to weigh.",
            ],
            "picture": "The risk side of this decision is empty. Only the reward side has "
                       "anything written on it.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        4: {
            "hook": "Eleven against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time, and an 11 makes 21 about 31% of the time on one "
                "card. Both numbers are pulling in the same direction and neither has a "
                "downside attached.",
                "Doubling, splitting and the 3-to-2 you get for a blackjack are the three "
                "things dragging the house's advantage from roughly 5% down to roughly 0.5%. "
                "This cell is one of the biggest of them.",
            ],
            "picture": "Skip your doubles and you are playing a version of blackjack that "
                       "loses ten times faster.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "house edge", "3 to 2"],
        },
        5: {
            "hook": "Eleven against a 5. Double.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5, and you are holding the best "
                "starting total in the game. One card makes 21 about 31% of the time.",
                "There is no card that can break you and no realistic way to end up worse off "
                "for having drawn. Put the money out.",
            ],
            "picture": "If you only ever learn one doubling cell, learn the 11 row. This is "
                       "the middle of it.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        6: {
            "hook": "Eleven against a 6. The single best cell on the chart. Double.",
            "paragraphs": [
                "Your best total against their worst card. The dealer busts 42% of the time "
                "from a 6 and one card takes you to 21 about 31% of the time.",
                "If there is one hand where failing to get extra money down actually costs you "
                "something you can feel, this is it.",
            ],
            "picture": "Everything that can be in your favour is in your favour at the same "
                       "time. That happens about once every forty hands. Don't waste it.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        7: {
            "hook": "Eleven against a 7. Double.",
            "paragraphs": [
                "The dealer's most likely finish is seventeen, 37% of the time. An 11 turns "
                "into 18 or better on any card from a 7 upwards \u2014 well over half the shoe \u2014 "
                "and into 21 about 31% of the time.",
                "The dealer stopping at seventeen is not a wall, it's a low ceiling you clear "
                "most of the time. Double.",
            ],
            "picture": "They are aiming at seventeen. You are aiming past it and you cannot "
                       "bust on the way.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "upcard"],
        },
        8: {
            "hook": "Eleven against an 8. Double.",
            "paragraphs": [
                "Eighteen is their most likely finish, 36% of the time. One card on an 11 beats "
                "eighteen with any 8, 9 or ten-value card \u2014 comfortably more than half the shoe.",
                "The 11 row does not care very much what the dealer has. That's what makes it "
                "the easiest row on the chart to remember.",
            ],
            "picture": "Eleven is the only total in the game that is a favourite against every "
                       "single upcard.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "upcard"],
        },
        9: {
            "hook": "Eleven against a 9. Double.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time, so you do need a real card. You get "
                "a ten about 31% of the time for 21, and a 9 gives you 20. That is a lot of the "
                "shoe landing above nineteen.",
                "You still cannot bust. Every card leaves you with a live hand, so the only "
                "question is how much money is on it.",
            ],
            "picture": "A strong dealer card lowers how often you win. It does not change the "
                       "fact that you are the favourite.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        10: {
            "hook": "Eleven against a 10. Double \u2014 yes, really.",
            "paragraphs": [
                "This is the cell that gets skipped most often, because a ten looks frightening. "
                "The dealer's likeliest finish is twenty, 37% of the time, and they bust 23% of "
                "the time. It is still a double.",
                "One card gives you 21 about 31% of the time and 20 about 8% more. You cannot "
                "bust. A hand that is a favourite and cannot break is a hand that deserves a "
                "second bet, however unfriendly the upcard looks.",
            ],
            "picture": "Being nervous is not the same as being behind. Against a ten you are "
                       "still ahead here \u2014 just by less.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "bust", "upcard"],
        },
        11: {
            "hook": "Eleven against an ace. The one cell in the row that hits.",
            "paragraphs": [
                "An ace is the only upcard strong enough to close this row. The dealer busts "
                "just 17% of the time from it and spreads evenly across 17 through 20, so a "
                "single bought card is not reliably enough.",
                "Hit instead and keep the right to draw again. " + H17,
            ],
            "picture": "One exception at the far right of the row. Eleven doubles against "
                       "everything \u2014 until the ace.",
            "remember": "Eleven doubles against everything except an ace.",
            "terms": ["double down", "hit", "s17"],
        },
    },
}


# --- 12 through 16: the stiff hands. Where most money is lost. ----------

HARD.update({

    # --- 12: stands against 4, 5 and 6 only -----------------------------
    12: {
        2: {
            "hook": "Twelve against a 2. Hit \u2014 this is the cell people get wrong.",
            "paragraphs": [
                "Standing on 12 wins only when the dealer busts, and from a 2 that's 35% of "
                "the time. That is the whole of your upside: 35%, and you lose the other 65%.",
                "Hitting looks worse and isn't. Only a ten-value card busts a 12, so you break "
                "just 31% of the time \u2014 the lowest bust chance of any stiff hand. The other 69% "
                "you land somewhere between 13 and 21 and get to keep playing. That's a better "
                "hand than a flat 35%.",
            ],
            "picture": "Twelve is the one stiff total where drawing is safer than it feels and "
                       "standing is worse than it feels. The 2 and the 3 are where that flips "
                       "the answer.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        3: {
            "hook": "Twelve against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time. Stand and that 37% is everything you get \u2014 the "
                "other 63% of hands you lose, because any total they finish on beats a 12.",
                "Draw and you bust only 31% of the time, because only a ten breaks you. The "
                "margin is thin, but it points at hitting, and it goes on pointing there until "
                "the dealer shows a 4.",
            ],
            "picture": "This is the last cell before the 12 row turns over. One more column "
                       "and the answer changes.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        4: {
            "hook": "Twelve against a 4. Now stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. That is finally more than the 31% chance you break "
                "by drawing, and that crossover is the entire reason this row starts standing "
                "here and not a column earlier.",
                "You have a bad total either way. Standing just makes the dealer be the one who "
                "has to draw out of a hole.",
            ],
            "picture": "The 12 row is a hinge: hit, hit, stand, stand, stand, then hit all the "
                       "way to the ace. The hinge sits on the 4.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        5: {
            "hook": "Twelve against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5. Drawing busts you 31% of the time "
                "and, when it doesn't, usually leaves you on another stiff total you'd then "
                "have to make the same decision about.",
                "Hand the risk back. Let them draw from a 5 and break.",
            ],
            "picture": "Small cards showing are the dealer's trap. Standing is stepping aside "
                       "and letting them walk into it.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        6: {
            "hook": "Twelve against a 6. Stand.",
            "paragraphs": [
                "A 6 is the dealer's worst card: 42% bust, the highest on the board. Your 12 "
                "does not need to be good. It only needs to still exist when they break.",
                "Drawing risks 31% of hands for no reason. You already have the best thing you "
                "can have against a 6, which is a live hand and no obligation to draw.",
            ],
            "picture": "Against a 6 you are not trying to win the hand. You are trying to be "
                       "present when they lose it.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        7: {
            "hook": "Twelve against a 7. Hit.",
            "paragraphs": [
                "The stand band ends at the 6. A 7 busts only 26% of the time and lands on "
                "seventeen 37% of the time, so standing on 12 loses roughly three hands in four.",
                "Drawing busts you just 31% of the time \u2014 the safest draw of any stiff hand \u2014 "
                "and the rest of the time you get a shot at a total that can actually beat "
                "seventeen.",
            ],
            "picture": "Against 7 and up, the dealer is not going to break for you. You have "
                       "to make a hand.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        8: {
            "hook": "Twelve against an 8. Hit.",
            "paragraphs": [
                "Eighteen is where an 8 most often finishes, 36% of the time, and they bust "
                "only 24% of the time. A 12 beats none of that.",
                "You bust 31% of the time drawing, which is the cheapest draw in the stiff "
                "block. Take it.",
            ],
            "picture": "A 12 is not a hand you are protecting. It is a hand you are escaping.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        9: {
            "hook": "Twelve against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts 23% of the time. Standing "
                "on 12 wins less than a quarter of the time.",
                "Drawing costs you 31% in busts and buys a real chance at a real total. It "
                "isn't close.",
            ],
            "picture": "Twelve against a big card is a hand you have to fix, not one you can sit on.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        10: {
            "hook": "Twelve against a 10. Hit.",
            "paragraphs": [
                "Twenty is the dealer's most likely finish here, 37% of the time, and they "
                "bust only 23% of the time. Standing on 12 wins fewer than one hand in four.",
                "Hitting busts you 31% of the time. It's the least bad option by a wide margin, "
                "and it's the same answer for every total from 12 to 16 against this card.",
            ],
            "picture": "You can't outlast a ten. You have to outdraw it.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        11: {
            "hook": "Twelve against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time \u2014 the lowest of any upcard. Standing on 12 "
                "means winning 17% of these hands and losing the other 83%.",
                "Draw. You break 31% of the time and give yourself a hand worth having the "
                "other 69%.",
            ],
            "picture": "The dealer's ace is the card least likely to save you. Save yourself.",
            "remember": "Twelve stands against 4, 5 and 6 only. Against a 2 or a 3 it hits.",
            "terms": ["stiff hand", "hit", "bust"],
        },
    },

    # --- 13: stand against 2 through 6 ----------------------------------
    13: {
        2: {
            "hook": "Thirteen against a 2. Stand.",
            "paragraphs": [
                "This is where the big block of the chart begins, and it begins one column "
                "earlier than the 12 row did. At 13 you bust 38% of the time if you draw, which "
                "is now more than the 35% chance the dealer breaks from a 2.",
                "Neither number is good. Standing is simply the one that loses less often, and "
                "that is what most of this chart is: picking the smaller loss.",
            ],
            "picture": "You are not choosing how to win. You are choosing which way loses "
                       "least often.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        3: {
            "hook": "Thirteen against a 3. Stand.",
            "paragraphs": [
                "A 3 busts 37% of the time. Drawing to a 13 busts you 38% of the time \u2014 and "
                "when you bust you lose immediately, before the dealer has to do anything at all.",
                "That asymmetry is the whole house edge in one sentence. Don't volunteer for it.",
            ],
            "picture": "Busting is the only way to lose a hand the dealer never had to win.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        4: {
            "hook": "Thirteen against a 4. Stand.",
            "paragraphs": [
                "The dealer busts 39% of the time from a 4 and you bust 38% of the time if you "
                "draw. Those are close, and the tiebreak is that their bust wins you the hand "
                "outright while yours loses it outright.",
                "Stand and make them play it out.",
            ],
            "picture": "Two bad hands, but only one of you is forced to draw. Make sure it's "
                       "not you.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        5: {
            "hook": "Thirteen against a 5. Stand.",
            "paragraphs": [
                "A 5 busts 42% of the time. You have a hand that beats a busted dealer and "
                "nothing else, which is exactly enough here.",
                "Drawing would break you 38% of the time in pursuit of a total you don't "
                "actually need.",
            ],
            "picture": "When the dealer is holding a 5 you already have the only asset that "
                       "matters: a hand that is still alive.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        6: {
            "hook": "Thirteen against a 6. Stand.",
            "paragraphs": [
                "The best version of this cell. A 6 busts 42% of the time, more than any other "
                "upcard, and your 13 collects every one of those.",
                "Drawing risks 38% of your hands to improve a total that only has to survive.",
            ],
            "picture": "Do nothing, and win nearly half of them. It is the laziest profit in "
                       "the game.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        7: {
            "hook": "Thirteen against a 7. Hit.",
            "paragraphs": [
                "Seventeen is a 7's most likely finish, 37% of the time, and they bust only "
                "26% of the time. A 13 loses to everything they can make.",
                "You bust 38% of the time drawing. That's real \u2014 but standing loses about three "
                "quarters of these hands, and 38% is the smaller number.",
            ],
            "picture": "People get this wrong because busting feels like your own fault, while "
                       "losing to a dealer's nineteen feels like bad luck. The money doesn't "
                       "know the difference.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        8: {
            "hook": "Thirteen against an 8. Hit.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time and busts only 24% of the time. "
                "Standing on 13 wins less than a quarter of the time.",
                "Drawing busts you 38% of the time and gives you a real hand the other 62%. "
                "Take the draw.",
            ],
            "picture": "Against a big card, a stiff hand is not something to protect. It is "
                       "something to get out of.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        9: {
            "hook": "Thirteen against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time and busts 23% of the time. Thirteen "
                "beats none of it.",
                "You break 38% of the time by drawing, which is a lot better than the 77% of "
                "hands you simply hand over by standing.",
            ],
            "picture": "One number is 38% and the other is 77%. That is the entire argument.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        10: {
            "hook": "Thirteen against a 10. Hit.",
            "paragraphs": [
                "Twenty is where a ten most often finishes, 37% of the time, and they bust only "
                "23% of the time. There is no waiting this one out.",
                "Drawing busts you 38% of the time. Standing loses you about 77% of the time. "
                "The chart picks the first one every time.",
            ],
            "picture": "Against a ten you are always behind. The only question is whether you "
                       "go down fighting or standing still.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        11: {
            "hook": "Thirteen against an ace. Hit.",
            "paragraphs": [
                "An ace busts just 17% of the time, the least of any upcard. Standing on 13 "
                "wins one hand in six.",
                "Drawing breaks you 38% of the time and leaves you with something playable the "
                "other 62%. Not good \u2014 better.",
            ],
            "picture": "The ace is the card you cannot outlast. You have to build past it.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
    },

    # --- 14: stand against 2 through 6 ----------------------------------
    14: {
        2: {
            "hook": "Fourteen against a 2. Stand.",
            "paragraphs": [
                "Drawing to a 14 busts you 46% of the time \u2014 nearly one hand in two. The dealer "
                "busts 35% of the time from a 2. You are the one more likely to break, so let "
                "them do the drawing.",
                "Fourteen is a bad hand. Standing doesn't fix it; it just stops you making it "
                "worse.",
            ],
            "picture": "Once your bust chance passes the dealer's, standing wins the argument "
                       "automatically. At 14 it has passed comfortably.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        3: {
            "hook": "Fourteen against a 3. Stand.",
            "paragraphs": [
                "You break 46% of the time if you draw. They break 37% of the time if you don't. "
                "Those are the only two numbers in this decision and they are not close.",
                "Stand, and lose the hand their way rather than yours.",
            ],
            "picture": "Forty-six versus thirty-seven. Pick the smaller one and move on.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        4: {
            "hook": "Fourteen against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. Drawing to 14 busts you 46% of the time and often "
                "leaves you on another stiff total when it doesn't.",
                "There is nothing to gain by taking a card and a lot to lose.",
            ],
            "picture": "Half the shoe kills this hand. The other half mostly hands you a "
                       "slightly different version of the same problem.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        5: {
            "hook": "Fourteen against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5 \u2014 and they have to draw to find out, "
                "while you don't.",
                "Drawing would break you 46% of the time. Standing keeps you in for every one "
                "of their 42%.",
            ],
            "picture": "The dealer has no choice about drawing. That is the one structural "
                       "advantage you have, and standing is how you use it.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        6: {
            "hook": "Fourteen against a 6. Stand.",
            "paragraphs": [
                "A 6 busts 42% of the time, the most of any upcard. You collect all of it just "
                "by staying in the hand.",
                "Drawing breaks you 46% of the time \u2014 you would be throwing away almost half "
                "your winners to chase a total you don't need.",
            ],
            "picture": "Against a 6, the right move is almost always to do nothing. Doing "
                       "nothing is harder than it sounds.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        7: {
            "hook": "Fourteen against a 7. Hit.",
            "paragraphs": [
                "A 7 busts 26% of the time and finishes on seventeen 37% of the time. Fourteen "
                "loses to every total they can make, so standing wins only that 26%.",
                "Drawing busts you 46% of the time. That's ugly, and it's still better than "
                "giving away three hands in four.",
            ],
            "picture": "This is the row where the chart stops protecting you and starts making "
                       "you fight. It is also where most people quietly stop following it.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        8: {
            "hook": "Fourteen against an 8. Hit.",
            "paragraphs": [
                "Eighteen is their likeliest finish, 36% of the time, and they bust only 24% "
                "of the time. A 14 needs to improve or it loses.",
                "You break 46% of the time drawing and get a live hand the other 54%. Standing "
                "gives you 24% and nothing else.",
            ],
            "picture": "Fifty-four percent of something beats twenty-four percent of anything.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        9: {
            "hook": "Fourteen against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts 23% of the time. Standing "
                "on 14 wins less than a quarter of these.",
                "Take the card. You bust 46% of the time, but the alternative is worse and it "
                "is worse every single time.",
            ],
            "picture": "You are not drawing because it is likely to work. You are drawing "
                       "because standing is guaranteed not to.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        10: {
            "hook": "Fourteen against a 10. Hit.",
            "paragraphs": [
                "Twenty, 37% of the time, and a bust only 23% of the time. Fourteen is beaten "
                "by everything that isn't a bust.",
                "Drawing busts you 46% of the time. Standing loses about 77% of the time. Same "
                "answer as 13, and the same answer as 15 and 16.",
            ],
            "picture": "Against a ten, everything from 12 to 16 does the same thing: hit. One "
                       "rule, five rows.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        11: {
            "hook": "Fourteen against an ace. Hit.",
            "paragraphs": [
                "An ace busts 17% of the time. Stand on 14 and that 17% is the whole of your "
                "win rate.",
                "Drawing breaks you 46% of the time and gives you a chance the rest. Against "
                "the best upcard on the table, a chance is what you are playing for.",
            ],
            "picture": "Seventeen percent is not a plan. It is what happens when you don't "
                       "have one.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
    },

    # --- 15: stand against 2 through 6 ----------------------------------
    15: {
        2: {
            "hook": "Fifteen against a 2. Stand.",
            "paragraphs": [
                "Over half the shoe busts this hand \u2014 54% of cards break a 15. The dealer "
                "breaks 35% of the time from a 2.",
                "You are far more likely to destroy this hand than they are to destroy theirs. "
                "Standing is the only sane side of that trade.",
            ],
            "picture": "Fifteen is the point where drawing becomes a coin flip you lose more "
                       "often than you win.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        3: {
            "hook": "Fifteen against a 3. Stand.",
            "paragraphs": [
                "Drawing busts you 54% of the time. A 3 busts 37% of the time on its own, with "
                "no help from you.",
                "Sit still and let the worse hand be theirs.",
            ],
            "picture": "There is no version of taking a card here that improves your position "
                       "on average. None.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        4: {
            "hook": "Fifteen against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. You bust 54% of the time if you draw. The gap is "
                "fifteen points and it all runs in one direction.",
                "Stand and collect the busts.",
            ],
            "picture": "A hand that breaks on more than half the shoe should not be drawing to "
                       "anything.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        5: {
            "hook": "Fifteen against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time. You bust 54% of the time. Those two numbers "
                "settle it before anything else gets a say.",
                "Fifteen is a poor hand. Against a 5 it does not have to be a good one.",
            ],
            "picture": "Your hand does not need to win. It needs to still be there when theirs "
                       "falls over.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        6: {
            "hook": "Fifteen against a 6. Stand.",
            "paragraphs": [
                "A 6 is the dealer's worst card, busting 42% of the time. Fifteen wins all of "
                "those and loses the rest, and that is a perfectly good outcome for a hand this "
                "bad.",
                "Drawing would throw away 54% of your hands outright.",
            ],
            "picture": "The whole plan against a 6 is to still be holding cards at the end. "
                       "Fifteen does that job as well as twenty does.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        7: {
            "hook": "Fifteen against a 7. Hit.",
            "paragraphs": [
                "A 7 busts only 26% of the time and lands on seventeen 37% of the time. "
                "Standing on 15 wins roughly a quarter of these hands and loses the other "
                "three quarters.",
                "Drawing busts you 54% of the time. It is genuinely unpleasant, and it is still "
                "the better half of a bad pair of options.",
            ],
            "picture": "Both doors lead somewhere bad. The chart's only job is to tell you "
                       "which one is less bad, and here it is the draw.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        8: {
            "hook": "Fifteen against an 8. Hit.",
            "paragraphs": [
                "Eighteen is their most likely finish, 36% of the time. They bust 24% of the "
                "time. Fifteen beats none of the first and needs all of the second.",
                "You break 54% of the time by drawing \u2014 and win far more of the remaining 46% "
                "than you would by standing.",
            ],
            "picture": "Standing here is choosing a 24% hand over a messy one that is worth "
                       "more. Messy and worth more still wins.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        9: {
            "hook": "Fifteen against a 9. Hit.",
            "paragraphs": [
                "A 9 busts 23% of the time and finishes on nineteen 35% of the time. Standing "
                "on 15 is a bet that they break, and they mostly don't.",
                "Drawing busts you 54% of the time. Take it anyway \u2014 this is one of the cells "
                "the chart is most confident about, however it feels.",
            ],
            "picture": "The hands you remember are the ones where you drew and broke. The ones "
                       "you lose silently by standing never stick in the memory.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        10: {
            "hook": "Fifteen against a 10. Hit. This is the hand everybody argues about.",
            "paragraphs": [
                "The dealer's likeliest finish is twenty, 37% of the time, and they bust just "
                "23% of the time. Stand on 15 and you win fewer than a quarter of these hands.",
                "Hitting busts you 54% of the time, so it looks like the reckless option and "
                "isn't. It is worth a little more than standing, every single time, and a "
                "little more repeated for long enough is the whole game.",
            ],
            "picture": "The hands you lose by hitting are memorable. The ones you lose by "
                       "standing are quiet. They cost the same.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        11: {
            "hook": "Fifteen against an ace. Hit.",
            "paragraphs": [
                "An ace busts 17% of the time and lands on 17 through 20 about evenly. Standing "
                "on 15 wins one hand in six.",
                "Drawing breaks you 54% of the time and wins you more than one in six. That is "
                "the entire case, and it is enough.",
            ],
            "picture": "Against an ace there is no waiting game to play. There is only the "
                       "hand you can build.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
    },

    # --- 16: stand against 2 through 6 ----------------------------------
    16: {
        2: {
            "hook": "Sixteen against a 2. Stand.",
            "paragraphs": [
                "Sixteen is the worst total in blackjack. Drawing breaks it 62% of the time \u2014 "
                "nearly two cards in three \u2014 while a 2 only breaks the dealer 35% of the time.",
                "You cannot make this hand good. You can only avoid making it dead, and that "
                "means standing.",
            ],
            "picture": "Sixteen is not a hand you play. It is a hand you survive.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        3: {
            "hook": "Sixteen against a 3. Stand.",
            "paragraphs": [
                "You break 62% of the time by drawing. They break 37% of the time by having to "
                "play at all.",
                "Two bad hands, but only one of you is obliged to take cards. Stand and make "
                "sure it's them.",
            ],
            "picture": "The dealer has no judgement and no choice. Against a small card that is "
                       "the worst thing to be.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        4: {
            "hook": "Sixteen against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. Drawing to 16 busts you 62% of the time. The "
                "difference is enormous and it is the entire decision.",
                "Do nothing and win nearly two hands in five.",
            ],
            "picture": "Sixty-two against thirty-nine. You don't need to like the hand to read "
                       "the numbers.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        5: {
            "hook": "Sixteen against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5. Your 16 wins every one of those "
                "without doing anything at all.",
                "Drawing would break you 62% of the time and throw most of those winners away.",
            ],
            "picture": "The worst hand in the game is still a winning hand 42% of the time "
                       "against a 5, as long as you leave it alone.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        6: {
            "hook": "Sixteen against a 6. Stand.",
            "paragraphs": [
                "A 6 busts 42% of the time, the highest of any upcard. This is the friendliest "
                "cell the 16 row has.",
                "Drawing breaks you 62% of the time. Against the one card most likely to break "
                "them, that would be an expensive way to be brave.",
            ],
            "picture": "Your terrible hand and their terrible card cancel out \u2014 but only if "
                       "you keep your hands off it.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "stand", "bust"],
        },
        7: {
            "hook": "Sixteen against a 7. Hit.",
            "paragraphs": [
                "The stand band ends at the 6. A 7 busts only 26% of the time and lands on "
                "seventeen 37% of the time, and your 16 loses to seventeen.",
                "Drawing busts you 62% of the time, which is awful. Standing loses you about "
                "74% of the time, which is worse.",
            ],
            "picture": "Sixteen against a big card is the most expensive hand in blackjack, "
                       "whichever way you play it. The chart just picks the cheaper disaster.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        8: {
            "hook": "Sixteen against an 8. Hit.",
            "paragraphs": [
                "Eighteen is the likeliest finish for an 8, 36% of the time, and they bust only "
                "24% of the time. Standing on 16 wins about a quarter of these hands.",
                "You break 62% of the time by drawing and still come out ahead of standing. "
                "That's how bad the alternative is.",
            ],
            "picture": "When both options are this poor, the gap between them is small \u2014 and "
                       "small gaps repeated a thousand times are exactly what you are practising for.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        9: {
            "hook": "Sixteen against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts 23% of the time. Sixteen "
                "beats none of that.",
                "Hitting busts you 62% of the time. Standing loses about 77% of the time. The "
                "chart takes the draw, and so should you.",
            ],
            "picture": "Sixteen against a big card is the most expensive spot in blackjack. "
                       "Play it correctly and move on quickly.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        10: {
            "hook": "Sixteen against a 10. The worst cell on the chart. Hit.",
            "paragraphs": [
                "This is the single most common losing hand in blackjack, and there is no good "
                "answer to it. The dealer's likeliest finish is twenty, 37% of the time, and "
                "they bust only 23% of the time.",
                "Drawing breaks you 62% of the time. Standing loses about 77% of the time. You "
                "lose this hand roughly three times in four no matter what you do \u2014 hitting "
                "just loses slightly less of it.",
            ],
            "picture": "You are not choosing a good outcome. You are shaving a percent off a "
                       "bad one, and doing that consistently is the entire skill.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
        11: {
            "hook": "Sixteen against an ace. Hit.",
            "paragraphs": [
                "An ace busts just 17% of the time. Stand on 16 and you are betting on the one "
                "outcome the dealer is least likely to hand you.",
                "Drawing breaks you 62% of the time \u2014 and still beats standing, because "
                "standing wins only 17%.",
            ],
            "picture": "The two worst things at the table have met: your worst total and their "
                       "best card. Take the card and move on quickly.",
            "remember": "Thirteen through sixteen: stand against 2 through 6, hit against 7 through ace.",
            "terms": ["stiff hand", "hit", "bust"],
        },
    },
})


# --- 17 and up: always stand -------------------------------------------

HARD.update({

    # --- 17: a bad hand you are stuck with ------------------------------
    17: {
        2: {
            "hook": "Hard 17 against a 2. Stand \u2014 and stop thinking about it.",
            "paragraphs": [
                "Seventeen is the weakest total worth keeping. Against a 2 it is roughly a "
                "coin flip: they bust 35% of the time and beat you with 18 or better a little "
                "less than half the time.",
                "Drawing breaks you 69% of the time. There is no card that improves this hand "
                "often enough to matter \u2014 a 4 is the only one that really helps, and it's one "
                "rank in thirteen.",
            ],
            "picture": "Seventeen is where the hand stops being yours to influence. Stand and "
                       "let it play out.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        3: {
            "hook": "Hard 17 against a 3. Stand.",
            "paragraphs": [
                "A 3 busts 37% of the time. Seventeen collects all of those and loses most of "
                "the rest, which is about as much as this total can ask for.",
                "Drawing busts you 69% of the time. That turns a hand that sometimes wins into "
                "one that mostly doesn't.",
            ],
            "picture": "Seventeen against a small card is a modest, unexciting winner. Take it.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        4: {
            "hook": "Hard 17 against a 4. Stand.",
            "paragraphs": [
                "The dealer busts 39% of the time from a 4. Add the hands where they finish "
                "below you and 17 comes out slightly ahead here.",
                "Drawing would break you 69% of the time. Nobody improves a 17 on purpose.",
            ],
            "picture": "Against the small cards, 17 is quietly profitable. It only feels bad "
                       "because the number is low.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        5: {
            "hook": "Hard 17 against a 5. Stand.",
            "paragraphs": [
                "A 5 busts 42% of the time. Seventeen is a winning hand against it, just not "
                "by much.",
                "Drawing busts you 69% of the time and would throw away a hand that is "
                "currently ahead.",
            ],
            "picture": "The rule for 17 is the same everywhere, which is precisely why it is "
                       "easy to keep.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        6: {
            "hook": "Hard 17 against a 6. Stand.",
            "paragraphs": [
                "A 6 busts 42% of the time, the most of any upcard. Seventeen wins about 42% "
                "of these hands and loses about 41% \u2014 the best this total ever does.",
                "Drawing breaks you 69% of the time. Leave it alone.",
            ],
            "picture": "This is 17 at its best: narrowly ahead. Don't spend it chasing a "
                       "better number.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        7: {
            "hook": "Hard 17 against a 7. Stand. This is the most likely push on the board.",
            "paragraphs": [
                "A 7 finishes on exactly seventeen 37% of the time \u2014 more often than any "
                "dealer total against any upcard. So more than a third of these hands are ties "
                "where nobody wins and your bet comes back.",
                "Drawing breaks you 69% of the time and turns the most likely push in blackjack "
                "into an immediate loss.",
            ],
            "picture": "Upcard plus ten is the dealer's most likely finish. Hold that same "
                       "number and you are holding a push.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "push"],
        },
        8: {
            "hook": "Hard 17 against an 8. Stand.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time, so you are behind here \u2014 17 loses "
                "to their single most likely hand.",
                "That is unpleasant and it changes nothing. Drawing busts you 69% of the time, "
                "which is far worse than being a modest underdog.",
            ],
            "picture": "Being behind is not a reason to set fire to the hand.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        9: {
            "hook": "Hard 17 against a 9. Stand.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time and busts only 23% of the time. "
                "Seventeen is a clear underdog.",
                "It is still much better than a 69% chance of busting on the spot. Stand.",
            ],
            "picture": "A losing hand that might win beats a losing hand that cannot.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        10: {
            "hook": "Hard 17 against a 10. Stand, however wrong it feels.",
            "paragraphs": [
                "This is the hand that tempts people into drawing. You win about 23% of the "
                "time by standing and lose about 65% \u2014 a genuinely bad spot, since the dealer's "
                "likeliest finish is twenty.",
                "Drawing busts you 69% of the time. You'd be trading a hand that wins nearly a "
                "quarter of the time for one that mostly loses on the spot.",
            ],
            "picture": "Seventeen against a ten is a losing hand. Hitting it is a more "
                       "expensive losing hand. That's the whole choice.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        11: {
            "hook": "Hard 17 against an ace. Stand.",
            "paragraphs": [
                "An ace busts only 17% of the time and lands on 17 through 20 about evenly, so "
                "roughly a fifth of these hands are pushes and most of the rest are losses.",
                "Drawing breaks you 69% of the time. The bad hand you have is better than the "
                "broken one you'd be buying.",
            ],
            "picture": "Some hands are simply lost when they are dealt. Playing them correctly "
                       "means losing them cheaply.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "push"],
        },
    },

    # --- 18 -------------------------------------------------------------
    18: {
        2: {
            "hook": "Eighteen against a 2. Stand.",
            "paragraphs": [
                "Eighteen is a real hand. Against a 2 it wins well over half the time: they "
                "bust 35% of the time and finish below you a good chunk of the rest.",
                "Drawing breaks you 77% of the time. There is nothing here worth risking.",
            ],
            "picture": "Eighteen against a small card is money in the bank. Leave it in the bank.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        3: {
            "hook": "Eighteen against a 3. Stand.",
            "paragraphs": [
                "They bust 37% of the time from a 3, and 18 beats every finish below nineteen "
                "on top of that. This is comfortably a winning hand.",
                "Drawing busts you 77% of the time \u2014 more than three cards in four.",
            ],
            "picture": "You are ahead. The only way to stop being ahead is to take a card.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        4: {
            "hook": "Eighteen against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. Eighteen is well ahead of everything else they are "
                "likely to make from it.",
                "Drawing breaks you 77% of the time. Not close.",
            ],
            "picture": "Good hand, bad dealer card. Do nothing and collect.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        5: {
            "hook": "Eighteen against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5. Eighteen wins those and most of "
                "what's left.",
                "Drawing busts you 77% of the time. This is one of the easiest stands on the "
                "chart.",
            ],
            "picture": "Eighteen against a 5 wins close to three hands in five. That is a "
                       "great result in this game.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        6: {
            "hook": "Eighteen against a 6. Stand.",
            "paragraphs": [
                "A 6 busts 42% of the time and rarely gets past seventeen when it doesn't. "
                "Eighteen wins about 59% of these hands and loses about 31%.",
                "Drawing breaks you 77% of the time. There is no argument here at all.",
            ],
            "picture": "Your good hand against their worst card. Enjoy it and stand.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        7: {
            "hook": "Eighteen against a 7. Stand \u2014 you are ahead.",
            "paragraphs": [
                "A 7's most likely finish is exactly seventeen, 37% of the time. Eighteen beats "
                "it by one, which is all it has to do.",
                "Drawing busts you 77% of the time and throws away a hand that is currently "
                "winning.",
            ],
            "picture": "The card above their likeliest total is worth more than it looks. One "
                       "point is the same as a hundred.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        8: {
            "hook": "Eighteen against an 8. Stand. Expect a lot of ties.",
            "paragraphs": [
                "An 8 finishes on exactly eighteen 36% of the time, so more than a third of "
                "these hands are pushes. Upcard plus ten is always the dealer's most likely "
                "total, and here it happens to be yours too.",
                "Drawing breaks you 77% of the time and converts a lot of those pushes into "
                "losses.",
            ],
            "picture": "Matching the dealer's likeliest finish is not winning, but it isn't "
                       "losing either, and it costs nothing.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "push"],
        },
        9: {
            "hook": "Eighteen against a 9. Stand.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time, so eighteen is behind \u2014 this is a "
                "losing cell and it is meant to be.",
                "Drawing busts you 77% of the time. Losing slowly beats losing instantly.",
            ],
            "picture": "Eighteen looks like a good hand and stops being one the moment the "
                       "upcard is a 9 or bigger.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        10: {
            "hook": "Eighteen against a 10. Stand.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time, so eighteen loses more "
                "often than it wins here \u2014 about 53% against 35%.",
                "Drawing breaks you 77% of the time. A losing hand is not improved by burning it.",
            ],
            "picture": "Against a ten you need nineteen or twenty to feel comfortable. "
                       "Eighteen just has to take its chances.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        11: {
            "hook": "Eighteen against an ace. Stand.",
            "paragraphs": [
                "An ace busts only 17% of the time and spreads evenly across 17 to 20, so "
                "eighteen wins some, ties some and loses more than it wins.",
                "Drawing busts you 77% of the time. Keep the hand.",
            ],
            "picture": "Against an ace almost everything is an underdog. Eighteen is a "
                       "respectable one.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
    },

    # --- 19 -------------------------------------------------------------
    19: {
        2: {
            "hook": "Nineteen against a 2. Stand.",
            "paragraphs": [
                "Nineteen beats or ties almost everything a 2 can turn into, and they bust 35% "
                "of the time on top of that.",
                "Drawing breaks you 85% of the time. Only a 2 improves this hand, and there is "
                "one of those for every thirteen cards.",
            ],
            "picture": "Nineteen is a hand you win with. There is nothing to think about.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        3: {
            "hook": "Nineteen against a 3. Stand.",
            "paragraphs": [
                "They bust 37% of the time and need twenty or twenty-one to beat you. Nineteen "
                "wins the large majority of these.",
                "Drawing busts you 85% of the time.",
            ],
            "picture": "Strong hand, weak card, no decision.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        4: {
            "hook": "Nineteen against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time. Nineteen beats every finish below twenty.",
                "Drawing breaks you 85% of the time. Don't.",
            ],
            "picture": "The chart has nothing interesting to say about nineteen, which is "
                       "exactly what makes it a good hand.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        5: {
            "hook": "Nineteen against a 5. Stand.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5 and rarely reaches twenty when they "
                "don't. Nineteen is a strong favourite.",
                "Drawing busts you 85% of the time.",
            ],
            "picture": "Nineteen against a small card wins about seven hands in ten. Bank it.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        6: {
            "hook": "Nineteen against a 6. Stand.",
            "paragraphs": [
                "A 6 busts 42% of the time, the most of any upcard. Nineteen wins about 70% of "
                "these hands and loses about 20%.",
                "Drawing breaks you 85% of the time. This is as settled as blackjack gets.",
            ],
            "picture": "Your strong hand against their worst card. The only mistake available "
                       "is to invent one.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        7: {
            "hook": "Nineteen against a 7. Stand.",
            "paragraphs": [
                "Their likeliest finish is seventeen, 37% of the time, and nineteen clears it "
                "easily. Only an eventual twenty or twenty-one beats you.",
                "Drawing busts you 85% of the time.",
            ],
            "picture": "Two clear above their most likely total. That is a comfortable place "
                       "to be standing.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        8: {
            "hook": "Nineteen against an 8. Stand.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Nineteen beats that, and beats "
                "everything below it.",
                "Drawing breaks you 85% of the time. Keep what you have.",
            ],
            "picture": "One above their best guess again. It keeps being enough.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        9: {
            "hook": "Nineteen against a 9. Stand. Expect ties.",
            "paragraphs": [
                "A 9 finishes on exactly nineteen 35% of the time, so this is the push cell of "
                "the row \u2014 upcard plus ten, matched.",
                "Drawing busts you 85% of the time and turns a third of these pushes into "
                "instant losses.",
            ],
            "picture": "A tie is not a win, but it is the whole of your bet coming back. "
                       "That's worth protecting.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "push"],
        },
        10: {
            "hook": "Nineteen against a 10. Stand.",
            "paragraphs": [
                "The dealer's likeliest finish is twenty, 37% of the time, so nineteen is only "
                "narrowly ahead overall \u2014 about 47% wins against 41% losses.",
                "Drawing breaks you 85% of the time. Narrowly ahead is still ahead.",
            ],
            "picture": "Against a ten, nineteen is a good hand that doesn't feel like one. "
                       "Trust the number, not the feeling.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
        11: {
            "hook": "Nineteen against an ace. Stand.",
            "paragraphs": [
                "An ace busts 17% of the time and spreads evenly across 17 to 20. Nineteen "
                "beats most of that spread and ties a slice of it.",
                "Drawing busts you 85% of the time.",
            ],
            "picture": "Even against the best upcard in the game, nineteen is doing fine.",
            "remember": "Hard 17 and up always stands. There is no exception anywhere in the row.",
            "terms": ["hard hand", "stand", "bust"],
        },
    },

    # --- 20 -------------------------------------------------------------
    20: {
        2: {
            "hook": "Twenty against a 2. Stand. Obviously.",
            "paragraphs": [
                "Twenty loses only to a dealer twenty-one and ties only a dealer twenty. "
                "Against a 2 you win about four hands in five.",
                "Drawing breaks you 92% of the time. There is exactly one helpful card in the "
                "shoe and twelve that ruin you.",
            ],
            "picture": "Twenty is the second-best hand in blackjack. There is no version of "
                       "this where you touch it.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "bust"],
        },
        3: {
            "hook": "Twenty against a 3. Stand.",
            "paragraphs": [
                "Nothing beats twenty except twenty-one. Against a 3 that is a rare event, and "
                "they bust 37% of the time besides.",
                "Drawing busts you 92% of the time.",
            ],
            "picture": "You already hold a near-certain winner. Selling it buys nothing.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "bust"],
        },
        4: {
            "hook": "Twenty against a 4. Stand.",
            "paragraphs": [
                "A 4 busts 39% of the time and almost never gets to twenty-one. This hand is "
                "as close to decided as they come.",
                "Drawing breaks you 92% of the time.",
            ],
            "picture": "The only thing that can go wrong here is you.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "bust"],
        },
        5: {
            "hook": "Twenty against a 5. Stand.",
            "paragraphs": [
                "They bust 42% of the time and need a perfect twenty-one to beat you. You win "
                "roughly four hands in five.",
                "Drawing busts you 92% of the time.",
            ],
            "picture": "This is what you were hoping for when the cards came out. Don't "
                       "improve it.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "bust"],
        },
        6: {
            "hook": "Twenty against a 6. Stand.",
            "paragraphs": [
                "The best hand against the worst card. They bust 42% of the time and you win "
                "about 80% of these overall.",
                "Drawing breaks you 92% of the time, which would be a spectacular way to lose "
                "a won hand.",
            ],
            "picture": "Eighty percent. Stand.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "bust"],
        },
        7: {
            "hook": "Twenty against a 7. Stand.",
            "paragraphs": [
                "Their likeliest finish is seventeen, 37% of the time, and twenty is three "
                "clear of it. Only twenty-one beats you.",
                "Drawing busts you 92% of the time.",
            ],
            "picture": "Comfortably ahead of everything they are likely to make.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        8: {
            "hook": "Twenty against an 8. Stand.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Twenty beats it and everything "
                "below it.",
                "Drawing breaks you 92% of the time.",
            ],
            "picture": "There is no upcard that makes twenty a difficult decision.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        9: {
            "hook": "Twenty against a 9. Stand.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time. Twenty beats it by one, and beats "
                "everything else they can make except twenty-one.",
                "Drawing busts you 92% of the time.",
            ],
            "picture": "One above their likeliest total, again. One is enough, again.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "upcard"],
        },
        10: {
            "hook": "Twenty against a 10. Stand. Expect a lot of pushes.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time, so a big share of these "
                "hands tie. You still win about 59% and lose under 4%.",
                "Drawing breaks you 92% of the time. Nothing about a ten upcard changes that.",
            ],
            "picture": "Even in its worst cell, twenty loses fewer than one hand in twenty-five.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "push"],
        },
        11: {
            "hook": "Twenty against an ace. Stand.",
            "paragraphs": [
                "An ace busts 17% of the time and lands on 17 through 20 about evenly. Twenty "
                "beats or ties nearly all of it.",
                "Drawing busts you 92% of the time. And no, this is not a reason to take "
                "insurance either.",
            ],
            "picture": "Holding twenty against an ace is the most common moment people talk "
                       "themselves into a bad side bet. Don't.",
            "remember": "Hard 17 and up always stands. Twenty especially: never break a twenty.",
            "terms": ["hard hand", "stand", "insurance"],
        },
    },

    # --- 21 -------------------------------------------------------------
    21: {
        u: {
            "hook": "Twenty-one. Stand.",
            "paragraphs": [
                "You have the best total in the game. Nothing beats it and only another "
                "twenty-one ties it.",
                "Every card in the shoe busts this hand. There is no decision here at all.",
            ],
            "picture": "The hand is over. The dealer just doesn't know it yet.",
            "remember": "Hard 17 and up always stands. Twenty-one most of all.",
            "terms": ["hard hand", "stand", "bust"],
        } for u in range(2, 12)
    },
})


# ---------------------------------------------------------------------------
# Soft totals. Keyed by the soft total, then by dealer upcard.
#
# A soft hand is one where an ace is counting as 11 and can still drop to 1.
# That single fact drives the whole section: no card in the shoe can bust a
# soft hand, so drawing is free and standing early is the only real mistake.
#
# The doubling ladder, which is the thing actually worth memorising:
#     soft 13 and 14 ...... double against 5, 6
#     soft 15 and 16 ...... double against 4, 5, 6
#     soft 17 and 18 ...... double against 3, 4, 5, 6
# Every rung ends at the 6. Each step up the hand starts one column earlier.
# ---------------------------------------------------------------------------

SOFT = {

    # --- soft 12: a pair of aces you weren't able to split ---------------
    12: {
        u: {
            "hook": "Two aces you can't split. Hit.",
            "paragraphs": [
                "A,A is a soft 12 \u2014 and that is the worst use of the best card in the game. "
                "You would normally split it, but you can't here: either you already have four "
                "hands going or the money for a second bet isn't there.",
                "So take a card. You cannot bust \u2014 the ace simply drops from 11 to 1 \u2014 and "
                "standing on 12 would hand the hand over for nothing.",
            ],
            "picture": "One ace is doing all the work and the other is sitting on top of it "
                       "doing nothing. If you can't give the second one its own hand, at least "
                       "give it a card.",
            "remember": "A soft hand never stands below 18. Nothing in the shoe can bust it.",
            "terms": ["soft hand", "hit", "split"],
        } for u in range(2, 12)
    },

    # --- soft 13 (A,2): doubles against 5 and 6 --------------------------
    13: {
        2: {
            "hook": "Soft 13 against a 2. Hit.",
            "paragraphs": [
                "A,2 is the weakest soft hand there is, and a 2 is the least weak of the "
                "dealer's small cards \u2014 they bust just 35% of the time. Not enough to justify "
                "buying one card and stopping.",
                "So hit, and keep hitting. You cannot bust: the ace drops from 11 to 1 the "
                "moment it needs to. A draw with no downside is never wrong.",
            ],
            "picture": "The bottom rung of the soft ladder starts at the 5. This is two "
                       "columns short of it.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "bust"],
        },
        3: {
            "hook": "Soft 13 against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time, which is not yet enough to commit a second bet on "
                "a hand this small. Soft 13 needs real improvement, not one card and a stop.",
                "Hitting is free. No card in the shoe can break a soft hand.",
            ],
            "picture": "A weak dealer is only worth extra money when your own hand can use it. "
                       "Thirteen can't yet.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "bust"],
        },
        4: {
            "hook": "Soft 13 against a 4. Hit.",
            "paragraphs": [
                "A 4 busts 39% of the time. Soft 15 and 16 would double here \u2014 soft 13 is one "
                "rung too low, because a single card on A,2 so rarely lands anywhere strong.",
                "Hit instead, as many times as you like. A soft hand cannot be busted.",
            ],
            "picture": "The ladder: 13 and 14 start at 5, 15 and 16 start at 4, 17 and 18 "
                       "start at 3. Knowing which rung you're on is most of this section.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "double down"],
        },
        5: {
            "hook": "Soft 13 against a 5. Double \u2014 the row opens here.",
            "paragraphs": [
                "A 5 busts 42% of the time. That is finally weak enough to be worth a second "
                "bet even on a hand as thin as A,2.",
                "And the double is risk-free in one specific sense: the card you buy cannot "
                "bust you. Worst case the ace drops to 1 and you are left with a low total "
                "against a dealer who is about to draw from a 5.",
            ],
            "picture": "You are not doubling because your hand is good. You are doubling "
                       "because theirs is bad and yours cannot be damaged.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 13 against a 6. Double.",
            "paragraphs": [
                "A 6 is the dealer's worst card, busting 42% of the time. Even the weakest soft "
                "hand on the chart is worth extra money against it.",
                "No card can break you. The whole decision is about them, not you \u2014 and they "
                "are in as much trouble as they ever get.",
            ],
            "picture": "A soft hand is a hand with a spare life. Spending it on a free card "
                       "costs you nothing at all.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 13 against a 7. Hit.",
            "paragraphs": [
                "The row closes after the 6. A 7 busts only 26% of the time and finishes on "
                "seventeen 37% of the time \u2014 there is no weakness to buy into.",
                "Hit, and go on hitting until you have something worth keeping. It costs "
                "nothing: soft hands cannot bust.",
            ],
            "picture": "Against the big cards, soft hands stop being about extra money and go "
                       "back to being about building a total.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        8: {
            "hook": "Soft 13 against an 8. Hit.",
            "paragraphs": [
                "An 8 lands on eighteen 36% of the time and busts only 24% of the time. You "
                "need a genuine hand here, and A,2 is a long way from one.",
                "Draw freely. Nothing in the shoe can break a soft total.",
            ],
            "picture": "Free cards are free cards. Take as many as the hand will give you.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        9: {
            "hook": "Soft 13 against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time. Soft 13 beats nothing at all, so "
                "the only route to winning is more cards.",
                "Which is fine, because they are free. The ace absorbs whatever turns up.",
            ],
            "picture": "There is no risk in this decision, only a shortage of total.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        10: {
            "hook": "Soft 13 against a 10. Hit.",
            "paragraphs": [
                "Twenty is a ten's likeliest finish, 37% of the time. You will need to build "
                "something substantial, and A,2 is the start of that, not the end.",
                "Nothing can bust you on the way. Keep drawing.",
            ],
            "picture": "Against a ten you are always climbing. A soft hand is the easiest "
                       "thing to climb with.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        11: {
            "hook": "Soft 13 against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time, the least of any upcard, and lands on 17 "
                "through 20 about evenly. Waiting them out is not a plan.",
                "Draw. A soft hand can take a card against anything without risk.",
            ],
            "picture": "Your ace and their ace are not the same thing. Yours is protection; "
                       "theirs is a weapon.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
    },

    # --- soft 14 (A,3): doubles against 5 and 6 --------------------------
    14: {
        2: {
            "hook": "Soft 14 against a 2. Hit.",
            "paragraphs": [
                "A,3 shares its row with A,2: both start doubling at the 5. A 2 busts 35% of "
                "the time, which isn't enough to buy one card and stop.",
                "Hitting costs nothing \u2014 a soft hand cannot bust. Draw and reassess.",
            ],
            "picture": "Same rung, same answer. A,2 and A,3 behave identically all the way "
                       "across the chart.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "bust"],
        },
        3: {
            "hook": "Soft 14 against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time. Soft 17 would double here; soft 14 is two rungs "
                "lower and needs a weaker card before a second bet makes sense.",
                "Take the free card instead. Nothing can break a soft hand.",
            ],
            "picture": "The lower the soft hand, the weaker the dealer has to be before "
                       "doubling is worth it. That's the whole ladder.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "double down"],
        },
        4: {
            "hook": "Soft 14 against a 4. Hit.",
            "paragraphs": [
                "A 4 busts 39% of the time and it is tempting \u2014 but this is where soft 15 and "
                "16 start doubling, not soft 13 and 14.",
                "One card on A,3 lands somewhere useful too rarely to be worth freezing the "
                "hand. Hit, and keep your options.",
            ],
            "picture": "One column short. The 14 row opens at the 5, not the 4.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "double down"],
        },
        5: {
            "hook": "Soft 14 against a 5. Double.",
            "paragraphs": [
                "The row opens here. A 5 busts 42% of the time \u2014 weak enough that getting a "
                "second bet down beats keeping the right to draw again.",
                "And there is no bust risk in the card you buy. The ace drops to 1 if it has "
                "to and you carry on with whatever you've got.",
            ],
            "picture": "Doubling a soft hand is a bet on the dealer breaking, not on your own "
                       "card being good.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 14 against a 6. Double.",
            "paragraphs": [
                "A 6 busts 42% of the time, the most of any upcard. Weak dealer plus a hand "
                "that cannot be damaged means put more money out.",
                "The card you buy might make the hand worse on paper and it cannot make it "
                "dead. That asymmetry is what you're paying for.",
            ],
            "picture": "Every rung of the soft ladder ends at the 6. If you remember one "
                       "column, remember that one.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 14 against a 7. Hit.",
            "paragraphs": [
                "A 7 busts only 26% of the time and finishes on seventeen 37% of the time. "
                "Soft 14 has to become a real hand to beat that, and one card won't do it "
                "often enough.",
                "Hit. It's free, and you can do it as many times as you need.",
            ],
            "picture": "The doubling window slams shut at the 7 for every soft hand on the "
                       "chart.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        8: {
            "hook": "Soft 14 against an 8. Hit.",
            "paragraphs": [
                "Eighteen is their most likely finish, 36% of the time. You need to get past "
                "it, and you are starting from 14.",
                "Nothing in the shoe can bust you, so keep taking cards until the hand is "
                "worth standing on.",
            ],
            "picture": "A soft hand against a big card is simply a work in progress.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        9: {
            "hook": "Soft 14 against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time and busts 23% of the time. Fourteen "
                "beats none of it.",
                "Draw freely \u2014 there is no card that can hurt a soft hand.",
            ],
            "picture": "No risk, not enough total. The answer writes itself.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        10: {
            "hook": "Soft 14 against a 10. Hit.",
            "paragraphs": [
                "The dealer's likeliest finish is twenty, 37% of the time. A,3 is nowhere near "
                "that yet.",
                "Keep drawing. A soft hand cannot bust, so there is no reason to stop early.",
            ],
            "picture": "Against a ten, stopping short is the only way to guarantee losing.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        11: {
            "hook": "Soft 14 against an ace. Hit.",
            "paragraphs": [
                "An ace busts just 17% of the time. There is no outlasting it, only outbuilding "
                "it.",
                "Fortunately drawing is free. The ace in your own hand makes sure of that.",
            ],
            "picture": "Two aces on the table, and only one of them is working for you.",
            "remember": "Soft 13 and 14 double against 5 and 6 only. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
    },

    # --- soft 15 (A,4): doubles against 4, 5 and 6 -----------------------
    15: {
        2: {
            "hook": "Soft 15 against a 2. Hit.",
            "paragraphs": [
                "A 2 busts 35% of the time \u2014 the least of the dealer's small cards, and not "
                "weak enough to commit a second bet to a soft 15.",
                "Hit instead. The ace protects you completely: no card in the shoe can break "
                "this hand.",
            ],
            "picture": "The 15 row opens at the 4. This is two columns early.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "bust"],
        },
        3: {
            "hook": "Soft 15 against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time. Soft 17 and 18 start doubling here; soft 15 needs "
                "one more column of dealer weakness first.",
                "Draw. It's free, and it keeps the right to draw again.",
            ],
            "picture": "Each step up the soft ladder buys you one extra column on the left. "
                       "Fifteen hasn't earned the 3.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "double down"],
        },
        4: {
            "hook": "Soft 15 against a 4. Double \u2014 the row opens here.",
            "paragraphs": [
                "A 4 busts 39% of the time. That is the threshold where a soft 15 becomes worth "
                "a second bet, one column earlier than soft 13 and 14 manage.",
                "The card you buy cannot bust you. You are spending money on the dealer's "
                "weakness, not gambling on your own draw.",
            ],
            "picture": "Middle rung of the ladder: 4, 5, 6. Learn the three rungs and the soft "
                       "section is basically done.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        5: {
            "hook": "Soft 15 against a 5. Double.",
            "paragraphs": [
                "A 5 busts 42% of the time. Your hand cannot be damaged by the card you take. "
                "Both of those point the same way.",
                "This is the shape of every soft double: weak dealer, no downside, more money.",
            ],
            "picture": "You are buying a lottery ticket that cannot lose its own value \u2014 only "
                       "fail to gain any.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 15 against a 6. Double.",
            "paragraphs": [
                "The dealer's worst card, busting 42% of the time, against a hand that cannot "
                "bust at all.",
                "Double. There is no version of this where keeping the extra bet in your "
                "pocket is right.",
            ],
            "picture": "Their 6 does the work. Your ace makes sure you're still there to "
                       "collect.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 15 against a 7. Hit.",
            "paragraphs": [
                "The row closes after the 6, every time. A 7 busts 26% of the time and lands "
                "on seventeen 37% of the time.",
                "Hit and rebuild. Soft hands draw for free, so there is no cost to taking as "
                "many cards as the hand needs.",
            ],
            "picture": "Seven and up: no soft hand doubles, ever. One rule, one edge of the "
                       "table.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        8: {
            "hook": "Soft 15 against an 8. Hit.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Fifteen doesn't get near it.",
                "Draw. There is no risk in it and no reason to stop.",
            ],
            "picture": "A soft 15 is not a hand yet. It's raw material.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        9: {
            "hook": "Soft 15 against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time and busts only 23% of the time. You "
                "need to build, not wait.",
                "Nothing can break a soft hand. Keep going.",
            ],
            "picture": "The only mistake available against a big card is stopping too soon.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        10: {
            "hook": "Soft 15 against a 10. Hit.",
            "paragraphs": [
                "Twenty is where a ten most often ends up, 37% of the time. Fifteen is not in "
                "the conversation.",
                "Draw, and go on drawing. The ace makes every one of those cards free.",
            ],
            "picture": "Soft hands are the one part of blackjack with no fear in them. Use "
                       "that.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        11: {
            "hook": "Soft 15 against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time. The dealer is not going to lose this hand "
                "for you.",
                "So take cards until you have something real. They cost nothing.",
            ],
            "picture": "Against an ace, every hand is a building project.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
    },

    # --- soft 16 (A,5): doubles against 4, 5 and 6 -----------------------
    16: {
        2: {
            "hook": "Soft 16 against a 2. Hit.",
            "paragraphs": [
                "A,5 sits on the same rung as A,4: both open at the 4. A 2 busts 35% of the "
                "time, which isn't enough.",
                "Hit. A soft hand cannot bust, so this is a free card every single time.",
            ],
            "picture": "Soft 15 and soft 16 are the same row. One fewer thing to remember.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "bust"],
        },
        3: {
            "hook": "Soft 16 against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time \u2014 enough for soft 17 and 18 to double, not enough "
                "for soft 16.",
                "Take the free card instead and see where the hand lands.",
            ],
            "picture": "Three rungs, three starting columns: 5, then 4, then 3. Soft 16 is on "
                       "the middle one.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "double down"],
        },
        4: {
            "hook": "Soft 16 against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time, and that's the line where soft 16 starts putting "
                "extra money out.",
                "You cannot bust on the card you buy. The worst outcome is a low total against "
                "a dealer who still has to draw from a 4.",
            ],
            "picture": "Soft doubles are not about your hand improving. They are about their "
                       "hand collapsing while your bet is twice as big.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        5: {
            "hook": "Soft 16 against a 5. Double.",
            "paragraphs": [
                "A 5 busts 42% of the time. Nearly half of these hands you win without your "
                "own total ever being compared to anything.",
                "And the card you take cannot break you. Put the money out.",
            ],
            "picture": "Weak card, spare life, second bet. The same three ingredients every "
                       "time.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 16 against a 6. Double.",
            "paragraphs": [
                "The 6 is the dealer's worst card at 42% bust, and a soft 16 has nothing to "
                "lose by taking one card.",
                "Every soft rung includes the 6. This is the most reliable column on the whole "
                "soft chart.",
            ],
            "picture": "If the dealer shows a 6 and you are holding an ace, money should be "
                       "going down. Almost without exception.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 16 against a 7. Hit.",
            "paragraphs": [
                "Seventeen is a 7's most likely finish, 37% of the time, and they bust only "
                "26% of the time. Nothing to buy into here.",
                "Hit, for free, as often as the hand needs.",
            ],
            "picture": "Past the 6, soft hands go back to being ordinary hands with a safety "
                       "net.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        8: {
            "hook": "Soft 16 against an 8. Hit.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Soft 16 loses to that and to "
                "almost everything else.",
                "Draw. It costs nothing and it's the only way this hand gets better.",
            ],
            "picture": "Sixteen is a terrible hard total and a perfectly relaxed soft one. The "
                       "ace is the entire difference.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "stiff hand"],
        },
        9: {
            "hook": "Soft 16 against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time. You are a long way behind and there is "
                "no cost to catching up.",
                "Keep drawing until the hand is worth standing on.",
            ],
            "picture": "No card in the shoe can hurt you. Act like it.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        10: {
            "hook": "Soft 16 against a 10. Hit.",
            "paragraphs": [
                "Twenty, 37% of the time, is what you are chasing. Soft 16 is not close.",
                "Draw freely. The ace drops to 1 whenever it needs to and the hand survives.",
            ],
            "picture": "The same 16 that you'd agonise over as a hard total is a non-event as "
                       "a soft one.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "stiff hand"],
        },
        11: {
            "hook": "Soft 16 against an ace. Hit.",
            "paragraphs": [
                "An ace busts 17% of the time, less than any other upcard. Standing on a soft "
                "16 would be giving the hand away for no reason at all.",
                "Draw. There is no risk attached.",
            ],
            "picture": "You have a spare life. Not spending it doesn't save it \u2014 it just "
                       "costs you the hand.",
            "remember": "Soft 15 and 16 double against 4, 5 and 6. Otherwise hit.",
            "terms": ["soft hand", "hit", "upcard"],
        },
    },

    # --- soft 17 (A,6): doubles against 3 through 6, never stands --------
    17: {
        2: {
            "hook": "Soft 17 against a 2. Hit \u2014 and never stand on it.",
            "paragraphs": [
                "Soft 17 is the great trap of this section. It looks like a made hand and "
                "isn't: seventeen loses to every dealer total from eighteen up, and standing "
                "on it wins only when they bust.",
                "A 2 busts 35% of the time, not quite enough to double. So hit \u2014 which costs "
                "nothing, because the ace drops to 1 if the card is big.",
            ],
            "picture": "A soft 17 that you stand on is just a hard 17 you chose on purpose. "
                       "Nobody chooses a hard 17.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "stand"],
        },
        3: {
            "hook": "Soft 17 against a 3. Double \u2014 the row opens here.",
            "paragraphs": [
                "A 3 busts 37% of the time. Soft 17 is high enough up the ladder to take the "
                "3, one column earlier than soft 15 and 16 manage.",
                "The card you buy cannot break you. You are putting money out against a dealer "
                "who has to draw from a bad start.",
            ],
            "picture": "Top rung of the ladder: 3, 4, 5, 6. Soft 17 and soft 18 share it.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "double down", "bust"],
        },
        4: {
            "hook": "Soft 17 against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time. Your hand cannot be damaged by a single card. That "
                "is all the justification a double needs.",
                "Standing is not on the table here and neither is caution \u2014 soft 17 wants "
                "either more money or more cards, never less of both.",
            ],
            "picture": "The ace makes the risk vanish. All that's left is the dealer's weakness.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "double down", "bust"],
        },
        5: {
            "hook": "Soft 17 against a 5. Double.",
            "paragraphs": [
                "The dealer busts 42% of the time from a 5. Soft 17 doubles into that happily.",
                "If the card is a small one you improve; if it's a big one the ace drops and "
                "you're on a low hard total against a dealer about to draw badly. Neither is a "
                "disaster.",
            ],
            "picture": "You are getting paid twice for a hand that was going to be decided by "
                       "their cards anyway.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 17 against a 6. Double.",
            "paragraphs": [
                "The best soft double there is: their worst card at 42% bust, against a hand "
                "with no downside.",
                "This is what the ladder has been building towards. Take it every time.",
            ],
            "picture": "Ace and six, dealer shows a six. Money out.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 17 against a 7. Hit. Do not stand.",
            "paragraphs": [
                "This is the single most commonly misplayed soft hand. A 7 finishes on exactly "
                "seventeen 37% of the time \u2014 so standing gets you a push at best against their "
                "likeliest hand, and a loss against everything above it.",
                "Hitting is free. The ace absorbs any card, so you get a shot at eighteen or "
                "better with nothing at risk.",
            ],
            "picture": "Standing on soft 17 against a 7 is choosing a tie over a free chance "
                       "at a win. It is never right.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "push"],
        },
        8: {
            "hook": "Soft 17 against an 8. Hit.",
            "paragraphs": [
                "An 8 lands on eighteen 36% of the time. Seventeen loses to that outright.",
                "You cannot bust, so drawing is pure upside. There is no argument for keeping "
                "a losing total when improving it is free.",
            ],
            "picture": "A hand that can only be improved should always be improved.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        9: {
            "hook": "Soft 17 against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time and busts only 23% of the time. "
                "Standing on seventeen here is close to conceding.",
                "Draw. Nothing in the shoe can break you.",
            ],
            "picture": "Seventeen is not a total. It's a stopping point you should keep "
                       "walking past.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        10: {
            "hook": "Soft 17 against a 10. Hit.",
            "paragraphs": [
                "Twenty is where a ten most often lands, 37% of the time. Seventeen is three "
                "short and standing changes nothing.",
                "Hit, for free, and keep hitting.",
            ],
            "picture": "Free cards against the strongest upcards is exactly when the ace earns "
                       "its keep.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "upcard"],
        },
        11: {
            "hook": "Soft 17 against an ace. Hit.",
            "paragraphs": [
                "An ace busts just 17% of the time, so standing on seventeen wins about one "
                "hand in six.",
                "Drawing costs nothing at all. There is no defensible reason to stop here.",
            ],
            "picture": "Never stand on soft 17. Not against a 7, not against an ace, not "
                       "against anything.",
            "remember": "Soft 17 doubles against 3 through 6 and hits everywhere else. It never stands.",
            "terms": ["soft hand", "hit", "stand"],
        },
    },

    # --- soft 18 (A,7): the busiest row on the chart ---------------------
    18: {
        2: {
            "hook": "Soft 18 against a 2. Stand.",
            "paragraphs": [
                "Soft 18 is the only row on the chart that does all three things \u2014 stand, "
                "double and hit \u2014 and this is its left edge. A 2 busts 35% of the time, which "
                "isn't weak enough to double, and eighteen is already ahead of most of what "
                "they make from a 2.",
                "So keep it. " + H17,
            ],
            "picture": "One column to the right and this becomes a double. Soft 18 is the row "
                       "worth learning cell by cell.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "stand", "s17"],
        },
        3: {
            "hook": "Soft 18 against a 3. Double.",
            "paragraphs": [
                "A 3 busts 37% of the time and soft 18 sits on the top rung of the ladder, so "
                "the doubling window opens here.",
                "You cannot bust on the card you take. If it's small you improve on eighteen; "
                "if it's large the ace drops and you still have a live hand against a weak "
                "dealer.",
            ],
            "picture": "Doubling an eighteen feels wrong because eighteen looks finished. "
                       "Against a 3 it isn't finished, it's just adequate.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "double down", "bust"],
        },
        4: {
            "hook": "Soft 18 against a 4. Double.",
            "paragraphs": [
                "A 4 busts 39% of the time. You are doubling to get money down against a "
                "dealer in trouble, not because you need a better total.",
                "If the table won't let you double, stand \u2014 never hit this one. That's the "
                "one place in the chart where a blocked double becomes a stand instead of a "
                "hit.",
            ],
            "picture": "Double if you can, stand if you can't. Soft 18 against the small cards "
                       "is the only row that works that way.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "double down", "stand"],
        },
        5: {
            "hook": "Soft 18 against a 5. Double.",
            "paragraphs": [
                "A 5 busts 42% of the time. Eighteen is already a decent hand; the double is "
                "about the second bet, not about the eighteen.",
                "And the card is free \u2014 no soft hand can bust on one card.",
            ],
            "picture": "Two bets on a hand that cannot be broken, against a dealer who very "
                       "well might be.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "double down", "bust"],
        },
        6: {
            "hook": "Soft 18 against a 6. Double.",
            "paragraphs": [
                "Their worst card, 42% bust, against your best soft hand short of nineteen. "
                "The right edge of the doubling window, as always.",
                "If doubling isn't available, stand on the eighteen rather than hitting it.",
            ],
            "picture": "Every soft rung ends at the 6. This is the last cell of the last rung.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "double down", "bust"],
        },
        7: {
            "hook": "Soft 18 against a 7. Stand.",
            "paragraphs": [
                "A 7's most likely finish is exactly seventeen, 37% of the time. Eighteen beats "
                "it by one, which is the entire reason this cell stands.",
                "Doubling is out \u2014 a 7 isn't weak. Hitting is out too: you'd be risking a made "
                "winner for a hand that's already ahead.",
            ],
            "picture": "The 7 is the card that turns soft 18 from a double into a keeper.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        8: {
            "hook": "Soft 18 against an 8. Stand.",
            "paragraphs": [
                "An 8 finishes on exactly eighteen 36% of the time, so this cell produces a lot "
                "of pushes \u2014 and a push is your whole bet coming back.",
                "Hitting would put that at risk to chase nineteen. Not worth it. Stand.",
            ],
            "picture": "Matching their likeliest total is not a win, but it is free, and "
                       "giving it up costs real money.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "stand", "push"],
        },
        9: {
            "hook": "Soft 18 against a 9. Hit.",
            "paragraphs": [
                "This is the cell people refuse to play. A 9 finishes on nineteen 35% of the "
                "time and busts only 23% of the time, so standing on eighteen loses far more "
                "often than it wins.",
                "And hitting is free. The ace drops to 1 if a big card comes, so you cannot "
                "bust \u2014 you are getting a shot at nineteen or better with nothing at risk.",
            ],
            "picture": "Eighteen against a 9 is not a made hand. It's a hand that looks made "
                       "and loses anyway.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "hit", "bust"],
        },
        10: {
            "hook": "Soft 18 against a 10. Hit.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time. Eighteen is beaten by "
                "nineteen, twenty and twenty-one \u2014 most of what they actually make.",
                "Hitting cannot bust you. Standing on a losing total to avoid a risk that "
                "doesn't exist is the worst kind of mistake.",
            ],
            "picture": "You are not protecting anything. There is nothing here to protect.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "hit", "bust"],
        },
        11: {
            "hook": "Soft 18 against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time and lands on 17 through 20 fairly evenly. "
                "Eighteen ties one slice of that and loses to two more.",
                "Take the free card. There is no downside and a genuine chance of turning a "
                "loser into a winner.",
            ],
            "picture": "The right edge of the soft 18 row: three columns where a hand that "
                       "looks finished still has to go back to work.",
            "remember": "Soft 18: stand against 2, 7 and 8, double against 3 through 6, hit against 9, 10 and ace.",
            "terms": ["soft hand", "hit", "bust"],
        },
    },

    # --- soft 19 (A,8): always stands ------------------------------------
    19: {
        2: {
            "hook": "Soft 19 against a 2. Stand.",
            "paragraphs": [
                "Nineteen beats or ties nearly everything a 2 turns into, and they bust 35% of "
                "the time on top of that.",
                "The soft ladder stops at 18. From nineteen up, a soft hand is simply a good "
                "hand and you keep it.",
            ],
            "picture": "Two rows of soft hands do nothing but stand. This is the first of them.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        3: {
            "hook": "Soft 19 against a 3. Stand.",
            "paragraphs": [
                "A 3 busts 37% of the time and needs twenty or twenty-one to beat you.",
                "There is nothing to gain from another card and a made nineteen to lose.",
            ],
            "picture": "Nineteen is where soft hands stop being projects and start being "
                       "results.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        4: {
            "hook": "Soft 19 against a 4. Stand.",
            "paragraphs": [
                "The dealer busts 39% of the time from a 4, and nineteen beats every finish "
                "below twenty.",
                "Keep it.",
            ],
            "picture": "A strong hand against a weak card. No decision to make.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        5: {
            "hook": "Soft 19 against a 5. Stand.",
            "paragraphs": [
                "A 5 busts 42% of the time and rarely reaches twenty when it doesn't. Nineteen "
                "is a big favourite here.",
                "Stand and take the money.",
            ],
            "picture": "You have already got what the soft doubles were trying to buy.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        6: {
            "hook": "Soft 19 against a 6. Stand.",
            "paragraphs": [
                "A 6 is the dealer's worst card, busting 42% of the time, and this is the one "
                "cell in the row that gets argued about. At this table it stands.",
                H17,
            ],
            "picture": "The only soft 19 cell with any debate in it \u2014 and the debate belongs "
                       "to a different table, not this one.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "s17"],
        },
        7: {
            "hook": "Soft 19 against a 7. Stand.",
            "paragraphs": [
                "Seventeen is their likeliest finish, 37% of the time, and nineteen is two "
                "clear of it.",
                "Nothing to think about.",
            ],
            "picture": "Comfortably ahead of their best guess.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        8: {
            "hook": "Soft 19 against an 8. Stand.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Nineteen beats it.",
                "Stand.",
            ],
            "picture": "One above their most likely total, which keeps turning out to be "
                       "enough.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        9: {
            "hook": "Soft 19 against a 9. Stand.",
            "paragraphs": [
                "A 9 lands on exactly nineteen 35% of the time, so expect a lot of pushes here.",
                "Hitting would trade those pushes for a hand that has to improve to stay level. "
                "Stand.",
            ],
            "picture": "A tie is the whole bet coming back. That is worth more than a free "
                       "card here.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "push"],
        },
        10: {
            "hook": "Soft 19 against a 10. Stand.",
            "paragraphs": [
                "Twenty is their likeliest finish, 37% of the time, so nineteen is only "
                "narrowly ahead overall. Narrowly ahead is still ahead.",
                "Hitting a soft 19 is free but it is not profitable: you lose more nineteens "
                "than you gain twenties.",
            ],
            "picture": "Free is not the same as worth doing. At nineteen the free card starts "
                       "costing you.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "upcard"],
        },
        11: {
            "hook": "Soft 19 against an ace. Stand.",
            "paragraphs": [
                "An ace busts 17% of the time and spreads evenly across 17 to 20. Nineteen "
                "beats most of that and ties a chunk of it.",
                "Stand. And decline the insurance while you're at it.",
            ],
            "picture": "Even against the best upcard in the game, nineteen is doing fine.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "insurance"],
        },
    },

    # --- soft 20 (A,9): always stands ------------------------------------
    20: {
        u: {
            "hook": "Soft 20. Stand.",
            "paragraphs": [
                "A,9 is a twenty, and twenty loses only to twenty-one. It is the second-best "
                "hand in blackjack and there is no upcard that changes what to do with it.",
                "Drawing can't bust you, which is exactly the trap: a free card that turns "
                "twenty into something worse is still a bad card. Stand.",
            ],
            "picture": "The ace has already done its job. Let it finish.",
            "remember": "Soft 19 and soft 20 always stand.",
            "terms": ["soft hand", "stand", "blackjack"],
        } for u in range(2, 12)
    },

    # --- soft 21: nothing to decide --------------------------------------
    21: {
        u: {
            "hook": "Twenty-one. Stand.",
            "paragraphs": [
                "The best total in the game. Nothing beats it and only another twenty-one "
                "ties it.",
                "There is no decision here.",
            ],
            "picture": "Done. Wait for the money.",
            "remember": "Soft 19 and soft 20 always stand. Twenty-one goes without saying.",
            "terms": ["soft hand", "stand", "blackjack"],
        } for u in range(2, 12)
    },
}


# ---------------------------------------------------------------------------
# Pairs. Keyed by the value of the paired card, then by dealer upcard.
# 11 is a pair of aces, 10 is any two ten-valued cards.
#
# This table allows doubling after a split, which is what lets 2s and 3s split
# against a 2 and a 3, and lets 4s split at all. Without it those cells would
# just hit.
#
# The two lines that cover most of it:
#     always split aces and eights
#     never split tens and fives
# Everything in between splits against the dealer's small cards.
# ---------------------------------------------------------------------------

PAIRS = {

    # --- A,A: always split ----------------------------------------------
    11: {
        u: {
            "hook": "Two aces is the worst possible use of the best card in the deck.",
            "paragraphs": [
                "Kept together they make a soft 12. You can't bust, but you can't win either "
                "without drawing again \u2014 and the second ace is contributing exactly one point. "
                "Separate them and each hand starts on eleven, which is the best position you "
                "can be dealt.",
                "You only get one card on each after splitting, so neither hand can be built "
                "up. That's fine: about 31% of the shoe is worth ten, so each of them has "
                "close to a one-in-three shot at twenty-one.",
            ],
            "picture": "One ace is doing all the work and the second is sitting on top of it "
                       "doing nothing. Splitting gives the second one its own hand to be good in.",
            "remember": "Always split aces and eights. One frees a great card, one escapes a terrible hand.",
            "terms": ["split", "soft hand", "blackjack"],
        } for u in range(2, 12)
    },

    # --- 2,2: split against 2 through 7 ----------------------------------
    2: {
        2: {
            "hook": "A pair of 2s against a 2. Split.",
            "paragraphs": [
                "Together they are a 4 \u2014 a total with nowhere to go. Apart, each hand starts "
                "on 2 against a dealer who busts 35% of the time and can build from there.",
                "This cell only works because you're allowed to double after splitting. Without "
                "that rule it would be a plain hit.",
            ],
            "picture": "Four is not a hand. Two hands starting at 2 at least have somewhere to "
                       "go.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "double after split", "upcard"],
        },
        3: {
            "hook": "A pair of 2s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time. Two hands, each able to draw and double, are worth "
                "more against that than one hand stuck on 4.",
                "Again this cell depends on doubling after splitting being allowed here.",
            ],
            "picture": "You're not splitting because 2s are good. You're splitting because 4 "
                       "is useless.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "double after split", "upcard"],
        },
        4: {
            "hook": "A pair of 2s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. Every extra hand you get in front of a weak dealer "
                "is another bet collecting on those busts.",
                "Splitting and doubling are the only two ways you ever increase a wager after "
                "seeing cards. This is one of them.",
            ],
            "picture": "A weak dealer is a sale. Splitting is buying two of the item instead "
                       "of one.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        5: {
            "hook": "A pair of 2s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. Two live hands against that are clearly worth more "
                "than one hand starting at 4.",
                "Both new hands inherit the same weak dealer, and both can be doubled if they "
                "improve.",
            ],
            "picture": "Two tickets in the same favourable draw.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        6: {
            "hook": "A pair of 2s against a 6. Split.",
            "paragraphs": [
                "The dealer's worst card, busting 42% of the time. This is the strongest cell "
                "in the row.",
                "Get a second bet in front of a dealer who breaks nearly half the time.",
            ],
            "picture": "When the dealer is this weak, the number of hands you have out matters "
                       "more than how good any of them is.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 2s against a 7. Split \u2014 the last cell in the row.",
            "paragraphs": [
                "A 7 isn't weak: it busts 26% of the time and finishes on seventeen 37% of the "
                "time. But a hand starting on 2 can reach eighteen or better, and a hand stuck "
                "on 4 has to climb the whole way from there.",
                "This is the right edge of the row. One more column and it becomes a hit.",
            ],
            "picture": "Against a 7 you need a real total. Two chances at one beats a single "
                       "bad start.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard"],
        },
        8: {
            "hook": "A pair of 2s against an 8. Hit.",
            "paragraphs": [
                "The row closes at the 7. An 8 finishes on eighteen 36% of the time and busts "
                "only 24% of the time \u2014 too strong to be putting a second bet in front of.",
                "Play it as a 4 and hit. Nothing in the shoe can bust you from there.",
            ],
            "picture": "Splitting into a strong upcard just doubles your exposure to a dealer "
                       "who is probably going to make a hand.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        9: {
            "hook": "A pair of 2s against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time. Two weak hands against that is two "
                "ways to lose.",
                "Keep it as one 4 and build. You cannot bust from a total this low.",
            ],
            "picture": "One bad hand is cheaper than two bad hands.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        10: {
            "hook": "A pair of 2s against a 10. Hit.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time. Splitting here puts a "
                "second bet up against the strongest common upcard in the game.",
                "Hit the 4 instead and keep your losses to one bet.",
            ],
            "picture": "Extra money belongs in front of weak dealers, not strong ones.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        11: {
            "hook": "A pair of 2s against an ace. Hit.",
            "paragraphs": [
                "An ace busts just 17% of the time, the least of any upcard. There is no "
                "weakness here to split into.",
                "Play the 4 as one hand and draw.",
            ],
            "picture": "Splitting is an aggressive move. An ace is the worst possible time for "
                       "one.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
    },

    # --- 3,3: split against 2 through 7 ----------------------------------
    3: {
        2: {
            "hook": "A pair of 3s against a 2. Split.",
            "paragraphs": [
                "Together they make 6, which is one of the worst starting totals there is: too "
                "low to stand on, and it draws into the stiff range far too often.",
                "Apart, each hand starts on 3 against a dealer who busts 35% of the time. This "
                "cell needs doubling after splitting to be allowed, and here it is.",
            ],
            "picture": "Six is the total most likely to turn into a 16. Breaking it up is "
                       "escaping that in advance.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "double after split", "stiff hand"],
        },
        3: {
            "hook": "A pair of 3s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time. Two hands each starting on 3 are worth more than "
                "one hand starting on 6.",
                "Another cell that exists only because you can double after splitting here.",
            ],
            "picture": "Same card on both sides of the table, and the split is still the "
                       "aggressive, correct move.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "double after split", "upcard"],
        },
        4: {
            "hook": "A pair of 3s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. Getting two bets in front of that is worth more "
                "than the quality of either hand.",
                "Both halves can be doubled if they improve, which is where a lot of the value "
                "comes from.",
            ],
            "picture": "Weak dealer, cheap hands, two bets. That is the whole splitting logic "
                       "in one line.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        5: {
            "hook": "A pair of 3s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. Six is a total you'd rather not have; two 3s is "
                "two fresh starts against a dealer in real trouble.",
                "Split.",
            ],
            "picture": "Trade one hopeless hand for two ordinary ones. Ordinary twice is worth "
                       "more.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        6: {
            "hook": "A pair of 3s against a 6. Split.",
            "paragraphs": [
                "The dealer's worst card at 42% bust. This is the best cell in the row.",
                "Two hands, two bets, one very weak dealer.",
            ],
            "picture": "You want as much money as possible in front of a 6. Splitting is how "
                       "you get it there.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 3s against a 7. Split \u2014 and this one matters.",
            "paragraphs": [
                "A 7 finishes on seventeen 37% of the time. A hand starting on 3 can get past "
                "seventeen comfortably; a hand starting on 6 has to get past it from further "
                "back, and lands in the stiff range on the way far too often.",
                "Right edge of the row. From an 8 onwards this becomes a hit.",
            ],
            "picture": "Against a 7 you need eighteen. Two hands that can reach it beat one "
                       "that struggles to.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "upcard", "stiff hand"],
        },
        8: {
            "hook": "A pair of 3s against an 8. Hit.",
            "paragraphs": [
                "An 8 lands on eighteen 36% of the time and busts only 24% of the time. Too "
                "strong to be doubling your exposure to.",
                "Play the 6 as one hand and draw. Nothing can bust you from there.",
            ],
            "picture": "The row ends where the dealer stops being beatable on the cheap.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        9: {
            "hook": "A pair of 3s against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time. Two hands starting on 3 against "
                "that is two hands likely to lose.",
                "One bet, one hand, keep drawing.",
            ],
            "picture": "Splitting into a strong card is paying extra to lose twice.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        10: {
            "hook": "A pair of 3s against a 10. Hit.",
            "paragraphs": [
                "Twenty, 37% of the time, is what you're up against. Neither a 6 nor two 3s is "
                "good news, but only one of them costs a single bet.",
                "Hit and hope.",
            ],
            "picture": "When you're behind, the cheapest way to be behind is with one bet out.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
        11: {
            "hook": "A pair of 3s against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time. There is no weak dealer to exploit and no "
                "reason to put out a second bet.",
                "Hit the 6.",
            ],
            "picture": "Aggression needs a target. An ace isn't one.",
            "remember": "Split 2s and 3s against 2 through 7. Otherwise just hit.",
            "terms": ["split", "hit", "upcard"],
        },
    },

    # --- 4,4: split against 5 and 6 only ---------------------------------
    4: {
        2: {
            "hook": "A pair of 4s against a 2. Hit.",
            "paragraphs": [
                "Eight is a perfectly serviceable total: nothing in the shoe can bust it, and "
                "it draws into good hands often. Two hands starting on 4 are worse than that.",
                "This is the narrowest split row on the chart \u2014 5 and 6 only.",
            ],
            "picture": "Unlike 2s and 3s, a pair of 4s is already a decent hand. Breaking it "
                       "up usually makes things worse.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "bust"],
        },
        3: {
            "hook": "A pair of 4s against a 3. Hit.",
            "paragraphs": [
                "A 3 busts 37% of the time, which isn't quite weak enough to justify breaking "
                "up a hand that can't bust.",
                "Hit the 8 and build normally.",
            ],
            "picture": "The 4s row waits for the two weakest cards on the board and nothing "
                       "else.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
        4: {
            "hook": "A pair of 4s against a 4. Hit.",
            "paragraphs": [
                "A 4 busts 39% of the time. Still not enough \u2014 eight is a better starting "
                "point than 4, and splitting costs a second bet to get two worse hands.",
                "One more column and the answer changes.",
            ],
            "picture": "Close, but the row opens at the 5.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
        5: {
            "hook": "A pair of 4s against a 5. Split \u2014 the row opens here.",
            "paragraphs": [
                "A 5 busts 42% of the time. That's finally weak enough that having two bets "
                "out beats holding one better hand.",
                "This cell only exists because you can double after splitting at this table. "
                "Without that rule, 4s never split at all.",
            ],
            "picture": "Two hands that can each be doubled, in front of a dealer who breaks "
                       "more than four times in ten.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "double after split", "bust"],
        },
        6: {
            "hook": "A pair of 4s against a 6. Split.",
            "paragraphs": [
                "The dealer's worst card, busting 42% of the time. The second of the two cells "
                "where breaking up an 8 is worth it.",
                "Again, this depends on being able to double the split hands, which you can here.",
            ],
            "picture": "The whole 4s row is two cells wide. Learn where it is and the rest is "
                       "automatic.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "double after split", "bust"],
        },
        7: {
            "hook": "A pair of 4s against a 7. Hit.",
            "paragraphs": [
                "The row closes immediately. A 7 busts only 26% of the time and finishes on "
                "seventeen 37% of the time.",
                "Eight is the better hand here and it costs one bet instead of two.",
            ],
            "picture": "Two cells open, two cells shut. The 4s row is the narrowest on the "
                       "chart.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
        8: {
            "hook": "A pair of 4s against an 8. Hit.",
            "paragraphs": [
                "An 8 lands on eighteen 36% of the time. You need a real hand, and an 8 that "
                "can't bust is a better start towards one than a 4.",
                "Hit.",
            ],
            "picture": "Keep the total you have. It's the better one.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
        9: {
            "hook": "A pair of 4s against a 9. Hit.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time. Splitting would put two weak hands "
                "in front of a strong dealer.",
                "Hit the 8 and build one good total instead.",
            ],
            "picture": "Against big cards you want one strong hand, not two ordinary ones.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
        10: {
            "hook": "A pair of 4s against a 10. Hit.",
            "paragraphs": [
                "Twenty is their likeliest finish, 37% of the time. There is no case at all "
                "for a second bet here.",
                "Hit the 8.",
            ],
            "picture": "Eight cannot bust. That is the most useful thing about this hand and "
                       "splitting throws it away.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "bust"],
        },
        11: {
            "hook": "A pair of 4s against an ace. Hit.",
            "paragraphs": [
                "An ace busts 17% of the time, less than anything else. No weakness, no split.",
                "Play the 8 and draw.",
            ],
            "picture": "Splitting is for weak dealers. This is the opposite end of the table.",
            "remember": "Split 4s against 5 and 6 only. Everywhere else, hit the 8.",
            "terms": ["split", "hit", "upcard"],
        },
    },

    # --- 5,5: never split. It's a hard 10. -------------------------------
    5: {
        2: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "Never split 5s. Ten is one of the best starting totals in the game and two "
                "hands starting on 5 are two of the worst \u2014 you'd be trading your strongest "
                "asset for two hands that can't bust but can't do much else either.",
                "Play it as a hard 10 and double against a 2, exactly as the 10 row says.",
            ],
            "picture": "Two 5s look like a pair and behave like a ten. Read it as a ten and "
                       "the answer is obvious.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "hard hand"],
        },
        3: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "Splitting 5s is one of the most expensive mistakes available, because it "
                "destroys a doubling hand to create two weak ones.",
                "A 3 busts 37% of the time and one card makes 20 about 31% of the time. Double.",
            ],
            "picture": "The 5,5 row is the 10 row wearing a disguise.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "hard hand"],
        },
        4: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "A 4 busts 39% of the time and you are holding the second-best two-card total "
                "in blackjack.",
                "Double. Splitting here would be throwing that away for no reason at all.",
            ],
            "picture": "Strong hand, weak dealer. Nothing about the cards being a pair changes "
                       "that.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "bust"],
        },
        5: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "A 5 busts 42% of the time. One card makes you 20 about 31% of the time.",
                "This is a premium doubling cell, and splitting would turn it into two "
                "mediocre hands.",
            ],
            "picture": "Every 5 at the table is working against the dealer. Yours should be "
                       "working together.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "bust"],
        },
        6: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "Their worst card at 42% bust, your second-best total. Double without "
                "hesitating.",
                "Splitting fives against a 6 is the classic beginner's error: it feels "
                "aggressive and it is actually the weakest thing you can do with the hand.",
            ],
            "picture": "The dealer is in maximum trouble. Meet it with a ten, not with two 5s.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "bust"],
        },
        7: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "A 7's likeliest finish is seventeen, 37% of the time, and a ten beats that "
                "with most single cards.",
                "Double, as the hard 10 row says. Don't split.",
            ],
            "picture": "Ten doubles all the way out to a 9. The pair of 5s comes along for "
                       "the ride.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "upcard"],
        },
        8: {
            "hook": "A pair of 5s is a ten. Double it.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. A ten turns into 18, 19 or 20 far "
                "more often than not.",
                "Double.",
            ],
            "picture": "Read the total, not the shape of the cards.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "upcard"],
        },
        9: {
            "hook": "A pair of 5s is a ten. Double it \u2014 the last doubling cell.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time, so you need a big card. You get one "
                "about 31% of the time, which is still enough.",
                "This is the right edge of the 10 row. One more column and it's a hit.",
            ],
            "picture": "Nine is in, ten is out. The same boundary as the hard 10 row, because "
                       "it is the hard 10 row.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "double down", "upcard"],
        },
        10: {
            "hook": "A pair of 5s against a 10. Hit \u2014 don't double, don't split.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time. Doubling into one card "
                "would leave you on 20 about 31% of the time, and 20 against 20 is only a push.",
                "So hit the ten and keep the right to draw again. Splitting remains wrong here "
                "for the same reason it's wrong everywhere.",
            ],
            "picture": "Two things not to do and one to do. Hit.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "hit", "push"],
        },
        11: {
            "hook": "A pair of 5s against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time. There's no weakness to double into and "
                "certainly none to split into.",
                "Play the ten and draw.",
            ],
            "picture": "The 5,5 hand never splits. Against an ace it doesn't double either.",
            "remember": "Never split fives. Play them as a hard 10 and double against 2 through 9.",
            "terms": ["split", "hit", "upcard"],
        },
    },

    # --- 6,6: split against 2 through 6 ----------------------------------
    6: {
        2: {
            "hook": "A pair of 6s against a 2. Split.",
            "paragraphs": [
                "Together they make 12 \u2014 a stiff hand with no good move in it. Apart, each "
                "hand starts on 6, which is at least something you can build from.",
                "A 2 busts 35% of the time. This cell needs doubling after splitting to be "
                "allowed, and it is.",
            ],
            "picture": "Twelve is a hand you escape from. Splitting is the emergency exit.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "stiff hand", "double after split"],
        },
        3: {
            "hook": "A pair of 6s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time. Two hands starting on 6 against a weak dealer beat "
                "one hand stuck on 12.",
                "You're not splitting to make good hands. You're splitting to stop having a "
                "stiff one.",
            ],
            "picture": "Cutting a bad hand in half doesn't make it good. It makes it two "
                       "ordinary problems instead of one serious one.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        4: {
            "hook": "A pair of 6s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. Two bets in front of that are worth more than one "
                "bet on a 12.",
                "Both halves can be doubled if they land well.",
            ],
            "picture": "Weak dealer plus a hand you didn't want anyway. An easy split.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "upcard", "bust"],
        },
        5: {
            "hook": "A pair of 6s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. Getting more money out against that is the whole "
                "point.",
                "Twelve, meanwhile, is a total you would be hitting or standing on unhappily "
                "either way.",
            ],
            "picture": "Two live hands beat one dead one, and 12 against a weak card is close "
                       "to dead.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "stiff hand", "bust"],
        },
        6: {
            "hook": "A pair of 6s against a 6. Split.",
            "paragraphs": [
                "The dealer's worst card, busting 42% of the time. The best cell in the row "
                "and the right edge of it.",
                "Two bets in front of a dealer who breaks nearly half the time.",
            ],
            "picture": "Sixes on both sides. Yours split, theirs breaks.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 6s against a 7. Hit.",
            "paragraphs": [
                "The row closes at the 6. A 7 busts only 26% of the time and lands on seventeen "
                "37% of the time \u2014 splitting would just get two weak hands beaten instead of one.",
                "Play the 12 and hit it. You bust only 31% of the time from there, the lowest "
                "of any stiff total.",
            ],
            "picture": "Sixes split against small cards only. Against a 7 the 12 goes back to "
                       "being an ordinary stiff hand.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "hit", "stiff hand"],
        },
        8: {
            "hook": "A pair of 6s against an 8. Hit.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Two hands starting on 6 are two "
                "underdogs.",
                "Hit the 12 instead \u2014 one bet, and the cheapest draw in the stiff block.",
            ],
            "picture": "Splitting into a strong card multiplies a bad position rather than "
                       "fixing it.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "hit", "stiff hand"],
        },
        9: {
            "hook": "A pair of 6s against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time. There's no weakness here worth a "
                "second bet.",
                "Hit the 12.",
            ],
            "picture": "One bad hand, one bet. That's the best available outcome here.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "hit", "stiff hand"],
        },
        10: {
            "hook": "A pair of 6s against a 10. Hit.",
            "paragraphs": [
                "Twenty is their most likely finish, 37% of the time. Splitting doubles your "
                "money into a hand you are probably losing.",
                "Hit the 12 and take the 31% bust risk, which is the lowest in the stiff range.",
            ],
            "picture": "When you're beaten, be beaten for one bet.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "hit", "stiff hand"],
        },
        11: {
            "hook": "A pair of 6s against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time. Nothing here justifies a second bet.",
                "Play the 12 as one hand and draw.",
            ],
            "picture": "Against an ace, the goal is to lose as little as possible. Splitting "
                       "does the opposite.",
            "remember": "Split 6s against 2 through 6. Otherwise hit the 12.",
            "terms": ["split", "hit", "upcard"],
        },
    },
}


PAIRS.update({

    # --- 7,7: split against 2 through 7 ----------------------------------
    7: {
        2: {
            "hook": "A pair of 7s against a 2. Split.",
            "paragraphs": [
                "Together they make 14 \u2014 a stiff hand that loses most of the time whatever you "
                "do with it. Apart, each hand starts on 7, which is a normal, buildable total.",
                "A 2 busts 35% of the time, and both of your new hands get to play against "
                "that weakness.",
            ],
            "picture": "Fourteen is a hand with no good answer. Two 7s at least ask a question "
                       "worth answering.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        3: {
            "hook": "A pair of 7s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time. Escaping a 14 and getting a second bet down "
                "against a weak dealer is worth more than the extra money at risk.",
                "Each new hand can also be doubled if it improves.",
            ],
            "picture": "You're paying one extra bet to stop holding the worst kind of total.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "stiff hand", "double after split"],
        },
        4: {
            "hook": "A pair of 7s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. Two hands collecting on that beat one stiff 14 "
                "that has to stand and hope.",
                "Split.",
            ],
            "picture": "Against the small cards, the more hands you have alive the better.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "upcard", "bust"],
        },
        5: {
            "hook": "A pair of 7s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. This is exactly the dealer weakness that makes an "
                "extra bet worth putting out.",
                "And you get rid of a 14 in the process, which is worth something on its own.",
            ],
            "picture": "Two ordinary hands in front of a bad dealer beat one bad hand in front "
                       "of the same dealer.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "stiff hand", "bust"],
        },
        6: {
            "hook": "A pair of 7s against a 6. Split.",
            "paragraphs": [
                "The dealer's worst card, busting 42% of the time. Get as much money as you "
                "reasonably can in front of it.",
                "Fourteen would only be standing and waiting. Two 7s can actually make hands.",
            ],
            "picture": "Their 6 does the damage. Your job is just to have bets on the table "
                       "when it happens.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 7s against a 7. Split \u2014 the last cell in the row.",
            "paragraphs": [
                "This one looks odd and isn't. A 7 finishes on seventeen 37% of the time, and "
                "a hand starting on 7 beats seventeen far more often than a stiff 14 does.",
                "There's a second quiet advantage: three of the sevens are already on the "
                "table, which makes the dealer's seventeen slightly less likely than usual.",
            ],
            "picture": "You're not splitting to win big. You're splitting because 14 against a "
                       "7 is one of the worst places to be sitting.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        8: {
            "hook": "A pair of 7s against an 8. Hit.",
            "paragraphs": [
                "The row closes at the 7. An 8 finishes on eighteen 36% of the time and busts "
                "only 24% of the time \u2014 too strong to put a second bet against.",
                "Play the 14 and hit it. You bust 46% of the time doing that, which is still "
                "better than standing.",
            ],
            "picture": "Past the 7, a pair of 7s goes back to being an ordinary stiff hand.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "hit", "stiff hand"],
        },
        9: {
            "hook": "A pair of 7s against a 9. Hit.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time. Two hands starting on 7 would both be "
                "underdogs, for twice the money.",
                "Hit the 14 instead.",
            ],
            "picture": "Splitting is for weak dealers. A 9 is not one.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "hit", "stiff hand"],
        },
        10: {
            "hook": "A pair of 7s against a 10. Hit.",
            "paragraphs": [
                "Twenty is their likeliest finish, 37% of the time. You are behind however you "
                "play it, so play it for one bet.",
                "Hit the 14. It busts 46% of the time and still beats standing.",
            ],
            "picture": "Losing one bet is a much better outcome than losing two.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "hit", "stiff hand"],
        },
        11: {
            "hook": "A pair of 7s against an ace. Hit.",
            "paragraphs": [
                "An ace busts only 17% of the time. There is no weakness to attack and no "
                "reason to put a second bet out.",
                "Hit the 14 and take your chances.",
            ],
            "picture": "The strongest upcard in the game is the worst possible time to split.",
            "remember": "Split 7s against 2 through 7. Otherwise hit the 14.",
            "terms": ["split", "hit", "upcard"],
        },
    },

    # --- 8,8: always split -----------------------------------------------
    8: {
        2: {
            "hook": "You're not splitting eights to win. You're splitting to lose less.",
            "paragraphs": [
                "Sixteen is the worst hand in the game. Too weak to keep, too close to the "
                "edge to draw to. A 2 busts 35% of the time, so a stiff 16 is a modest loser "
                "here at best.",
                "Two hands starting on 8 are each pretty ordinary. But ordinary twice beats "
                "terrible once, even after you've put a second bet down.",
            ],
            "picture": "It's the same instinct as cutting a loss in half instead of hoping it "
                       "turns around. You're not buying a good outcome. You're buying a less "
                       "bad one.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "bust"],
        },
        3: {
            "hook": "A pair of 8s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time, and two hands starting on 8 collect on that far "
                "better than one 16 can.",
                "Sixteen has no good play in it. Eight has plenty.",
            ],
            "picture": "Getting rid of a 16 is worth paying for. That is the whole idea.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "bust"],
        },
        4: {
            "hook": "A pair of 8s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. This is the easy end of the 8s row: you escape the "
                "worst total in blackjack and get a second bet down against a weak dealer at "
                "the same time.",
                "Both things are worth doing, and here they happen together.",
            ],
            "picture": "Two problems solved with one move.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "bust"],
        },
        5: {
            "hook": "A pair of 8s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. Splitting here is genuinely profitable rather than "
                "merely defensive \u2014 two live hands in front of a dealer likely to break.",
                "This is the 8s row at its best.",
            ],
            "picture": "Most of the time splitting 8s is damage control. Against a 5 it's an "
                       "attack.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "upcard", "bust"],
        },
        6: {
            "hook": "A pair of 8s against a 6. Split.",
            "paragraphs": [
                "Their worst card at 42% bust, against the worst total you can hold. Splitting "
                "turns the second fact into an advantage.",
                "Two hands, two bets, a dealer breaking nearly half the time.",
            ],
            "picture": "The single most profitable split on the chart lives around here.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 8s against a 7. Split.",
            "paragraphs": [
                "This one is easy to justify: their likeliest finish is seventeen, 37% of the "
                "time, and a hand starting on 8 beats seventeen comfortably. A 16 doesn't beat "
                "anything.",
                "There is also a decent chance of drawing a ten onto one of them for an "
                "eighteen.",
            ],
            "picture": "Against a 7 you actually expect to win these hands, which is more than "
                       "you can say for a 16.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        8: {
            "hook": "A pair of 8s against an 8. Split.",
            "paragraphs": [
                "An 8 finishes on eighteen 36% of the time. Sixteen loses to that every single "
                "time; a hand starting on 8 has a real chance of getting past it.",
                "Split. The second bet is the price of having a hand worth playing.",
            ],
            "picture": "Two eights on your side, one on theirs. Yours are worth more apart.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        9: {
            "hook": "A pair of 8s against a 9. Split.",
            "paragraphs": [
                "A 9 lands on nineteen 35% of the time and busts only 23% of the time. Sixteen "
                "here is close to hopeless.",
                "Splitting doesn't make you a favourite. It makes you a smaller underdog, "
                "twice, which adds up to losing less money.",
            ],
            "picture": "The right move and the comfortable move part company around here. Take "
                       "the right one.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "upcard"],
        },
        10: {
            "hook": "A pair of 8s against a 10. Split. Especially against a 10.",
            "paragraphs": [
                "This is the cell everybody wants to skip, because putting a second bet out "
                "against a ten feels reckless. Their most likely finish is twenty, 37% of the "
                "time, and a 16 loses to it every time.",
                "Two hands starting on 8 both lose money here. They lose less money than one "
                "hand holding a 16 does. That's the whole argument, and it's enough.",
            ],
            "picture": "You are choosing between losing a lot once and losing a bit less twice. "
                       "The second one is cheaper, however it feels.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "expected value"],
        },
        11: {
            "hook": "A pair of 8s against an ace. Split.",
            "paragraphs": [
                "An ace busts just 17% of the time \u2014 the hardest upcard there is. A 16 against "
                "it is about as bad as blackjack gets.",
                "Split anyway. Two hands starting on 8 lose less than one hand starting on 16, "
                "and 'loses less' is the whole game in this corner of the chart.",
            ],
            "picture": "The rule has no exceptions for a reason. The moment you start making "
                       "them, you're back to guessing.",
            "remember": "Always split aces and eights. Every upcard, no exceptions, including a ten.",
            "terms": ["split", "stiff hand", "expected value"],
        },
    },

    # --- 9,9: split except against 7, 10 and ace -------------------------
    9: {
        2: {
            "hook": "A pair of 9s against a 2. Split.",
            "paragraphs": [
                "Eighteen is a decent hand, which is why this row surprises people. But a 2 "
                "busts 35% of the time, and two hands starting on 9 are together worth more "
                "than one eighteen against a dealer that weak.",
                "You're trading a good hand for two better ones, not for two worse ones.",
            ],
            "picture": "Nines are the one pair where you break up something that already works, "
                       "because against small cards two 9s work harder.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "upcard", "bust"],
        },
        3: {
            "hook": "A pair of 9s against a 3. Split.",
            "paragraphs": [
                "A 3 busts 37% of the time. Each new hand starts on 9 and can be doubled if it "
                "improves, which is where a lot of the extra value lives.",
                "Eighteen would win a fair share of these. Two 9s win more.",
            ],
            "picture": "Good is the enemy of better. Eighteen is good; two 9s against a 3 are "
                       "better.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "double after split", "upcard"],
        },
        4: {
            "hook": "A pair of 9s against a 4. Split.",
            "paragraphs": [
                "A 4 busts 39% of the time. Two bets in front of that are worth more than one "
                "bet on an eighteen.",
                "Split.",
            ],
            "picture": "The weaker their card, the more you want on the table. Splitting is "
                       "how you get it there.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "upcard", "bust"],
        },
        5: {
            "hook": "A pair of 9s against a 5. Split.",
            "paragraphs": [
                "A 5 busts 42% of the time. This is one of the most profitable splits on the "
                "chart \u2014 two strong starting cards against a dealer likely to break.",
                "Take it.",
            ],
            "picture": "Nine is a good card to start a hand with. Two of them against a 5 is "
                       "close to ideal.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "upcard", "bust"],
        },
        6: {
            "hook": "A pair of 9s against a 6. Split.",
            "paragraphs": [
                "Their worst card at 42% bust. Two hands, two bets, one dealer in serious "
                "trouble.",
                "Eighteen would be sitting and waiting. Two 9s are doing something.",
            ],
            "picture": "Against a 6 you want maximum money in play. This is the way to get it.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "upcard", "bust"],
        },
        7: {
            "hook": "A pair of 9s against a 7. Stand. Eighteen is already ahead.",
            "paragraphs": [
                "A 7's single most likely finish is exactly seventeen, 37% of the time \u2014 and "
                "you are holding the card above it. Eighteen beats their most probable hand "
                "outright.",
                "Splitting would give up a made winner for two hands that start behind that "
                "seventeen and have to climb past it.",
            ],
            "picture": "The first of the three exceptions. Their 7 points at seventeen, and "
                       "you're already one better.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "stand", "upcard"],
        },
        8: {
            "hook": "A pair of 9s against an 8. Split.",
            "paragraphs": [
                "The row reopens here. An 8 finishes on exactly eighteen 36% of the time, so "
                "standing on your eighteen is mostly buying pushes rather than wins.",
                "Two hands starting on 9 can get past eighteen. That's worth more than a tie.",
            ],
            "picture": "Against a 7 your eighteen wins. Against an 8 it merely ties. That is "
                       "the difference between standing and splitting.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "push", "upcard"],
        },
        9: {
            "hook": "A pair of 9s against a 9. Split.",
            "paragraphs": [
                "A 9 finishes on nineteen 35% of the time, which beats your eighteen. Standing "
                "means losing to their most likely hand.",
                "Two hands starting on 9 each have a real chance of reaching nineteen or "
                "twenty. Splitting is the only way to get there.",
            ],
            "picture": "When their likeliest total is above yours, standing is just waiting to "
                       "lose politely.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "upcard", "stand"],
        },
        10: {
            "hook": "A pair of 9s against a 10. Stand.",
            "paragraphs": [
                "Twenty is a ten's most likely finish, 37% of the time, so eighteen is behind "
                "here \u2014 this is a losing hand and it is meant to be.",
                "Splitting would put a second bet into the same losing position. Two hands "
                "starting on 9 against a ten lose more money than one eighteen does. Keep the "
                "eighteen and keep the bet small.",
            ],
            "picture": "The second exception. You're behind either way; standing is the "
                       "cheaper way to be behind.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "stand", "upcard"],
        },
        11: {
            "hook": "A pair of 9s against an ace. Stand.",
            "paragraphs": [
                "An ace busts only 17% of the time and spreads evenly across 17 through 20. "
                "Eighteen ties a slice of that and loses to more of it than it beats.",
                "Splitting into the strongest upcard in the game doubles the money on a losing "
                "proposition. Stand instead.",
            ],
            "picture": "The third and last exception. Seven, ten, ace \u2014 learn those three and "
                       "the rest of the row splits.",
            "remember": "Split nines against everything except 7, 10 and ace \u2014 the three cards where eighteen is already the right answer.",
            "terms": ["split", "stand", "upcard"],
        },
    },

    # --- 10,10: never split ----------------------------------------------
    10: {
        u: {
            "hook": "Never break a twenty.",
            "paragraphs": [
                "Twenty beats or ties almost everything the dealer can end up with. Splitting "
                "swaps one near-certain winner for two ordinary hands and a second bet at risk.",
                "This is the most expensive 'brave' play in blackjack, and it's popular "
                "precisely because it feels brave. There is no upcard that makes it right \u2014 "
                "not a 5, not a 6, not anything.",
            ],
            "picture": "You already hold the second-best hand possible. Trading it for two "
                       "average ones is selling a winning ticket to buy two scratch cards.",
            "remember": "Never split tens. Twenty stands against every card on the table.",
            "terms": ["split", "stand", "expected value"],
        } for u in range(2, 12)
    },
})



# ---------------------------------------------------------------------------
# Glossary. Every term the app uses, in plain words.
# ---------------------------------------------------------------------------

GLOSSARY = [
    # --- the table
    {"term": "upcard", "group": "At the table",
     "short": "The dealer's face-up card.",
     "long": "The dealer gets two cards, one face up and one face down. The face-up one is "
             "the only information you have about their hand, and it drives every decision "
             "you make. Small upcards (4, 5, 6) mean a dealer in trouble. Big ones (10, ace) "
             "mean a dealer likely to end up with a strong total.",
     "example": "Dealer shows a 6 \u2192 they go bust about 42% of the time. Dealer shows a 10 "
                "\u2192 only about 23%."},
    {"term": "hole card", "group": "At the table",
     "short": "The dealer's face-down card.",
     "long": "You never see it until the dealer plays their hand. Every probability in this app "
             "treats the hole card as unknown, exactly as you'd have to at a real table.",
     "example": "Insurance is a bet purely on what the hole card is."},
    {"term": "hit", "group": "At the table",
     "short": "Take another card.",
     "long": "You can keep hitting as long as you're under 21. Go over and you lose right away, "
             "before the dealer plays.",
     "example": ""},
    {"term": "stand", "group": "At the table",
     "short": "Keep what you've got and end your turn.",
     "long": "Once you stand, your total is locked in and the dealer plays.",
     "example": ""},
    {"term": "double down", "group": "At the table",
     "short": "Double your bet, take exactly one more card, then stop.",
     "long": "Only allowed on your first two cards. It's one of only two ways to increase your "
             "wager after seeing cards, which is why it matters so much \u2014 you're putting "
             "more money down at moments when you're already the favourite.",
     "example": "You have 11 against a dealer 6. Double."},
    {"term": "split", "group": "At the table",
     "short": "Turn a pair into two separate hands, with a second bet on the new one.",
     "long": "Each hand then gets played on its own. Split aces normally get only one card each. "
             "Ten and a Jack counts as a pair for splitting purposes, but you should never split it.",
     "example": "Two 8s is a 16, the worst total in the game. Split it into two hands starting on 8."},
    {"term": "insurance", "group": "At the table",
     "short": "A side bet that the dealer's hidden card is worth ten. Always decline it.",
     "long": "Offered when the dealer shows an ace. It pays 2 to 1, so it needs to win more than "
             "a third of the time to break even. Only four ranks out of thirteen are worth ten, "
             "so it wins about 31% of the time. It has nothing to do with your own cards.",
     "example": "A 7% house edge \u2014 worse than any other bet on a blackjack table."},
    {"term": "push", "group": "At the table",
     "short": "A tie. You get your bet back, nobody wins.",
     "long": "Happens on roughly 8\u20139% of hands.",
     "example": ""},
    {"term": "bust", "group": "At the table",
     "short": "Going over 21. You lose immediately.",
     "long": "The single most important asymmetry in blackjack: if you bust, you lose even if the "
             "dealer busts afterwards. That's the entire source of the house's advantage.",
     "example": ""},

    # --- kinds of hand
    {"term": "hard hand", "group": "Kinds of hand",
     "short": "A hand with no ace, or one where the ace has to count as 1.",
     "long": "Hard hands can bust on the next card. That's what makes them hard.",
     "example": "10 + 6 is a hard 16. Ace + 9 + 8 is also a hard 18, because the ace had to drop to 1."},
    {"term": "soft hand", "group": "Kinds of hand",
     "short": "A hand where an ace is counting as 11 and could safely drop to 1.",
     "long": "Soft hands cannot bust on the next card \u2014 the ace absorbs the damage. That "
             "makes drawing risk-free, which is why soft hands get played much more aggressively.",
     "example": "Ace + 6 is a soft 17. Draw a 10 and it becomes a hard 17, not a bust."},
    {"term": "stiff hand", "group": "Kinds of hand",
     "short": "A hard 12 through 16 \u2014 too weak to keep, too fat to draw to safely.",
     "long": "These are the hands where most money gets lost. There's no good option, only a "
             "less bad one, and which one that is depends entirely on the dealer's upcard.",
     "example": "Hard 16 loses about three quarters of the time however you play it."},
    {"term": "blackjack", "group": "Kinds of hand",
     "short": "An ace plus any ten-valued card, on your first two cards. Pays 3 to 2.",
     "long": "You get it about once every 21 hands. A 21 made from three cards is not a blackjack "
             "and only pays even money \u2014 and neither is a 21 made after splitting.",
     "example": "Bet $10, get a blackjack, win $15."},

    # --- the money
    {"term": "expected value", "group": "The money",
     "short": "What a bet is worth on average, if you could play it thousands of times.",
     "long": "Written per dollar wagered. Minus 0.5% means that for every dollar you put out, you "
             "lose half a cent on average. Any single hand wins or loses much more than that \u2014 "
             "expected value is the long-run average, not a prediction of what happens next.",
     "example": "Standing on 16 against a 10 has an expected value of about \u22120.54, meaning "
                "you lose about 54 cents per dollar bet on that specific situation."},
    {"term": "house edge", "group": "The money",
     "short": "The casino's built-in advantage, as a percentage of what you wager.",
     "long": "For 6-deck blackjack played perfectly, it's about 0.5%. That's one of the best in "
             "the building \u2014 roulette is 5.3%, most slots are worse. Play badly and it climbs "
             "to 2\u20133%. Play a table that pays 6 to 5 on blackjack instead of 3 to 2 and it "
             "roughly triples on its own.",
     "example": "0.5% of $100 wagered is 50 cents. But you might be up $200 or down $200 on the day."},
    {"term": "variance", "group": "The money",
     "short": "How much your results bounce around the average.",
     "long": "Blackjack has a lot of it. One hand swings about 1.14 bets either way, which is more "
             "than 200 times the size of the house edge on that hand. That's why a winning night "
             "tells you nothing about whether you played well.",
     "example": "Over 100 hands you expect to lose half a bet, but the typical swing is about 11 bets."},
    {"term": "bankroll", "group": "The money",
     "short": "The money you've set aside for playing, and are willing to lose.",
     "long": "The only number that matters for bet sizing. Bets should be a small fraction of it \u2014 "
             "roughly 1\u20132% per hand for a game that swings like this one \u2014 so that a normal "
             "run of bad luck doesn't finish you before the maths gets a chance to play out.",
     "example": "$100 bankroll at a $25 table is four bets. That's not enough to survive a normal "
                "losing streak."},
    {"term": "risk of ruin", "group": "The money",
     "short": "The chance you lose your entire bankroll.",
     "long": "If your expected value is negative \u2014 which it is, unless you're counting "
             "successfully \u2014 then given enough hands it's 100%. Not likely. Certain. The only "
             "real questions are how long it takes and whether you enjoyed the time.",
     "example": "The app shows this on the Betting tab for whatever bet size you pick."},
    {"term": "kelly", "group": "The money",
     "short": "A formula for the bet size that grows a bankroll fastest, when you actually have an edge.",
     "long": "Roughly: bet your edge divided by the variance. With no edge, the formula says bet "
             "nothing \u2014 which is mathematically correct and practically useless if you came to "
             "play. In that case the least-bad size is the table minimum, because it minimises how "
             "much of the house edge you pay per hour.",
     "example": "A 1% edge with blackjack's variance suggests betting roughly 0.8% of your bankroll."},
    {"term": "unit", "group": "The money",
     "short": "One bet, used as a measuring stick.",
     "long": "Easier to reason about than dollars, because it scales. '11 units of swing over 100 "
             "hands' is true whether you're betting $5 or $500.",
     "example": ""},

    # --- counting and the shoe
    {"term": "shoe", "group": "Counting and the shoe",
     "short": "The box holding several decks shuffled together, that cards are dealt from.",
     "long": "Six decks is standard. Because cards aren't returned until the shoe is reshuffled, "
             "what's already been dealt genuinely changes what's left \u2014 which is the only "
             "reason card counting works at all.",
     "example": ""},
    {"term": "penetration", "group": "Counting and the shoe",
     "short": "How far into the shoe they deal before reshuffling.",
     "long": "The single most important number for anyone counting. Deep penetration (say 90%) "
             "means the composition drifts far from normal and the count becomes meaningful. "
             "Shallow penetration, or a continuous shuffler, means it never does.",
     "example": "75% of a six-deck shoe means about 234 cards get dealt before the reshuffle."},
    {"term": "continuous shuffler", "group": "Counting and the shoe",
     "short": "A machine that returns played cards to the deck constantly.",
     "long": "It exists specifically to make counting impossible. With one in play the composition "
             "never drifts, the count never means anything, and no strategy beyond basic strategy "
             "has any value at all. Your correct plays don't change \u2014 but your ceiling does.",
     "example": "Set the reshuffling option in Setup to a shuffling machine, and the count stops "
                "being worth keeping at all."},
    {"term": "running count", "group": "Counting and the shoe",
     "short": "A tally of the cards dealt so far: low cards +1, middles 0, high cards \u22121.",
     "long": "The idea is that tens and aces left in the shoe are good for you \u2014 they make "
             "blackjacks and they bust the dealer. A high running count means plenty of those "
             "are still to come.",
     "example": "Cards 2\u20136 are +1. Cards 7\u20139 are 0. Tens and aces are \u22121."},
    {"term": "true count", "group": "Counting and the shoe",
     "short": "The running count divided by how many decks are left.",
     "long": "A running count of +6 means very different things with one deck left versus five. "
             "Dividing fixes that. As a rule of thumb, each point of true count above +1 is worth "
             "about half a percent of edge.",
     "example": "Running count +6 with 3 decks left is a true count of +2, or roughly a 0.5% edge."},
    {"term": "discard tray", "group": "Counting and the shoe",
     "short": "The stack of played cards, and the only clue to how deep the shoe is.",
     "long": "No table tells you how many decks are left. You look at the pile of dealt cards "
             "and judge it, then divide your running count by that guess. It is half of "
             "counting and the half nobody practises \u2014 an estimate a deck out turns a "
             "perfectly kept count into the wrong true count, silently.",
     "example": "Three decks left judged as one turns a running count of +6 into a believed "
                "true count of +6, when it is really +2."},
    {"term": "index play", "group": "Counting and the shoe",
     "short": "A square where a big enough count changes the right move.",
     "long": "Basic strategy is worked out for a fresh shoe. As the shoe drifts, a handful of "
             "squares flip, and each one has a true count at which it does \u2014 its index. "
             "Above the index you deviate; below it you play the chart. The Chart tab lists "
             "every one with the number.",
     "example": "16 against a 10 has an index of 0: stand at zero or above, hit below it."},
    {"term": "illustrious 18", "group": "Counting and the shoe",
     "short": "The eighteen index plays worth almost all of the value.",
     "long": "There are far more than eighteen squares a count can move, but the returns fall "
             "off a cliff. These eighteen carry nearly all of it, insurance most of all, and "
             "they are chosen for value per unit of memory rather than completeness.",
     "example": "The first six are worth more than the remaining twelve put together."},
    {"term": "bet spread", "group": "The money",
     "short": "The gap between your smallest bet and your largest.",
     "long": "Where a counter's money actually comes from. Playing the index plays perfectly "
             "and betting flat earns close to nothing; the edge only exists on the hands where "
             "the count is high, so you have to have more out on those. It is also the single "
             "easiest thing for a casino to notice.",
     "example": "A 1-to-8 spread means betting one unit at a dead count and eight at a good one."},
    {"term": "composition", "group": "Counting and the shoe",
     "short": "Exactly which cards are still unseen, and how many of each.",
     "long": "This app computes every probability from the actual composition rather than from a "
             "printed table, which is why the numbers shift as a shoe gets used. It's the exact "
             "version of what counting approximates.",
     "example": "The Table tab shows the live composition in step 1 of the working, once you "
                "have played the hand."},

    # --- strategy
    {"term": "basic strategy", "group": "Strategy",
     "short": "The single best move for every combination of your hand and the dealer's upcard.",
     "long": "It isn't opinion or a system \u2014 it's the result of working out the expected value "
             "of every option and taking the highest one. Following it perfectly is what gets the "
             "house edge down to about 0.5%. It cannot get you past zero.",
     "example": "The chart this app scores you against."},
    {"term": "deviation", "group": "Strategy",
     "short": "A moment when the cards left make a different play better than the chart's.",
     "long": "Basic strategy is computed for a fresh shoe. When lots of low cards have gone, the "
             "shoe is rich in tens and a handful of cells flip \u2014 most famously, standing on "
             "16 against a 10. Worth a fraction of a percent, and only if you're counting reliably. "
             "Learn the chart first.",
     "example": "This app flags a deviation whenever the live composition disagrees with the chart "
                "by a meaningful margin."},
    {"term": "s17", "group": "Strategy",
     "short": "The dealer stands on all 17s, including soft ones.",
     "long": "Better for you than H17, where the dealer hits a soft 17 \u2014 worth about 0.2%. "
             "The chart in this app is the S17 version. A few cells change under H17.",
     "example": "Look for it printed on the felt."},
    {"term": "double after split", "group": "Strategy",
     "short": "You're allowed to double a hand you created by splitting.",
     "long": "Worth about 0.14% to you. When it isn't allowed, a few marginal splits stop being "
             "worth it \u2014 4s in particular.",
     "example": "This app allows it."},
    {"term": "3 to 2", "group": "Strategy",
     "short": "What a blackjack should pay. Bet $10, win $15.",
     "long": "Some tables pay 6 to 5 instead, which sounds similar and isn't \u2014 it adds about "
             "1.4% to the house edge, roughly tripling it. No amount of correct play makes up for "
             "it. It's the first thing to check before sitting down.",
     "example": "3:2 on a $10 bet pays $15. 6:5 pays $12."},
]


def glossary_lookup():
    return {g["term"]: g for g in GLOSSARY}
