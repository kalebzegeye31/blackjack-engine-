"""Play the chart perfectly for a long time. The house edge should land on the published number."""
import random, time
import engine as E
from game import Table

random.seed(11)
t = Table(config={"decks": 6, "others": 2, "table_min": 15, "penetration": 0.75}, bankroll=100.0)

N = 8000
wagered = deposited = 100.0
decisions = correct = shoe_match = 0
start = time.time()

for i in range(N):
    t.new_round()
    bet = t.config["table_min"]
    wagered += bet
    t.bet = bet
    t.bankroll -= bet
    t.deal()
    if t.phase == "insurance":
        t.insurance(False)
        decisions += 1; correct += 1; shoe_match += 1
    guard = 0
    while t.phase == "play":
        hand = t.hands[t.active]
        before = len(t.hands)
        play = E.chart_play(hand["cards"], E.card_value(t.dealer[0]["rank"]),
                            t.can_double(hand), t.can_split(hand))
        if play["move"] == "D":
            wagered += hand["bet"]
        if play["move"] == "P":
            wagered += hand["bet"]
        a = t.act(play["move"])
        decisions += 1
        correct += 1 if a["correct"] else 0
        chosen = next((o for o in a["options"] if o["move"] == play["move"] and o["legal"]), None)
        if chosen and a["best_ev"] - chosen["ev"] <= 0.002:
            shoe_match += 1
        guard += 1
        assert guard < 60
    assert t.phase == "settled"
    if t.bankroll < t.config["table_min"]:
        t.bankroll += 100.0
        deposited += 100.0

net = t.bankroll - deposited
edge = net / wagered * 100
se = E.HAND_SD / (N ** 0.5) * 100

print("rounds            %d in %.1fs" % (N, time.time() - start))
print("chart accuracy    %.1f%%   (must be exactly 100.0)" % (correct / decisions * 100))
print("matched the cards %.1f%%   (chart vs live shoe)" % (shoe_match / decisions * 100))
print("total wagered     $%.0f" % wagered)
print("house edge        %+.3f%%  +/- %.3f%% (one standard error)" % (edge, se))
print("published         -0.43%% for 6 decks, stand on soft 17, double after split, 3:2")
off = abs(edge + 0.43) / se
print("distance          %.2f standard errors  ->  %s" % (off, "PASS" if off < 2.5 else "FAIL"))
