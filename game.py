"""
game.py — one blackjack table.

Holds the shoe, the seats, whose turn it is, and the money. Every decision
you make gets handed to engine.py to be scored before it's applied.
"""

import random
import engine as E

MIN_CARDS = 20


def fresh_shoe(decks):
    cards = [
        {"rank": r, "suit": s, "red": red}
        for _ in range(decks)
        for s, red in E.SUITS
        for r in E.RANKS
    ]
    random.shuffle(cards)
    return cards


class Table:
    def __init__(self, config=None, bankroll=100.0):
        self.config = {
            "decks": 6,
            "others": 2,          # other people sitting at the table
            "table_min": 15,
            "penetration": 0.75,  # how deep before they reshuffle
        }
        if config:
            self.config.update({k: v for k, v in config.items() if k in self.config})
        self.bankroll = float(bankroll)
        self.shuffle()
        self.reset_round()

    # ---------------- shoe ----------------
    def shuffle(self):
        self.shoe = fresh_shoe(self.config["decks"])
        self.dealt = 0
        self.running_count = 0

    def needs_shuffle(self):
        return self.dealt > self.config["penetration"] * self.config["decks"] * 52

    def draw(self, counted=True):
        if len(self.shoe) < MIN_CARDS:
            self.shuffle()
        card = self.shoe.pop()
        self.dealt += 1
        if counted:
            self.running_count += E.hilo(E.card_value(card["rank"]))
        return card

    def decks_left(self):
        return max(0.25, (self.config["decks"] * 52 - self.dealt) / 52.0)

    def true_count(self):
        return self.running_count / self.decks_left()

    def unseen(self):
        """Everything the player can't see: the shoe, plus the hole card."""
        extra = [self.dealer[1]] if (self.hole_hidden and len(self.dealer) > 1) else []
        return self.shoe + extra

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

    def new_round(self):
        if self.needs_shuffle():
            self.shuffle()
        self.reset_round()

    def place_bet(self, amount):
        amount = max(self.config["table_min"], min(float(amount), self.bankroll))
        self.bet = amount
        self.last_bet_check = self.judge_bet(amount)
        self.bankroll -= amount
        self.deal()
        return self.last_bet_check

    def deal(self):
        self.seats = [{"cards": [], "total": 0, "bust": False}
                      for _ in range(self.config["others"])]
        self.hands = []
        # one card to each seat left to right, then the dealer, twice over.
        # you sit at third base, so everyone else is dealt to first.
        for round_no in range(2):
            for seat in self.seats:
                seat["cards"].append(self.draw())
            if round_no == 0:
                self.hands.append(self._new_hand([self.draw()], self.bet))
                self.dealer.append(self.draw())
            else:
                self.hands[0]["cards"].append(self.draw())
                self.dealer.append(self.draw(counted=False))  # hole card
        # insurance is offered before the dealer looks at the hole card
        if E.card_value(self.dealer[0]["rank"]) == 11:
            self.phase = "insurance"
            return
        self.resolve_naturals()

    def _new_hand(self, cards, bet):
        return {"cards": cards, "bet": bet, "done": False, "doubled": False,
                "from_split": False, "split_ace": False, "result": None}

    def reveal(self):
        if len(self.dealer) > 1 and self.hole_hidden:
            self.running_count += E.hilo(E.card_value(self.dealer[1]["rank"]))
        self.hole_hidden = False

    def resolve_naturals(self):
        player_nat = E.hand_value(self.hands[0]["cards"])[0] == 21
        dealer_nat = E.hand_value(self.dealer)[0] == 21
        if self.took_insurance and dealer_nat:
            self.bankroll += self.bet * 1.5   # 0.5 stake back plus 1.0 winnings
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
            total, soft = E.hand_value(seat["cards"])
            if total > 21:
                break
            play = E.chart_play(seat["cards"], E.card_value(self.dealer[0]["rank"]),
                                len(seat["cards"]) == 2, False)
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
        return len(hand["cards"]) == 2 and not hand["split_ace"] and self.bankroll >= hand["bet"]

    def can_split(self, hand):
        return (len(hand["cards"]) == 2 and not hand["split_ace"] and len(self.hands) < 4
                and self.bankroll >= hand["bet"]
                and E.card_value(hand["cards"][0]["rank"]) == E.card_value(hand["cards"][1]["rank"]))

    def analyse(self, hand, chosen):
        """Score a decision before applying it."""
        up = E.card_value(self.dealer[0]["rank"])
        odds = E.Odds(self.unseen(), up)
        total, soft = E.hand_value(hand["cards"])
        cd, cs = self.can_double(hand), self.can_split(hand)
        chart = E.chart_play(hand["cards"], up, cd, cs)

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
        return {
            "kind": "play",
            "row": chart["row"], "hand_kind": chart["kind"],
            "pair": chart.get("pair"), "total": total, "soft": soft,
            "up": up, "chart_move": chart["move"], "fallback": chart["fallback"],
            "chosen": chosen, "correct": chosen == chart["move"],
            "options": [{"move": o["move"], "ev": o["ev"], "legal": o["legal"]} for o in options],
            "best_move": best["move"], "best_ev": best["ev"],
            "chart_ev": chart_opt["ev"] if chart_opt else None,
            "cost": (best["ev"] - mine["ev"]) if mine else 0.0,
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
        }

    def act(self, move):
        hand = self.hands[self.active]
        analysis = self.analyse(hand, move)
        self.last_analysis = analysis
        self.verdict = {
            "correct": analysis["correct"], "chosen": move,
            "should": analysis["chart_move"], "row": analysis["row"],
            "up": "A" if analysis["up"] == 11 else str(analysis["up"]),
            "fallback": analysis["fallback"], "kind": "play",
        }

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
            moved = hand["cards"].pop()
            is_ace = hand["cards"][0]["rank"] == "A"
            new_hand = self._new_hand([moved], hand["bet"])
            new_hand["from_split"] = True
            new_hand["split_ace"] = is_ace
            hand["from_split"] = True
            hand["split_ace"] = is_ace
            self.bankroll -= hand["bet"]
            hand["cards"].append(self.draw())
            new_hand["cards"].append(self.draw())
            if is_ace:
                hand["done"] = new_hand["done"] = True
            if E.hand_value(hand["cards"])[0] == 21:
                hand["done"] = True
            self.hands.insert(self.active + 1, new_hand)

        self.advance()
        return analysis

    def insurance(self, take):
        odds = E.Odds(self.unseen(), 11)
        p_ten = odds.p(10)
        ev = 3 * p_ten - 1
        if take:
            self.bankroll -= self.bet / 2
            self.took_insurance = True
        self.last_analysis = {
            "kind": "insurance", "took": bool(take), "p_ten": p_ten, "ev": ev,
            "tens_left": odds.counts[10], "unseen": odds.total,
            "correct": bool(take) == (ev > 0),
            "true_count": self.true_count(), "running_count": self.running_count,
        }
        self.verdict = {"kind": "insurance", "correct": not take, "chosen": "take" if take else "decline"}
        self.resolve_naturals()
        return self.last_analysis

    def advance(self):
        while self.active < len(self.hands) and self.hands[self.active]["done"]:
            self.active += 1
        if self.active < len(self.hands):
            self.phase = "play"
            return
        self.reveal()
        if any(E.hand_value(h["cards"])[0] <= 21 for h in self.hands):
            while E.hand_value(self.dealer)[0] < 17:
                self.dealer.append(self.draw())
        self.settle()

    def settle(self):
        self.reveal()
        dealer_total = E.hand_value(self.dealer)[0]
        dealer_nat = len(self.dealer) == 2 and dealer_total == 21
        net = 0.0
        for hand in self.hands:
            total = E.hand_value(hand["cards"])[0]
            natural = (not hand["from_split"]) and len(hand["cards"]) == 2 and total == 21
            bet = hand["bet"]
            if natural and dealer_nat:
                hand["result"] = "push"; self.bankroll += bet
            elif natural:
                hand["result"] = "blackjack"; self.bankroll += bet * 2.5; net += bet * 1.5
            elif total > 21:
                hand["result"] = "bust"; net -= bet
            elif dealer_nat:
                hand["result"] = "lose"; net -= bet
            elif dealer_total > 21 or total > dealer_total:
                hand["result"] = "win"; self.bankroll += bet * 2; net += bet
            elif total < dealer_total:
                hand["result"] = "lose"; net -= bet
            else:
                hand["result"] = "push"; self.bankroll += bet
        self.phase = "settled"
        self.round_result = {"net": net,
                             "outcome": "win" if net > 0 else "lose" if net < 0 else "push"}
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
                "That's a chasing pattern. It doesn't change your odds at all \u2014 it just "
                "puts more money at risk in fewer hands, so you go broke faster."})
        if last_outcome == "win" and last_bet and amount > last_bet * 2 and tc < 2:
            flags.append({"key": "press", "level": "warn", "text":
                "You doubled up after a win. Each hand is dealt from a fresh position \u2014 "
                "the last result tells you nothing about the next one."})
        if amount > table_min:
            if share > 0.15:
                flags.append({"key": "over", "level": "bad", "text":
                    "This bet is %d%% of everything you have, and you weren't forced into it \u2014 "
                    "the minimum here is $%d. A normal run of bad luck wipes you out at this size."
                    % (round(share * 100), table_min)})
            elif share > 0.05:
                flags.append({"key": "big", "level": "warn", "text":
                    "This bet is %d%% of your money. For a game that swings this much, "
                    "1\u20132%% per hand is the usual guidance." % round(share * 100)})
        if table_min / bankroll > 0.15:
            flags.append({"key": "undercap", "level": "warn", "text":
                "The smallest bet allowed here is %d%% of your money. This table is too "
                "expensive for what you're carrying, however well you play."
                % round(table_min / bankroll * 100)})
        if tc >= 2 and amount <= table_min:
            flags.append({"key": "watch", "level": "info", "text":
                "The count is +%.1f, which is the rare moment the odds tip your way, and "
                "you're betting the minimum. Not a mistake \u2014 flat betting is right unless "
                "you're genuinely tracking the cards \u2014 but this is the only time betting "
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
                "doubled": h["doubled"], "result": h["result"],
                "active": (self.phase == "play" and i == self.active),
                "bust": total > 21,
            })
        dealer_total, _ = E.hand_value(self.dealer)
        return {
            "phase": self.phase,
            "bankroll": round(self.bankroll, 2),
            "bet": self.bet,
            "dealer": {
                "cards": self.dealer,
                "hole_hidden": self.hole_hidden,
                "showing": E.card_value(self.dealer[0]["rank"]) if self.dealer else None,
                "total": None if self.hole_hidden else dealer_total,
                "bust": (not self.hole_hidden) and dealer_total > 21,
            },
            "hands": hero,
            "seats": [{"cards": s["cards"], "total": E.hand_value(s["cards"])[0],
                       "bust": E.hand_value(s["cards"])[0] > 21} for s in self.seats],
            "can_double": self.can_double(self.hands[self.active])
                          if self.phase == "play" and self.active < len(self.hands) else False,
            "can_split": self.can_split(self.hands[self.active])
                         if self.phase == "play" and self.active < len(self.hands) else False,
            "running_count": self.running_count,
            "true_count": round(self.true_count(), 2),
            "shoe_used": round(self.dealt / (self.config["decks"] * 52), 3),
            "cards_left": len(self.shoe),
            "config": self.config,
            "verdict": self.verdict,
            "analysis": self.last_analysis,
            "bet_check": self.last_bet_check,
            "round_result": self.round_result,
        }
