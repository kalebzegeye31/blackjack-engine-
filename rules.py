"""
rules.py — the rule set, and the basic strategy chart that follows from it.

The chart used to live compressed inside engine.py, which made it impossible to
draw on screen and impossible to vary with the table rules. It lives here now as
a full grid, one row per hand you can hold, one column per dealer upcard.

Two consumers:
  * engine.chart_play()  — grades your decisions against it
  * the Chart tab        — draws it

Notation in the grid:
    H   hit
    S   stand
    D   double if you're allowed to, otherwise hit
    Ds  double if you're allowed to, otherwise stand
    P   split

Everything below is for 6 decks. The base grid is dealer-stands-on-soft-17 with
doubling allowed after a split, because that is the game most people learn on.
The other rule sets are expressed as patches to it, so the differences are
visible rather than buried in a second table.
"""

UPCARDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
UP_LABEL = {11: "A"}

DEFAULT_RULES = {
    "decks": 6,
    "hit_soft_17": False,     # dealer stands on all 17s
    "das": True,              # double after split
    "resplit_aces": False,
    "max_hands": 4,           # how many hands you may split to
    "blackjack_pays": 1.5,    # 3:2.  1.2 is the 6:5 table you should walk away from
}

def normalise(raw):
    """Fill in anything missing and coerce the types. Never trusts its input."""
    out = dict(DEFAULT_RULES)
    for key, default in DEFAULT_RULES.items():
        if raw and key in raw:
            try:
                out[key] = type(default)(raw[key])
            except (TypeError, ValueError):
                pass
    out["decks"] = max(1, min(8, int(out["decks"])))
    out["max_hands"] = max(2, min(4, int(out["max_hands"])))
    if out["blackjack_pays"] not in (1.5, 1.2):
        out["blackjack_pays"] = 1.5
    return out


def rules_key(rules):
    """Everything that can change the chart, as a hashable tuple."""
    return (bool(rules["hit_soft_17"]), bool(rules["das"]))


# ---------------------------------------------------------------------------
# The base grid: 6 decks, dealer stands on all 17s, double after split allowed.
# Columns run 2 3 4 5 6 7 8 9 10 A.
# ---------------------------------------------------------------------------

_HARD = {
    5:  "HHHHHHHHHH",
    6:  "HHHHHHHHHH",
    7:  "HHHHHHHHHH",
    8:  "HHHHHHHHHH",
    9:  "HDDDDHHHHH",
    10: "DDDDDDDDHH",
    11: "DDDDDDDDDH",
    12: "HHSSSHHHHH",
    13: "SSSSSHHHHH",
    14: "SSSSSHHHHH",
    15: "SSSSSHHHHH",
    16: "SSSSSHHHHH",
    17: "SSSSSSSSSS",
    18: "SSSSSSSSSS",
    19: "SSSSSSSSSS",
    20: "SSSSSSSSSS",
    21: "SSSSSSSSSS",
}

# keyed by the card sitting next to the ace, so 2 means A,2 — a soft 13
_SOFT = {
    2: "HHHDDHHHHH",
    3: "HHHDDHHHHH",
    4: "HHDDDHHHHH",
    5: "HHDDDHHHHH",
    6: "HDDDDHHHHH",
    7: ["S", "Ds", "Ds", "Ds", "Ds", "S", "S", "H", "H", "H"],
    8: "SSSSSSSSSS",
    9: "SSSSSSSSSS",
}

# keyed by the value of one card of the pair; 11 is a pair of aces
_PAIRS = {
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

# (section, row key, upcard) -> move.  Applied on top of the base grid.
_H17_PATCH = {
    ("hard", 11, 11): "D",    # dealer's ace is weaker when they must hit soft 17
    ("soft", 7, 2): "Ds",
    ("soft", 8, 6): "Ds",
}

_NO_DAS_PATCH = {
    ("pair", 2, 2): "H",      # splitting is worth less if you can't double the halves
    ("pair", 2, 3): "H",
    ("pair", 3, 2): "H",
    ("pair", 3, 3): "H",
    ("pair", 4, 5): "H",
    ("pair", 4, 6): "H",
    ("pair", 6, 2): "H",
}

def _row(spec):
    return list(spec) if isinstance(spec, str) else list(spec)


_CACHE = {}


def grid(rules):
    """
    The whole chart for one rule set.

    {"hard": {5: [...10 moves...], ...}, "soft": {...}, "pair": {...}}
    """
    key = rules_key(rules)
    if key in _CACHE:
        return _CACHE[key]
    out = {
        "hard": {k: _row(v) for k, v in _HARD.items()},
        "soft": {k: _row(v) for k, v in _SOFT.items()},
        "pair": {k: _row(v) for k, v in _PAIRS.items()},
    }
    patches = {}
    if rules["hit_soft_17"]:
        patches.update(_H17_PATCH)
    if not rules["das"]:
        patches.update(_NO_DAS_PATCH)
    for (section, row, up), move in patches.items():
        out[section][row][UPCARDS.index(up)] = move
    _CACHE[key] = out
    return out


def up_index(up):
    return 9 if up == 11 else up - 2


def up_label(up):
    return UP_LABEL.get(up, str(up))


def resolve(code, can_double):
    """
    Turn a chart entry into a move you can actually make.

    Returns (move, fell_back). D and Ds both mean "double if the table lets you",
    and they differ only in what you do when it doesn't.
    """
    if code == "D":
        return ("D", False) if can_double else ("H", True)
    if code == "Ds":
        return ("D", False) if can_double else ("S", True)
    return (code, False)


# ---------------------------------------------------------------------------
# Naming a cell. One string, used as the key for every statistic in the app,
# so it has to be stable and it has to round-trip back into real cards.
# ---------------------------------------------------------------------------

def cell_name(section, row, up):
    """e.g. ("hard", 16, 10) -> "hard 16 vs 10" """
    if section == "pair":
        hand = "pair of " + ("aces" if row == 11 else str(row) + "s")
    elif section == "soft":
        hand = "soft %d (A,%d)" % (row + 11, row)
    else:
        hand = "hard %d" % row
    return "%s vs %s" % (hand, up_label(up))


def parse_cell(name):
    """Inverse of cell_name. Returns (section, row, up) or None."""
    try:
        hand, up_txt = name.rsplit(" vs ", 1)
        up = 11 if up_txt.strip() == "A" else int(up_txt)
        hand = hand.strip()
        if hand.startswith("pair of "):
            rest = hand[len("pair of "):]
            row = 11 if rest.startswith("ace") else int(rest.rstrip("s"))
            return ("pair", row, up)
        if hand.startswith("soft "):
            row = int(hand.split("(A,")[1].rstrip(")"))
            return ("soft", row, up)
        if hand.startswith("hard "):
            return ("hard", int(hand.split()[1]), up)
    except (ValueError, IndexError):
        return None
    return None


def cells_for(rules, sections=("hard", "soft", "pair")):
    """Every (section, row, up, move) the chart contains, for quizzes and heatmaps."""
    g = grid(rules)
    out = []
    for section in sections:
        for row in sorted(g[section]):
            for up in UPCARDS:
                out.append((section, row, up, g[section][row][up_index(up)]))
    return out


def cards_for_cell(section, row):
    """
    Ranks that produce this row. Quiz questions need real cards, not totals.

    Hard rows avoid pairs and aces so the hand can't be read as something else:
    a hard 16 shown as 8+8 would be a split question instead, and a hard 21 needs
    three cards because two would be a blackjack.
    """
    if section == "pair":
        return ["A", "A"] if row == 11 else [str(row), str(row)]
    if section == "soft":
        return ["A", str(row)]
    if row <= 11:
        return ["2", str(row - 2)]          # 5 -> 2+3 ... 11 -> 2+9, never a pair
    if row == 20:
        return ["9", "J"]                   # not a pair of tens
    if row == 21:
        return ["10", "6", "5"]             # two cards would be a blackjack
    return ["10", str(row - 10)]            # 12..19


def chart_move(rules, section, row, up):
    return grid(rules)[section][row][up_index(up)]


# ---------------------------------------------------------------------------
# When the table's rules move a square, the explanation for it needs saying.
#
# coach.py writes one passage per square for the standard table -- six decks,
# dealer stands on all 17s, doubling allowed after a split -- and several of
# those passages state which table they are describing. Change the rule in Setup
# and the passage is still correct about the standard game and wrong about yours,
# so the caller gets a sentence to put next to it. The words live here rather
# than in coach.py because coach.py is about hands, and this is about rooms.
# ---------------------------------------------------------------------------

_WHY_MOVED = {
    "hit_soft_17": "a dealer who has to hit a soft 17 busts more often and finishes "
                   "higher when they don't, which is worth one more bet here",
    "das": "splitting is worth less when you cannot double the halves, and this pair "
           "is one of the ones that stops being worth it",
}


def moved_by_rules(rules, section, row, up):
    """
    Has this square moved away from the standard table?

    Returns (standard move, your move, which rule did it) or None. Only the two
    rules that actually shift the grid are considered, and only one of them can
    have moved any given square.
    """
    live = chart_move(rules, section, row, up)
    base = chart_move(DEFAULT_RULES, section, row, up)
    if live == base:
        return None
    culprit = "hit_soft_17" if rules["hit_soft_17"] and (
        chart_move(dict(rules, das=True), section, row, up) == live) else "das"
    return (base, live, culprit)


def rule_note(rules, section, row, up):
    """One sentence, or nothing, for a square your table plays differently."""
    moved = moved_by_rules(rules, section, row, up)
    if not moved:
        return None
    base, live, culprit = moved
    return ("The explanation below is written for the usual table. Yours is not that "
            "table: %s, so the play here is %s rather than %s \u2014 %s."
            % (("the dealer hits soft 17" if culprit == "hit_soft_17"
                else "there is no doubling after a split"),
               MOVE_WORD.get(live, live), MOVE_WORD.get(base, base),
               _WHY_MOVED[culprit]))


MOVE_WORD = {"H": "hit", "S": "stand", "D": "double", "Ds": "double", "P": "split"}


# ---------------------------------------------------------------------------
# How often each cell actually turns up at a real table. Used to weight the
# skill score (a mistake you make twice an hour matters more than one you make
# twice a year) and to drive the "rare hands" quiz.
# ---------------------------------------------------------------------------

_TEN_P = 4 / 13.0
_OTHER_P = 1 / 13.0


def _rank_p(value):
    return _TEN_P if value == 10 else _OTHER_P


def _two_card_p(section, row):
    """Chance your first two cards land on this row, ignoring the dealer."""
    if section == "pair":
        # a "pair" here means two cards of equal value, so any two tens count
        return _rank_p(10 if row == 10 else 1 if row == 11 else row) ** 2
    if section == "soft":
        return 2 * _OTHER_P * _rank_p(row)
    # hard rows: enumerate the unordered non-pair, non-soft two-card combinations
    total = 0.0
    for a in range(2, 12):
        for b in range(a, 12):
            if a == 11 or b == 11 or a == b:
                continue
            if a + b != row:
                continue
            total += 2 * _rank_p(a) * _rank_p(b)
    return total


_FREQ = {}


def cell_frequency(section, row, up):
    """Relative chance of facing this exact decision. Normalised to sum to 1."""
    if not _FREQ:
        raw = {}
        for sec in ("hard", "soft", "pair"):
            rows = _HARD if sec == "hard" else _SOFT if sec == "soft" else _PAIRS
            for r in rows:
                hand_p = _two_card_p(sec, r)
                for u in UPCARDS:
                    raw[(sec, r, u)] = hand_p * _rank_p(10 if u == 10 else u)
        scale = sum(raw.values()) or 1.0
        _FREQ.update({k: v / scale for k, v in raw.items()})
    return _FREQ.get((section, row, up), 0.0)
