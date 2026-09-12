# Research: when to walk away

Two simulation studies built on `sim.py` (the fast table that shares its rules and
strategy chart with the trainer), each run for 100,000 sessions, plus the tools to
reproduce them. Nothing in here touches the app; it imports the engine from the
repository root.

| Question | Solver | Results | Report |
|---|---|---|---|
| Flat $15 bets, basic strategy, $300 bankroll, 100 hands: when is the best time to stop? | `stop_solver.py` | `results/stop-results.json` | `reports/stop-analysis.md` · `reports/stop-analysis.html` |
| Same table, Hi-Lo counter with a bet spread and index plays: when should you walk out? | `count_solver.py` | `results/count-results.json` | `reports/count-analysis.md` · `reports/count-analysis.html` |

The HTML reports are self-contained (charts drawn from the embedded numbers) and open
in any browser. Published copies:

- Flat bet: https://claude.ai/code/artifact/88de45a5-19aa-4b8f-a08b-b520d7a61165
- Counting: https://claude.ai/code/artifact/236ba709-fdbc-41ac-8e93-d6a81a1612ce

## Findings in brief

**Flat bet, basic strategy.** Every hand costs about 6.5 cents on average (house edge
0.436%, against the published 0.43%). All 208 stopping rules tested (fixed lengths, win
targets, loss limits, trailing stops) land on one line: expected result equals −$0.065
times hands played. The best time to stop for expected profit is before the first hand.
Rules change the shape of the night, not its average: leaving the first moment you are
ahead wins 92% of sessions, and the other 8% lose enough to cancel it. 92% of sessions
were ahead at some point (average peak +$126), and the timing of the peak follows the
arcsine law, so there is no signal to act on.

**Counting.** With Hi-Lo, the Illustrious 18 and insurance at +3, 24.8% of rounds carry
a positive edge (+0.3% at true count +1, +1.1% at +3, +2.0% at +4). The walk-out
decision was solved by backward induction over rounds left, true count, shoe depth and
stack, then every policy was replayed on 100,000 sessions with the real $300:

| Policy | Average per session | Broke |
|---|---|---|
| flat $15, basic strategy | −$6.38 | 8.8% |
| 1-8 spread, play every round | +$0.73 | 37.3% |
| 1-8 spread, walk-out grid | +$4.66 | 28.8% |
| 1-4 spread, walk-out grid | +$4.35 | 17.1% |
| 1-4 spread, sit out below +1 | +$9.11 | 18.5% |
| flat $15 only at +1 or better | +$3.62 | 0.4% |

Sitting out negative counts beats walking out on them. If you must bet every round, the
leave threshold depends on the clock and the shoe: tolerate −4 with 40 or more rounds
left, −2/−3/−4 by depth with 11 to 39 left, −1/−2/−3 with 3 to 10 left, and only a
positive count in the last two rounds. $300 is far too small for a 1-8 spread; the 1-4
spread earns the same and busts half as often. Profit targets now cost money.

## Reproduce

Both solvers use only the standard library and 16 worker processes by default.

```
python3 research/stop_solver.py --sessions 100000 --hands 100 --bankroll 300 --bet 15 \
    --seed 20260912 --out research/results/stop-results.json          # about 12 s

python3 research/count_solver.py --sessions 100000 --rounds 100 --bankroll 300 --bet 15 \
    --table-max 500 --seed 20260912 --out research/results/count-results.json   # about 4 min
```

Flags `--h17`, `--no-das` and `--six-five` re-run the flat-bet study under the harsher
rule sets the trainer supports. Seeds are fixed, so the numbers in the reports come back
exactly.

`play_api_demo.py` plays one $300 session through a running `server.py` over HTTP,
choosing every move from `engine.chart_play`, and prints the bankroll after each hand.

## What is where in the JSON

- `stop-results.json`: `baseline_play_all`, `fixed_length` (stats after n hands),
  `hindsight_peak`, `peak_hand_distribution`, `final_distribution`, `rules` (every
  win-target / loss-limit / trailing-stop combination), `next_hand_ev_by_position`.
- `count-results.json`: `model.ev_by_tc` (edge and frequency by true count),
  `dp.<ramp>.dp2_thresholds[stack][rounds left]` (the leave grids, one entry per 10%
  of shoe depth; `null` means stay), `dp.optimal.bets_mid_shoe`, and `policies` with
  the full result distribution of each policy.

## Method notes

- Rules: 6 decks, dealer stands on soft 17, double after split, no re-splitting aces,
  up to four hands, 3:2 blackjack, cut card at 75%, fresh shoe each session.
- The counting player floors the true count, bets 1 unit at 0 and below, and does not
  count the dealer's hole card until it is turned over.
- Standard error of a flat-bet session average is about $0.5; counting policies are
  near $1 because the spread triples the variance.
- The counting state model pools outcomes by true count (the count already normalises
  for depth); depth enters through the measured transitions, which is where the
  shuffle lives. The bankroll-aware solve assumes a bet can always be doubled or split,
  so it overestimates policies that bet a large share of the stack; the simulations
  are the ground truth.
