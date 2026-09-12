#!/usr/bin/env python3
"""
Card-counting walk-out solver.

Same table as the flat-bet study (6 decks, dealer stands on soft 17, double after
split, 3:2 blackjack, cut card at 75%, no continuous shuffler), but the player
now keeps a Hi-Lo count, spreads their bets with the true count, and plays the
Illustrious 18 index plays plus insurance at true count +3.

What comes out of it:

  1. A state model from 100,000 sessions played with an unlimited bankroll: the
     value and outcome distribution of one round at every (true count, shoe
     depth) state, and the transition probabilities between those states.
  2. Dynamic-programming solutions of the walk-out decision:
       * DP1 over (round, count, depth): unlimited bankroll.
       * DP2 over (round, count, depth, stack): the real bankroll, fixed ramp.
       * DP2-opt: the same, but the bet size is chosen too (perfect play for
         expected profit, table maximum respected).
     Each gives a leave region, and from it the decision tree.
  3. 100,000-session verification of every policy with the real $300 bankroll.

Usage:
  python3 research/count_solver.py \
      [--sessions 100000] [--rounds 100] [--bankroll 300] [--bet 15] [--seed 20260912] \
      [--out results.json]
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from multiprocessing import Pool

TC_MIN, TC_MAX = -6, 6                # floor(true count), clamped
N_TC = TC_MAX - TC_MIN + 1
N_DEPTH = 8                           # 10% bins of the shoe (the cut card sits at 75%)
NS = N_TC * N_DEPTH
BMAX_UNITS = 120                      # stacks above this many minimum bets are treated as "plenty"
HB = BMAX_UNITS * 2                   # stack levels in half-units (a 3:2 blackjack pays 1.5 units)
OPT_CHOICES = [1, 2, 4, 8, 16, 33]    # bet sizes the perfect bettor may choose (33 x $15 = table max $495)

RAMPS = {                             # units of the minimum bet, by floor(true count); below +1 is always 1 unit
    "flat": {},
    "1-4": {1: 2, 2: 3, 3: 4},
    "1-8": {1: 2, 2: 4, 3: 6, 4: 8},
    "1-12": {1: 2, 2: 4, 3: 8, 4: 12},
}
WIN_TARGETS = [15, 30, 60, 105, 150, 210, 300, None]
LOSS_LIMITS = [30, 60, 105, 150, 210, None]
INF = 10 ** 9


def units_for(ramp, tci):
    r = RAMPS[ramp]
    if not r or tci < 1:
        return 1
    top = max(r)
    return r[top] if tci >= top else r.get(tci, 1)


def tc_idx(tci):
    return min(TC_MAX, max(TC_MIN, tci)) - TC_MIN


def depth_idx(frac):
    return min(N_DEPTH - 1, int(frac * 10))


def state(tci, frac):
    return tc_idx(tci) * N_DEPTH + depth_idx(frac)


def make_sim_class(S):
    """Build the counting table on top of sim.Sim from the repo (imported inside the worker)."""

    class CountSim(S.Sim):
        def __init__(self, rules, decks, penetration, rng, index_plays=True):
            super().__init__(rules, decks, penetration, rng)
            self.index_plays = index_plays

        def visible_tc(self, hole):
            """True count as the player sees it mid-hand: the hole card is face down."""
            left = max(0.25, (self.decks * 52 - self.dealt) / 52.0)
            return (self.count - S._HILO[hole]) / left

        # Illustrious 18 (no surrender at this table) -- returns a move, or None for "use the chart"
        def _index(self, cards, up, total, soft, can_double, can_split, tc):
            first_two = len(cards) == 2
            pair = first_two and cards[0] == cards[1]
            if pair and can_split and cards[0] != 10:
                return None
            if pair and cards[0] == 10 and can_split:
                if up == 5 and tc >= 5:
                    return "P"
                if up == 6 and tc >= 4:
                    return "P"
                return None
            if soft:
                return None
            if total == 16 and up == 10:
                return "S" if tc >= 0 else "H"
            if total == 15 and up == 10:
                return "S" if tc >= 4 else "H"
            if total == 16 and up == 9:
                return "S" if tc >= 5 else "H"
            if total == 13 and up == 2:
                return "S" if tc >= -1 else "H"
            if total == 13 and up == 3:
                return "S" if tc >= -2 else "H"
            if total == 12 and up == 2:
                return "S" if tc >= 3 else "H"
            if total == 12 and up == 3:
                return "S" if tc >= 2 else "H"
            if total == 12 and up == 4:
                return "S" if tc >= 0 else "H"
            if total == 12 and up == 5:
                return "S" if tc >= -2 else "H"
            if total == 12 and up == 6:
                return "S" if tc >= -1 else "H"
            if first_two:
                dbl = "D" if can_double else "H"
                if total == 10 and up == 10:
                    return dbl if tc >= 4 else "H"
                if total == 10 and up == 11:
                    return dbl if tc >= 4 else "H"
                if total == 11 and up == 11:
                    return dbl if tc >= 1 else "H"
                if total == 9 and up == 2:
                    return dbl if tc >= 1 else "H"
                if total == 9 and up == 7:
                    return dbl if tc >= 3 else "H"
            return None

        def decide_tc(self, cards, up, can_double, can_split, tc):
            total, soft = S._total(cards)
            if self.index_plays:
                m = self._index(cards, up, total, soft, can_double, can_split, tc)
                if m is not None:
                    return m
            if can_split and len(cards) == 2 and cards[0] == cards[1]:
                section, row = "pair", cards[0]
            elif soft:
                section, row = "soft", max(2, min(9, total - 11))
            else:
                section, row = "hard", max(5, min(21, total))
            code = self.chart.get((section, row, up), "S")
            if code == "D":
                return "D" if can_double else "H"
            if code == "Ds":
                return "D" if can_double else "S"
            return code

        def play(self, bet, bankroll=None):
            """One round. bet=0 means sitting out (cards still leave the shoe). Returns (net, wagered)."""
            spare = (bankroll - bet) if bankroll is not None else float("inf")
            dealer = [self.draw(), self.draw()]
            hands = [[self.draw(), self.draw()]]
            bets = [bet]
            split_ace = [False]
            done = [False]
            net = 0.0
            wagered = bet
            hole = dealer[1]
            d_total, _ = S._total(dealer)
            p_total, _ = S._total(hands[0])

            if (dealer[0] == 11 and bet > 0 and self.index_plays
                    and math.floor(self.visible_tc(hole)) >= 3 and spare >= bet / 2):
                ins = bet / 2
                wagered += ins
                if d_total == 21:
                    return (ins * 2 + (0.0 if p_total == 21 else -bet), wagered)
                net -= ins
                spare -= ins

            if d_total == 21 or p_total == 21:
                if p_total == 21 and d_total == 21:
                    return (net, wagered)
                if p_total == 21:
                    return (net + bet * self.bj, wagered)
                return (net - bet, wagered)

            i = 0
            guard = 0
            while i < len(hands):
                guard += 1
                if guard > 40:
                    break
                if len(hands[i]) == 1:
                    hands[i].append(self.draw())
                    if split_ace[i]:
                        done[i] = not (self.resplit_aces and hands[i][0] == hands[i][1]
                                       and len(hands) < self.max_hands and spare >= bets[i])
                    elif S._total(hands[i])[0] >= 21:
                        done[i] = True
                while not done[i]:
                    cards = hands[i]
                    total, _ = S._total(cards)
                    if total >= 21:
                        break
                    first_two = len(cards) == 2
                    can_double = (first_two and not split_ace[i] and spare >= bets[i]
                                  and (self.das or len(hands) == 1))
                    can_split = (first_two and cards[0] == cards[1]
                                 and len(hands) < self.max_hands and spare >= bets[i]
                                 and not (split_ace[i] and not self.resplit_aces))
                    tc = math.floor(self.visible_tc(hole))
                    move = self.decide_tc(cards, dealer[0], can_double, can_split, tc)
                    if move == "S":
                        break
                    if move == "D":
                        spare -= bets[i]
                        wagered += bets[i]
                        bets[i] *= 2
                        cards.append(self.draw())
                        break
                    if move == "P":
                        spare -= bets[i]
                        wagered += bets[i]
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
                    cards.append(self.draw())
                done[i] = True
                i += 1

            if any(S._total(h)[0] <= 21 for h in hands):
                while True:
                    t, s = S._total(dealer)
                    if t < 17 or (t == 17 and s and self.h17):
                        dealer.append(self.draw())
                    else:
                        break
            d_total, _ = S._total(dealer)
            for cards, stake in zip(hands, bets):
                t, _ = S._total(cards)
                if t > 21:
                    net -= stake
                elif d_total > 21 or t > d_total:
                    net += stake
                elif t < d_total:
                    net -= stake
            return (net, wagered)

    return CountSim


# ---------------------------------------------------------------------------
# One worker: a chunk of sessions under one policy
# ---------------------------------------------------------------------------

def worker(job):
    repo, seed, n_sessions, rounds, bankroll, min_bet, table_max, policy, rules_over, collect_dp = job
    sys.path.insert(0, repo)
    import random
    import rules as R
    import sim as S

    CountSim = make_sim_class(S)
    rset = R.normalise(rules_over or {})
    rng = random.Random(seed)
    sim = CountSim(rset, rset["decks"], 0.75, rng, index_plays=policy["index"])
    cards_total = rset["decks"] * 52
    ramp = policy["ramp"]
    kind = policy["kind"]
    table = policy.get("table")            # leave_dp: list[rounds] of list[NS] bools; leave_dp2: list[rounds] of list[NS] ints
    bet_table = policy.get("bets")         # opt_dp2: bytes, units by [round][state][stack half-units], 0 = leave
    stride_s = HB + 1
    stride_r = NS * stride_s

    W2 = [None if w is None else w * 2 for w in WIN_TARGETS]
    L2 = [None if l is None else l * 2 for l in LOSS_LIMITS]
    w_sorted = [i for i, w in enumerate(W2) if w is not None]
    l_sorted = [i for i, l in enumerate(L2) if l is not None]
    rule_dist = [Counter() for _ in range(len(W2) * len(L2))]
    rule_rounds = [0] * (len(W2) * len(L2))

    final = Counter()
    dist_at = [Counter() for _ in range(rounds + 1)]
    busted = 0
    rounds_sum = 0
    hands_sum = 0
    wagered_sum = 0.0
    peak_dist = Counter()
    ev_by_tc_sum = [0.0] * N_TC        # $ won per $ of initial bet, by true count at the bet
    ev_by_tc_cnt = [0] * N_TC
    wag_by_tc = [0.0] * N_TC
    bet_by_tc = [0.0] * N_TC
    trans = Counter()
    unit_sum = [0.0] * NS
    unit_cnt = [0] * NS
    out_dist = [Counter() for _ in range(NS)] if collect_dp else None
    leave_at = Counter()               # round on which the policy left (leave rules only)
    leave_tc = Counter()
    max_bet_seen = 0.0

    for _ in range(n_sessions):
        sim.shuffle()
        stack = float(bankroll)
        in_play = True
        path = [0] * (rounds + 1)
        played = rounds
        hands = 0
        wagered = 0.0
        for r in range(rounds):
            if sim.cut_card():
                sim.shuffle()
            tc = sim.true_count()
            tci = math.floor(tc)
            s = state(tci, sim.dealt / cards_total)
            sh = min(HB, int(stack // (min_bet / 2.0)))
            if stack < min_bet:                        # cannot cover a minimum bet: busted
                busted += 1
                played = r
                break

            units = None
            if kind == "leave_tc" and tci <= policy["T"]:
                played = r
                leave_at[r] += 1
                leave_tc[max(TC_MIN, tci)] += 1
                break
            if kind == "leave_dp" and table[r][s]:
                played = r
                leave_at[r] += 1
                leave_tc[max(TC_MIN, tci)] += 1
                break
            if kind == "leave_dp2" and sh <= table[r][s]:
                played = r
                leave_at[r] += 1
                leave_tc[max(TC_MIN, tci)] += 1
                break
            if kind == "opt_dp2":
                units = bet_table[r * stride_r + s * stride_s + sh]
                if units == 0:
                    played = r
                    leave_at[r] += 1
                    leave_tc[max(TC_MIN, tci)] += 1
                    break
            if kind == "wong":
                if in_play and tci <= policy["exit"]:
                    in_play = False
                elif not in_play and tci >= policy["enter"]:
                    in_play = True
            if kind == "wong" and not in_play:
                bet = 0.0
            else:
                if units is None:
                    units = units_for(ramp, tci)
                bet = min(units * min_bet, table_max, stack)
            net, wag = sim.play(bet, bankroll=stack if bet > 0 else None)
            stack += net
            wagered += wag
            if bet > 0:
                hands += 1
                k = tc_idx(tci)
                ev_by_tc_sum[k] += net / bet
                ev_by_tc_cnt[k] += 1
                wag_by_tc[k] += wag
                bet_by_tc[k] += bet
                if bet > max_bet_seen:
                    max_bet_seen = bet
            if collect_dp and bet > 0:
                if sim.cut_card():
                    s2 = state(0, 0.0)
                else:
                    s2 = state(math.floor(sim.true_count()), sim.dealt / cards_total)
                trans[(s, s2)] += 1
                unit_sum[s] += net / bet
                unit_cnt[s] += 1
                out_dist[s][int(round(net / bet * 2))] += 1
            path[r + 1] = int(round((stack - bankroll) * 2))
        last = path[played]
        for m in range(played + 1, rounds + 1):
            path[m] = last
        rounds_sum += played
        hands_sum += hands
        wagered_sum += wagered
        final[path[rounds]] += 1
        for n in range(rounds + 1):
            dist_at[n][path[n]] += 1
        peak_dist[max(path)] += 1

        if kind == "playall":
            t_up = [INF] * len(W2)
            t_dn = [INF] * len(L2)
            wi = li = 0
            for n in range(1, played + 1):
                v = path[n]
                while wi < len(w_sorted) and v >= W2[w_sorted[wi]]:
                    t_up[w_sorted[wi]] = n
                    wi += 1
                while li < len(l_sorted) and v <= -L2[l_sorted[li]]:
                    t_dn[l_sorted[li]] = n
                    li += 1
            k = 0
            for iw in range(len(W2)):
                for il in range(len(L2)):
                    t = min(t_up[iw], t_dn[il], played)
                    rule_dist[k][path[t]] += 1
                    rule_rounds[k] += t
                    k += 1

    return {
        "sessions": n_sessions, "busted": busted, "rounds_sum": rounds_sum, "hands_sum": hands_sum,
        "wagered_sum": wagered_sum, "final": final, "dist_at": dist_at, "peak_dist": peak_dist,
        "ev_by_tc_sum": ev_by_tc_sum, "ev_by_tc_cnt": ev_by_tc_cnt, "wag_by_tc": wag_by_tc, "bet_by_tc": bet_by_tc,
        "trans": trans, "unit_sum": unit_sum, "unit_cnt": unit_cnt, "out_dist": out_dist,
        "rule_dist": rule_dist, "rule_rounds": rule_rounds, "leave_at": leave_at, "leave_tc": leave_tc,
        "max_bet_seen": max_bet_seen,
    }


def merge(parts, rounds):
    out = parts[0]
    for p in parts[1:]:
        for k in ("sessions", "busted", "rounds_sum", "hands_sum", "wagered_sum"):
            out[k] += p[k]
        out["max_bet_seen"] = max(out["max_bet_seen"], p["max_bet_seen"])
        out["final"].update(p["final"])
        out["peak_dist"].update(p["peak_dist"])
        out["trans"].update(p["trans"])
        out["leave_at"].update(p["leave_at"])
        out["leave_tc"].update(p["leave_tc"])
        for n in range(rounds + 1):
            out["dist_at"][n].update(p["dist_at"][n])
        for i in range(N_TC):
            out["ev_by_tc_sum"][i] += p["ev_by_tc_sum"][i]
            out["ev_by_tc_cnt"][i] += p["ev_by_tc_cnt"][i]
            out["wag_by_tc"][i] += p["wag_by_tc"][i]
            out["bet_by_tc"][i] += p["bet_by_tc"][i]
        for i in range(NS):
            out["unit_sum"][i] += p["unit_sum"][i]
            out["unit_cnt"][i] += p["unit_cnt"][i]
            if out["out_dist"] is not None:
                out["out_dist"][i].update(p["out_dist"][i])
        for k in range(len(out["rule_dist"])):
            out["rule_dist"][k].update(p["rule_dist"][k])
            out["rule_rounds"][k] += p["rule_rounds"][k]
    return out


def stats_from_counter(c):
    n = sum(c.values())
    total = sum(k * v for k, v in c.items())
    mean = total / n
    var = sum(v * (k - mean) ** 2 for k, v in c.items()) / n
    keys = sorted(c)

    def q(p):
        target = p * (n - 1)
        acc = 0
        for k in keys:
            acc += c[k]
            if acc - 1 >= target:
                return k
        return keys[-1]

    pos = sum(v for k, v in c.items() if k > 0)
    return {"n": n, "mean": mean / 2.0, "sd": math.sqrt(var) / 2.0, "median": q(0.5) / 2.0,
            "p05": q(0.05) / 2.0, "p10": q(0.10) / 2.0, "p25": q(0.25) / 2.0, "p75": q(0.75) / 2.0,
            "p90": q(0.90) / 2.0, "p95": q(0.95) / 2.0, "min": keys[0] / 2.0, "max": keys[-1] / 2.0,
            "p_profit": pos / n, "p_zero": c.get(0, 0) / n, "p_loss": (n - pos - c.get(0, 0)) / n}


def summarise(r, rounds, min_bet, name, policy):
    N = r["sessions"]
    st = stats_from_counter(r["final"])
    fan = []
    for n in range(rounds + 1):
        f = stats_from_counter(r["dist_at"][n])
        fan.append([n, f["p10"], f["p25"], f["median"], f["p75"], f["p90"], round(f["mean"], 3), round(f["p_profit"], 4)])
    ev_tc = []
    for i in range(N_TC):
        if r["ev_by_tc_cnt"][i] >= 500:
            ev_tc.append({"tc": i + TC_MIN, "rounds": r["ev_by_tc_cnt"][i],
                          "share": r["ev_by_tc_cnt"][i] / max(1, r["hands_sum"]),
                          "ev_per_bet": r["ev_by_tc_sum"][i] / r["ev_by_tc_cnt"][i],
                          "avg_bet": r["bet_by_tc"][i] / r["ev_by_tc_cnt"][i]})
    out = dict(st)
    out.update({
        "name": name, "policy": {k: v for k, v in policy.items() if k not in ("table", "bets")},
        "bust_rate": r["busted"] / N, "mean_rounds": r["rounds_sum"] / N, "mean_hands": r["hands_sum"] / N,
        "mean_wagered": r["wagered_sum"] / N, "max_bet_seen": r["max_bet_seen"],
        "edge_per_wagered": (st["mean"] * N) / r["wagered_sum"] if r["wagered_sum"] else None,
        "per_round": st["mean"] / (r["rounds_sum"] / N) if r["rounds_sum"] else None,
        "se_mean": st["sd"] / math.sqrt(N),
        "fan": fan, "ev_by_tc": ev_tc,
        "final_distribution": {str(k / 2.0): c for k, c in sorted(r["final"].items())},
        "peak": stats_from_counter(r["peak_dist"]),
        "leave_at": {int(k): v / N for k, v in sorted(r["leave_at"].items())},
        "leave_tc": {int(k): v / N for k, v in sorted(r["leave_tc"].items())},
        "elapsed_s": round(r.get("elapsed", 0), 1),
    })
    if policy["kind"] == "playall":
        rules = []
        k = 0
        for w in WIN_TARGETS:
            for l in LOSS_LIMITS:
                s = stats_from_counter(r["rule_dist"][k])
                rules.append({"win_target": w, "loss_limit": l, "mean": s["mean"], "median": s["median"],
                              "p_profit": s["p_profit"], "p10": s["p10"], "mean_rounds": r["rule_rounds"][k] / N})
                k += 1
        out["profit_rules"] = rules
    return out


# ---------------------------------------------------------------------------
# The state model, regularised for the corners nobody visits
# ---------------------------------------------------------------------------

def build_model(m):
    trans = m["trans"]
    tot = [0] * NS
    P = [dict() for _ in range(NS)]
    for (s, s2), c in trans.items():
        P[s][s2] = P[s].get(s2, 0) + c
        tot[s] += c
    for s in range(NS):
        if tot[s] >= 500:
            P[s] = {s2: c / tot[s] for s2, c in P[s].items()}
    for s in range(NS):
        if tot[s] < 500:
            t, d = divmod(s, N_DEPTH)
            donor = None
            for dt in range(1, N_TC):
                for tt in (t - dt, t + dt):
                    if 0 <= tt < N_TC and tot[tt * N_DEPTH + d] >= 500:
                        donor = tt * N_DEPTH + d
                        break
                if donor is not None:
                    break
            P[s] = dict(P[donor]) if donor is not None else {state(0, 0.0): 1.0}

    # per-unit outcome distribution, shrunk toward the true-count marginal where thin
    marg = [Counter() for _ in range(N_TC)]
    for s in range(NS):
        marg[s // N_DEPTH].update(m["out_dist"][s])
    # The edge at a given true count is (by construction of the true count) the same at any
    # depth, and the per-state samples are too thin to say otherwise (SE ~0.5% per state vs
    # 0.5% per count step), so every state shares its count's marginal outcome distribution.
    # Depth still matters through the transitions: how soon the shuffle resets the count.
    O = []
    unit_ev = []
    for s in range(NS):
        mg = marg[s // N_DEPTH]
        total = sum(mg.values()) or 1
        outs = [(k, v / total) for k, v in sorted(mg.items())]
        O.append(outs)
        unit_ev.append(sum(k * p for k, p in outs) / 2.0)
    return {"P": P, "O": O, "unit_ev": unit_ev, "visits": tot,
            "state_ev": [m["unit_sum"][s] / m["unit_cnt"][s] if m["unit_cnt"][s] else None for s in range(NS)]}


# ---------------------------------------------------------------------------
# DP1: walk out or stay, unlimited bankroll
# ---------------------------------------------------------------------------

def solve_dp1(model, ramp, min_bet, rounds):
    P, unit_ev = model["P"], model["unit_ev"]
    reward = [unit_ev[s] * min_bet * units_for(ramp, s // N_DEPTH + TC_MIN) for s in range(NS)]
    V_next = [0.0] * NS
    leave = [None] * rounds
    V0 = None
    for r in range(rounds - 1, -1, -1):
        V = [0.0] * NS
        row = [False] * NS
        for s in range(NS):
            stay = reward[s] + sum(p * V_next[s2] for s2, p in P[s].items())
            if stay < 0:
                row[s] = True
            else:
                V[s] = stay
        leave[r] = row
        V_next = V
        V0 = V
    return {"leave": leave, "start_value": V0[state(0, 0.0)], "reward": reward}


# ---------------------------------------------------------------------------
# DP2: walk out or stay (and optionally how much to bet), with the real stack
# ---------------------------------------------------------------------------

def solve_dp2(model, ramp, min_bet, rounds, table_max, optimise_bet=False):
    """
    V[r][s][b]: expected profit of the rest of the session from state s at round r
    with a stack of b half-units. Leaving is worth 0. Busting is worth 0.
    Returns leave thresholds (highest stack at which you leave, -1 = never) per
    (round, state), the chosen bet units per (round, state, stack) when optimising,
    and the value at the start.
    """
    P, O = model["P"], model["O"]
    max_units = int(table_max // min_bet)
    choices = [u for u in OPT_CHOICES if u <= max_units] if optimise_bet else None
    V_next = [[0.0] * (HB + 1) for _ in range(NS)]
    thr = [None] * rounds
    bets = bytearray(rounds * NS * (HB + 1)) if optimise_bet else None
    tci_of = [s // N_DEPTH + TC_MIN for s in range(NS)]
    V0 = None
    for r in range(rounds - 1, -1, -1):
        W = []
        for s in range(NS):
            acc = [0.0] * (HB + 1)
            for s2, p in P[s].items():
                vn = V_next[s2]
                for b in range(HB + 1):
                    acc[b] += p * vn[b]
            W.append(acc)
        V = []
        row_thr = [-1] * NS
        base = r * NS * (HB + 1)
        for s in range(NS):
            outs = O[s]
            Ws = W[s]
            row = [0.0] * (HB + 1)
            ramp_units = None if optimise_bet else units_for(ramp, tci_of[s])
            for b in range(2, HB + 1):
                best = 0.0
                best_u = 0
                if optimise_bet:
                    cand = [u for u in choices if 2 * u <= b]
                else:
                    cand = [min(ramp_units, b // 2, max_units)]
                for u in cand:
                    v = 0.0
                    gain = u * min_bet / 2.0          # dollars per half-unit of outcome
                    for o, p in outs:
                        nb = b + o * u
                        if nb < 0:
                            nb = 0
                        elif nb > HB:
                            nb = HB
                        v += p * (o * gain + Ws[nb])
                    if v > best:
                        best = v
                        best_u = u
                row[b] = best
                if best_u == 0:
                    row_thr[s] = b
                if optimise_bet:
                    bets[base + s * (HB + 1) + b] = best_u
            V.append(row)
        thr[r] = row_thr
        V_next = V
        V0 = V
    return {"thr": thr, "bets": bets, "V0": V0}


def contiguous_threshold(is_leave):
    """is_leave: list over TC index. Highest TC such that every TC at or below it says leave."""
    best = None
    for t in range(N_TC):
        if is_leave[t]:
            best = t + TC_MIN
        else:
            break
    return best


def dp1_thresholds(leave, rounds, marks):
    out = {}
    for left in marks:
        r = rounds - left
        row = leave[r]
        out[str(left)] = [contiguous_threshold([row[t * N_DEPTH + d] for t in range(N_TC)]) for d in range(N_DEPTH)]
    return out


def stack_key(su, min_bet):
    return str(int(round(su * min_bet)))


def dp2_thresholds(thr, rounds, marks, stacks_units, min_bet):
    """thresholds[stack][rounds left] -> per depth: highest floor(TC) at which the DP leaves with that stack."""
    out = {}
    for su in stacks_units:
        b = min(HB, su * 2)
        per = {}
        for left in marks:
            r = rounds - left
            row = thr[r]
            per[str(left)] = [contiguous_threshold([row[t * N_DEPTH + d] >= b for t in range(N_TC)]) for d in range(N_DEPTH)]
        out[stack_key(su, min_bet)] = per
    return out


def opt_bets_table(bets, rounds, marks, stacks_units, depth_bin, min_bet):
    """What the perfect bettor bets, in units, by true count, for a few stacks and rounds left, mid-shoe."""
    out = {}
    for su in stacks_units:
        b = min(HB, su * 2)
        per = {}
        for left in marks:
            r = rounds - left
            per[str(left)] = [bets[r * NS * (HB + 1) + (t * N_DEPTH + depth_bin) * (HB + 1) + b] for t in range(N_TC)]
        out[stack_key(su, min_bet)] = per
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="path to the blackjack-engine checkout (default: the parent of this folder)")
    ap.add_argument("--sessions", type=int, default=100_000)
    ap.add_argument("--rounds", type=int, default=100)
    ap.add_argument("--bankroll", type=float, default=300)
    ap.add_argument("--bet", type=float, default=15)
    ap.add_argument("--table-max", type=float, default=500)
    ap.add_argument("--seed", type=int, default=20260912)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    repo = os.path.abspath(a.repo)
    rules_over = {}
    workers = max(1, min(a.workers, a.sessions))
    per = [a.sessions // workers + (1 if i < a.sessions % workers else 0) for i in range(workers)]
    jobs_base = [(repo, a.seed + i * 7919, per[i], a.rounds, a.bankroll, a.bet, a.table_max, None, rules_over, False)
                 for i in range(workers) if per[i] > 0]
    MARKS = [m for m in (100, 80, 60, 40, 20, 10, 5, 2, 1) if m <= a.rounds]
    STACKS = [5, 10, 20, 40, 80]       # units of the minimum bet: $75, $150, $300, $600, $1200
    results = {"config": {"sessions": a.sessions, "rounds": a.rounds, "bankroll": a.bankroll, "bet": a.bet,
                          "table_max": a.table_max, "seed": a.seed, "repo": repo, "ramps": RAMPS,
                          "win_targets": WIN_TARGETS, "loss_limits": LOSS_LIMITS, "marks": MARKS,
                          "stacks": [s * a.bet for s in STACKS], "opt_choices": OPT_CHOICES}}
    policies = []
    t_all = time.time()

    def jobs_for(pol, bankroll=None, table_max=None, collect=False):
        return [tuple([j[0], j[1], j[2], j[3], bankroll if bankroll is not None else j[4], j[5],
                       table_max if table_max is not None else j[6], pol, j[8], collect]) for j in jobs_base]

    with Pool(len(jobs_base)) as pool:
        # 1. the state model: unlimited bankroll, 1-8 ramp, index plays, play everything
        print("collecting the count-state model (unlimited bankroll) ...", flush=True)
        t0 = time.time()
        model_policy = {"kind": "playall", "ramp": "1-8", "index": True}
        m = merge(pool.map(worker, jobs_for(model_policy, bankroll=1e9, table_max=1e9, collect=True)), a.rounds)
        m["elapsed"] = time.time() - t0
        ms = summarise(m, a.rounds, a.bet, "model: unlimited bankroll, 1-8, index plays", model_policy)
        for k in ("fan", "final_distribution", "profit_rules"):
            ms.pop(k, None)
        results["model"] = ms
        model = build_model(m)
        results["unit_ev_by_state"] = [[None if model["state_ev"][t * N_DEPTH + d] is None else round(model["state_ev"][t * N_DEPTH + d], 5) for d in range(N_DEPTH)] for t in range(N_TC)]
        results["unit_ev_by_tc"] = [round(model["unit_ev"][t * N_DEPTH], 5) for t in range(N_TC)]
        results["visits_by_state"] = [[model["visits"][t * N_DEPTH + d] for d in range(N_DEPTH)] for t in range(N_TC)]
        print("model pass %.1fs, %d transitions" % (m["elapsed"], sum(model["visits"])), flush=True)

        # 2. queue the plain policies on the pool while the DPs run in this process
        plan = [
            ("flat bet, basic strategy", {"kind": "playall", "ramp": "flat", "index": False}),
            ("flat bet, index plays", {"kind": "playall", "ramp": "flat", "index": True}),
            ("1-4 spread, play everything", {"kind": "playall", "ramp": "1-4", "index": True}),
            ("1-8 spread, basic strategy only", {"kind": "playall", "ramp": "1-8", "index": False}),
            ("1-8 spread, play everything", {"kind": "playall", "ramp": "1-8", "index": True}),
            ("1-12 spread, play everything", {"kind": "playall", "ramp": "1-12", "index": True}),
            ("1-8, leave at TC <= -1", {"kind": "leave_tc", "ramp": "1-8", "index": True, "T": -1}),
            ("1-8, leave at TC <= -2", {"kind": "leave_tc", "ramp": "1-8", "index": True, "T": -2}),
            ("1-8, leave at TC <= -3", {"kind": "leave_tc", "ramp": "1-8", "index": True, "T": -3}),
            ("1-8, leave at TC <= -4", {"kind": "leave_tc", "ramp": "1-8", "index": True, "T": -4}),
            ("1-4, leave at TC <= -2", {"kind": "leave_tc", "ramp": "1-4", "index": True, "T": -2}),
            ("1-8, sit out at TC <= -1, back in at 0", {"kind": "wong", "ramp": "1-8", "index": True, "exit": -1, "enter": 0}),
            ("1-8, sit out below +1, back in at +1", {"kind": "wong", "ramp": "1-8", "index": True, "exit": 0, "enter": 1}),
            ("1-8, sit out below +2, back in at +2", {"kind": "wong", "ramp": "1-8", "index": True, "exit": 1, "enter": 2}),
        ]
        pending = [(name, pol, pool.map_async(worker, jobs_for(pol))) for name, pol in plan]

        # 3. the dynamic programmes
        dp = {}
        for ramp in ("flat", "1-4", "1-8", "1-12"):
            t0 = time.time()
            d1 = solve_dp1(model, ramp, a.bet, a.rounds)
            dp[ramp] = {"dp1_start_value": d1["start_value"],
                        "dp1_thresholds": dp1_thresholds(d1["leave"], a.rounds, MARKS),
                        "reward_by_state": [[round(d1["reward"][t * N_DEPTH + d], 4) for d in range(N_DEPTH)] for t in range(N_TC)]}
            print("DP1 %-5s start value %+.2f  (%.1fs)" % (ramp, d1["start_value"], time.time() - t0), flush=True)
        dp2_tables = {}
        for ramp in ("1-4", "1-8", "1-12"):
            t0 = time.time()
            d2 = solve_dp2(model, ramp, a.bet, a.rounds, a.table_max)
            dp2_tables[ramp] = d2["thr"]
            b0 = min(HB, int(a.bankroll // (a.bet / 2)))
            dp[ramp]["dp2_start_value"] = d2["V0"][state(0, 0.0)][b0]
            dp[ramp]["dp2_thresholds"] = dp2_thresholds(d2["thr"], a.rounds, MARKS, STACKS, a.bet)
            dp[ramp]["dp2_value_by_stack"] = {stack_key(su, a.bet): round(d2["V0"][state(0, 0.0)][min(HB, su * 2)], 3) for su in STACKS}
            print("DP2 %-5s start value with $%g: %+.2f  (%.1fs)" % (ramp, a.bankroll, dp[ramp]["dp2_start_value"], time.time() - t0), flush=True)
        t0 = time.time()
        d2o = solve_dp2(model, "1-8", a.bet, a.rounds, a.table_max, optimise_bet=True)
        b0 = min(HB, int(a.bankroll // (a.bet / 2)))
        dp["optimal"] = {"dp2_start_value": d2o["V0"][state(0, 0.0)][b0],
                         "dp2_thresholds": dp2_thresholds(d2o["thr"], a.rounds, MARKS, STACKS, a.bet),
                         "dp2_value_by_stack": {stack_key(su, a.bet): round(d2o["V0"][state(0, 0.0)][min(HB, su * 2)], 3) for su in STACKS},
                         "bets_mid_shoe": opt_bets_table(d2o["bets"], a.rounds, MARKS, STACKS, 3, a.bet)}
        print("DP2 optimal bets, start value with $%g: %+.2f  (%.1fs)" % (a.bankroll, dp["optimal"]["dp2_start_value"], time.time() - t0), flush=True)
        results["dp"] = dp

        # 4. collect the plain policies, then verify the DP policies
        for name, pol, ar in pending:
            t0 = time.time()
            r = merge(ar.get(), a.rounds)
            r["elapsed"] = time.time() - t0
            s = summarise(r, a.rounds, a.bet, name, pol)
            policies.append(s)
            print("%-44s mean %+7.2f  median %+7.1f  P(profit) %5.1f%%  bust %5.2f%%  rounds %5.1f  hands %5.1f"
                  % (name, s["mean"], s["median"], 100 * s["p_profit"], 100 * s["bust_rate"], s["mean_rounds"], s["mean_hands"]), flush=True)
        verify = [
            ("1-8, DP walk-out (unlimited-bankroll rule)", {"kind": "leave_dp", "ramp": "1-8", "index": True, "table": solve_dp1(model, "1-8", a.bet, a.rounds)["leave"]}),
            ("1-4, DP walk-out with stack", {"kind": "leave_dp2", "ramp": "1-4", "index": True, "table": dp2_tables["1-4"]}),
            ("1-8, DP walk-out with stack", {"kind": "leave_dp2", "ramp": "1-8", "index": True, "table": dp2_tables["1-8"]}),
            ("1-12, DP walk-out with stack", {"kind": "leave_dp2", "ramp": "1-12", "index": True, "table": dp2_tables["1-12"]}),
            ("optimal bets and walk-out (perfect play)", {"kind": "opt_dp2", "ramp": "1-8", "index": True, "bets": bytes(d2o["bets"])}),
        ]
        for name, pol in verify:
            t0 = time.time()
            r = merge(pool.map(worker, jobs_for(pol)), a.rounds)
            r["elapsed"] = time.time() - t0
            s = summarise(r, a.rounds, a.bet, name, pol)
            policies.append(s)
            print("%-44s mean %+7.2f  median %+7.1f  P(profit) %5.1f%%  bust %5.2f%%  rounds %5.1f  hands %5.1f  max bet $%g"
                  % (name, s["mean"], s["median"], 100 * s["p_profit"], 100 * s["bust_rate"], s["mean_rounds"], s["mean_hands"], s["max_bet_seen"]), flush=True)

    results["policies"] = policies
    results["config"]["elapsed_s"] = round(time.time() - t_all, 1)

    print("\nEV per round by true count (1-8 ramp, index plays, unlimited bankroll):")
    for e in results["model"]["ev_by_tc"]:
        print("  TC %+d  %5.1f%% of rounds  %+.3f%% per $ bet  avg bet $%.0f" % (e["tc"], 100 * e["share"], 100 * e["ev_per_bet"], e["avg_bet"]))

    def show(title, table):
        print("\n" + title)
        print("  rounds left  " + "".join("%7s" % ("%d-%d%%" % (d * 10, d * 10 + 10)) for d in range(N_DEPTH)))
        for k, v in table.items():
            print("  %11s  " % k + "".join("%7s" % ("stay" if x is None else "%+d" % x) for x in v))

    show("DP1 (unlimited bankroll), 1-8 ramp: leave when floor(TC) is at or below ...", dp["1-8"]["dp1_thresholds"])
    for st in ("150", "300", "600"):
        show("DP2 1-8 ramp with a $%s stack: leave when floor(TC) is at or below ..." % st, dp["1-8"]["dp2_thresholds"][st])
    print("\nPerfect bettor, mid-shoe (30-40%%), units of $%g by floor(TC) %d..%d:" % (a.bet, TC_MIN, TC_MAX))
    for st, per in dp["optimal"]["bets_mid_shoe"].items():
        print("  stack $%-6s rounds left %d: %s" % (st, MARKS[0], " ".join("%2d" % u for u in per[str(MARKS[0])])))

    if a.out:
        with open(a.out, "w") as f:
            json.dump(results, f, indent=1)
        print("\nwrote", a.out)


if __name__ == "__main__":
    main()
