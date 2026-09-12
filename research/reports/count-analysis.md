# Walking away with the count: card-counting walk-out rules over 100,000 sessions

Setup: $300 bankroll, $15 minimum, $500 maximum, up to 100 rounds, 6 decks, dealer stands on
soft 17, double after split, 3:2 blackjack, cut card at 75%, no continuous shuffler.
Player: Hi-Lo count, floored true count, bet spread by count, Illustrious 18 index plays,
insurance at +3. Engine: `sim.py` from https://github.com/kalebzegeye31/blackjack-engine-
subclassed to count. 100,000 sessions per policy, seed 20260912.

Full numbers: `research/results/count-results.json`.
Solver: `research/count_solver.py`.
Interactive report: `research/reports/count-analysis.html`.

## What one round is worth, by true count (per $ of initial bet)

| TC | −6 | −5 | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +4 | +5 | +6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| result | −3.8% | −2.4% | −2.3% | −1.0% | −1.0% | −0.6% | −0.2% | +0.3% | +0.8% | +1.1% | +2.0% | +2.9% | +4.3% |
| share of rounds | 2.4% | 1.8% | 3.4% | 6.1% | 12.1% | 20.4% | 29.0% | 11.5% | 5.9% | 3.2% | 1.8% | 1.0% | 1.2% |

Rounds at +1 or better: 24.8%. Everything a counter earns comes from that quarter.

## The decision tree (seated counter, $300, $15 table, 1-8 spread)

Read from the top before every round: floor the true count, know the rounds left, know
how deep the shoe is.

1. **Chips under $15** → you are out. Under $30 you cannot double or split.
2. **Can you sit out hands and keep the seat?**
   - **Yes → never walk out.** Bet only at floor(TC) ≥ +1 (2/3/4 units at +1/+2/+3 on
     the 1-4 spread), sit out everything else.
     +$9.11 per 100 rounds (±0.74), broke 18%, 21 hands bet.
     (1-8 spread: +$10.39 ±1.01, broke 30%. Flat $15 only at +1 or better: +$3.62 ±0.27,
     broke 0.4%.)
   - **No** → continue.
3. **floor(TC) ≥ +1 → stay.** Bet 2/4/6/8 units at +1/+2/+3/+4, insure at +3, index plays.
4. **TC 0 or below → depends on rounds left:**
   - **40 or more left:** stay at the minimum. Leave only at TC ≤ −4 while the shoe is
     10–60% dealt. Past 60% the shuffle is near: sit it out at $15. (80+ left: the line
     is −5; under $150 in chips: −3.)
   - **11 to 39 left:** leave at TC ≤ −2 if under 20% dealt, ≤ −3 at 20–50%, ≤ −4 past 50%.
   - **3 to 10 left:** leave at TC ≤ −1 if under 20% dealt, ≤ −2 at 20–50%, ≤ −3 past 50%.
   - **1 or 2 left:** leave at TC ≤ 0. Only a positive count is worth one more hand.

Followed exactly (the full grid below), this earned +$4.66 ±1.01 per session on the 1-8
spread (broke 29%) and +$4.35 ±0.73 on 1-4 (broke 17%). The simpler "leave at TC ≤ −3
whatever the depth" earned +$4.55 ±0.84 with 21% broke. With $300 the 1-4 spread is the
better choice: same profit, half the ruin.

### The full grid (1-8 spread, $300 stack): leave when floor(TC) is at or below

| rounds left | 0-10% | 10-20% | 20-30% | 30-40% | 40-50% | 50-60% | 60-70% | 70-80% |
|---|---|---|---|---|---|---|---|---|
| 100 | stay | stay | −6 | −6 | −6 | stay | stay | stay |
| 80 | stay | stay | −5 | −5 | −6 | stay | stay | stay |
| 60 | stay | −4 | −4 | −4 | −5 | −6 | stay | stay |
| 40 | stay | −4 | −4 | −4 | −4 | −4 | −6 | stay |
| 20 | −2 | −2 | −3 | −3 | −3 | −4 | −4 | −4 |
| 10 | −1 | −1 | −2 | −2 | −2 | −3 | −3 | −2 |
| 5 | 0 | −1 | −1 | −1 | −1 | −2 | −2 | −1 |
| 2 | 0 | 0 | 0 | 0 | 0 | −1 | −1 | −1 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Grids for $150, $600 and $1,200 stacks, and for the 1-4, 1-12 and optimal-bet
variants, are in the JSON (`dp.<ramp>.dp2_thresholds`).

## Every policy, verified with $300 (100,000 sessions each)

| policy | average | ± SE | median | finish ahead | broke | rounds | hands bet |
|---|---|---|---|---|---|---|---|
| flat bet, basic strategy | −$6.38 | 0.54 | −$7.50 | 47.3% | 8.8% | 97.4 | 97.4 |
| flat bet, index plays | −$5.35 | 0.54 | −$7.50 | 47.8% | 8.9% | 97.4 | 97.4 |
| flat bet, sit out below +1 | +$3.62 | 0.27 | $0 | 47.3% | 0.4% | 99.9 | 24.7 |
| 1-4 spread, play everything | +$0.27 | 0.85 | −$15 | 46.9% | 27.5% | 87.6 | 87.6 |
| 1-4, leave at TC ≤ −2 | +$3.16 | 0.53 | $0 | 48.1% | 9.7% | 25.5 | 25.5 |
| 1-4, DP walk-out with stack | +$4.35 | 0.73 | −$7.50 | 47.7% | 17.1% | 56.2 | 56.2 |
| 1-4, sit out at TC ≤ −1, back in at 0 | +$7.57 | 0.78 | $0 | 48.8% | 21.7% | 89.9 | 47.3 |
| 1-4, sit out below +1, back in at +1 | +$9.11 | 0.74 | $0 | 46.6% | 18.5% | 91.5 | 21.5 |
| 1-8 spread, basic strategy only | −$0.54 | 1.06 | −$67.50 | 43.1% | 36.9% | 82.2 | 82.2 |
| 1-8 spread, play everything | +$0.73 | 1.07 | −$67.50 | 42.8% | 37.3% | 82.0 | 82.0 |
| 1-8, leave at TC ≤ −1 | +$1.42 | 0.42 | $0 | 44.0% | 4.9% | 7.4 | 7.4 |
| 1-8, leave at TC ≤ −2 | +$3.20 | 0.70 | $0 | 46.2% | 14.2% | 23.9 | 23.9 |
| 1-8, leave at TC ≤ −3 | +$4.55 | 0.84 | −$7.50 | 46.1% | 20.7% | 39.0 | 39.0 |
| 1-8, leave at TC ≤ −4 | +$4.51 | 0.91 | −$15 | 45.5% | 25.2% | 50.7 | 50.7 |
| 1-8, DP walk-out (unlimited-bankroll rule) | +$3.23 | 1.04 | −$52.50 | 43.8% | 34.6% | 70.2 | 70.2 |
| 1-8, DP walk-out with stack | +$4.66 | 1.01 | −$45 | 42.5% | 28.8% | 63.1 | 63.1 |
| 1-8, sit out at TC ≤ −1, back in at 0 | +$9.06 | 1.03 | −$30 | 44.9% | 32.1% | 84.3 | 43.7 |
| 1-8, sit out below +1, back in at +1 | +$10.39 | 1.01 | −$15 | 42.0% | 29.7% | 85.4 | 19.2 |
| 1-8, sit out below +2, back in at +2 | +$9.31 | 0.96 | $0 | 35.4% | 26.9% | 86.9 | 9.7 |
| 1-12 spread, play everything | +$1.01 | 1.25 | −$112.50 | 39.8% | 42.2% | 79.3 | 79.3 |
| 1-12, DP walk-out with stack | +$3.35 | 1.20 | −$82.50 | 39.5% | 35.3% | 64.4 | 64.4 |
| optimal bets and walk-out (perfect play) | +$4.04 | 2.29 | −$292.50 | 24.5% | 55.3% | 66.1 | 66.1 |

Model values (what the solve expected before ruin effects the model cannot see): 1-8 with
$300 +$7.48, with unlimited bankroll +$14.48; 1-4 with $300 +$4.39; optimal bets with
$300 +$15.50. The gap between model and simulation grows with the bet size because a big
bet from a thin stack cannot be doubled or split.

## Findings

- **Sitting out beats walking out.** Skipping negative counts costs nothing; leaving forfeits
  the rest of the session. If back-counting is allowed, never walk out.
- **Walking out is worth about $4.50 per session** over playing through, on a game that is
  otherwise break-even for a $300 counter.
- **The threshold moves with the clock and the shoe.** Tolerate −4 with a long session ahead
  and a shuffle near; tolerate nothing but a positive count in the last two rounds.
- **$300 is far too small for a 1-8 spread.** Playing through busts 37% of sessions; the
  1-4 spread earns the same and busts half as often. The perfect-EV bettor busts 55%.
- **Profit targets now cost money.** With a positive edge per round, "leave when up $30" turns
  +$0.73 into −$0.99 despite winning 87% of nights. Only a loss limit helps, slightly.
- **Index plays are worth about $1 per 100 flat-bet hands** (−$6.38 → −$5.35).

## Method

State model from 100,000 unlimited-bankroll sessions (10 million rounds): outcome
distribution per unit bet pooled by true count, transitions between (count, depth) states
measured directly. Backward induction over 100 rounds × 13 counts × 8 depth bins × 241
stack levels; the perfect-bettor variant also chooses among 1/2/4/8/16/33 units. Every
policy then replayed on fresh sessions with $300 and common seeds. 23 policies, about
180 million rounds, four minutes on 16 cores.

## Reproduce

    python3 research/count_solver.py \
        --sessions 100000 --rounds 100 \
        --bankroll 300 --bet 15 --table-max 500 --seed 20260912 \
        --out research/results/count-results.json
