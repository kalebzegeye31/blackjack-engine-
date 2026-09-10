"""
coach.py — the words, not the maths.

Two jobs:
  1. Turn a scored decision into an explanation a person can actually keep.
  2. Define every piece of jargon the app uses, in plain language.

The rule for everything in this file: if a sentence needs a term the reader
might not know, that term goes in GLOSSARY and gets underlined in the UI.
"""


def _pct(x, places=0):
    return ("%." + str(places) + "f%%") % (x * 100)


def explain(a):
    """
    Build the plain-language explanation for one scored decision.

    `a` is the analysis dict from game.Table.analyse().
    Returns hook / paragraphs / picture / remember.
    """
    if a["kind"] == "insurance":
        return {
            "hook": "It's a bet on the dealer's face-down card. Your own hand isn't invited.",
            "paragraphs": [
                "Insurance sounds like protection. It isn't. It's a completely separate bet "
                "that the dealer's hidden card is worth ten, and it gets settled before your "
                "hand is even played. You could be holding a 7 and a 4 and the maths would be "
                "exactly the same.",
                "It pays two to one, so it only makes money if the hidden card is a ten more "
                "than a third of the time. Four ranks out of thirteen are worth ten, so right "
                "now it's %s. Short, nearly always."
                % _pct(a["p_ten"], 1),
            ],
            "picture": "Someone is offering you 2-to-1 on a coin that only lands your way three "
                       "times in ten. If a friend offered you that in a pub you'd spot it instantly. "
                       "The felt just makes it feel like a service being provided.",
            "remember": "Never take insurance. Not on a twenty, and especially not on a blackjack.",
            "terms": ["insurance", "hole card", "expected value"],
        }

    kind, move, total = a["hand_kind"], a["chart_move"], a["total"]
    up = a["up"]
    up_word = "an ace" if up == 11 else "a " + str(up)
    up_short = "ace" if up == 11 else str(up)
    dealer_bust = a["dealer_bust"]
    bust = a["bust"]
    pair = a.get("pair")

    if kind == "pair" and move == "P" and pair == 11:
        return {
            "hook": "Two aces is the worst possible use of the best card in the deck.",
            "paragraphs": [
                "Kept together they make twelve. You can't go bust, but you also can't win "
                "without drawing again. Separate them and each hand starts on eleven, which is "
                "the best position you can be dealt.",
                "You're paying one extra bet to stop wasting a great card.",
            ],
            "picture": "One ace is doing all the work and the second is sitting on top of it "
                       "doing nothing. Splitting gives the second one its own hand to be good in.",
            "remember": "Always split aces and eights. One to free a great card, one to escape a terrible hand.",
            "terms": ["split", "soft hand"],
        }

    if kind == "pair" and move == "P" and pair == 8:
        return {
            "hook": "You're not splitting eights to win. You're splitting to lose less.",
            "paragraphs": [
                "Sixteen is the worst hand in the game. Too weak to keep, too close to the edge "
                "to draw to. Against %s it loses roughly three times out of four no matter what "
                "you do with it." % up_word,
                "Two hands starting on eight are each pretty ordinary. But ordinary twice beats "
                "terrible once, even after you've put a second bet down.",
            ],
            "picture": "It's the same instinct as cutting a loss in half instead of hoping it "
                       "turns around. You're not buying a good outcome. You're buying a less bad one.",
            "remember": "Split eights against everything, including a ten. Especially a ten.",
            "terms": ["split", "stiff hand"],
        }

    if kind == "pair" and move == "P":
        return {
            "hook": "Two live hands beat one dead one.",
            "paragraphs": [
                "%d on its own is a bad total. Broken into two hands starting on %d, each one is "
                "worth more than the whole was. And %s goes bust %s of the time, so both of your "
                "new hands inherit a dealer in trouble."
                % (pair * 2, pair, up_word, _pct(dealer_bust)),
                "Splitting and doubling are the only two moves that let you put more money down "
                "after you've seen cards. That's where the whole player advantage comes from.",
            ],
            "picture": "A dealer showing a small card is the shop having a sale. Splitting is how "
                       "you buy more of it.",
            "remember": "Split when the dealer is weak and your total is worse than its two halves.",
            "terms": ["split", "upcard", "bust"],
        }

    if kind == "pair" and move == "S" and pair == 10:
        return {
            "hook": "Never break a twenty.",
            "paragraphs": [
                "Twenty beats or ties almost everything the dealer can end up with. Splitting "
                "swaps one near-certain winner for two ordinary hands and a second bet at risk.",
                "This is the most expensive 'brave' play in blackjack, and it's popular precisely "
                "because it feels brave.",
            ],
            "picture": "You already hold the second-best hand possible. Trading it for two average "
                       "ones is selling a winning ticket to buy two scratch cards.",
            "remember": "Twenty stands. There is no dealer card that changes that.",
            "terms": ["split", "stand"],
        }

    if kind == "pair" and move == "S":
        return {
            "hook": "Eighteen is already ahead here.",
            "paragraphs": [
                "A dealer showing a 7 is heading for seventeen more often than anything else. "
                "Your eighteen beats that. Splitting would give up a made winner for two hands "
                "that start behind.",
                "Nines split against most cards. Not against the ones where eighteen already wins.",
            ],
            "picture": "The 7 up means the dealer's single most likely finish is exactly seventeen. "
                       "You're holding the card above it. Take the win.",
            "remember": "Split nines except against 7, 10 and ace \u2014 the three cards where it's already decided.",
            "terms": ["upcard", "split"],
        }

    if move == "D" and a["soft"]:
        return {
            "hook": "You can't go bust. So the only question left is whether they can.",
            "paragraphs": [
                "With the ace counted as eleven, no card in the deck can break this hand. The "
                "worst that happens is the ace quietly drops to one and you carry on. That takes "
                "all the risk out of drawing.",
                "So the decision stops being about your cards and becomes entirely about the "
                "dealer. %s goes bust %s of the time. Weak dealer plus no risk means get more "
                "money down." % (up_word.capitalize(), _pct(dealer_bust)),
            ],
            "picture": "A soft hand is a hand with a spare life. Spending it on a free card costs "
                       "you nothing.",
            "remember": "Soft hands double against the dealer's weak cards \u2014 4, 5 and 6 \u2014 and just take a free card everywhere else.",
            "terms": ["soft hand", "double down", "bust"],
        }

    if move == "D":
        return {
            "hook": ("Eleven is the best two cards you'll ever be dealt."
                     if total == 11 else "This is the moment to get more money down."),
            "paragraphs": [
                "Nearly a third of the deck is worth ten, so one card turns this into %s about "
                "%s of the time, and something decent most of the rest. Meanwhile %s goes bust "
                "%s of the time." % ("21" if total == 11 else "20", _pct(0.307),
                                     up_word, _pct(dealer_bust)),
                "If blackjack paid even money on every hand and nothing else, it would be a clear "
                "loser. Doubling, splitting, and the extra you get paid for a blackjack are the "
                "three things that drag the house's advantage down from roughly 5% to roughly "
                "0.5%. Skip them and you're playing the losing version.",
            ],
            "picture": "Think of your bet as going down in two parts: one blind, one informed. "
                       "Doubling is the informed part \u2014 the only bet in the building you place "
                       "while already knowing you're ahead.",
            "remember": "Ten and eleven double against anything weaker than themselves.",
            "terms": ["double down", "house edge", "bust"],
        }

    if kind == "soft" and move == "H":
        return {
            "hook": "The ace is a free pass. Use it.",
            "paragraphs": [
                "At soft %d there's no card that can break you \u2014 the ace just drops from "
                "eleven to one and the hand keeps going. A draw with no downside is never wrong."
                % total,
                "Standing would mean keeping a total that loses to nearly everything the dealer "
                "finishes on, to avoid a risk that doesn't exist.",
            ],
            "picture": "You're holding a spare life. Not spending it doesn't save it \u2014 it just "
                       "costs you the hand.",
            "remember": "Never stand on soft 17 or below. There's no such thing as a bad card here.",
            "terms": ["soft hand", "hit"],
        }

    if kind == "soft" and move == "S":
        return {
            "hook": "You already have a good hand. Stop improving it.",
            "paragraphs": [
                "Soft %d beats most of what the dealer ends up with, and drawing risks turning a "
                "made hand into an awkward one. %s isn't weak enough to justify pushing more "
                "money out." % (total, up_word.capitalize()),
                "The ace protects you from busting on this card. It only protects you once.",
            ],
            "picture": "The spare life is worth more unspent when the hand it's protecting is "
                       "already winning.",
            "remember": "Soft 19 and 20 always stand. Soft 18 stands against the small cards and against 7 or 8.",
            "terms": ["soft hand", "stand"],
        }

    if move == "S" and total >= 17:
        return {
            "hook": "Seventeen is a bad hand. Drawing to it is worse.",
            "paragraphs": [
                "This total loses more often than it wins. That's just true, and it's why the hand "
                "feels so uncomfortable. But drawing breaks you %s of the time, which turns a hand "
                "that sometimes wins into one that never does." % _pct(bust),
                "Most decisions here aren't between good and bad. They're between bad and worse, "
                "and knowing which is which is basically the whole skill.",
            ],
            "picture": "You're not choosing how to win. You're choosing which way loses least often.",
            "remember": "Hard 17 and up always stands, however bad it feels against a ten.",
            "terms": ["hard hand", "stand", "bust"],
        }

    if move == "S":
        return {
            "hook": "Don't go bust. Make them go bust.",
            "paragraphs": [
                "Drawing breaks you %s of the time, and when you break you lose immediately \u2014 "
                "the dealer doesn't even have to play their hand. Standing hands the risk back to "
                "them, and %s breaks %s of the time."
                % (_pct(bust), up_word, _pct(dealer_bust)),
                "That's the whole trade. You'll lose plenty of these either way, but standing means "
                "losing them to a dealer who had to draw out, instead of throwing them away yourself.",
            ],
            "picture": "Small cards showing \u2014 4, 5, 6 \u2014 are the dealer's trap cards. They "
                       "force a draw from a weak start. Standing is you stepping aside and letting "
                       "them walk into it.",
            "remember": "Twelve through sixteen: stand against 2\u20136, draw against 7 through ace. One line covers most of the chart.",
            "terms": ["stiff hand", "stand", "bust", "upcard"],
        }

    if move == "H" and total >= 12:
        return {
            "hook": "Both options are bad. This one is less bad.",
            "paragraphs": [
                "You break %s of the time if you draw. That's real, and it's why this one feels "
                "wrong. But %s only breaks %s of the time, so standing means winning about %s of "
                "these hands and losing all the rest."
                % (_pct(bust), up_word, _pct(dealer_bust), _pct(dealer_bust)),
                "Drawing loses more often than it feels like it should. Standing loses more often "
                "than it feels like it does. The numbers say draw.",
            ],
            "picture": "People get this one wrong because going bust feels like your own fault, "
                       "while losing to a dealer's twenty feels like bad luck. The money doesn't "
                       "care which one it felt like.",
            "remember": "Against 7 through ace, keep drawing until you reach 17. The dealer is too strong to wait out.",
            "terms": ["stiff hand", "hit", "bust"],
        }

    return {
        "hook": "There's nothing to decide here.",
        "paragraphs": [
            "At %d, no card in the deck can break you \u2014 every single one leaves you at 21 or "
            "under. Taking one is free." % total,
            "Standing on a total this low just hands the dealer the hand.",
        ],
        "picture": "Anything eleven or under isn't really a hand yet. It's a starting point.",
        "remember": "Eight or less: always draw. Nothing can hurt you.",
        "terms": ["hit", "bust"],
    }


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
     "example": "Set penetration to 'continuous shuffler' in Setup and watch the count stop moving."},
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
    {"term": "composition", "group": "Counting and the shoe",
     "short": "Exactly which cards are still unseen, and how many of each.",
     "long": "This app computes every probability from the actual composition rather than from a "
             "printed table, which is why the numbers shift as a shoe gets used. It's the exact "
             "version of what counting approximates.",
     "example": "The Table tab shows the live composition in step 1 of the explanation."},

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
