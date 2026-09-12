#!/usr/bin/env python3
"""
When is the best time to stop?  A stopping-rule solver for blackjack sessions.

Plays N independent sessions (default 100,000) of up to H hands (default 100)
with a fixed bankroll and a flat bet, using the fast table in sim.py from
https://github.com/kalebzegeye31/blackjack-engine-  (same rules and the same
basic-strategy chart as the trainer; 6 decks, dealer stands on soft 17, double
after split, 3:2 blackjack, 75% penetration, perfect basic strategy).

For every session the whole profit path is kept, so every stopping rule can be
scored on the same 100,000 sessions without re-dealing:

  * fixed length      - stop after exactly n hands, for every n from 0 to H
  * win target / loss limit  - leave when up W or down L, whichever comes first
  * trailing stop     - leave when you have given back D from the session high
  * hindsight         - the peak of each path, and the hand it happened on
  * next-hand EV by current position (does being up or down change the odds?)

Usage:
  python3 research/stop_solver.py \
      [--sessions 100000] [--hands 100] [--bankroll 300] [--bet 15] \
      [--seed 20260912] [--workers 16] [--out results.json]
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from multiprocessing import Pool

# Thresholds in dollars.  None means "this side never stops you".
WIN_TARGETS = [7.5, 15, 22.5, 30, 45, 60, 75, 90, 105, 120, 150, 180, 210, 240, 300, None]
LOSS_LIMITS = [15, 30, 45, 60, 75, 90, 120, 150, 180, 210, 240, 270, None]
TRAIL_STOPS = [15, 30, 45, 60, 75, 90, 120, 150, None]

INF = 10 ** 9


def _half(x):
    """Dollars -> half-dollar integer units (a 3:2 blackjack on $15 pays $22.50)."""
    return None if x is None else int(round(x * 2))


def worker(job):
    repo, seed, n_sessions, hands, bankroll, bet, rules_over = job
    sys.path.insert(0, repo)
    import random
    import rules as R
    import sim as S

    rset = R.normalise(rules_over or {})
    rng = random.Random(seed)
    sim = S.Sim(rset, decks=rset["decks"], penetration=0.75, rng=rng)

    W2 = [_half(w) for w in WIN_TARGETS]
    L2 = [_half(l) for l in LOSS_LIMITS]
    D2 = [_half(d) for d in TRAIL_STOPS]
    w_sorted = [i for i, w in enumerate(W2) if w is not None]     # already ascending
    l_sorted = [i for i, l in enumerate(L2) if l is not None]
    d_sorted = [i for i, d in enumerate(D2) if d is not None]

    n_wl = len(W2) * len(L2)
    n_wd = len(W2) * len(D2)
    rule_dist = [Counter() for _ in range(n_wl + n_wd)]
    rule_hands = [0] * (n_wl + n_wd)
    rule_hit_up = [0] * (n_wl + n_wd)
    rule_hit_dn = [0] * (n_wl + n_wd)

    sum_at = [0] * (hands + 1)
    pos_at = [0] * (hands + 1)
    dist_at = [Counter() for _ in range(hands + 1)]
    peak_dist = Counter()
    peak_hand_dist = Counter()
    trough_dist = Counter()
    cond_sum = Counter()
    cond_cnt = Counter()
    busted = 0
    bust_hand = Counter()
    hands_played_total = 0

    for _ in range(n_sessions):
        sim.shuffle()                       # fresh shoe each session, like run_session
        stack = float(bankroll)
        path = [0] * (hands + 1)
        played = hands
        for n in range(1, hands + 1):
            if sim.cut_card():
                sim.shuffle()
            b = min(bet, stack)
            if b < bet:                     # cannot cover a minimum bet: busted out
                played = n - 1
                last = path[n - 1]
                for m in range(n, hands + 1):
                    path[m] = last
                break
            stack += sim.round(b, 0.0, None, bankroll=stack)
            path[n] = int(round((stack - bankroll) * 2))
        if played < hands:
            busted += 1
            bust_hand[played] += 1
        hands_played_total += played

        # ---- first-hit times for every threshold, one pass ----
        t_up = [INF] * len(W2)
        t_dn = [INF] * len(L2)
        t_tr = [INF] * len(D2)
        wi = li = di = 0
        runmax = 0
        peak, peak_hand, trough = 0, 0, 0
        for n in range(1, played + 1):
            v = path[n]
            if v > runmax:
                runmax = v
            if v > peak:
                peak, peak_hand = v, n
            if v < trough:
                trough = v
            while wi < len(w_sorted) and v >= W2[w_sorted[wi]]:
                t_up[w_sorted[wi]] = n
                wi += 1
            while li < len(l_sorted) and v <= -L2[l_sorted[li]]:
                t_dn[l_sorted[li]] = n
                li += 1
            dd = runmax - v
            while di < len(d_sorted) and dd >= D2[d_sorted[di]]:
                t_tr[d_sorted[di]] = n
                di += 1
            # next-hand change conditioned on where you stood before it
            prev = path[n - 1]
            bucket = math.floor(prev / (2.0 * bet))      # in units of one bet
            cond_sum[bucket] += v - prev
            cond_cnt[bucket] += 1

        peak_dist[peak] += 1
        peak_hand_dist[peak_hand] += 1
        trough_dist[trough] += 1

        for n in range(hands + 1):
            v = path[n]
            sum_at[n] += v
            if v > 0:
                pos_at[n] += 1
            dist_at[n][v] += 1

        k = 0
        for iw in range(len(W2)):
            tu = t_up[iw]
            for il in range(len(L2)):
                td = t_dn[il]
                t = tu if tu < td else td
                if t > played:
                    t = played
                rule_dist[k][path[t]] += 1
                rule_hands[k] += t
                if tu <= td and tu <= played and tu < INF:
                    rule_hit_up[k] += 1
                elif td <= played and td < INF:
                    rule_hit_dn[k] += 1
                k += 1
        for iw in range(len(W2)):
            tu = t_up[iw]
            for idd in range(len(D2)):
                td = t_tr[idd]
                t = tu if tu < td else td
                if t > played:
                    t = played
                rule_dist[k][path[t]] += 1
                rule_hands[k] += t
                if tu <= td and tu <= played and tu < INF:
                    rule_hit_up[k] += 1
                elif td <= played and td < INF:
                    rule_hit_dn[k] += 1
                k += 1

    return {
        "sessions": n_sessions,
        "busted": busted,
        "bust_hand": bust_hand,
        "hands_played_total": hands_played_total,
        "sum_at": sum_at,
        "pos_at": pos_at,
        "dist_at": dist_at,
        "peak_dist": peak_dist,
        "peak_hand_dist": peak_hand_dist,
        "trough_dist": trough_dist,
        "cond_sum": cond_sum,
        "cond_cnt": cond_cnt,
        "rule_dist": rule_dist,
        "rule_hands": rule_hands,
        "rule_hit_up": rule_hit_up,
        "rule_hit_dn": rule_hit_dn,
    }


# ---------------------------------------------------------------------------
# Reducing 100,000 sessions to numbers
# ---------------------------------------------------------------------------

def stats_from_counter(c):
    """mean / sd / median / quantiles / P(>0) from a Counter of half-dollar outcomes."""
    n = sum(c.values())
    if not n:
        return None
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
    zero = c.get(0, 0)
    return {
        "n": n,
        "mean": mean / 2.0,
        "sd": math.sqrt(var) / 2.0,
        "median": q(0.5) / 2.0,
        "p05": q(0.05) / 2.0, "p10": q(0.10) / 2.0, "p25": q(0.25) / 2.0,
        "p75": q(0.75) / 2.0, "p90": q(0.90) / 2.0, "p95": q(0.95) / 2.0,
        "min": keys[0] / 2.0, "max": keys[-1] / 2.0,
        "p_profit": pos / n, "p_zero": zero / n, "p_loss": (n - pos - zero) / n,
    }


def merge(parts, hands):
    out = parts[0]
    for p in parts[1:]:
        out["sessions"] += p["sessions"]
        out["busted"] += p["busted"]
        out["bust_hand"].update(p["bust_hand"])
        out["hands_played_total"] += p["hands_played_total"]
        for n in range(hands + 1):
            out["sum_at"][n] += p["sum_at"][n]
            out["pos_at"][n] += p["pos_at"][n]
            out["dist_at"][n].update(p["dist_at"][n])
        out["peak_dist"].update(p["peak_dist"])
        out["peak_hand_dist"].update(p["peak_hand_dist"])
        out["trough_dist"].update(p["trough_dist"])
        out["cond_sum"].update(p["cond_sum"])
        out["cond_cnt"].update(p["cond_cnt"])
        for k in range(len(out["rule_dist"])):
            out["rule_dist"][k].update(p["rule_dist"][k])
            out["rule_hands"][k] += p["rule_hands"][k]
            out["rule_hit_up"][k] += p["rule_hit_up"][k]
            out["rule_hit_dn"][k] += p["rule_hit_dn"][k]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="path to the blackjack-engine checkout (default: the parent of this folder)")
    ap.add_argument("--sessions", type=int, default=100_000)
    ap.add_argument("--hands", type=int, default=100)
    ap.add_argument("--bankroll", type=float, default=300)
    ap.add_argument("--bet", type=float, default=15)
    ap.add_argument("--seed", type=int, default=20260912)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--out", default=None, help="write full results as JSON here")
    ap.add_argument("--h17", action="store_true", help="dealer hits soft 17")
    ap.add_argument("--no-das", action="store_true", help="no double after split")
    ap.add_argument("--six-five", action="store_true", help="blackjack pays 6:5")
    a = ap.parse_args()

    rules_over = {"hit_soft_17": a.h17, "das": not a.no_das,
                  "blackjack_pays": 1.2 if a.six_five else 1.5}
    repo = os.path.abspath(a.repo)
    if not os.path.exists(os.path.join(repo, "sim.py")):
        sys.exit("no sim.py in %s" % repo)

    workers = max(1, min(a.workers, a.sessions))
    per = [a.sessions // workers + (1 if i < a.sessions % workers else 0) for i in range(workers)]
    jobs = [(repo, a.seed + i * 7919, per[i], a.hands, a.bankroll, a.bet, rules_over)
            for i in range(workers) if per[i] > 0]

    t0 = time.time()
    with Pool(len(jobs)) as pool:
        parts = pool.map(worker, jobs)
    r = merge(parts, a.hands)
    elapsed = time.time() - t0
    N = r["sessions"]
    hands_dealt = r["hands_played_total"]

    # ---- fixed-length stops ----
    fixed = []
    for n in range(a.hands + 1):
        s = stats_from_counter(r["dist_at"][n])
        s["hands"] = n
        fixed.append(s)

    # ---- win/loss and win/trailing rules ----
    rules = []
    k = 0
    for w in WIN_TARGETS:
        for l in LOSS_LIMITS:
            s = stats_from_counter(r["rule_dist"][k])
            s.update({"kind": "win_loss", "win_target": w, "loss_limit": l, "trail": None,
                      "mean_hands": r["rule_hands"][k] / N,
                      "p_hit_win": r["rule_hit_up"][k] / N,
                      "p_hit_stop": r["rule_hit_dn"][k] / N})
            rules.append(s)
            k += 1
    for w in WIN_TARGETS:
        for d in TRAIL_STOPS:
            s = stats_from_counter(r["rule_dist"][k])
            s.update({"kind": "win_trail", "win_target": w, "loss_limit": None, "trail": d,
                      "mean_hands": r["rule_hands"][k] / N,
                      "p_hit_win": r["rule_hit_up"][k] / N,
                      "p_hit_stop": r["rule_hit_dn"][k] / N})
            rules.append(s)
            k += 1

    peak = stats_from_counter(r["peak_dist"])
    trough = stats_from_counter(r["trough_dist"])
    ever_ahead = sum(v for kk, v in r["peak_dist"].items() if kk > 0) / N
    peak_hand = {int(h): c / N for h, c in sorted(r["peak_hand_dist"].items())}
    cond = []
    for b in sorted(r["cond_cnt"]):
        c = r["cond_cnt"][b]
        if c >= 200:
            cond.append({"position_from": b * a.bet, "position_to": (b + 1) * a.bet,
                         "hands": c, "next_hand_ev": r["cond_sum"][b] / c / 2.0})

    baseline = fixed[a.hands]
    result = {
        "config": {"sessions": N, "hands": a.hands, "bankroll": a.bankroll, "bet": a.bet,
                   "seed": a.seed, "rules": rules_over, "repo": repo,
                   "elapsed_s": round(elapsed, 1), "hands_dealt": hands_dealt},
        "baseline_play_all": dict(baseline, bust_rate=r["busted"] / N,
                                  mean_hands=hands_dealt / N,
                                  edge_per_initial_bet=(baseline["mean"] / (hands_dealt / N) / a.bet)),
        "bust_by_hand": {int(h): c for h, c in sorted(r["bust_hand"].items())},
        "fixed_length": fixed,
        "hindsight_peak": dict(peak, p_ever_ahead=ever_ahead),
        "hindsight_trough": trough,
        "peak_hand_distribution": peak_hand,
        # full outcome distributions, keyed by dollars (x2 -> half-dollar units internally)
        "final_distribution": {str(k / 2.0): c for k, c in sorted(r["dist_at"][a.hands].items())},
        "peak_distribution": {str(k / 2.0): c for k, c in sorted(r["peak_dist"].items())},
        "trough_distribution": {str(k / 2.0): c for k, c in sorted(r["trough_dist"].items())},
        "next_hand_ev_by_position": cond,
        "rules": rules,
        "win_targets": WIN_TARGETS, "loss_limits": LOSS_LIMITS, "trail_stops": TRAIL_STOPS,
    }

    # ---- console summary ----
    print("%d sessions x up to %d hands, $%g bankroll, $%g flat bet  (%.1fs, %d hands dealt)"
          % (N, a.hands, a.bankroll, a.bet, elapsed, hands_dealt))
    b = result["baseline_play_all"]
    print("\nPLAY ALL %d HANDS (or until broke)" % a.hands)
    print("  mean %+.2f  median %+.2f  sd %.2f  P(profit) %.1f%%  bust %.2f%%  edge %.3f%% of initial bet"
          % (b["mean"], b["median"], b["sd"], 100 * b["p_profit"], 100 * b["bust_rate"],
             100 * b["edge_per_initial_bet"]))
    print("  p10 %+.1f  p25 %+.1f  p75 %+.1f  p90 %+.1f  best %+.1f  worst %+.1f"
          % (b["p10"], b["p25"], b["p75"], b["p90"], b["max"], b["min"]))

    print("\nSTOP AFTER EXACTLY n HANDS   (mean profit / P(profit>0))")
    for n in (0, 1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        if n <= a.hands:
            f = fixed[n]
            print("  n=%3d  mean %+6.2f  median %+6.1f  P(profit) %5.1f%%" % (n, f["mean"], f["median"], 100 * f["p_profit"]))

    print("\nHINDSIGHT (the best moment to have stopped, known only afterwards)")
    print("  P(ever ahead at some point) %.1f%%" % (100 * ever_ahead))
    print("  peak profit: mean %+.2f  median %+.1f  p90 %+.1f" % (peak["mean"], peak["median"], peak["p90"]))
    print("  worst point: mean %+.2f  median %+.1f  p10 %+.1f" % (trough["mean"], trough["median"], trough["p10"]))
    top = sorted(peak_hand.items(), key=lambda kv: -kv[1])[:5]
    print("  hand on which the peak happened, most common: " + ", ".join("%d (%.1f%%)" % (h, 100 * p) for h, p in top))

    print("\nNEXT-HAND EV BY CURRENT POSITION  (is there ever a state worth continuing from?)")
    for c in cond:
        print("  %+7.0f .. %+7.0f : %+.4f per hand  (%d hands)" % (c["position_from"], c["position_to"], c["next_hand_ev"], c["hands"]))

    def fmt(x):
        return "none" if x is None else "$%g" % x

    print("\nWIN TARGET x LOSS LIMIT, mean profit  (rows: win target, cols: loss limit)")
    print("        " + "".join("%8s" % fmt(l) for l in LOSS_LIMITS))
    for w in WIN_TARGETS:
        row = [x for x in rules if x["kind"] == "win_loss" and x["win_target"] == w]
        print("%7s " % fmt(w) + "".join("%+8.2f" % x["mean"] for x in row))
    print("\nWIN TARGET x LOSS LIMIT, P(profit > 0)")
    print("        " + "".join("%8s" % fmt(l) for l in LOSS_LIMITS))
    for w in WIN_TARGETS:
        row = [x for x in rules if x["kind"] == "win_loss" and x["win_target"] == w]
        print("%7s " % fmt(w) + "".join("%7.1f%%" % (100 * x["p_profit"]) for x in row))
    print("\nWIN TARGET x TRAILING STOP, mean profit")
    print("        " + "".join("%8s" % fmt(d) for d in TRAIL_STOPS))
    for w in WIN_TARGETS:
        row = [x for x in rules if x["kind"] == "win_trail" and x["win_target"] == w]
        print("%7s " % fmt(w) + "".join("%+8.2f" % x["mean"] for x in row))

    playing = [x for x in rules if x["mean_hands"] > 0]
    best_mean = max(playing, key=lambda x: x["mean"])
    best_p = max(playing, key=lambda x: x["p_profit"])
    best_med = max(playing, key=lambda x: (x["median"], x["mean"]))
    print("\nBEST RULES AMONG THOSE THAT ACTUALLY PLAY")
    for label, x in (("highest mean profit", best_mean), ("highest P(profit)", best_p), ("highest median", best_med)):
        print("  %-22s %s: win %s / %s %s  ->  mean %+.2f  median %+.1f  P(profit) %.1f%%  avg hands %.1f"
              % (label, x["kind"], fmt(x["win_target"]),
                 "loss" if x["kind"] == "win_loss" else "trail",
                 fmt(x["loss_limit"] if x["kind"] == "win_loss" else x["trail"]),
                 x["mean"], x["median"], 100 * x["p_profit"], x["mean_hands"]))

    if a.out:
        with open(a.out, "w") as f:
            json.dump(result, f, indent=1)
        print("\nwrote", a.out)


if __name__ == "__main__":
    main()
