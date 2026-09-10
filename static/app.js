/* app.js — talks to the Python server, draws the table. */

const $ = (id) => document.getElementById(id);
const MOVE = { H: "hit", S: "stand", D: "double", P: "split" };
const PAST = { H: "hit", S: "stood", D: "doubled", P: "split" };

let ACCOUNT = null;          // {id, name}
let S = null;                // last snapshot from the server
let STATS = null;
let GLOSSARY = {};
let GLOSSARY_LIST = [];
let TAB = "table";
let PENDING_BET = 0;
let LAST_BET = null, LAST_OUTCOME = null;

const money = (n) => (n < 0 ? "\u2212$" : "$") + Math.abs(n).toFixed(Math.abs(n) % 1 ? 2 : 0);
const pct = (x, d = 0) => (x * 100).toFixed(d) + "%";
const ev = (n) => (n < 0 ? "\u2212" : "+") + Math.abs(n).toFixed(3);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const esc = (s) => String(s).replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, opts);
  return res.json();
}

/* ---------------- boot ---------------- */
async function boot() {
  const g = await api("/api/glossary");
  GLOSSARY_LIST = g.terms;
  g.terms.forEach((t) => (GLOSSARY[t.term] = t));
  const saved = window.name && window.name.startsWith("bj:") ? +window.name.slice(3) : null;
  const { accounts } = await api("/api/accounts");
  if (saved && accounts.some((a) => a.id === saved)) return open_account(saved);
  if (accounts.length === 1) return open_account(accounts[0].id);
  gate(accounts);
}

function gate(accounts) {
  $("root").innerHTML =
    '<div class="gate"><h1>Blackjack <b>trainer</b></h1>' +
    '<p class="lede">Play real hands. Every decision gets scored twice \u2014 against the strategy chart, ' +
    "and against the cards actually left in the shoe. Your bet sizes get scored too. " +
    "Everything is stored in a file on this machine and goes nowhere else.</p>" +
    (accounts.length
      ? accounts
          .map(
            (a) =>
              '<div class="arow" onclick="open_account(' + a.id + ')"><div><b>' + esc(a.name) +
              "</b><span>" + a.rounds + " rounds \u00b7 " +
              (a.accuracy === null ? "no decisions yet" : a.accuracy + "% accurate") +
              "</span></div><b class=\"" + (a.lifetime > 0 ? "up" : a.lifetime < 0 ? "down" : "") +
              '">' + money(a.lifetime) + "</b></div>"
          )
          .join("")
      : "") +
    '<div class="field" style="margin-top:18px"><label>NEW PLAYER</label>' +
    '<input type="text" id="nm" placeholder="Your name" maxlength="32"></div>' +
    '<button class="mv go" style="width:100%" onclick="make_account()">Sit down</button></div>';
  const input = $("nm");
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") make_account(); });
}

async function make_account() {
  const { id } = await api("/api/accounts", { name: $("nm").value });
  open_account(id);
}

async function open_account(id) {
  window.name = "bj:" + id;
  S = await api("/api/state?account=" + id);
  if (S.error) return boot();
  ACCOUNT = S.account;
  STATS = await api("/api/stats?account=" + id);
  PENDING_BET = S.config.table_min;
  draw();
}

async function refresh_stats() {
  STATS = await api("/api/stats?account=" + ACCOUNT.id);
}

/* ---------------- actions ---------------- */
async function send(path, body) {
  const next = await api(path, Object.assign({ account: ACCOUNT.id }, body || {}));
  if (next.error) return;
  S = next;
  if (S.round_result) LAST_OUTCOME = S.round_result.outcome;
  if (S.reloaded) toast("Out of money \u2014 another " + money(S.reload_amount) + " added. It counts against your lifetime total.");
  await refresh_stats();
  draw();
}
const doBet = () => { LAST_BET = PENDING_BET; return send("/api/bet", { amount: PENDING_BET, last_bet: LAST_BET, last_outcome: LAST_OUTCOME }); };
const doMove = (m) => send("/api/action", { move: m });
const doIns = (t) => send("/api/insurance", { take: t });
const doNext = () => send("/api/next");
const setBet = (v) => { PENDING_BET = v; draw(); };
const addBet = (v) => { PENDING_BET = Math.min(S.bankroll, PENDING_BET + v); draw(); };
const clearBet = () => { PENDING_BET = S.config.table_min; draw(); };

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- shell ---------------- */
function draw() {
  const lifetime = S.lifetime;
  const acc = STATS && STATS.accuracy !== null ? Math.round(STATS.accuracy * 100) + "%" : "\u2014";
  $("root").innerHTML =
    '<div class="bar"><div class="logo">Blackjack <b>trainer</b></div>' +
    '<div class="tabs">' +
    ["table", "betting", "ledger", "glossary", "setup"]
      .map((t) => '<button class="' + (TAB === t ? "on" : "") + '" onclick="go(\'' + t + "')\">" + cap(t) + "</button>")
      .join("") +
    "</div>" +
    '<div class="stats">' +
    '<div class="stat"><b>' + acc + "</b><span>ACCURACY</span></div>" +
    '<div class="stat"><b>' + money(S.bankroll) + "</b><span>MONEY</span></div>" +
    '<div class="stat"><b class="' + (lifetime > 0 ? "up" : lifetime < 0 ? "down" : "") + '">' +
    money(lifetime) + "</b><span>ALL TIME</span></div>" +
    "</div></div>" +
    '<div class="wrap" id="wrap"></div><div class="foot" id="foot"></div>';
  ({ table: viewTable, betting: viewBetting, ledger: viewLedger, glossary: viewGlossary, setup: viewSetup }[TAB])();
  wireTerms();
}
function go(t) { TAB = t; draw(); }

/* ---------------- table view ---------------- */
function viewTable() {
  $("wrap").innerHTML =
    '<div class="cols">' +
    '<div><div class="panel"><div class="phead"><h2>WHERE THE NUMBER COMES FROM</h2>' +
    '<em id="uc"></em></div><div class="pbody" id="deriv"></div></div></div>' +
    '<div class="mid" id="mid"></div>' +
    '<div><div class="panel"><div class="phead"><h2>HOW TO REMEMBER IT</h2></div>' +
    '<div class="pbody" id="intu"></div></div></div></div>';
  drawTable(); drawDeriv(); drawIntu();
  $("foot").innerHTML =
    "<b>" + S.config.decks + " decks \u00b7 " + S.config.others + " other player" +
    (S.config.others === 1 ? "" : "s") + " \u00b7 $" + S.config.table_min +
    " minimum \u00b7 dealer stands on all 17s \u00b7 blackjack pays 3 to 2 \u00b7 " +
    "you may double after splitting \u00b7 up to four hands.</b><br>" +
    "The other players sit ahead of you and play by the chart. Their cards come out of the same shoe, " +
    "so they change what is left to draw \u2014 and every number on this page is worked out from what " +
    "is actually left, not from a printed table. Keyboard: H hit, S stand, D double, P split, space to deal.";
}

const cardEl = (c, down) =>
  down
    ? '<div class="card down"></div>'
    : '<div class="card' + (c.red ? " red" : "") + '"><i>' + c.suit + "</i>" +
      (c.rank === "10" ? "10" : c.rank) + "</div>";
const miniEl = (c) =>
  '<div class="mc' + (c.red ? " red" : "") + '">' + (c.rank === "10" ? "T" : c.rank) + "</div>";

function drawTable() {
  const d = S.dealer;
  const tc = S.true_count;
  let h =
    '<div class="rail"><div class="felt">' +
    '<div class="arc"></div><div class="arc two"></div>' +
    '<div class="felt-text">BLACKJACK PAYS 3 TO 2<small>DEALER MUST DRAW TO 16 AND STAND ON ALL 17s ' +
    "\u00b7 INSURANCE PAYS 2 TO 1</small></div>" +
    '<div class="shoebar"><span>COUNT ' + (S.running_count >= 0 ? "+" : "\u2212") +
    Math.abs(S.running_count) + " \u00b7 PER DECK " + (tc >= 0 ? "+" : "\u2212") +
    Math.abs(tc).toFixed(1) + '</span><span>SHOE USED <span class="meter"><i style="width:' +
    Math.round(S.shoe_used * 100) + '%"></i></span></span></div>';

  /* dealer */
  h +=
    '<div class="dealer-zone"><div class="zlab">DEALER</div>' +
    '<div class="hand-row">' + (d.cards.length ? d.cards.map((c, i) => cardEl(c, d.hole_hidden && i === 1)).join("") : "") + "</div>" +
    (d.cards.length
      ? '<div class="total' + (d.bust ? " bust" : "") + '">' +
        (d.hole_hidden ? d.showing + "<em>SHOWING</em>" : d.total + (d.bust ? "<em>BUST</em>" : "")) + "</div>"
      : "") + "</div>";

  /* other seats, nudged into an arc */
  if (S.seats.length) {
    const n = S.seats.length, mid = (n - 1) / 2;
    h += '<div class="seats">' + S.seats.map((s, i) => {
      const lift = Math.round(Math.abs(i - mid) * 7);
      return '<div class="seat' + (s.bust ? " bustd" : "") + '" style="transform:translateY(-' + lift + 'px)">' +
        '<div class="slab">SEAT ' + (i + 1) + '</div><div class="mini">' +
        s.cards.map(miniEl).join("") + '</div><div class="stot">' +
        (s.cards.length ? (s.bust ? "bust" : s.total) : "\u2014") + "</div></div>";
    }).join("") + "</div>";
  }

  /* your spots */
  h += '<div class="hero">';
  if (S.hands.length) {
    h += S.hands.map((x, i) => {
      let head = "";
      if (S.hands.length > 1) head += "<span>HAND " + (i + 1) + "</span>";
      head += "<span>" + money(x.bet) + (x.doubled ? " DOUBLED" : "") + "</span>";
      if (x.result) head += '<span class="res ' + x.result + '">' + x.result.toUpperCase() + "</span>";
      return '<div class="spot' + (x.active ? " live" : "") + (x.result ? " over" : "") + '">' +
        '<div class="spot-head">' + head + "</div>" +
        '<div class="hand-row">' + x.cards.map((c) => cardEl(c)).join("") + "</div>" +
        '<div style="text-align:center"><span class="total' + (x.bust ? " bust" : "") + '">' +
        x.total + (x.soft && x.total < 21 ? "<em>SOFT</em>" : "") + (x.bust ? "<em>BUST</em>" : "") +
        "</span></div></div>";
    }).join("");
  } else {
    h += '<div class="spot"><div class="circle">' + money(PENDING_BET) + "</div></div>";
  }
  h += "</div></div></div>";

  /* verdict */
  const v = S.verdict;
  if (v) {
    if (v.kind === "insurance") {
      h += '<div class="verdict ' + (v.correct ? "yes" : "no") + '"><h3>' +
        (v.correct ? "Right call \u2014 you turned it down" : "Never take insurance") + "</h3>" +
        "<p>It is a side bet on the dealer\u2019s face-down card, not on your hand.</p></div>";
    } else {
      h += '<div class="verdict ' + (v.correct ? "yes" : "no") + '"><h3>' +
        (v.correct ? "Right \u2014 " + MOVE[v.chosen] : "You should have " + PAST[v.should]) + "</h3>" +
        "<p>" + cap(v.row) + " against a dealer " + v.up + " \u2192 <kbd>" + MOVE[v.should] + "</kbd>" +
        (v.correct ? "" : ". You chose <kbd>" + MOVE[v.chosen] + "</kbd>") + "." +
        (v.fallback ? " The chart says double here, but you can only double on your first two cards." : "") +
        "</p></div>";
    }
  }

  /* controls */
  h += '<div class="controls">';
  if (S.phase === "bet") {
    const denoms = [5, 15, 25, 50, 100].filter((v) => v <= S.bankroll);
    h += '<div class="tray">' +
      denoms.map((v) => '<button class="chip" data-v="' + v + '" onclick="addBet(' + v + ')"><span>' + v + "</span></button>").join("") +
      '<button class="mv" style="flex:0 0 auto;padding:9px 14px" onclick="clearBet()">Reset</button></div>' +
      '<div class="betline">Betting <b>' + money(PENDING_BET) + "</b> of " + money(S.bankroll) +
      " \u2014 that is " + pct(PENDING_BET / S.bankroll) + " of your money, " +
      (S.bankroll / PENDING_BET).toFixed(1) + " bets deep.</div>" +
      '<button class="mv go" style="width:100%" onclick="doBet()">Deal<small>SPACE</small></button>';
  } else if (S.phase === "insurance") {
    h += '<div class="moves"><button class="mv" onclick="doIns(true)">Take insurance</button>' +
      '<button class="mv" onclick="doIns(false)">No thanks</button></div>';
  } else if (S.phase === "play") {
    h += '<div class="moves">' +
      '<button class="mv" onclick="doMove(\'H\')">Hit<small>H</small></button>' +
      '<button class="mv" onclick="doMove(\'S\')">Stand<small>S</small></button>' +
      '<button class="mv" onclick="doMove(\'D\')"' + (S.can_double ? "" : " disabled") + ">Double<small>D</small></button>" +
      '<button class="mv" onclick="doMove(\'P\')"' + (S.can_split ? "" : " disabled") + ">Split<small>P</small></button></div>";
  } else {
    h += '<button class="mv go" style="width:100%" onclick="doNext()">Next hand<small>SPACE</small></button>';
  }
  h += "</div>";
  $("mid").innerHTML = h;
}

/* ---------------- derivation ---------------- */
const step = (n, title, body) => '<div class="step"><h4><i>' + n + "</i>" + title + "</h4>" + body + "</div>";

function drawDeriv() {
  const box = $("deriv"), lab = $("uc");
  const a = S.analysis;
  if (!a) {
    lab.textContent = "";
    box.innerHTML =
      '<p class="idle">This side shows the working: exactly which cards are still unseen, where the ' +
      "dealer is likely to end up, and what each of your options is worth. It stays empty until you " +
      "act, so it cannot give you the answer in advance.</p>";
    return;
  }
  lab.textContent = a.unseen + " cards unseen";

  if (a.kind === "insurance") {
    box.innerHTML =
      step(1, "What you were offered",
        '<p>A separate bet that the dealer\u2019s face-down card is worth ten. It pays two to one ' +
        "and is settled before your own hand is played.</p>") +
      step(2, "What it needs to break even",
        '<div class="eq">win \u00d7 2 \u2212 lose \u00d7 1 = 0<br>\u2192 needs to win <b>1 in 3</b> ' +
        "(<b>33.3%</b>) of the time</div>") +
      step(3, "What it actually is right now",
        '<div class="eq"><b>' + a.tens_left + "</b> ten-valued cards \u00f7 <b>" + a.unseen +
        "</b> unseen = <b>" + pct(a.p_ten, 1) + "</b></div>") +
      step(4, "So the bet is worth",
        '<div class="eq">3 \u00d7 ' + a.p_ten.toFixed(4) + ' \u2212 1 = <b class="' +
        (a.ev >= 0 ? "pos" : "neg") + '">' + ev(a.ev) + "</b> per dollar</div><p>" +
        (a.ev > 0
          ? "At this exact composition insurance actually makes money. That only happens when a lot of " +
            "small cards have already gone \u2014 it is the one bet that flips with the count."
          : "That is a " + pct(-a.ev, 1) + " loss on every dollar you put on it. Worse than any other bet on this table.") +
        "</p>");
    return;
  }

  const up = a.up === 11 ? "an ace" : "a " + a.up;
  const ends = ["17", "18", "19", "20", "21"];
  let comp = '<table class="t"><tr><th>card</th>';
  for (const c of a.composition) comp += "<th>" + (c.value === 11 ? "A" : c.value) + "</th>";
  comp += "</tr><tr><td>left</td>";
  for (const c of a.composition) comp += "<td>" + c.left + "</td>";
  comp += '</tr><tr class="hl"><td>chance</td>';
  for (const c of a.composition) comp += "<td>" + Math.round(c.p * 100) + "</td>";
  comp += "</tr></table>";

  let dist = '<table class="t"><tr><th>ends on</th>' + ends.map((e) => "<th>" + e + "</th>").join("") +
    "<th>bust</th></tr><tr class=\"hl\"><td>chance</td>" +
    ends.map((e) => "<td>" + Math.round((a.dealer_dist[e] || 0) * 100) + "</td>").join("") +
    "<td>" + Math.round(a.dealer_bust * 100) + "</td></tr></table>";

  const legal = a.options.filter((o) => o.legal);
  const span = Math.max(1, ...legal.map((o) => Math.abs(o.ev)));
  const rows = a.options.map((o) => {
    if (!o.legal)
      return '<div class="evrow no"><div class="nm">' + cap(MOVE[o.move]) +
        '</div><div class="tk"></div><div class="vl">n/a</div></div>';
    const w = (Math.abs(o.ev) / span) * 50, left = o.ev >= 0 ? 50 : 50 - w;
    return '<div class="evrow' + (o.move === a.best_move ? " win" : "") + '"><div class="nm">' +
      cap(MOVE[o.move]) + '</div><div class="tk"><u></u><i style="left:' + left + "%;width:" + w +
      '%"></i></div><div class="vl">' + ev(o.ev) + "</div></div>";
  }).join("");

  const evStand = a.options[0].ev, evHit = a.options[1].ev;
  box.innerHTML =
    step(1, "What is still in the shoe",
      "<p>Everything below is worked out from these " + a.unseen + " cards you have not seen. " +
      "The other players\u2019 cards are already gone from the count.</p>" + comp) +
    step(2, "Where the dealer is likely to finish, starting from " + up,
      "<p>The dealer has no choices \u2014 they must draw until they reach 17. So you can work out " +
      "every card sequence they might take and add up how often each ending happens. " +
      "This assumes they do not already have a blackjack, because then the hand would be over.</p>" + dist) +
    step(3, "What standing on " + a.total + " is worth",
      '<div class="eq">they bust (' + pct(a.dealer_bust, 1) + ") + they finish under you (" +
      pct(a.p_below, 1) + ") \u2212 they beat you (" + pct(a.p_above, 1) + ")<br>= <b class=\"" +
      (evStand >= 0 ? "pos" : "neg") + '">' + ev(evStand) + "</b> per dollar bet</div>" +
      "<p>Ties (" + pct(a.p_tie, 1) + ") give your money back, so they count as nothing either way.</p>") +
    step(4, "What taking a card is worth",
      '<div class="eq">chance this card breaks you = <b>' + pct(a.bust, 1) + "</b><br>" +
      "value of drawing = <b class=\"" + (evHit >= 0 ? "pos" : "neg") + '">' + ev(evHit) + "</b></div>" +
      "<p>The value after drawing already assumes you go on to play the new hand correctly, " +
      "so this is a fair comparison rather than a one-card snapshot.</p>") +
    step(5, "Every option side by side", rows +
      '<p style="margin-top:8px">These are per dollar of your original bet. Doubling and splitting ' +
      "put a second dollar at risk, so they can go past \u00b11.</p>") +
    step(6, "The verdict",
      "<p>The chart says <kbd>" + MOVE[a.chart_move] + "</kbd>. The cards left say <kbd>" +
      MOVE[a.best_move] + "</kbd>" +
      (a.deviation
        ? ", which is a real disagreement worth " + a.dev_gap.toFixed(4) + " per dollar."
        : " \u2014 they agree.") + "</p>" +
      (a.cost > 0.0005
        ? '<div class="note bad">Your choice gave up <b>' + a.cost.toFixed(4) +
          "</b> per dollar. Do that a hundred times and it is <b>" + (a.cost * 100).toFixed(1) +
          " dollars per dollar bet</b>. For comparison, the casino\u2019s whole built-in advantage on a " +
          "correctly played hand is about half a cent.</div>"
        : '<div class="note ok">Nothing given up. That was the best available play.</div>'));
}

/* ---------------- intuition ---------------- */
function drawIntu() {
  const box = $("intu"), e = S.explanation, a = S.analysis;
  if (!e) {
    box.innerHTML =
      '<p class="idle">This side is the version you can carry to a real table \u2014 the picture, the ' +
      "comparison, and one line worth memorising. The other side proves it; this side makes it stick." +
      "<br><br>Anything <span class=\"gt\" data-term=\"house edge\">underlined like this</span> is " +
      "explained if you click it.</p>";
    return;
  }
  const terms = e.terms || [];
  box.innerHTML =
    '<div class="hook">' + link(e.hook, terms) + "</div>" +
    '<div class="prose">' + e.paragraphs.map((p) => "<p>" + link(p, terms) + "</p>").join("") + "</div>" +
    '<div class="pic">' + e.picture + "</div>" +
    (a && a.deviation
      ? '<div class="note"><b>Right now the cards disagree with the chart.</b> With the count at ' +
        (a.true_count >= 0 ? "+" : "\u2212") + Math.abs(a.true_count).toFixed(1) + ", what is left makes <b>" +
        MOVE[a.best_move] + "</b> better by " + a.dev_gap.toFixed(3) +
        ' per dollar. Learn the chart first \u2014 these <span class="gt" data-term="deviation">deviations</span> ' +
        "are worth a fraction of a percent, and only if you are tracking the cards properly.</div>"
      : "") +
    '<div class="recall"><span>WORTH MEMORISING</span><p>' + e.remember + "</p></div>";
}

/* wrap known glossary terms in the prose so they can be clicked */
function link(text, terms) {
  let out = esc(text);
  for (const t of terms) {
    const re = new RegExp("\\b(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")\\b", "i");
    if (re.test(out) && GLOSSARY[t])
      out = out.replace(re, '<span class="gt" data-term="' + t + '">$1</span>');
  }
  return out;
}

function wireTerms() {
  document.querySelectorAll(".gt").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const g = GLOSSARY[el.dataset.term];
      if (!g) return;
      const p = $("pop");
      p.innerHTML = "<h5>" + cap(g.term) + '</h5><div class="s">' + g.short + '</div><div class="l">' +
        g.long + "</div>" + (g.example ? '<div class="e">' + g.example + "</div>" : "");
      p.hidden = false;
      const r = el.getBoundingClientRect();
      p.style.left = Math.max(10, Math.min(window.innerWidth - 350, r.left - 20)) + "px";
      p.style.top = (r.bottom + 8 + 260 > window.innerHeight ? Math.max(10, r.top - 250) : r.bottom + 8) + "px";
    };
  });
  document.onclick = () => { $("pop").hidden = true; };
}

/* ---------------- betting tab ---------------- */
function viewBetting() {
  const b = S.bet_check;
  const st = STATS || {};
  const names = { chase: "Raised the bet after losing", press: "Doubled up after winning",
    over: "Bet more than 15% of your money", big: "Bet more than 5% of your money",
    undercap: "Table is too expensive for your bankroll", watch: "Bet small on a good count" };
  const tc = S.true_count, edge = -0.005 + 0.005 * Math.max(0, tc - 1);
  const bankroll = S.bankroll || 1;

  $("wrap").innerHTML =
    '<div class="cols">' +
    '<div><div class="panel"><div class="phead"><h2>HOW MUCH TO PUT OUT</h2></div><div class="pbody">' +
    step(1, "Do you have any advantage right now?",
      '<div class="eq">count per deck <b>' + (tc >= 0 ? "+" : "\u2212") + Math.abs(tc).toFixed(1) + "</b><br>" +
      'your edge \u2248 <b class="' + (edge >= 0 ? "pos" : "neg") + '">' + (edge * 100).toFixed(2) +
      "%</b> of every dollar</div><p>The rule of thumb: you start about half a percent behind, and each " +
      'point of <span class="gt" data-term="true count">count per deck</span> above +1 gives you back ' +
      "roughly half a percent. Below that, you are a losing bettor no matter how well you play the cards.</p>") +
    step(2, "So what size does that justify?",
      edge > 0
        ? '<div class="eq">edge \u00f7 swing = ' + edge.toFixed(4) + " \u00f7 1.30 = <b>" +
          pct(edge / 1.3, 2) + "</b> of your money<br>= <b>" + money(bankroll * (edge / 1.3)) + "</b></div>" +
          '<p>This is the <span class="gt" data-term="kelly">Kelly</span> size, which grows money fastest ' +
          "but swings hard. Most people who do this seriously bet a half or a third of it.</p>"
        : '<div class="eq">no advantage \u2192 the size that grows money fastest is <b>$0</b></div>' +
          "<p>That is the honest answer, and a useless one if you came here to play. So the least-bad " +
          "size is the table minimum, <b>" + money(S.config.table_min) + "</b>, because it keeps the " +
          'amount you are handing over per hour as small as possible.</p>') +
    step(3, "Can you survive that size?",
      '<div class="eq">your money = <b>' + (bankroll / (b ? b.amount : S.config.table_min)).toFixed(1) +
      "</b> bets<br>a typical hand swings about <b>1.14 bets</b> either way</div>" +
      (b
        ? '<div class="kv"><span>Chance you double your money before losing it</span><b>' + pct(b.p_double) + "</b></div>" +
          '<div class="kv"><span>Chance you eventually lose it all if you keep playing</span><b>' +
          (b.edge > 0 ? pct(b.p_ruin) : "100%") + "</b></div>"
        : '<p class="idle">Place a bet and these fill in.</p>') +
      "<p style=\"margin-top:8px\">" + (b && b.edge > 0
        ? "Having a real advantage is the only thing that makes going broke avoidable at all."
        : 'With no advantage, going broke is not a risk \u2014 it is a certainty given enough hands. ' +
          'The only questions are how long it takes and whether you enjoyed it. That is what ' +
          '<span class="gt" data-term="risk of ruin">risk of ruin</span> means.') + "</p>") +
    "</div></div></div>" +

    '<div class="mid"><div class="panel"><div class="phead"><h2>YOUR LAST BET</h2><em>' +
    (b ? money(b.amount) : "none yet") + "</em></div><div class=\"pbody\">" +
    (b
      ? '<div class="two"><div><div class="big ' + (b.ok ? "up" : "down") + '">' +
        (b.ok ? "Fine" : "Too big") + '</div><div class="sub">verdict on the size</div></div>' +
        '<div><div class="big">' + money(b.suggested) + '</div><div class="sub">what the maths supports</div></div></div>' +
        '<div class="bar2"><i class="' + (b.share > 0.15 ? "b" : b.share > 0.05 ? "w" : "") +
        '" style="width:' + Math.min(100, b.share * 400) + '%"></i></div>' +
        '<div class="kv"><span>Share of your money</span><b>' + pct(b.share, 1) + "</b></div>" +
        '<div class="kv"><span>How many bets deep you are</span><b>' + b.units.toFixed(1) + "</b></div>" +
        b.flags.map((f) => '<div class="note ' + (f.level === "bad" ? "bad" : f.level === "info" ? "ok" : "") + '">' + f.text + "</div>").join("") +
        (b.flags.some((f) => f.level !== "info") ? "" :
          '<div class="note ok">Nothing to flag. Sensible against your bankroll, and not driven by what happened last hand.</div>')
      : '<p class="idle">Place a bet on the Table tab and it gets scored here \u2014 how big it is next to ' +
        "your money, whether it is reacting to the last result, and what it does to your chances of lasting the session.</p>") +
    "</div></div></div>" +

    '<div><div class="panel"><div class="phead"><h2>YOUR BETTING RECORD</h2></div><div class="pbody">' +
    '<div class="big">' + (st.bet_accuracy == null ? "\u2014" : Math.round(st.bet_accuracy * 100) + "%") +
    '</div><div class="sub">sensible bets, out of ' + (st.bets || 0) + "</div>" +
    (st.bet_flags && Object.keys(st.bet_flags).length
      ? '<div style="margin-top:14px">' + Object.entries(st.bet_flags).sort((a, c) => c[1] - a[1])
          .map(([k, n]) => '<div class="miss"><div>' + (names[k] || k) + "</div><span>" + n + "\u00d7</span></div>").join("") + "</div>"
      : '<p class="idle" style="margin-top:12px">No sizing problems recorded yet.</p>') +
    '<div class="pic" style="margin-top:16px">There are two ways to lose money at this game: ' +
    "<b>playing the cards wrong</b> and <b>betting the wrong amount</b>. The first costs about half a " +
    "percent. The second is what actually empties wallets \u2014 it is the difference between losing " +
    "slowly and losing everything in twenty minutes.</div>" +
    '<div class="recall"><span>WORTH MEMORISING</span><p>Bet size should follow the cards, never the last result.</p></div>' +
    "</div></div></div></div>";
  $("foot").innerHTML =
    "The survival numbers use a standard random-walk approximation with a swing of 1.14 bets per hand, " +
    "which is the usual figure for blackjack played by the chart including doubles and splits.";
}

/* ---------------- ledger ---------------- */
function viewLedger() {
  const st = STATS || {};
  const life = st.lifetime || 0;
  const curve = st.curve || [];
  $("wrap").innerHTML =
    '<div class="cols">' +
    '<div><div class="panel"><div class="phead"><h2>MONEY</h2><em>' + esc(ACCOUNT.name) + "</em></div>" +
    '<div class="pbody"><div class="big ' + (life > 0 ? "up" : life < 0 ? "down" : "") + '">' +
    money(life) + '</div><div class="sub">all time, across ' + (st.buy_ins || 1) + " buy-in" +
    ((st.buy_ins || 1) > 1 ? "s" : "") + " of $100</div>" + spark(curve) +
    '<div class="kv"><span>Rounds played</span><b>' + (st.rounds || 0) + "</b></div>" +
    '<div class="kv"><span>Total put out</span><b>' + money(st.wagered || 0) + "</b></div>" +
    '<div class="kv"><span>Kept per dollar bet</span><b class="' +
    (st.return_per_dollar >= 0 ? "up" : "down") + '">' +
    (st.return_per_dollar == null ? "\u2014" : pct(st.return_per_dollar, 2)) + "</b></div>" +
    '<div class="kv"><span>Money on the table now</span><b>' + money(S.bankroll) + "</b></div>" +
    '<div class="note">Played by the chart, this settles at about <b>\u22120.5%</b> in the long run. ' +
    "If your number is far off that in either direction it is almost certainly luck, not skill \u2014 " +
    'that is <span class="gt" data-term="variance">variance</span>, and it takes tens of thousands of ' +
    "hands to wash out. The accuracy number on the right settles far faster.</div>" +
    "</div></div></div>" +

    '<div class="mid"><div class="panel"><div class="phead"><h2>SKILL</h2></div><div class="pbody">' +
    '<div class="two"><div><div class="big ' +
    (st.accuracy == null ? "" : st.accuracy >= 0.95 ? "up" : st.accuracy < 0.8 ? "down" : "") + '">' +
    (st.accuracy == null ? "\u2014" : Math.round(st.accuracy * 100) + "%") +
    '</div><div class="sub">matched the chart</div></div>' +
    '<div><div class="big">' + (st.shoe_accuracy == null ? "\u2014" : Math.round(st.shoe_accuracy * 100) + "%") +
    '</div><div class="sub">matched the actual cards</div></div></div>' +
    (st.recent_accuracy != null
      ? '<div class="kv" style="margin-top:12px"><span>Last 50 decisions</span><b>' +
        Math.round(st.recent_accuracy * 100) + "%</b></div>" : "") +
    '<div class="kv"><span>Decisions scored</span><b>' + (st.decisions || 0) + "</b></div>" +
    '<div class="kv"><span>Value given away by mistakes</span><b class="down">' +
    (st.ev_given_up || 0).toFixed(2) + "</b></div>" +
    '<h2 style="font-size:10px;letter-spacing:.12em;color:var(--dim);margin:18px 0 8px">WHAT YOU KEEP GETTING WRONG</h2>' +
    ((st.weak_spots || []).length
      ? st.weak_spots.map((w) => '<div class="miss"><div>' + w.cell + "</div><span>" + w.misses + "\u00d7</span></div>").join("")
      : '<p class="idle">Nothing wrong yet.</p>') +
    "</div></div></div>" +

    '<div><div class="panel"><div class="phead"><h2>THIS PROFILE</h2></div><div class="pbody">' +
    '<div class="kv"><span>Stored in</span><b>blackjack.db</b></div>' +
    '<div class="kv"><span>Started</span><b>' +
    (st.account ? new Date(st.account.created * 1000).toLocaleDateString() : "\u2014") + "</b></div>" +
    '<div class="moves" style="margin-top:14px"><button class="mv" onclick="switchPlayer()">Switch player</button>' +
    '<button class="mv" onclick="wipe()">Delete this profile</button></div>' +
    '<div class="pic" style="margin-top:16px">Two numbers doing two different jobs. <b>Accuracy</b> ' +
    "measures you \u2014 it moves when you get better and sits still when you do not. <b>All time</b> " +
    "measures luck, with a small steady leak underneath it. Judge yourself on the first. Look at the " +
    "second to remember who paid for the building.</div>" +
    "</div></div></div></div>";
  $("foot").innerHTML =
    "When your money drops below one table minimum you get another $100 automatically, counted as a fresh " +
    "buy-in. The all-time figure is everything you have now minus everything you have been given, so it " +
    "never resets \u2014 it is the only honest scoreboard.";
}

function spark(vals) {
  if (!vals || vals.length < 2) return '<div style="height:56px"></div>';
  const w = 280, h = 48;
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), range = hi - lo || 1;
  const pts = vals.map((v, i) => ((i / (vals.length - 1)) * w).toFixed(1) + "," + (h - ((v - lo) / range) * h).toFixed(1)).join(" ");
  const zero = (h - ((0 - lo) / range) * h).toFixed(1);
  return '<svg viewBox="0 0 ' + w + " " + h + '" width="100%" height="56" style="margin:10px 0" role="img" ' +
    'aria-label="Money over the last ' + vals.length + ' rounds"><line x1="0" y1="' + zero + '" x2="' + w +
    '" y2="' + zero + '" stroke="#25302f"/><polyline points="' + pts + '" fill="none" stroke="' +
    (vals[vals.length - 1] >= 0 ? "#4bbd83" : "#d76a56") + '" stroke-width="1.5"/></svg>';
}

async function switchPlayer() { window.name = ""; const { accounts } = await api("/api/accounts"); gate(accounts); }
async function wipe() {
  if (!confirm("Delete " + ACCOUNT.name + " and all their history? This cannot be undone.")) return;
  await api("/api/accounts/delete", { account: ACCOUNT.id });
  window.name = ""; boot();
}

/* ---------------- glossary ---------------- */
function viewGlossary() {
  const groups = {};
  GLOSSARY_LIST.forEach((g) => (groups[g.group] = groups[g.group] || []).push(g));
  $("wrap").innerHTML =
    '<div style="max-width:760px;margin:0 auto"><div class="panel"><div class="phead">' +
    "<h2>EVERY TERM THIS APP USES</h2><em>" + GLOSSARY_LIST.length + " entries</em></div>" +
    '<div class="pbody"><p class="idle" style="margin-bottom:22px">Nothing here assumes you already ' +
    "know the game. Anything underlined elsewhere in the app opens the same explanation in a small " +
    "box where you are standing.</p>" +
    Object.entries(groups).map(([name, items]) =>
      '<div class="gsec"><h3>' + name.toUpperCase() + "</h3>" +
      items.map((g) => '<div class="gitem"><h4>' + cap(g.term) + '</h4><div class="s">' + g.short +
        '</div><div class="l">' + g.long + "</div>" +
        (g.example ? '<div class="e">' + g.example + "</div>" : "") + "</div>").join("") + "</div>"
    ).join("") + "</div></div></div>";
  $("foot").innerHTML = "";
}

/* ---------------- setup ---------------- */
function viewSetup() {
  const c = S.config;
  const opt = (v, cur, label) => '<option value="' + v + '"' + (String(cur) === String(v) ? " selected" : "") + ">" + label + "</option>";
  $("wrap").innerHTML =
    '<div style="max-width:520px;margin:0 auto"><div class="panel"><div class="phead"><h2>THE TABLE</h2></div>' +
    '<div class="pbody">' +
    '<div class="field"><label>OTHER PEOPLE AT THE TABLE</label><select id="s_others">' +
    [0, 1, 2, 3, 4, 5].map((n) => opt(n, c.others, n === 0 ? "Just you" : n + " other" + (n > 1 ? "s" : ""))).join("") +
    "</select></div>" +
    '<div class="field"><label>SMALLEST BET ALLOWED</label><select id="s_min">' +
    [5, 10, 15, 25, 50].map((n) => opt(n, c.table_min, "$" + n)).join("") + "</select></div>" +
    '<div class="field"><label>DECKS IN THE SHOE</label><select id="s_decks">' +
    [1, 2, 6, 8].map((n) => opt(n, c.decks, n + (n === 1 ? " deck" : " decks"))).join("") + "</select></div>" +
    '<div class="field"><label>HOW DEEP THEY DEAL BEFORE RESHUFFLING</label><select id="s_pen">' +
    [[0.5, "Half the shoe \u2014 shallow"], [0.75, "Three quarters \u2014 typical"],
     [0.9, "Nearly all of it \u2014 deep"], [0.02, "Reshuffled every hand \u2014 a shuffling machine"]]
      .map(([v, l]) => opt(v, c.penetration, l)).join("") + "</select></div>" +
    '<button class="mv go" style="width:100%" onclick="saveSetup()">Apply and reshuffle</button>' +
    '<div class="note" style="margin-top:16px"><b>What the number of players actually changes.</b> ' +
    "Not your correct play. Other people\u2019s cards never affect which move is right for your hand \u2014 " +
    "if anyone tells you a bad player at third base cost them the hand, they are wrong. What it does " +
    "change is how quickly the shoe gets used up, and therefore how far the mix of remaining cards " +
    'drifts from normal. That drift is the whole basis of <span class="gt" data-term="true count">counting</span>. ' +
    "Set the last option to a shuffling machine and it stops mattering entirely, which is exactly why " +
    "casinos bought them.</div></div></div></div>";
  $("foot").innerHTML = "";
}
async function saveSetup() {
  await send("/api/config", {
    others: +$("s_others").value, table_min: +$("s_min").value,
    decks: +$("s_decks").value, penetration: +$("s_pen").value,
  });
  PENDING_BET = S.config.table_min;
  TAB = "table"; draw();
}

/* ---------------- keyboard ---------------- */
document.addEventListener("keydown", (e) => {
  if (!S || TAB !== "table" || e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  const k = e.key.toLowerCase();
  if (S.phase === "play") {
    if (k === "h") doMove("H");
    if (k === "s") doMove("S");
    if (k === "d" && S.can_double) doMove("D");
    if (k === "p" && S.can_split) doMove("P");
  } else if (e.code === "Space") {
    e.preventDefault();
    if (S.phase === "bet") doBet();
    else if (S.phase === "settled") doNext();
  }
});

boot();
