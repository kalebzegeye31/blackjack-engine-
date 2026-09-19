"""
game.py — one blackjack table, for one session.

Holds the shoe, the seats, whose turn it is, and the money. Every decision
you make gets handed to engine.py to be scored before it's applied.

The table deals the way a real one does. That matters most when you split: the
dealer slides one card onto the first half and waits for you to finish it before
the second half is touched at all. An earlier version dealt to both halves at
once, which quietly taught the wrong thing — you were choosing for hand one
while already looking at hand two.
"""

import random

import count as C
import engine as E
import rules as R

MIN_CARDS = 15          # never deal off the bottom of the shoe


def fresh_shoe(decks):
    cards = [
        {"rank": r, "suit": s, "red": red}
        for _ in range(decks)
        for s, red in E.SUITS
        for r in E.RANKS
    ]
    random.shuffle(cards)
    return cards


def blank_session(bankroll):
    return {
        "hands": 0, "rounds": 0, "decisions": 0, "correct": 0,
        "wagered": 0.0, "net": 0.0, "ev_lost": 0.0,
        "start": float(bankroll), "peak": float(bankroll), "trough": float(bankroll),
        "wins": 0, "losses": 0, "pushes": 0, "blackjacks": 0, "busts": 0,
        "streak": 0, "best_streak": 0, "shuffles": 0,
    }


class Table:
    """
    A table you are sitting at with a fixed buy-in.

    `config` carries both the things about the room (decks, minimum, how many
    other people) and the rules of the game itself (soft 17, double after split,
    what a blackjack pays). Everything that can change the strategy chart is in
    the second group and is normalised through rules.py.
    """

    def __init__(self, config=None, bankroll=100.0):
        self.config = {
            "decks": 6,
            "others": 2,          # other people sitting at the table
            "table_min": 15,
            "table_max": 500,
            "penetration": 0.75,  # how deep before they reshuffle
            "hit_soft_17": False,
            "das": True,
            "resplit_aces": False,
            "max_hands": 4,
            "blackjack_pays": 1.5,
            # counting
            "random_checks": True,   # demand the count uninvited, now and then
            "check_rate": 0.12,      # roughly one round in eight
            "spread": 8,             # top bet in units, for grading the ramp
        }
        if config:
            self.config.update({k: v for k, v in config.items() if k in self.config})
        self.apply_rules()
        self.bankroll = float(bankroll)
        self.session = blank_session(self.bankroll)

        # --- counting ---------------------------------------------------
        # The count is hidden by default. That is the whole point: a number on
        # screen that you can glance at is not a count you can keep, and at a
        # real table nobody prints it for you.
        self.count_visible = False
        self.count_checks = []      # every time you were asked for it, and what you said
        self.pending_check = None   # an unanswered demand for the count

        self.shuffle()
        self.reset_round()

    def apply_rules(self):
        """Re-derive the strategy rule set and sanity-check the room settings."""
        self.config.update(R.normalise(self.config))
        self.config["decks"] = max(1, min(8, int(self.config["decks"])))
        self.config["others"] = max(0, min(5, int(self.config["others"])))
        self.config["table_min"] = max(1, int(self.config["table_min"]))
        self.config["table_max"] = max(self.config["table_min"],
                                       int(self.config.get("table_max", 500)))
        self.config["penetration"] = min(0.95, max(0.02, float(self.config["penetration"])))
        # counting settings, clamped the same way as everything else: nothing
        # reaching here is trusted, it all arrives over the network
        self.config["random_checks"] = bool(self.config.get("random_checks", True))
        self.config["check_rate"] = min(0.5, max(0.0, float(self.config.get("check_rate", 0.12))))
        self.config["spread"] = max(1, min(20, int(self.config.get("spread", 8))))
        self.rules = R.normalise(self.config)

    # ---------------- shoe ----------------
    def shuffle(self):
        self.shoe = fresh_shoe(self.config["decks"])
        self.dealt = 0
        self.running_count = 0

    def needs_shuffle(self):
        return self.dealt > self.config["penetration"] * self.config["decks"] * 52

    def draw(self, counted=True):
        if len(self.shoe) < MIN_CARDS:
            # a real table would have reached the cut card long before this; if we
            # get here mid-round the honest thing is to reshuffle and say so
            self.shuffle()
            self.session["shuffles"] += 1
        card = self.shoe.pop()
        self.dealt += 1
        if counted:
            self.running_count += E.hilo(E.card_value(card["rank"]))
        return card

    def decks_left(self):
        return max(0.25, (self.config["decks"] * 52 - self.dealt) / 52.0)

    # ---------------- the count, and keeping it to yourself ----------------
    def ask_for_count(self, reason="asked"):
        """Put up a demand for the running count. Returns the prompt."""
        if self.pending_check is None:
            self.pending_check = {
                "reason": reason,
                "decks_left": round(self.decks_left(), 2),
                "cards_left": len(self.shoe),
            }
        return self.pending_check

    def answer_count(self, said):
        """
        Mark an answer to a count check, then let the count be seen.

        Answering is what buys you the number: right or wrong, you get told what
        it actually is, because a check you cannot learn from is just a quiz.
        """
        actual = self.running_count
        result = C.grade_count(said, actual)
        result.update({
            "reason": (self.pending_check or {}).get("reason", "asked"),
            "true_count": round(self.true_count(), 2),
            "decks_left": round(self.decks_left(), 2),
            "at_hand": self.session.get("rounds", 0),
        })
        self.count_checks.append(result)
        self.pending_check = None
        self.count_visible = True
        return result

    def hide_count(self):
        self.count_visible = False

    def count_record(self):
        """How the count-keeping is going this session."""
        n = len(self.count_checks)
        ok = sum(1 for c in self.count_checks if c["ok"])
        drift = [abs(c["off"]) for c in self.count_checks if c.get("off") is not None]
        return {
            "asked": n,
            "right": ok,
            "accuracy": round(100.0 * ok / n) if n else None,
            "worst_drift": max(drift) if drift else 0,
            "last": self.count_checks[-1] if self.count_checks else None,
        }

    def maybe_interrupt(self):
        """
        Sometimes demand the count without being asked.

        A player who only checks when they feel confident is grading themselves
        on their best moments. The interruptions are what make the number mean
        something, so they arrive uninvited and at a bad time, like a real one.
        """
        if not self.config.get("random_checks", True):
            return None
        if self.pending_check or self.count_visible:
            return None
        if self.dealt < 26:          # nothing to count yet
            return None
        if random.random() < float(self.config.get("check_rate", 0.12)):
            return self.ask_for_count("interrupted")
        return None

    def _scrub(self, analysis):
        """
        Take the count back out of the feedback.

        One exception, and it is the important one: if you have just misplayed an
        index play, the count is exactly what you need to see. Getting it right
        tells you nothing you did not already know; getting it wrong is the
        lesson, so that is when the number comes out.
        """
        if analysis is None or self.count_visible:
            return analysis
        blew_it = (analysis.get("index") is not None
                   and analysis.get("count_correct") is False)
        if blew_it:
            return analysis
        out = dict(analysis)
        for key in ("true_count", "running_count", "count_move", "count_correct",
                    "count_ev", "index", "index_deviation", "index_cost"):
            out.pop(key, None)
        out["count_hidden"] = True
        return out

    def _scrub_bet(self, check):
        """The suggested bet and the edge both give the count away."""
        if check is None or self.count_visible:
            return check
        out = dict(check)
        for key in ("true_count", "edge", "suggested", "ramp"):
            out.pop(key, None)
        out["count_hidden"] = True
        out["flags"] = [f for f in out.get("flags", []) if f.get("key") != "watch"]
        return out

    def true_count(self):
        return self.running_count / self.decks_left()

    def unseen(self):
        """Everything the player can't see: the shoe, plus the hole card."""
        extra = [self.dealer[1]] if (self.hole_hidden and len(self.dealer) > 1) else []
        return self.shoe + extra

    def odds(self, up):
        return E.Odds(self.unseen(), up, hit_soft_17=self.rules["hit_soft_17"])

    # ---------------- round ----------------
    def reset_round(self):
        self.dealer = []
        self.hands = []
        self.seats = []
        self.hole_hidden = True
        self.active = 0
        self.phase = "bet"
        self.bet = 0.0
        self.took_insurance = False
        self.last_analysis = None
        self.last_bet_check = None
        self.verdict = None
        self.round_result = None
        self.even_money = False

    def new_round(self):
        if self.needs_shuffle():
            self.shuffle()
            self.session["shuffles"] += 1
        self.reset_round()
        # Revealing lasts one round. Otherwise the first peek turns the button
        # into a permanent readout and you stop counting altogether.
        self.hide_count()
        self.maybe_interrupt()

    def broke(self):
        """Can't make the smallest bet the table allows. The session is over."""
        return self.bankroll < self.config["table_min"]

    def clamp_bet(self, amount):
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = self.config["table_min"]
        ceiling = min(self.bankroll, self.config["table_max"])
        return max(self.config["table_min"], min(amount, ceiling))

    def place_bet(self, amount, last_bet=None, last_outcome=None):
        amount = self.clamp_bet(amount)
        self.last_bet_check = self.judge_bet(amount, last_bet, last_outcome)
        self.bet = amount
        self.bankroll -= amount
        self.deal()
        return self.last_bet_check

    def deal(self):
        self.seats = [{"cards": [], "total": 0, "bust": False}
                      for _ in range(self.config["others"])]
        self.hands = []
        self.dealer = []
        # one card to each seat left to right, then you, then the dealer, twice
        # over. You sit at third base, so everyone else is dealt to first.
        for round_no in range(2):
            for seat in self.seats:
                seat["cards"].append(self.draw())
            if round_no == 0:
                self.hands.append(self._new_hand([self.draw()], self.bet))
                self.dealer.append(self.draw())
            else:
                self.hands[0]["cards"].append(self.draw())
                self.dealer.append(self.draw(counted=False))  # hole card
        self.session["rounds"] += 1
        # insurance is offered before the dealer looks at the hole card
        if E.card_value(self.dealer[0]["rank"]) == 11:
            self.even_money = E.hand_value(self.hands[0]["cards"])[0] == 21
            self.phase = "insurance"
            return
        self.resolve_naturals()

    def _new_hand(self, cards, bet):
        return {"cards": cards, "bet": bet, "done": False, "doubled": False,
                "from_split": False, "split_ace": False,
                "result": None, "net": 0.0}

    def reveal(self):
        if len(self.dealer) > 1 and self.hole_hidden:
            self.running_count += E.hilo(E.card_value(self.dealer[1]["rank"]))
        self.hole_hidden = False

    def resolve_naturals(self):
        """
        The dealer peeks under a ten or an ace. If either side has a natural the
        hand is over before anybody plays.
        """
        player_nat = E.hand_value(self.hands[0]["cards"])[0] == 21
        dealer_nat = E.hand_value(self.dealer)[0] == 21
        if self.took_insurance and dealer_nat:
            self.bankroll += self.bet * 1.5   # half-stake back plus 2:1 winnings
        if player_nat or dealer_nat:
            self.reveal()
            self.hands[0]["done"] = True
            self.settle()
            return
        for seat in self.seats:
            self.play_seat(seat)
        self.phase = "play"

    def play_seat(self, seat):
        """Other players use basic strategy. They don't split, to keep it simple."""
        for _ in range(12):
            total, _ = E.hand_value(seat["cards"])
            if total > 21:
                break
            play = E.chart_play(seat["cards"], E.card_value(self.dealer[0]["rank"]),
                                len(seat["cards"]) == 2, False, self.rules)
            if play["move"] == "S":
                break
            seat["cards"].append(self.draw())
            if play["move"] == "D":
                break
        total, _ = E.hand_value(seat["cards"])
        seat["total"] = total
        seat["bust"] = total > 21

    # ---------------- decisions ----------------
    def can_double(self, hand):
        return (len(hand["cards"]) == 2 and not hand["split_ace"]
                and (hand["from_split"] is False or self.rules["das"])
                and self.bankroll >= hand["bet"])

    def can_hit(self, hand):
        """
        A split ace gets one card and that is the end of it.

        The hand only reaches you at all when the house allows re-splitting and
        the card was another ace, and the only thing you may do then is split it
        or leave it. Drawing to it is not on offer at a real table.
        """
        return not (hand["split_ace"] and len(hand["cards"]) == 2)

    def can_split(self, hand):
        if len(hand["cards"]) != 2 or len(self.hands) >= self.rules["max_hands"]:
            return False
        if self.bankroll < hand["bet"]:
            return False
        a, b = (E.card_value(c["rank"]) for c in hand["cards"])
        if a != b:
            return False
        if hand["split_ace"] and not self.rules["resplit_aces"]:
            return False
        return True

    def analyse(self, hand, chosen):
        """Score a decision before applying it."""
        up = E.card_value(self.dealer[0]["rank"])
        odds = self.odds(up)
        total, soft = E.hand_value(hand["cards"])
        cd, cs = self.can_double(hand), self.can_split(hand)
        chart = E.chart_play(hand["cards"], up, cd, cs, self.rules)

        options = [
            {"move": "S", "ev": odds.ev_stand(total), "legal": True},
            {"move": "H", "ev": odds.ev_hit(total, soft), "legal": True},
            {"move": "D", "ev": odds.ev_double(total, soft) if cd else None, "legal": cd},
            {"move": "P", "ev": odds.ev_split(E.card_value(hand["cards"][0]["rank"])) if cs else None,
             "legal": cs},
        ]
        legal = [o for o in options if o["legal"]]
        best = max(legal, key=lambda o: o["ev"])
        chart_opt = next((o for o in options if o["move"] == chart["move"] and o["legal"]), None)
        mine = next((o for o in options if o["move"] == chosen and o["legal"]), None)

        dist = odds.dealer()
        below = sum(p for k, p in dist.items() if k != "bust" and int(k) < total)
        above = sum(p for k, p in dist.items() if k != "bust" and int(k) > total)
        tie = sum(p for k, p in dist.items() if k != "bust" and int(k) == total)

        gap = (best["ev"] - chart_opt["ev"]) if chart_opt else 0.0

        # What a counter should do here. Graded separately from basic strategy,
        # because they are two different skills and collapsing them into one
        # number hides which of the two you are actually failing at.
        tc = self.true_count()
        count_move, index_entry, index_dev = C.correct_move(
            chart["move"], chart["kind"], total, chart.get("pair"), up, tc,
            can_split=cs, can_double=cd)
        count_opt = next((o for o in options if o["move"] == count_move and o["legal"]), None)

        return {
            "kind": "play",
            "row": chart["row"], "hand_kind": chart["kind"], "cell": chart["cell"],
            "pair": chart.get("pair"), "total": total, "soft": soft,
            "up": up, "chart_move": chart["move"], "chart_code": chart["code"],
            "fallback": chart["fallback"],
            "chosen": chosen, "correct": chosen == chart["move"],
            # the counting layer
            "count_move": count_move,
            "count_correct": chosen == count_move,
            "count_ev": count_opt["ev"] if count_opt else None,
            "index_deviation": index_dev,
            "index": (dict(index_entry, applies=True) if index_entry else None),
            "index_cost": (max(0.0, count_opt["ev"] - mine["ev"])
                           if (count_opt and mine) else 0.0),
            "options": [{"move": o["move"], "ev": o["ev"], "legal": o["legal"]} for o in options],
            "best_move": best["move"], "best_ev": best["ev"],
            "chart_ev": chart_opt["ev"] if chart_opt else None,
            "cost": max(0.0, (best["ev"] - mine["ev"])) if mine else 0.0,
            # only call it a deviation if it's worth more than rounding noise
            "deviation": best["move"] != chart["move"] and gap > 0.002,
            "dev_gap": gap,
            "bust": odds.bust_chance(total, soft),
            "dealer_dist": dist,
            "dealer_bust": odds.dealer_bust(),
            "p_below": below, "p_above": above, "p_tie": tie,
            "composition": [{"value": v, "left": odds.counts[v], "p": odds.p(v)}
                            for v in range(2, 12)],
            "unseen": odds.total,
            "true_count": self.true_count(), "running_count": self.running_count,
            "hand_index": self.active, "hand_count": len(self.hands),
        }

    def act(self, move):
        hand = self.hands[self.active]
        analysis = self.analyse(hand, move)
        self.last_analysis = analysis
        self.verdict = {
            "correct": analysis["correct"], "chosen": move,
            "should": analysis["chart_move"], "row": analysis["row"],
            "up": R.up_label(analysis["up"]),
            "fallback": analysis["fallback"], "kind": "play",
            "hand_index": self.active, "hand_count": len(self.hands),
        }
        self.session["decisions"] += 1
        self.session["correct"] += 1 if analysis["correct"] else 0
        self.session["ev_lost"] += analysis["cost"] * hand["bet"]

        if move == "H":
            hand["cards"].append(self.draw())
            if E.hand_value(hand["cards"])[0] >= 21:
                hand["done"] = True
        elif move == "S":
            hand["done"] = True
        elif move == "D":
            self.bankroll -= hand["bet"]
            hand["bet"] *= 2
            hand["doubled"] = True
            hand["cards"].append(self.draw())
            hand["done"] = True
        elif move == "P":
            self._split(hand)

        self.advance()
        return analysis

    def _split(self, hand):
        """
        Split the hand in front of you, casino style.

        The second card slides across to start a new spot, that spot is left face
        up with a single card, and the dealer deals one card to the hand you are
        still playing. The new spot gets its card only when the dealer reaches
        it — which is after this hand is completely finished.
        """
        moved = hand["cards"].pop()
        is_ace = hand["cards"][0]["rank"] == "A"

        new_hand = self._new_hand([moved], hand["bet"])
        new_hand["from_split"] = True
        new_hand["split_ace"] = is_ace
        hand["from_split"] = True
        hand["split_ace"] = is_ace

        self.bankroll -= hand["bet"]
        self.hands.insert(self.active + 1, new_hand)

        hand["cards"].append(self.draw())
        self._close_if_finished(hand)

    def _close_if_finished(self, hand):
        """
        Decide whether a freshly two-carded split hand still has a decision in it.

        Split aces get one card and that's the end of it, unless the house lets
        you re-split them and the card was another ace. Anything that reaches 21
        is finished too — there is nothing left to choose.
        """
        total, _ = E.hand_value(hand["cards"])
        if hand["split_ace"]:
            hand["done"] = not self.can_split(hand)
            return
        if total >= 21:
            hand["done"] = True

    def insurance(self, take):
        odds = self.odds(11)
        p_ten = odds.p(10)
        ev = 3 * p_ten - 1
        if take:
            self.bankroll -= self.bet / 2
            self.took_insurance = True
        # Insurance is the most valuable index play there is, and the only one
        # where basic strategy and a counter give opposite answers often enough
        # to matter. Graded both ways: never take it if you are not counting,
        # take it at +3 or better if you are.
        tc = self.true_count()
        should_take, entry = C.insurance_play(tc)
        self.last_analysis = {
            "kind": "insurance", "took": bool(take), "p_ten": p_ten, "ev": ev,
            "tens_left": odds.counts[10], "unseen": odds.total,
            "correct": not take,                      # basic strategy: always decline
            "count_move": "take" if should_take else "decline",
            "count_correct": bool(take) == should_take,
            "index_deviation": should_take,
            "index": dict(entry, applies=True),
            "even_money": self.even_money,
            "true_count": tc, "running_count": self.running_count,
        }
        self.verdict = {"kind": "insurance", "correct": not take,
                        "count_correct": bool(take) == should_take,
                        "even_money": self.even_money,
                        "chosen": "take" if take else "decline"}
        self.session["decisions"] += 1
        self.session["correct"] += 0 if take else 1
        self.resolve_naturals()
        return self.last_analysis

    def advance(self):
        """
        Move to the next hand that still needs a decision.

        A hand created by a split arrives here holding one card. That is the
        moment the dealer gives it its second — not a moment earlier.
        """
        guard = 0
        while self.active < len(self.hands):
            hand = self.hands[self.active]
            if len(hand["cards"]) == 1:
                hand["cards"].append(self.draw())
                self._close_if_finished(hand)
            if not hand["done"]:
                self.phase = "play"
                return
            self.active += 1
            guard += 1
            if guard > 16:
                break

        self.reveal()
        if any(E.hand_value(h["cards"])[0] <= 21 for h in self.hands):
            while self._dealer_draws():
                self.dealer.append(self.draw())
        self.settle()

    def _dealer_draws(self):
        total, soft = E.hand_value(self.dealer)
        if total < 17:
            return True
        return total == 17 and soft and self.rules["hit_soft_17"]

    def settle(self):
        self.reveal()
        dealer_total = E.hand_value(self.dealer)[0]
        dealer_nat = len(self.dealer) == 2 and dealer_total == 21
        bj_pay = self.rules["blackjack_pays"]
        net = 0.0
        wagered = 0.0
        for hand in self.hands:
            total = E.hand_value(hand["cards"])[0]
            natural = (not hand["from_split"]) and len(hand["cards"]) == 2 and total == 21
            bet = hand["bet"]
            wagered += bet
            if natural and dealer_nat:
                hand["result"], gain = "push", 0.0
                self.bankroll += bet
            elif natural:
                hand["result"], gain = "blackjack", bet * bj_pay
                self.bankroll += bet + gain
                self.session["blackjacks"] += 1
            elif total > 21:
                hand["result"], gain = "bust", -bet
                self.session["busts"] += 1
            elif dealer_nat:
                hand["result"], gain = "lose", -bet
            elif dealer_total > 21 or total > dealer_total:
                hand["result"], gain = "win", bet
                self.bankroll += bet * 2
            elif total < dealer_total:
                hand["result"], gain = "lose", -bet
            else:
                hand["result"], gain = "push", 0.0
                self.bankroll += bet
            hand["net"] = gain
            net += gain
            self.session["hands"] += 1
            if gain > 0:
                self.session["wins"] += 1
            elif gain < 0:
                self.session["losses"] += 1
            else:
                self.session["pushes"] += 1

        if self.took_insurance:
            wagered += self.bet / 2
            net += self.bet * (0.5 if dealer_nat else -0.5)

        self.phase = "settled"
        self.session["wagered"] += wagered
        self.session["net"] += net
        self.session["peak"] = max(self.session["peak"], self.bankroll)
        self.session["trough"] = min(self.session["trough"], self.bankroll)
        if net > 0:
            self.session["streak"] = max(0, self.session["streak"]) + 1
        elif net < 0:
            self.session["streak"] = min(0, self.session["streak"]) - 1
        else:
            self.session["streak"] = 0
        self.session["best_streak"] = max(self.session["best_streak"], self.session["streak"])

        self.round_result = {
            "net": net, "wagered": wagered,
            "outcome": "win" if net > 0 else "lose" if net < 0 else "push",
            "broke": self.broke(),
        }
        return self.round_result

    # ---------------- bet sizing ----------------
    def judge_bet(self, amount, last_bet=None, last_outcome=None):
        tc = self.true_count()
        edge = E.edge_at(tc)
        table_min = self.config["table_min"]
        bankroll = self.bankroll if self.phase == "bet" else self.bankroll + amount

        if edge > 0:
            kelly = bankroll * (edge / 1.3)
            suggested = max(table_min, round(kelly / table_min) * table_min)
        else:
            suggested = table_min
        suggested = min(suggested, max(table_min, (bankroll // table_min) * table_min))

        share = amount / bankroll if bankroll else 1.0
        units = bankroll / amount if amount else 0.0
        flags = []

        if last_outcome == "lose" and last_bet and amount > last_bet and tc < 2:
            flags.append({"key": "chase", "level": "bad", "text":
                "You raised your bet after losing, and the cards don't back it up. "
                "That's a chasing pattern. It doesn't change your odds at all — it just "
                "puts more money at risk in fewer hands, so you go broke faster."})
        if last_outcome == "win" and last_bet and amount > last_bet * 2 and tc < 2:
            flags.append({"key": "press", "level": "warn", "text":
                "You doubled up after a win. Each hand is dealt from a fresh position — "
                "the last result tells you nothing about the next one."})
        if amount > table_min:
            if share > 0.15:
                flags.append({"key": "over", "level": "bad", "text":
                    "This bet is %d%% of everything you have, and you weren't forced into it — "
                    "the minimum here is $%d. A normal run of bad luck wipes you out at this size."
                    % (round(share * 100), table_min)})
            elif share > 0.05:
                flags.append({"key": "big", "level": "warn", "text":
                    "This bet is %d%% of your money. For a game that swings this much, "
                    "1–2%% per hand is the usual guidance." % round(share * 100)})
        if table_min / bankroll > 0.15:
            flags.append({"key": "undercap", "level": "warn", "text":
                "The smallest bet allowed here is %d%% of your money. This table is too "
                "expensive for what you're carrying, however well you play."
                % round(table_min / bankroll * 100)})
        if tc >= 2 and amount <= table_min:
            flags.append({"key": "watch", "level": "info", "text":
                "The count is +%.1f, which is the rare moment the odds tip your way, and "
                "you're betting the minimum. Not a mistake — flat betting is right unless "
                "you're genuinely tracking the cards — but this is the only time betting "
                "more has real maths behind it." % tc})

        # betting the minimum is never an error: you can't bet less than the minimum
        ok = amount <= max(suggested, table_min) + 0.01 and not any(f["level"] == "bad" for f in flags)
        return {
            "amount": amount, "suggested": suggested, "edge": edge, "true_count": tc,
            "share": share, "units": units, "flags": flags, "ok": ok,
            "p_double": E.reach_before_ruin(units, units * 2, edge),
            "p_ruin": E.risk_of_ruin(units, edge),
            "table_min": table_min, "bankroll": bankroll,
        }

    # ---------------- serialisation ----------------
    def snapshot(self):
        hero = []
        for i, h in enumerate(self.hands):
            total, soft = E.hand_value(h["cards"])
            hero.append({
                "cards": h["cards"], "total": total, "soft": soft, "bet": h["bet"],
                "doubled": h["doubled"], "result": h["result"], "net": h["net"],
                "from_split": h["from_split"], "split_ace": h["split_ace"],
                "active": (self.phase == "play" and i == self.active),
                "pending": len(h["cards"]) == 1,
                "bust": total > 21,
            })
        dealer_total, _ = E.hand_value(self.dealer)
        active_hand = self.hands[self.active] if (
            self.phase == "play" and self.active < len(self.hands)) else None
        return {
            "phase": self.phase,
            "bankroll": round(self.bankroll, 2),
            "bet": self.bet,
            "broke": self.broke(),
            "even_money": self.even_money,
            "dealer": {
                "cards": self.dealer,
                "hole_hidden": self.hole_hidden,
                "showing": E.card_value(self.dealer[0]["rank"]) if self.dealer else None,
                "total": None if self.hole_hidden else dealer_total,
                "bust": (not self.hole_hidden) and dealer_total > 21,
            },
            "hands": hero,
            "active": self.active,
            "seats": [{"cards": s["cards"], "total": E.hand_value(s["cards"])[0],
                       "bust": E.hand_value(s["cards"])[0] > 21} for s in self.seats],
            "can_hit": self.can_hit(active_hand) if active_hand else False,
            "can_double": self.can_double(active_hand) if active_hand else False,
            "can_split": self.can_split(active_hand) if active_hand else False,
            "running_count": self.running_count if self.count_visible else None,
            "true_count": round(self.true_count(), 2) if self.count_visible else None,
            "count_hidden": not self.count_visible,
            "count_check": self.pending_check,
            "count_record": self.count_record(),
            "decks_left": round(self.decks_left(), 2),
            "shoe_used": round(self.dealt / (self.config["decks"] * 52), 3),
            "cards_left": len(self.shoe),
            "config": self.config,
            "rules": self.rules,
            "session": dict(self.session, bankroll=round(self.bankroll, 2)),
            "verdict": self.verdict,
            "analysis": self._scrub(self.last_analysis),
            "bet_check": self._scrub_bet(self.last_bet_check),
            "round_result": self.round_result,
        }
