# Blackjack trainer

A blackjack table that scores you, and a set of tools for working out what your
mistakes are actually costing. Every decision is marked against the strategy
chart *and* against the cards actually left in the shoe. Runs entirely on your
own machine.

## Running it

You need Python 3.8 or newer. Nothing else — no `pip install`, no internet.

```
python3 server.py
```

It prints a link and opens your browser at `http://localhost:8000`.
Stop it with Ctrl-C.

Options:

```
python3 server.py --port 9000      # different port
python3 server.py --no-browser     # don't open a browser
```

If it says the port is already in use, that is almost always this same program
still running from earlier — it says so, gives you the process to stop, and
suggests a free port if something else has it.

## How the money works

An account starts with **nothing**. There is no automatic top-up.

1. **The first time you sit down** you choose what you are carrying — $100, $250,
   $500 or $1000 — and it is granted to you. That is the only free money.
2. **Buying in** moves chips from your stack onto the table. **Standing up** brings
   whatever is left back.
3. **If you run out**, the session ends. To sit down again you need chips, and the
   only way to get more is the **Quiz** tab: ten questions, $10 in chips for every
   one you get right.

Every movement is written to a ledger, so the all-time figure is:

```
everything you're worth  −  everything you were given  −  everything you won at the quiz
```

which can only have come from the table. It is the one number that cannot flatter
you, and it is the reason the free top-up had to go: money that appears from
nowhere makes the scoreboard meaningless.

## The tabs

**Table** — play. The left column explains the hand you just played in plain
language. The right column is this session: hands played, up or down, high and
low, how you are playing, and your all-time records next to it.

**Betting** — how much to put out, and whether your last bet made sense. Flags
raising after a loss, betting too much of what you have, and playing a table
that's too expensive for your bankroll.

**Chart** — the full basic strategy chart, hard totals, soft totals and pairs.
Click any square for what it means and your own record on it. It redraws itself
for whatever rules you have set, and your decisions are graded against the same
grid, so the two can never disagree.

**Quiz** — the chart without the waiting. Drill your weak spots, the hands you
have actually got wrong, the rare corners you never get dealt, or build your own
filter. Or play for chips.

**Analysis** — four things: how well you play and what it costs per hour, a
simulator that runs the game hundreds of times so you can see the spread rather
than the average, a bankroll calculator, and the all-time ledger.

**Account** — who you are, the ledger, what you keep missing, and a straight
assessment of where you stand. Log out here.

**Setup** — decks, table limits, other players, penetration, and the rules that
change the chart: soft 17, double after split, re-splitting aces, and what a
blackjack pays.

## Keyboard

`H` hit · `S` stand · `D` double · `P` split · `Space` deal / next hand.
The same keys answer quiz questions.

## Accuracy, and why there are two numbers

Plain accuracy is a bad measure of a card player. Most hands you are dealt are
trivial — a hard 20, a hard 8 — and getting those right forever holds a number in
the nineties while six cells you keep fluffing quietly cost you money. Worse, the
number only goes up, so it stops telling you anything.

So there is a second number, **sharpness**. Every square of the chart carries a
weight:

- **difficulty** — driven by your recent record on that square. Get it right a few
  times running and the weight decays towards a floor; miss it and it springs back.
  Recent results count for far more than old ones.
- **cost** — how much expected value your mistakes on that square actually give
  away. Misplaying 16 against a 10 costs almost nothing; missing a double on 11
  costs a lot. Expensive squares weigh double.
- **exposure** — a square you have seen twice cannot swing the score. Weight ramps
  in as evidence accumulates.

Sharpness is the weighted average of how well you play each square. It is held
back until there is enough evidence to mean anything: below 250 decisions it is
blended towards plain accuracy so it doesn't lurch about while you are finding
your feet.

The gap between the two numbers is the part you are still getting away with. A
player at 85% accuracy and 59% sharpness is not 85% good — they are getting the
obvious hands right and losing the same few awkward ones over and over.

The Analysis tab turns that into money: how often you miss each square, times what
that miss costs, times how often the hand turns up, times 80 hands an hour.

## Counting

The count is **hidden**. That is the point of it: a number sitting on screen is
not a count you can keep, and no casino prints one for you.

Press **REVEAL COUNT** and it does not simply tell you — it asks you first. You
type what you think the running count is, it marks you, and only then shows the
truth. Peeking always costs a graded answer, so the button can never quietly
become a readout you lean on. Revealing lasts one round; the next deal hides it
again.

It also interrupts. Every so often, unasked and usually at a bad moment, the bar
demands the count whether you wanted to check or not. A player who only tests
themselves when they feel confident is grading their best moments, which is how
you end up at a real table discovering you lost the count twenty hands ago.

Answers are marked exactly. Close is still wrong: an error in the running count
does not average out, it rides with you to the shuffle and skews every true
count you derive from it.

### The index plays

Play is graded twice, against two different things, because they are two
different skills:

- **basic strategy** — what the chart says, ignoring the count
- **the index plays** — the hands where a big count changes the answer

The second is the Illustrious 18: the eighteen departures from the chart that
carry nearly all of the value, insurance at +3 being far and away the largest.
Get one wrong and the count breaks cover — the app stops, tells you the index,
what the true count actually was, and why that hand moves. Get it right and it
stays quiet, because being told the count when you already knew it teaches you
nothing.

Surrender indices (the Fab 4) are absent, because this game has no surrender.

### Where the index numbers came from

They are not copied out of a book on trust. Every one was re-derived from this
repository's own engine: six thousand shoes dealt card by card, the composition
of what remained recorded at each point the true count sat near an integer,
those compositions averaged per count and handed to `engine.Odds` to find the
exact true count at which each decision flips.

Sixteen of the eighteen landed on the published value. Two — 12 v 3 and 11 v A —
came out half a point away, which is to say the expected value either side is
near enough identical that the rounding could fall either way. The published
value is used for both, and the derived crossing is stored next to every index
and shown in the app, so it argues its case rather than asserting a number.

`python3 test_count.py` re-derives all eighteen from scratch and fails if the
table has drifted from the maths, and separately checks that every index still
agrees with basic strategy on one of its two sides.

### Betting

Playing the indices perfectly and betting flat earns almost nothing. The spread
is where a counter's money comes from, and it is also the thing a pit notices
first. The Betting tab grades your bet against the ramp in bands rather than
exactly, because a trainer that nags about one unit teaches you to ignore it.

## The explanations

`coach.py` holds one hand-written passage for every square of the chart — 340 of
them, plus insurance — keyed by the hand you hold and the card the dealer shows.
Not generated, and not assembled from branches: a passage can only ever appear
for the one situation it was written about, so it never tells you a hard 20 is a
bad hand or calls a dealer showing a ten "in trouble". Each one gives you a hook,
the reasoning, a comparison to something outside the game, and the block rule
worth memorising — the same rule across every square in its block, so repetition
drills the rule rather than the square.

They are written for the standard table: six decks, dealer stands on all 17s,
doubling allowed after a split. Ten squares move under a different soft-17 or
double-after-split rule, and on those the passage gets a sentence above it saying
so, because otherwise it would describe a table you are not sitting at while the
verdict directly above says the opposite. `rules.py` works out which squares
those are; nothing is flagged on a standard table.

## How it's put together

```
server.py    HTTP server and JSON API. Standard library only.
engine.py    The maths. Pure functions, no state, no I/O.
rules.py     The rule set, and the strategy chart that follows from it.
game.py      One table for one session: shoe, seats, whose turn, the money.
sim.py       A second, stripped table that deals 200,000 hands a second.
mastery.py   How well you actually know the chart.
quiz.py      Questions, drawn from wherever your record is worst.
count.py     Hi-Lo: the count, the Illustrious 18, and the bet ramp.
coach.py     The words. One written passage per square of the chart, plus the glossary.
db.py        SQLite storage: accounts, sessions, decisions, the chip ledger.
static/      The browser side: one HTML file, one CSS file, one JS file.
```

The split that matters: `engine.py` knows nothing about the game being played or
the database. You can import it on its own and ask it questions.

```python
import engine as E
shoe = [{"rank": r, "suit": s, "red": red}
        for _ in range(6) for s, red in E.SUITS for r in E.RANKS]
odds = E.Odds(shoe, up=10)
odds.ev_stand(16)           # -0.5404
odds.ev_hit(16, soft=False) # -0.5398
odds.dealer_bust()          # 0.230
```

There are deliberately **two** blackjack engines. `game.py` deals one careful hand
at a time and computes exact odds for every option from the cards actually left —
right for a trainer, hopeless for a simulation at a few hundred hands a second.
`sim.py` is the same rules with bare integers and a dictionary lookup for the
chart. `validate.py` plays both and checks they agree, which is the point: they
are separate code, so if one gets a rule wrong they diverge.

## The thing that makes this different

Most trainers look the answer up in a printed table. This one works it out from
the cards that are actually still unseen, every single time. The dealer's outcome
distribution is computed by walking every draw sequence they could take, weighted
by what's genuinely left in the shoe.

That has a real consequence: as a shoe gets used up, the right play sometimes
changes. The app notices and tells you when the cards disagree with the chart.
It has no table of deviations in it — it rediscovers them.

It also means the number of other players at the table matters honestly. They
don't change which move is right for your hand — nothing about someone else's
cards can — but they burn through the shoe faster, so the mix of what's left
drifts further. Set the shuffling-machine option in Setup and watch that effect
disappear completely, which is exactly why casinos bought them.

## Dealing, as a real table does it

The rules that are easy to get subtly wrong and impossible to notice afterwards:

- **Splitting.** The dealer slides one card onto the first half and waits. You play
  that hand to the end before the second half is touched at all. An earlier version
  dealt to both halves at once, which quietly taught the wrong thing — you were
  choosing for hand one while already looking at hand two.
- **Re-splitting** inserts the new hand next in line, not last.
- **Split aces** get exactly one card each and are finished, unless the house allows
  re-splitting them. Twenty-one on a split hand is 21, not a blackjack.
- **The dealer peeks** under a ten or an ace, and the hand ends there if they have it.
- **Insurance** is offered before the peek. Holding a blackjack against an ace, it
  is offered as even money, which is the same bet wearing a different hat.
- **The dealer doesn't draw** when every hand you hold has busted — but the hole card
  is still turned over.
- **The hole card isn't counted** while it's face down.
- **The shoe reshuffles at the cut card**, between rounds, never mid-hand.

Configurable, because real tables differ: soft 17, double after split, re-splitting
aces, how many hands you may split to, and whether a blackjack pays 3:2 or 6:5.
Each one changes the chart, and only where it should.

Not implemented: surrender, European no-hole-card, doubling for less.

## Checks it passes

`python3 test_engine.py` — the maths against published figures:

- Standing on 16 against a 10: −0.5404 (published −0.5404)
- Hitting 16 against a 10: −0.5398 (published −0.5398)
- Doubling 11 against a 6: +0.6674 (published +0.6674)
- Dealer bust rates from every upcard, to a tenth of a percent
- All 300 chart cells agree with the computed best play except two known
  borderline ones (soft 13 v 5 and soft 15 v 4), which differ by 0.007 and
  0.001 — smaller than the difference between six decks and infinite decks
- The chart changes with the rules, and only in the cells it should

`python3 test_game.py` — 49 checks that the table deals like a real one, including
every rule in the list above, and that every square of the chart has a written
passage to go with it under every rule set.

`python3 test_db.py` — 30 checks that the chip ledger adds up, that a database
from the previous version upgrades without losing a row, and that connections are
handed back rather than leaked.

`python3 validate.py` — the slow one, about 90 seconds (`--quick` for a tenth of it):

- Chart accuracy through the real game code comes out at exactly 100%
- The two engines agree on the house edge to a fraction of a standard error
- That figure matches the published −0.43%
- Each rule change costs what it is supposed to cost, measured on matched shoes
  so the shuffle cancels out: hitting soft 17 −0.22%, no double after split −0.14%,
  6:5 blackjacks −1.36%

That last one is worth a footnote. Pairing the runs makes the measurement more
precise than the figure everyone quotes: 6:5 is usually given as −1.39%, and the
measurement kept landing on −1.361% ± 0.006%. It is exactly computable — you are
dealt a natural 4.749% of the time with six decks, the dealer matches it in 4.562%
of those (a push, paid nothing either way), and the rest are paid 0.3 of a bet
short, giving 1.3597%. The round number was the thing that was wrong.

## Where your data lives

One file: `blackjack.db`, created next to `server.py` the first time you run it.
It's a normal SQLite database. Nothing is sent anywhere. Delete the file and
every account and statistic is gone.

A database from the previous version is upgraded in place on first run: the old
bankroll becomes chips, the old deposits become chips you were given, and every
decision, bet and round is kept.

You can poke at it directly if you want:

```
sqlite3 blackjack.db "SELECT cell, COUNT(*) FROM decisions WHERE correct=0 GROUP BY cell ORDER BY 2 DESC LIMIT 10;"
```

## Known limits

- Split hands are valued without allowing for re-splitting, so 8s and aces are
  scored very slightly conservatively.
- Expected values assume each draw is independent within a hand. With 200+ cards
  unseen the error is in the fourth decimal place.
- The table lives in memory. If the server restarts mid-session the session is
  closed and the money handed back from the last recorded position; your chips,
  history and statistics are on disk and survive.
- There are no passwords. Logging out returns you to the list of players on this
  machine — there is nothing here to protect from someone who already has your
  computer.
