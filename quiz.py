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
    move, fell_back = R.resolve(code, can_double)
    total, soft = E.hand_value(cards)

    return {
        "index": index,
        "cell": R.cell_name(section, row, up),
        "section": section, "row": row, "up": up,
        "cards": cards, "up_card": up_card,
        "total": total, "soft": soft,
        "can_double": can_double, "can_split": can_split,
        "answer": move, "code": code, "fallback": fell_back,
        "rarity": R.cell_frequency(section, row, up),
    }


#: never sent to the browser before an answer is committed
_SECRET = ("answer", "code", "chart_answer", "index_at")


def public(question):
    """
    The question with everything that gives it away stripped out.

    More than just `answer`: an index question that shipped its index number
    would be asking you to compare two numbers it had already handed you, and
    one that shipped the chart move would give away half of it. The starting
    count of a running-count question does go out, because without it there is
    nothing to add the cards to.
    """
    return {k: v for k, v in question.items() if k not in _SECRET}


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
        "cell": question["cell"],
        "hand_kind": question["section"],
        "pair": question["row"] if question["section"] == "pair" else None,
        "total": total, "soft": soft, "up": up,
        "chart_move": question["answer"],
        "fallback": question.get("fallback", False),
        "bust": odds.bust_chance(total, soft),
        "dealer_bust": odds.dealer_bust(),
    }
    explanation = coach.explain(analysis)
    note = R.rule_note(rules, question["section"], question["row"], up)
    if note:
        explanation = dict(explanation, rule_note=note)

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


# ---------------------------------------------------------------------------
# Counting questions
#
# The chart questions above ask what to do with a hand. These ask the three
# other things a counter has to be able to do under pressure: keep the running
# count, turn it into a true count, and know which squares it moves.
#
# They share the same question/grade shape as the chart questions, with a
# `kind` to say which is which, so the quiz can mix all of them together.
# ---------------------------------------------------------------------------

import count as C

def _sgn(n, places=0):
    """Signed number with a real minus sign, matching the rest of the app."""
    fmt = "%%.%df" % places
    body = fmt % abs(n)
    if float(body) == 0:
        return body if places else "0"
    return ("+" if n > 0 else "\u2212") + body


COUNT_MODES = ("counting", "deviations", "everything")
ALL_MODES = MODES + COUNT_MODES

#: how far out a true count answer may be before it is wrong
TC_TOLERANCE = 0.5


def build_running(rules, rng, index=0, length=None):
    """
    A row of cards. What is the running count after them?

    Deliberately includes the middle cards, which are worth nothing. Learning to
    skip a 7, 8 or 9 without thinking is most of what makes a count fast enough
    to keep at a real table.
    """
    n = length or rng.choice([5, 6, 7, 8, 10, 12])
    cards = [_card(rng.choice(E.RANKS), rng) for _ in range(n)]
    start = rng.choice([0, 0, 0, 2, -2, 4, -3, 5, -6])
    running = start + sum(C.tag(E.card_value(c["rank"])) for c in cards)
    return {
        "kind": "running", "index": index,
        "cards": cards, "start": start,
        "answer": running,
        "cell": "running count",
    }


def build_true(rules, rng, index=0):
    """
    A running count and a shoe depth. What is the true count?

    The decks remaining are given here rather than eyeballed, because this
    question is about the division. Judging the tray is practised at the table,
    where there is a tray to judge.
    """
    decks = int(rules.get("decks", 6))
    running = rng.choice([-12, -8, -6, -4, -3, -2, 2, 3, 4, 6, 8, 10, 12, 15])
    left = rng.choice([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0])
    left = min(left, float(decks))
    return {
        "kind": "true", "index": index,
        "running": running, "decks_left": left,
        "answer": round(running / left, 2),
        "cell": "true count",
    }


def build_insurance(rules, rng, index=0):
    """Take it or leave it, at a true count either side of the index."""
    entry = C.BY_KEY["insurance"]
    tc = rng.choice([-2, -1, 0, 1, 2, 2.5, 3, 3.5, 4, 5, 6])
    tc = float(tc) + rng.choice([0.0, 0.0, 0.3, -0.3])
    take, _ = C.insurance_play(tc)
    return {
        "kind": "insurance", "index": index,
        "true_count": round(tc, 1),
        "answer": "take" if take else "decline",
        "index_key": "insurance", "index_at": entry["index"],
        "cell": "insurance",
    }


def build_index(rules, rng, index=0, entry=None):
    """
    A hand, an upcard, and a true count. What does a counter do?

    Half the time the count is placed on the deviating side of the index and
    half on the chart's side, so the answer cannot be guessed from the fact
    that the question was asked at all.
    """
    plays = [p for p in C.ILLUSTRIOUS_18 if p["kind"] != "insurance"]
    entry = entry or rng.choice(plays)
    section = "pair" if entry["kind"] == "pair" else "hard"
    row = entry["pair"] if entry["kind"] == "pair" else entry["total"]
    up = entry["up"]

    # land either side of the index, with a little margin so it is never a
    # question about rounding
    deviate = rng.random() < 0.5
    idx = entry["index"]
    tc = (idx + rng.choice([0.0, 0.5, 1.0, 2.0])) if deviate else (idx - rng.choice([0.5, 1.0, 2.0]))

    q = build(section, row, up, rules, rng, index)
    chart_move = q["answer"]
    move, _, _ = C.correct_move(chart_move, section, q["total"], 
                                row if section == "pair" else None, up, tc,
                                can_split=q["can_split"], can_double=q["can_double"])
    q.update({
        "kind": "index",
        "true_count": round(tc, 1),
        "answer": move,
        "chart_answer": chart_move,
        "index_key": entry["key"], "index_at": idx,
    })
    return q


def build_counting(mode, count, rules, rng):
    """A mixed set of counting questions."""
    out = []
    if mode == "counting":
        kinds = ["running", "true", "insurance"]
    elif mode == "deviations":
        kinds = ["index", "index", "index", "insurance"]
    else:
        kinds = ["index", "running", "true", "insurance"]
    for i in range(count):
        k = kinds[i % len(kinds)] if mode != "everything" else rng.choice(kinds)
        if k == "running":
            out.append(build_running(rules, rng, i))
        elif k == "true":
            out.append(build_true(rules, rng, i))
        elif k == "insurance":
            out.append(build_insurance(rules, rng, i))
        else:
            out.append(build_index(rules, rng, i))
    return out


def grade_counting(question, given, rules, decks=6):
    """Mark a counting question. Numeric ones are parsed here, not in the browser."""
    kind = question["kind"]

    if kind == "running":
        try:
            said = int(str(given).strip().lstrip("+"))
        except (TypeError, ValueError):
            said = None
        actual = question["answer"]
        ok = said == actual
        tags = ", ".join("%s %s" % (c["rank"], _sgn(C.tag(E.card_value(c["rank"]))))
                         for c in question["cards"])
        return {
            "correct": ok, "chose": given, "answer": actual, "cell": "running count",
            "cost": 0.0,
            "detail": "Started at %s. %s. That is %s."
                      % (_sgn(question["start"]), tags, _sgn(actual)),
            "explanation": {
                "hook": "Running count %s." % _sgn(actual),
                "paragraphs": [
                    "Low cards 2 through 6 are each +1, the middles 7, 8 and 9 are nothing at "
                    "all, and every ten and ace is −1. Add them as they land and never "
                    "recompute from scratch.",
                    "Skipping the middles without pausing is most of what makes a count fast "
                    "enough to keep while a dealer is moving.",
                ],
                "picture": "The count is a single number you carry, not a sum you rebuild.",
                "remember": "2-6 up one, 7-9 nothing, tens and aces down one.",
                "terms": ["running count", "true count"],
            },
        }

    if kind == "true":
        try:
            said = float(str(given).strip().lstrip("+"))
        except (TypeError, ValueError):
            said = None
        actual = question["answer"]
        ok = said is not None and abs(said - actual) <= TC_TOLERANCE
        return {
            "correct": ok, "chose": given, "answer": actual, "cell": "true count",
            "cost": 0.0,
            "detail": "%s divided by %g decks is %s."
                      % (_sgn(question["running"]), question["decks_left"], _sgn(actual, 1)),
            "explanation": {
                "hook": "True count %s." % _sgn(actual, 1),
                "paragraphs": [
                    "Running count divided by the decks still to come. A running count of %s "
                    "with %g decks left is %s, and that is the number every index and every "
                    "bet decision is expressed in."
                    % (_sgn(question["running"]), question["decks_left"], _sgn(actual, 1)),
                    "Anything within half a point is fine. At a real table you are dividing by "
                    "an estimate anyway, so false precision is wasted effort.",
                ],
                "picture": "The same running count means completely different things at the "
                           "start of a shoe and at the end of one. Dividing is what makes it "
                           "mean one thing.",
                "remember": "True count is the running count per deck remaining.",
                "terms": ["true count", "running count"],
            },
        }

    if kind == "insurance":
        said = str(given).lower()
        actual = question["answer"]
        ok = said == actual
        tc = question["true_count"]
        return {
            "correct": ok, "chose": given, "answer": actual, "cell": "insurance",
            "cost": 0.0,
            "detail": "True count %s, and the index is %s."
                      % (_sgn(tc, 1), _sgn(question["index_at"])),
            "explanation": dict(
                coach.INSURANCE,
                hook=("Insurance is on at %s." % _sgn(tc, 1)) if actual == "take"
                     else ("Insurance stays off at %s." % _sgn(tc, 1)),
                paragraphs=[
                    "Insurance is a bet that the hole card is a ten. It pays two to one, so it "
                    "needs to come in more than a third of the time to be worth anything.",
                    ("At %s the shoe is ten-rich enough that it does. This is the one bet on "
                     "the table a count turns from bad to good, and it is worth more than every "
                     "playing deviation put together." % _sgn(tc, 1)) if actual == "take" else
                    ("At %s it is not. The index is %s, and below that it is the worst bet "
                     "on the table." % (_sgn(tc, 1), _sgn(question["index_at"]))),
                ],
                terms=["insurance", "true count", "hole card"],
            ),
        }

    raise ValueError("not a counting question: %r" % kind)


def counting_legal(question):
    kind = question["kind"]
    if kind == "insurance":
        return ["take", "decline"]
    if kind in ("running", "true"):
        return []          # a typed number, not a button
    return legal_moves(question)


def describe_counting(mode):
    return {
        "counting": ("KEEPING THE COUNT",
                     "Running counts, true counts and insurance. The arithmetic, "
                     "drilled away from the table where there is time to be slow."),
        "deviations": ("THE INDEX PLAYS",
                       "The eighteen squares a count moves, asked from both sides of "
                       "the index so the answer is never the one you expected."),
        "everything": ("EVERYTHING",
                       "Chart, counting and deviations mixed together, which is the "
                       "only way they ever arrive at a table."),
    }.get(mode, ("QUIZ", ""))


def any_legal(question):
    """Buttons for any question kind. An empty list means 'type a number'."""
    if question.get("kind") in ("running", "true", "insurance"):
        return counting_legal(question)
    return legal_moves(question)
