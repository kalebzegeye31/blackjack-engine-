"""
quiz.py — asking you about hands instead of waiting for them to turn up.

The table is an inefficient teacher. A pair of aces against a 5 is worth knowing
cold and you will be dealt it roughly once every two thousand hands, so the hands
that decide whether you are any good are precisely the hands you never get to
practise. This is the fix: no shoe, no money, no waiting — just the decision,
over and over, chosen from the parts of the chart you are worst at.

Questions are built from the same grid the table grades you against, so there is
no second copy of the strategy to drift out of step. Answers are graded on the
server and never travel to the browser before you have committed to one.
"""

import random

import coach
import engine as E
import rules as R
import mastery as M

MODES = ("weak", "missed", "rare", "chips", "custom")
CHIPS_QUESTIONS = 10
CHIPS_PER_CORRECT = 10.0

SUITS = [("♠", False), ("♥", True), ("♦", True), ("♣", False)]

# one full shoe per rule set, reused for every explanation
_SHOE = {}


def _full_shoe(decks, h17, up):
    key = (decks, h17, up)
    if key not in _SHOE:
        cards = [{"rank": r, "suit": s, "red": red}
                 for _ in range(decks) for s, red in SUITS for r in E.RANKS]
        _SHOE[key] = E.Odds(cards, up, hit_soft_17=h17)
    return _SHOE[key]


def _card(rank, rng):
    suit, red = rng.choice(SUITS)
    return {"rank": rank, "suit": suit, "red": red}


# ---------------------------------------------------------------------------
# Choosing what to ask
# ---------------------------------------------------------------------------

def _pool_from_filters(rules, filters):
    """Every chart cell allowed by the custom filters, as a set of coordinates."""
    filters = filters or {}
    sections = filters.get("sections") or ["hard", "soft", "pair"]
    ups = filters.get("upcards") or R.UPCARDS
    only = filters.get("only") or "all"
    ups = {11 if str(u).upper() == "A" else int(u) for u in ups}

    pool = set()
    for section, row, up, code in R.cells_for(rules):
        if section == "hard" and row >= 17:
            continue                      # nothing to decide on a made hand
        if section not in sections or up not in ups:
            continue
        if only == "splits" and code != "P":
            continue
        if only == "doubles" and code not in ("D", "Ds"):
            continue
        if only == "stand_or_hit" and code not in ("H", "S"):
            continue
        pool.add((section, row, up))
    return pool


def _rare_pool(rules, profile, cutoff=0.0015):
    """
    Hands you will almost never be dealt, which is exactly why you don't know them.

    Rarity is measured two ways and either one qualifies: cells that are rare at
    any table, and cells that are rare in *your* record because you have not put
    the hours in yet.
    """
    pool = set()
    for section, row, up, _ in R.cells_for(rules):
        if section == "hard" and row >= 17:
            continue
        name = R.cell_name(section, row, up)
        seen = profile.cells[name].n if (profile and name in profile.cells) else 0
        if R.cell_frequency(section, row, up) < cutoff or seen < 3:
            pool.add((section, row, up))
    return pool


def select_cells(mode, count, rules, profile, filters=None, rng=None, missed=None):
    """Pick the cells this quiz will ask about, hardest-first by weight."""
    rng = rng or random.Random()
    pool = None
    include_unseen = True

    if mode == "custom":
        pool = _pool_from_filters(rules, filters)
    elif mode == "rare":
        pool = _rare_pool(rules, profile)
    elif mode == "missed":
        pool = set()
        for name in (missed or []):
            parsed = R.parse_cell(name)
            if parsed and not (parsed[0] == "hard" and parsed[1] >= 17):
                pool.add(parsed)
        include_unseen = False
    elif mode in ("weak", "chips"):
        pool = None                      # the whole chart, weighted by how you play it

    if pool is not None and not pool:
        # asked for something with nothing in it -- fall back rather than fail
        pool, include_unseen = None, True

    # how far the quiz leans towards drilling your mistakes rather than covering
    # the chart. "Weak spots" drills hard; "play for chips" stays winnable.
    unseen, gain = {"weak": (0.12, 8.0), "chips": (0.5, 3.0)}.get(mode, (0.5, 4.0))
    weights = M.study_weights(profile, rules, pool, include_unseen, unseen, gain)
    if not weights:
        weights = M.study_weights(profile, rules, None, True)

    picked = M.pick(weights, count, rng)
    # a short pool can run out; go round again rather than ask fewer questions
    rounds = 0
    while len(picked) < count and weights and rounds < count:
        picked.extend(M.pick(weights, count - len(picked), rng))
        rounds += 1
    out = [(s, r, u) for s, r, u, _ in picked[:count]]
    rng.shuffle(out)          # so a short pool doesn't ask the same cell twice running
    return out


# ---------------------------------------------------------------------------
# Building one question
# ---------------------------------------------------------------------------

def build(section, row, up, rules, rng=None, index=0):
    """
    One question: real cards, a real dealer upcard, and the moves you may make.

    `answer` is kept out of everything the browser sees until it is graded.
    """
    rng = rng or random.Random()
    ranks = R.cards_for_cell(section, row)
    cards = [_card(r, rng) for r in ranks]
    up_rank = "A" if up == 11 else ("10" if up == 10 else str(up))
    up_card = _card(rng.choice(["10", "J", "Q", "K"]) if up == 10 else up_rank, rng)

    can_double = len(cards) == 2
    can_split = section == "pair"
    code = R.chart_move(rules, section, row, up)
    move, _ = R.resolve(code, can_double)
    total, soft = E.hand_value(cards)

    return {
        "index": index,
        "cell": R.cell_name(section, row, up),
        "section": section, "row": row, "up": up,
        "cards": cards, "up_card": up_card,
        "total": total, "soft": soft,
        "can_double": can_double, "can_split": can_split,
        "answer": move, "code": code,
        "rarity": R.cell_frequency(section, row, up),
    }


def public(question):
    """The question with the answer stripped out."""
    return {k: v for k, v in question.items()
            if k not in ("answer", "code")}


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def grade(question, chose, rules, decks=6):
    """
    Mark one answer, and work out what the mistake would have cost.

    The cost comes from a full fresh shoe rather than a live one, because a quiz
    question has no shoe behind it — the number is "what this mistake is worth in
    general", which is the right number for a drill.
    """
    correct = chose == question["answer"]
    up = question["up"]
    odds = _full_shoe(decks, bool(rules["hit_soft_17"]), up)
    cards = question["cards"]
    total, soft = E.hand_value(cards)

    evs = {
        "S": odds.ev_stand(total),
        "H": odds.ev_hit(total, soft),
    }
    if question["can_double"]:
        evs["D"] = odds.ev_double(total, soft)
    if question["can_split"]:
        evs["P"] = odds.ev_split(E.card_value(cards[0]["rank"]))

    best = max(evs, key=evs.get)
    mine = evs.get(chose)
    cost = max(0.0, evs[best] - mine) if mine is not None else 0.0

    analysis = {
        "kind": "play",
        "hand_kind": question["section"],
        "pair": question["row"] if question["section"] == "pair" else None,
        "total": total, "soft": soft, "up": up,
        "chart_move": question["answer"],
        "bust": odds.bust_chance(total, soft),
        "dealer_bust": odds.dealer_bust(),
    }
    try:
        explanation = coach.explain(analysis)
    except Exception:
        explanation = None

    return {
        "correct": correct,
        "chose": chose,
        "answer": question["answer"],
        "code": question["code"],
        "cell": question["cell"],
        "cost": round(cost, 4),
        "evs": {k: round(v, 4) for k, v in evs.items()},
        "best": best,
        "explanation": explanation,
    }


def legal_moves(question):
    out = ["H", "S"]
    if question["can_double"]:
        out.append("D")
    if question["can_split"]:
        out.append("P")
    return out


# ---------------------------------------------------------------------------
# Describing a quiz before it starts, so the button can say what it does
# ---------------------------------------------------------------------------

DESCRIPTIONS = {
    "weak": ("Your weak spots",
             "Drawn from wherever your record is worst, with the cells you keep "
             "missing coming up most often."),
    "missed": ("Recently missed",
               "Only the hands you have actually got wrong at the table, newest first."),
    "rare": ("Hands you never see",
             "Splits, soft doubles and the rest of the chart that turns up once an "
             "evening — the part everyone is worst at, for exactly that reason."),
    "chips": ("Play for chips",
              "Ten questions. Every one you get right is $%d in chips you can take "
              "to the table." % int(CHIPS_PER_CORRECT)),
    "custom": ("Build your own",
               "Pick the parts of the chart you want to drill."),
}


def describe(mode):
    return DESCRIPTIONS.get(mode, DESCRIPTIONS["weak"])
