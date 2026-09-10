import engine as E

def deck(n=6):
    return [{"rank": r, "suit": s, "red": red}
            for _ in range(n) for s, red in E.SUITS for r in E.RANKS]

full = deck(6)
print("dealer bust %% from each upcard (full 6-deck shoe, no-blackjack conditioned):")
print("  " + "  ".join(("A" if u == 11 else str(u)) + ":" + "%.1f%%" % (E.Odds(full, u).dealer_bust()*100)
                       for u in [2,3,4,5,6,7,8,9,10,11]))

o10, o6, o4 = E.Odds(full,10), E.Odds(full,6), E.Odds(full,4)
checks = []
def chk(name, got, want, tol, note=""):
    ok = abs(got-want) <= tol
    checks.append(ok)
    print("  %-22s %+.4f   (published %+.4f)  %s%s" % (name, got, want, "ok" if ok else "MISMATCH", note))

print("\nagainst published 6-deck S17 values:")
chk("stand 16 v 10", o10.ev_stand(16), -0.5404, 0.004)
chk("hit   16 v 10", o10.ev_hit(16,False), -0.5398, 0.004)
chk("double 11 v 6", o6.ev_double(11,False), 0.6674, 0.01)
chk("stand 12 v 4",  o4.ev_stand(12), -0.2111, 0.004)
chk("hit   12 v 4",  o4.ev_hit(12,False), -0.2135, 0.004)
print("  split 8,8 v 10        %+.4f   beats hitting (%+.4f): %s"
      % (o10.ev_split(8), o10.ev_hit(16,False), o10.ev_split(8) > o10.ev_hit(16,False)))
checks.append(o10.ev_split(8) > o10.ev_hit(16,False))

print("\nevery chart cell vs the maths on a full shoe:")
UP=[2,3,4,5,6,7,8,9,10,11]
def mk(rs): return [{"rank":r,"suit":"\u2660","red":False} for r in rs]
cases=[]
for k,row in E.HARD.items():
    t = 8 if k==8 else 15 if k==16 else 18 if k==21 else k
    cases.append((mk([str(t-2),"2"]) if t<=11 else mk(["10",str(t-10)]), row, "hard %d"%t))
for k,row in E.SOFT.items():
    cases.append((mk(["A",{"2-3":"2","4-5":"4","6":"6","7":"7","8+":"8"}[k]]), row, "soft "+k))
for k,row in E.PAIRS.items():
    r = "A" if k==11 else str(k)
    cases.append((mk([r,r]), row, "pair "+r))
bad=[]
for cards,row,name in cases:
    for i,u in enumerate(UP):
        o=E.Odds(full,u); t,s=E.hand_value(cards)
        opts={"S":o.ev_stand(t),"H":o.ev_hit(t,s),"D":o.ev_double(t,s)}
        if E.card_value(cards[0]["rank"])==E.card_value(cards[1]["rank"]):
            opts["P"]=o.ev_split(E.card_value(cards[0]["rank"]))
        best=max(opts,key=opts.get)
        if best!=row[i]:
            bad.append("%s v%s chart=%s maths=%s gap=%.4f"%(name,"A" if u==11 else u,row[i],best,opts[best]-opts[row[i]]))
print("  disagreements:", len(bad))
for b in bad: print("   ", b)
checks.append(len(bad) <= 2)

print("\ncount sensitivity (strip half the low cards -> ten-rich shoe):")
# remove half the low cards by position -- card dicts compare equal, so
# filtering by value would strip every low card instead of half of them
low_positions=[i for i,c in enumerate(full) if 2<=E.card_value(c["rank"])<=6]
gone=set(low_positions[:len(low_positions)//2])
rich=[c for i,c in enumerate(full) if i not in gone]
r10=E.Odds(rich,10); r2=E.Odds(rich,2)
print("  16 v 10  stand %+.4f  hit %+.4f  ->  %s" % (r10.ev_stand(16), r10.ev_hit(16,False),
      "STAND (deviates from chart)" if r10.ev_stand(16)>r10.ev_hit(16,False) else "hit"))
print("  12 v 2   stand %+.4f  hit %+.4f  ->  %s" % (r2.ev_stand(12), r2.ev_hit(12,False),
      "STAND (deviates from chart)" if r2.ev_stand(12)>r2.ev_hit(12,False) else "hit"))
checks.append(r10.ev_stand(16)>r10.ev_hit(16,False))
checks.append(r2.ev_stand(12)>r2.ev_hit(12,False))

print("\nbankroll maths:")
print("  P(double 100 units before broke, -0.5%% edge): %.1f%%" % (E.reach_before_ruin(100,200,-0.005)*100))
print("  P(4 units -> 28 units, -0.5%% edge):           %.1f%%" % (E.reach_before_ruin(4,28,-0.005)*100))

print("\n%s" % ("ALL CHECKS PASS" if all(checks) else "%d FAILURES" % checks.count(False)))
