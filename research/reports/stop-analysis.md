# When to walk away: blackjack stopping rules over 100,000 sessions

Setup: $300 bankroll, $15 flat bet per hand, perfect basic strategy, up to 100 hands.
Engine: `sim.py` from https://github.com/kalebzegeye31/blackjack-engine- (6 decks, dealer
stands on soft 17, double after split, 3:2 blackjack, 75% penetration, fresh shoe per session).
100,000 independent sessions, seed 20260912, 9,742,828 hands dealt in 11.6 s on 16 cores.

Full numbers: `research/results/stop-results.json`.
Solver: `research/stop_solver.py`.
Interactive report: `research/reports/stop-analysis.html`.

## The answer

**For the highest expected profit, stop before the first hand.** Every hand costs
$0.065 on average (house edge 0.436% of a $15 bet, matching the published 0.43%), and
nothing about the session so far changes that. All 208 stopping rules tested land on
one line:

    expected result per session = −$0.0652 × average hands played

No rule is above the line. Stopping rules change the *shape* of the night (how often
you leave a winner, how bad the bad nights are), never the average.

## Playing all 100 hands (or until broke)

| measure | value |
|---|---|
| average result | −$6.38 (standard error ±$0.54) |
| median | −$7.50 |
| standard deviation | $169.87 |
| finish ahead | 47.3% |
| go broke before hand 100 | 8.79% (never before hand 17) |
| worst tenth ends below | −$255 |
| best tenth ends above | +$217.50 |

## Hindsight: the best moment to have stopped

| measure | value |
|---|---|
| sessions that were ahead at some point | 92.2% |
| average session peak | +$125.88 |
| median peak | +$105 |
| top tenth of peaks | above +$270 |
| average session low point | −$126.70 |

When the peak happens follows the arcsine law: most often at hand 100 (4.0%, the
session was still climbing) or hand 1 (3.4%, it never got better than the first win),
least often in the middle. 7.8% of sessions were never ahead at all. There is no
signal that tells you the peak is happening.

## Chance of being up by a target at some point within 100 hands

| target | reached |
|---|---|
| +$15 | 91.1% |
| +$30 | 83.7% |
| +$45 | 76.6% |
| +$60 | 69.7% |
| +$90 | 57.0% |
| +$105 | 51.1% |
| +$150 | 35.7% |
| +$210 | 20.4% |
| +$300 | 7.2% |

## Best rule for each goal

| goal | rule | average | median | bad night (p10) | avg hands | finish ahead |
|---|---|---|---|---|---|---|
| highest expected profit | don't sit down | $0 | $0 | $0 | 0 | — |
| most nights ending ahead | leave the first time you're up anything, no loss limit | −$0.65 | +$15 | +$7.50 | 13.6 | 92.2% |
| highest median | up $105 target, down $210 limit | −$3.78 | +$105 | −$217.50 | 60.2 | 57.5% |
| sit the full 100 | no target, no limit | −$6.38 | −$7.50 | −$255 | 97.4 | 47.3% |
| cap the damage | no target, down $150 limit | −$5.69 | −$30 | −$150 | 80.6 | 43.9% |

The "leave the first time you're up" rule wins 92% of nights, but the 8% that never
see a profit play all 100 hands and lose about $190 on average (worst 5% end below
−$165), which cancels the small wins exactly.

Win target × loss limit grids (mean result and P(finish ahead)) and the trailing-stop
grid are printed by the solver and stored in the JSON.

## Is there ever a state worth continuing from?

Grouping every hand by the player's position going in ($15 buckets) and averaging the
next hand's result: every well-sampled bucket sits on −$0.065 within its standard
error. Being down does not make you due; being up does not make you hot. The only
buckets that drift are near the bottom of the bankroll, where the player can no longer
afford to double or split.

## One real session through the trainer's API

Played card by card via `server.py` (account "Claude stop-solver demo", $300 buy-in,
$15 bets, chart moves from `engine.chart_play`): graded 100% accurate, peaked at
+$67.50 after hand 13, finished −$127.50 after 100 hands. One draw from the
distribution above.

## Assumptions and limits

- "$15 buy-in" is read as a $15 bet per hand; $300 is the money on the table.
- Flat betting, no counting, no insurance, no surrender (the engine has none).
- Standard error of any session average is about $0.5; differences under $1 between
  rules are noise. The linear trend with hand count is not.
- Rules can be re-run under harsher tables with `--h17`, `--no-das`, `--six-five`.

## Reproduce

    python3 research/stop_solver.py \
        --sessions 100000 --hands 100 \
        --bankroll 300 --bet 15 --seed 20260912 \
        --out research/results/stop-results.json
