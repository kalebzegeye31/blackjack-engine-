# Blackjack trainer

A blackjack table that scores you. Every decision gets marked against the strategy
chart *and* against the cards actually left in the shoe, and your bet sizes get
marked too. Runs entirely on your own machine.

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

## Where your data lives

One file: `blackjack.db`, created next to `server.py` the first time you run it.
It's a normal SQLite database. Nothing is sent anywhere. Delete the file and
every profile and statistic is gone.

You can poke at it directly if you want:

```
sqlite3 blackjack.db "SELECT cell, COUNT(*) FROM decisions WHERE correct=0 GROUP BY cell ORDER BY 2 DESC;"
```

## The tabs

**Table** — play. The middle is the table itself. The left column shows the working
behind whatever you just did: which cards are still unseen, where the dealer is
likely to end up, and what each option was worth. The right column is the same
thing in plain language, with the one line worth memorising.

**Betting** — how much to put out, and whether your last bet made sense. Flags
raising after a loss, betting too much of what you have, and playing a table
that's too expensive for your bankroll.

**Ledger** — your record. Accuracy, what you keep getting wrong, and the money.

**Glossary** — every term the app uses, explained from scratch. Anything underlined
elsewhere opens the same explanation right where you're standing.

**Setup** — decks, table minimum, how many other people are at the table, and how
deep they deal before reshuffling.

## Keyboard

`H` hit · `S` stand · `D` double · `P` split · `Space` deal / next hand

## How it's put together

```
server.py    HTTP server and JSON API. Standard library only.
engine.py    The maths. Pure functions, no state, no I/O.
game.py      One table: shoe, seats, whose turn, the money.
coach.py     The words. Explanations and the glossary.
db.py        SQLite storage.
static/      The browser side: one HTML file, one CSS file, one JS file.
```

The split that matters: `engine.py` knows nothing about the game being played or
the database. You can import it on its own and ask it questions.

```python
import engine as E
shoe = [{"rank": r, "suit": s, "red": red}
        for _ in range(6) for s, red in E.SUITS for r in E.RANKS]
odds = E.Odds(shoe, up=10)
odds.ev_stand(16)          # -0.5404
odds.ev_hit(16, soft=False) # -0.5398
odds.dealer_bust()          # 0.230
```

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

## Rules as configured

Six decks, dealer stands on all 17s, blackjack pays 3 to 2, double on any first
two cards, double after splitting allowed, split up to four hands, split aces get
one card each. Other players use basic strategy and don't split, to keep the
number of hands sane.

## Bankroll

You start with $100. If you drop below one table minimum you're given another
$100 automatically, and it's counted. The "all time" figure is everything you
have now minus everything you've been given, so it never resets. That's
deliberate — it's the only number that can't flatter you.

## Checks it passes

`python3 test_engine.py` compares the maths against published figures:

- Standing on 16 against a 10: −0.5404 (published −0.5404)
- Hitting 16 against a 10: −0.5398 (published −0.5398)
- Doubling 11 against a 6: +0.6674 (published +0.6674)
- Dealer bust rates from every upcard, to a tenth of a percent
- All 200 chart cells agree with the computed best play except two known
  borderline ones (soft 13 v 5 and soft 15 v 4), which differ by 0.007 and
  0.001 — smaller than the difference between six decks and infinite decks

`python3 validate.py` plays the chart perfectly for tens of thousands of rounds
through the real game code:

- Chart accuracy comes out at exactly 100%
- House edge lands at −0.56% ± 0.47%, against a published −0.43%

That second one is the useful test: it can only come out right if dealing,
settlement, blackjack payouts, doubling, splitting, insurance and the dealer's
drawing rules are all correct together.

## Known limits

- Split hands are valued without allowing for re-splitting, so 8s and aces are
  scored very slightly conservatively.
- Expected values assume each draw is independent within a hand. With 200+ cards
  unseen the error is in the fourth decimal place.
- The table state lives in memory, so restarting the server starts a fresh shoe.
  Your money and statistics are on disk and survive.
