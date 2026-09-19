/* app.js — talks to the Python server, draws the table. */

const $ = (id) => document.getElementById(id);
const MOVE = { H: "hit", S: "stand", D: "double", P: "split" };
const PAST = { H: "hit", S: "stood", D: "doubled", P: "split" };
const CODE_NAME = { H: "Hit", S: "Stand", D: "Double", Ds: "Double / stand", P: "Split" };

const TABS = ["table", "betting", "chart", "quiz", "analysis", "account", "setup"];

let ACCOUNT = null;          // {id, name, chips, ...}
let S = null;                // last snapshot from the server
let STATS = null;            // /api/stats, loaded when a tab needs it
let CHART = null;            // /api/chart
let GLOSSARY = {};
let GLOSSARY_LIST = [];
let TAB = "table";
let PENDING_BET = 0;
let BUY_IN = 0;
let COUNT_RESULT = null;     // last count check, kept on screen until dismissed
let QUIZ = null;             // live quiz state
let QUIZ_SETUP = { mode: "weak", length: 10, sections: ["hard", "soft", "pair"],
                   upcards: [], only: "all" };
let SIM = null, SIM_BUSY = false;
let CALC = null;
let CHART_CELL = null, CHART_OVERLAY = true;

const money = (n) =>
  (n < 0 ? "−$" : "$") + Math.abs(+n || 0).toFixed(Math.abs(+n || 0) % 1 ? 2 : 0);
const pct = (x, d = 0) => (x == null ? "—" : (x * 100).toFixed(d) + "%");
const ev = (n) => (n < 0 ? "−" : "+") + Math.abs(n).toFixed(3);
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
const esc = (s) =>
  String(s).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
const num = (n) => (+n || 0).toLocaleString();
const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");
const day = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "—");
const upLabel = (u) => (u === 11 ? "A" : String(u));
const cls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");

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
  gate(accounts);
}

function gate(accounts) {
  $("root").innerHTML =
    '<div class="gate"><h1>Blackjack <b>trainer</b></h1>' +
    '<p class="lede">Play real hands. Every decision gets scored against the strategy chart, ' +
    "and the score is weighted so the hands you already know stop propping it up. " +
    "Everything is stored in a file on this machine and goes nowhere else.</p>" +
    (accounts.length
      ? '<div class="glab">WHO ARE YOU</div>' + accounts
          .map(
            (a) =>
              '<div class="arow" onclick="open_account(' + a.id + ')"><div><b>' + esc(a.name) +
              "</b><span>" + a.sessions + " session" + (a.sessions === 1 ? "" : "s") + " · " +
              num(a.hands) + " hands · " +
              (a.accuracy === null ? "no decisions yet" : a.accuracy + "% accurate") +
              '</span></div><div style="text-align:right"><b>' + money(a.chips) +
              '</b><span class="' + cls(a.lifetime) + '">' + money(a.lifetime) + " all time</span></div></div>"
          )
          .join("")
      : "") +
    '<div class="field" style="margin-top:18px"><label>NEW PLAYER</label>' +
    '<input type="text" id="nm" placeholder="Your name" maxlength="32"></div>' +
    '<button class="mv go" style="width:100%" onclick="make_account()">Create an account</button>' +
    '<p class="fine">A new account starts with nothing. You choose your own starting chips ' +
    "the first time you sit down; after that you either bring winnings back to the table or " +
    "earn more by answering questions.</p></div>";
  const input = $("nm");
  if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") make_account(); });
}

async function make_account() {
  const name = $("nm").value;
  const { id } = await api("/api/accounts", { name });
  open_account(id);
}

async function open_account(id) {
  window.name = "bj:" + id;
  S = await api("/api/state?account=" + id);
  if (S.error) { window.name = ""; return boot(); }
  ACCOUNT = S.account;
  STATS = null; CHART = null; QUIZ = null;
  PENDING_BET = S.config.table_min;
  BUY_IN = S.buy_in_choices[0];
  TAB = "table";
  draw();
}

function logout() {
  window.name = "";
  ACCOUNT = null; S = null; STATS = null; CHART = null; QUIZ = null;
  boot();
}

async function needStats(force) {
  if (!STATS || force) STATS = await api("/api/stats?account=" + ACCOUNT.id);
  return STATS;
}

/* Fetch stats for a view that has already rendered without them, and redraw once
   they arrive. Only redraws if they were actually missing -- redrawing on a cache
   hit would call straight back into the same view and never stop. */
function statsThenRedraw(tab, stillWanted) {
  if (STATS) return;
  needStats().then(() => { if (TAB === tab && (!stillWanted || stillWanted())) draw(); });
}
async function needChart(force) {
  if (!CHART || force) CHART = await api("/api/chart?account=" + ACCOUNT.id);
  return CHART;
}

/* ---------------- actions ---------------- */
async function send(path, body) {
  const next = await api(path, Object.assign({ account: ACCOUNT.id }, body || {}));
  if (next.error) { toast(next.error); return next; }
  S = next;
  ACCOUNT = S.account;
  STATS = null;                       // anything that changes the table changes the stats
  if (S.out_of_money) toast("That is below the table minimum. Stand up and buy in again.");
  draw();
  return next;
}
const doBet = () => send("/api/bet", { amount: PENDING_BET });
const doMove = (m) => send("/api/action", { move: m });
const doIns = (t) => send("/api/insurance", { take: t });
/* a new round clears the last count check, so it cannot sit there stale */
const doNext = () => { COUNT_RESULT = null; return send("/api/next"); };
const addBet = (v) => { PENDING_BET = Math.min(S.bankroll, PENDING_BET + v); draw(); };
const clearBet = () => { PENDING_BET = S.config.table_min; draw(); };

async function sitDown() {
  const r = await send("/api/session/start", { buy_in: BUY_IN });
  if (!r.error) PENDING_BET = S.config.table_min;
}
/* ---------------- asking before something irreversible ----------------
   window.confirm() is blocked outright in some embedded browsers — it returns
   false instantly without ever drawing a dialog, which silently turned "stand
   up and cash out" into a button that did nothing at all. This is the same
   question asked in the page, where nothing can suppress it. */
function ask(title, body, okLabel, danger) {
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.className = "modal";
    wrap.innerHTML =
      '<div class="mbox" role="dialog" aria-modal="true"><h3>' + esc(title) + "</h3>" +
      "<p>" + esc(body) + "</p>" +
      '<div class="mbtns"><button class="mv" data-no>Cancel</button>' +
      '<button class="mv ' + (danger ? "bad" : "go") + '" data-yes>' + esc(okLabel || "Yes") +
      "</button></div></div>";

    const done = (v) => {
      document.removeEventListener("keydown", key, true);
      wrap.remove();
      resolve(v);
    };
    const key = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
      if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); done(true); }
    };

    wrap.querySelector("[data-no]").onclick = () => done(false);
    wrap.querySelector("[data-yes]").onclick = () => done(true);
    wrap.onclick = (e) => { if (e.target === wrap) done(false); };
    document.addEventListener("keydown", key, true);   // ahead of the table shortcuts
    document.body.appendChild(wrap);
    wrap.querySelector("[data-yes]").focus();
  });
}

async function standUp() {
  const yes = await ask("Stand up?",
    "Your " + money(S.bankroll) + " goes back into chips and the session is closed.",
    "Stand up");
  if (!yes) return;
  const r = await send("/api/session/end", {});
  if (r.closed) {
    toast("Session " + r.closed.number + " closed — " + money(r.closed.cash_out) +
          " back in chips, " + money(r.closed.net) + " on the session.");
  }
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg;
  el.title = "click to dismiss";
  el.onclick = () => el.remove();
  document.body.appendChild(el);
  /* Long messages were vanishing mid-sentence. Roughly forty milliseconds a
     character on top of a four second floor, capped so nothing sticks forever,
     and a click clears it early. */
  const ms = Math.min(20000, 4000 + String(msg).length * 40);
  setTimeout(() => el.remove(), ms);
}

/* ---------------- shell ---------------- */
function draw() {
  const life = (S.all_time && S.all_time.lifetime) || 0;
  const worth = S.all_time ? S.all_time.worth : ACCOUNT.chips;
  $("root").innerHTML =
    '<div class="bar"><div class="logo">Blackjack <b>trainer</b></div>' +
    '<div class="tabs">' +
    TABS.map((t) => '<button class="' + (TAB === t ? "on" : "") + '" onclick="go(\'' + t + "')\">" + cap(t) + "</button>").join("") +
    "</div>" +
    '<div class="stats">' +
    (S.phase !== "idle"
      ? '<div class="stat"><b>' + money(S.bankroll) + "</b><span>ON THE TABLE</span></div>" : "") +
    '<div class="stat"><b>' + money(ACCOUNT.chips) + "</b><span>CHIPS</span></div>" +
    '<div class="stat"><b class="' + cls(life) + '">' + money(life) + "</b><span>ALL TIME</span></div>" +
    '<div class="stat who" title="' + esc(ACCOUNT.name) + '"><b>' + esc(ACCOUNT.name) +
    '</b><span>' + money(worth) + " TOTAL</span></div>" +
    "</div></div>" +
    '<div class="wrap" id="wrap"><p class="idle" style="padding:30px">Loading…</p></div>' +
    '<div class="foot" id="foot"></div>';
  const view = { table: viewTable, betting: viewBetting, chart: viewChart, quiz: viewQuiz,
                 analysis: viewAnalysis, account: viewAccount, setup: viewSetup }[TAB];
  Promise.resolve(view()).then(wireTerms);
}
function go(t) { TAB = t; draw(); }

/* =======================================================================
   TABLE
   ======================================================================= */
function viewTable() {
  if (S.phase === "idle") return viewSitDown();
  $("wrap").innerHTML =
    '<div class="cols">' +
    '<div><div class="panel"><div class="phead"><h2>HOW TO THINK ABOUT IT</h2><em id="uc"></em></div>' +
    '<div class="pbody" id="intu"></div></div></div>' +
    '<div class="mid" id="mid"></div>' +
    '<div id="side"></div></div>';
  drawTable(); drawIntu(); drawSide();
  $("foot").innerHTML =
    "<b>" + S.config.decks + " decks · " + S.config.others + " other player" +
    (S.config.others === 1 ? "" : "s") + " · " + money(S.config.table_min) + " to " +
    money(S.config.table_max) + " · " + ruleLine(S.rules) + ".</b><br>" +
    "Split a hand and the dealer deals one card to the first half only — you play that hand out " +
    "before the second is touched, exactly as at a real table. " +
    "Keyboard: H hit, S stand, D double, P split, space to deal.";
}

function ruleLine(r) {
  return [
    "dealer " + (r.hit_soft_17 ? "hits" : "stands on") + " soft 17",
    "blackjack pays " + (r.blackjack_pays === 1.5 ? "3 to 2" : "6 to 5"),
    r.das ? "double after split" : "no double after split",
    "up to " + r.max_hands + " hands",
    r.resplit_aces ? "aces may be re-split" : "split aces get one card",
  ].join(" · ");
}

function viewSitDown() {
  const first = ACCOUNT.first_time;
  const chips = ACCOUNT.chips;
  const min = S.min_buy_in;
  const choices = first
    ? S.buy_in_choices
    : [min * 5, min * 10, min * 20, min * 40, Math.floor(chips)].filter(
        (v, i, a) => v >= min && v <= chips && a.indexOf(v) === i);
  if (!first && !choices.length && chips >= min) choices.push(Math.floor(chips));
  if (choices.length && choices.indexOf(BUY_IN) < 0) BUY_IN = choices[choices.length - 1];

  $("wrap").innerHTML =
    '<div class="single"><div class="panel"><div class="phead"><h2>SIT DOWN</h2><em>' +
    money(chips) + " in chips</em></div><div class=\"pbody\">" +
    (first
      ? '<p class="lede2">This is your first session, so you get to choose what you are ' +
        "carrying. Pick the number you would actually walk in with — it decides how much of " +
        "a losing run you can absorb before the evening is over, and that matters far more " +
        "than anything else on this screen.</p>"
      : chips < min
        ? '<div class="note bad"><b>You are out of chips.</b> The smallest bet at this table is ' +
          money(min) + " and you have " + money(chips) + ". Win some back on the " +
          '<b>Quiz</b> tab — ten questions, ' + money(10) + " a correct answer — or lower the " +
          "table minimum in <b>Setup</b>.</div>" +
          '<div class="moves" style="margin-top:14px">' +
          '<button class="mv go" onclick="go(\'quiz\');QUIZ_SETUP.mode=\'chips\'">Play for chips</button>' +
          '<button class="mv" onclick="go(\'setup\')">Change the table</button></div>'
        : '<p class="lede2">Buying in moves chips from your stack onto the table. Whatever is ' +
          "left when you stand up comes back. Nothing is topped up for you — if you lose it, " +
          "you earn the next lot.</p>") +
    (choices.length
      ? '<div class="buyins">' + choices.map((v) =>
          '<button class="buyin' + (BUY_IN === v ? " on" : "") + '" onclick="BUY_IN=' + v +
          ';draw()"><b>' + money(v) + "</b><span>" + Math.floor(v / S.config.table_min) +
          " bets</span></button>").join("") + "</div>" +
        '<div class="betline">Buying in for <b>' + money(BUY_IN) + "</b> at a " +
        money(S.config.table_min) + " table — that is <b>" +
        Math.floor(BUY_IN / S.config.table_min) + " minimum bets</b> deep. " +
        (BUY_IN / S.config.table_min < 20
          ? "Under twenty bets is a short evening; a normal losing run ends it."
          : "Forty bets or more is the usual guidance for sitting down comfortably.") + "</div>" +
        '<button class="mv go" style="width:100%" onclick="sitDown()">' +
        (first ? "Take " + money(BUY_IN) + " and sit down" : "Buy in for " + money(BUY_IN)) +
        "</button>"
      : "") +
    "</div></div>" + sessionHistoryCard() + "</div>";
  $("foot").innerHTML = "";
  statsThenRedraw("table", () => S.phase === "idle");
}

function sessionHistoryCard() {
  const list = (STATS && STATS.sessions) || [];
  if (!list.length) return "";
  return '<div class="panel" style="margin-top:16px"><div class="phead"><h2>YOUR SESSIONS</h2><em>' +
    list.length + " so far</em></div><div class=\"pbody\">" +
    sessionTable(list.slice(0, 8)) + "</div></div>";
}

/* ---------------- dealing ----------------
   Cards used to animate on every render, so taking one card re-dealt the whole
   hand. ONSCREEN remembers how many each spot had last time; only the ones past
   that are new, and only those slide in from the shoe. A spot that shrinks is a
   fresh hand, so everything in it counts as new again. */
let ONSCREEN = {};
let HOLE_WAS_HIDDEN = true;      // so the hole card can be turned over, not swapped

function freshFrom(spot, n) {
  const before = ONSCREEN[spot] || 0;
  ONSCREEN[spot] = n;
  return n < before ? 0 : before;
}

const cardEl = (c, down, fresh, order, flip) => {
  const cls = "card" + (down ? " down" : c && c.red ? " red" : "") +
    (fresh ? " fresh" : flip ? " flip" : "");
  const delay = fresh && order ? ' style="animation-delay:' + order * 110 + 'ms"' : "";
  return '<div class="' + cls + '"' + delay + ">" +
    (down ? "" : '<i>' + c.suit + "</i>" + c.rank) + "</div>";
};
const backEl = () => '<div class="card down pending"></div>';
/* A ten is a ten. It used to be abbreviated to "T" to fit the small card, which
   reads as a rank that does not exist. The card is wider now instead. */
const miniEl = (c, fresh, order) =>
  '<div class="mc' + (c.red ? " red" : "") + (c.rank === "10" ? " ten" : "") +
  (fresh ? " fresh" : "") + '"' +
  (fresh && order ? ' style="animation-delay:' + order * 90 + 'ms"' : "") + ">" +
  c.rank + "</div>";

/* ---------------- the count ----------------
   Hidden by default. The button does not simply show it: it asks you for it
   first, so peeking always costs you a graded answer and the readout can never
   quietly become a substitute for counting. */
function countBar() {
  if (S.count_check) {
    const key = "if(event.key==='Enter'){event.preventDefault();answerCount();}";
    let h = '<span class="cask">' +
      (S.count_check.reason === "interrupted" ? "COUNT CHECK · " : "") + "RUNNING?</span>" +
      '<input class="cin" id="cans" type="text" inputmode="numeric" autocomplete="off" ' +
      'placeholder="+0" onkeydown="' + key + '">';
    if (S.count_check.ask_decks) {
      h += '<span class="cask thin">DECKS LEFT?</span>' +
        '<input class="cin" id="cdecks" type="text" inputmode="decimal" autocomplete="off" ' +
        'placeholder="0.0" onkeydown="' + key + '">';
    }
    return h + '<button class="cbtn go" onclick="answerCount()">Check</button>';
  }
  if (S.count_hidden) {
    const rec = S.count_record || {};
    return '<button class="cbtn" onclick="askCount()">REVEAL COUNT</button>' +
      (rec.asked ? '<span class="cmini">' + rec.right + "/" + rec.asked + " right</span>" : "");
  }
  /* Revealed. The running count is a fact you either kept or did not. The true
     count is division, and the app only does it for you if you asked it to. */
  const tc = S.true_count;
  return '<span class="cshow">RUNNING ' + sgn(S.running_count) +
    (tc != null ? " · TRUE " + (tc >= 0 ? "+" : "−") + Math.abs(tc).toFixed(1) : "") +
    "</span>";
}

function sgn(n) { return (n >= 0 ? "+" : "−") + Math.abs(n); }

/* The discard tray. Played cards pile up in it and that pile is the only thing
   telling you how deep the shoe is — no percentage, no decks-remaining. Judging
   it by eye is the half of counting that decides your true count, so the app
   will not do it for you unless you ask it to in Setup. */
function trayBar() {
  const t = S.tray || { dealt: 0, total: 312 };
  const frac = Math.max(0, Math.min(1, t.dealt / (t.total || 1)));
  const shoe = 1 - frac;
  return '<span class="trays">' +
    '<span class="tray shoe" title="cards still to come"><i style="height:' +
      (shoe * 100).toFixed(1) + '%"></i></span>' +
    '<span class="tlab">SHOE</span>' +
    '<span class="tray disc" title="cards already played"><i style="height:' +
      (frac * 100).toFixed(1) + '%"></i></span>' +
    '<span class="tlab">DISCARDS</span>' +
    (S.decks_left != null
      ? '<span class="tnum">' + S.decks_left + " decks left</span>"
      : "") +
    "</span>";
}

async function askCount() { await send("/api/count/ask", {}); const f = $("cans"); if (f) f.focus(); }

async function answerCount() {
  const el = $("cans");
  if (!el) return;
  const decks = $("cdecks");
  const next = await send("/api/count/answer", {
    said: el.value.trim(),
    decks: decks ? decks.value.trim() : null,
  });
  const r = next && next.count_result;
  if (!r) return;
  /* Kept on screen rather than toasted. It is two or three sentences of the most
     useful text in the app, and a banner that deletes itself after four seconds
     is unreadable while you are also playing a hand. */
  COUNT_RESULT = r;
  draw();
}

function dismissCount() { COUNT_RESULT = null; draw(); }

/* The result of a count check: what you said, what it was, and what the error
   does to you. Stays until you dismiss it or the next round starts. */
function countResult() {
  const r = COUNT_RESULT;
  if (!r) return "";
  const est = r.estimate;
  const bothOk = r.ok;
  const lines = [];
  if (r.count_ok) lines.push("Running count right at <b>" + sgn(r.actual) + "</b>.");
  else lines.push(esc(r.text));
  if (est) lines.push(est.ok
    ? "Deck estimate good: you said <b>" + est.said + "</b>, it was <b>" + est.actual + "</b>."
    : esc(est.text));
  if (bothOk && est) {
    lines.push("True count <b>" + sgn2(est.tc_actual) + "</b>.");
  }
  return '<div class="verdict ' + (bothOk ? "yes" : "no") + ' cres" onclick="dismissCount()">' +
    "<h3>" + (bothOk ? "Count check passed"
                     : r.count_ok ? "The count was right, the shoe was not"
                                  : "Count check missed") +
    (r.reason === "interrupted" ? " — you were interrupted" : "") + "</h3>" +
    lines.map((l) => "<p>" + l + "</p>").join("") +
    '<p class="fine">Click to dismiss.</p></div>';
}

function sgn2(n) { return (n >= 0 ? "+" : "−") + Math.abs(n).toFixed(1); }

/* The count only breaks cover for a missed index play. Getting one right tells
   you nothing you did not already know; getting one wrong is the whole lesson,
   so that is when the number comes out and says what it was. */
function indexVerdict() {
  const a = S.analysis;
  if (!a || !a.index || a.count_correct !== false) return "";
  const ix = a.index, tc = a.true_count;
  /* Which side of the index is the deviation depends on the sign of it. For
     16 v 10 the chart hits and a high count makes you stand; for 12 v 4 the
     chart stands and a LOW count makes you hit. Reading "at or above = the
     deviation" told a player who had correctly been moved off the chart that
     basic strategy still applied, one line above the passage explaining that
     it did not. The server already works out which it is. */
  const above = tc >= ix.index;
  const moved = !!a.index_deviation;
  const want = ix.kind === "insurance"
    ? (a.count_move === "take" ? "take insurance" : "decline insurance")
    : MOVE[a.count_move];
  return '<div class="verdict no ixv"><h3>Index play missed — ' + esc(want) + "</h3>" +
    "<p><b>" + esc(ixName(ix)) + "</b> is one of the Illustrious 18. The index is <kbd>" +
    ixNum(ix.index) + "</kbd>, and the true count was <kbd>" + ixNum(tc, 1) + "</kbd>, " +
    (above ? "at or above it" : "below it") + " — " +
    (moved
      ? "which is the side that moves this one, so the chart no longer applies."
      : "which is the side the chart already covers, so it still applies.") + "</p>" +
    "<p>" + esc(ix.why) + "</p>" +
    '<p class="fine">This engine puts the actual crossing at ' + ixNum(ix.crossing, 2) +
    ", which is where the published index of " + ixNum(ix.index) + " comes from.</p></div>";
}

/* A count of zero is "0", not "+0" — a sign on nothing reads like a typo. */
function ixNum(n, places) {
  const v = places ? Math.abs(n).toFixed(places) : Math.abs(n);
  if (Number(v) === 0) return places ? v : "0";
  return (n > 0 ? "+" : "−") + v;
}

function ixName(ix) {
  if (ix.kind === "insurance") return "Insurance";
  if (ix.kind === "pair") return "A pair of tens against a " + upLabel(ix.up);
  return "Hard " + ix.total + " against a " + upLabel(ix.up);
}

/* Nobody adds anybody's cards up for you at a table — not yours, not the other
   players', not the dealer's. Every total on the felt is withheld while the
   round is live and comes back once it settles, where it is feedback rather
   than help. Busts always show: they are called out loud and you can see the
   cards anyway. */
function totalsShown() {
  return !!S.config.show_totals || S.phase === "settled";
}

function heroTotal(x) {
  if (!totalsShown()) {
    return '<span class="total hid">' +
      (x.bust ? "<em>BUST</em>" : "&nbsp;·&nbsp;") + "</span>";
  }
  return '<span class="total' + (x.bust ? " bust" : "") + '">' + x.total +
    (x.soft && x.total < 21 ? "<em>SOFT</em>" : "") +
    (x.bust ? "<em>BUST</em>" : "") + "</span>";
}

function seatTotal(s) {
  return totalsShown() ? s.total : "·";
}

function drawTable() {
  const d = S.dealer;
  let h =
    '<div class="rail"><div class="felt">' +
    '<div class="arc"></div><div class="arc two"></div>' +
    '<div class="shoebar">' + countBar() + trayBar() + "</div>";

  /* dealer */
  h +=
    '<div class="dealer-zone"><div class="zlab">DEALER</div>' +
    '<div class="hand-row">' + (d.cards.length
      ? (() => { const b = freshFrom("dealer", d.cards.length);
                 // the hole card is not a new card, it is the same one turned over
                 const turned = HOLE_WAS_HIDDEN && !d.hole_hidden;
                 HOLE_WAS_HIDDEN = d.hole_hidden;
                 return d.cards.map((c, i) =>
                   cardEl(c, d.hole_hidden && i === 1, i >= b, i - b,
                          turned && i === 1)).join(""); })()
      : "") + "</div>" +
    (d.cards.length
      // the upcard label names a card sitting face up, so it is never withheld;
      // only the dealer's finished total is
      ? '<div class="total' + (d.bust ? " bust" : "") +
        (d.hole_hidden || totalsShown() ? "" : " hid") + '">' +
        (d.hole_hidden
          ? upLabel(d.showing) + "<em>SHOWING</em>"
          : (d.bust ? "<em>BUST</em>" : (totalsShown() ? d.total : "&nbsp;·&nbsp;"))) +
        "</div>"
      : "") + "</div>";

  /* The rules printed on the felt. In the flow rather than floated over it —
     absolutely positioned, it landed on top of the other players' cards. */
  h += '<div class="felt-text">BLACKJACK PAYS ' +
    (S.rules.blackjack_pays === 1.5 ? "3 TO 2" : "6 TO 5") +
    "<small>DEALER MUST DRAW TO 16 AND " +
    (S.rules.hit_soft_17 ? "HIT SOFT 17" : "STAND ON ALL 17s") +
    " · INSURANCE PAYS 2 TO 1</small></div>";

  /* The other players, spread along the arc of the table.

     They used to sit shoulder to shoulder in the middle, which read as one long
     hand rather than separate people, and the nudge pushed the outer seats UP —
     against the curve drawn behind them. The felt's arc is an ellipse seen from
     above with the dealer at the top, so it is highest in the middle: outer
     seats belong lower, not higher. */
  if (S.seats.length) {
    const n = S.seats.length, mid = (n - 1) / 2;
    h += '<div class="seats">' + S.seats.map((s, i) => {
      const off = mid ? (i - mid) / mid : 0;          // −1 at the far left, +1 at the far right
      const drop = Math.round(off * off * 16);        // follow the curve down and away
      return '<div class="seat' + (s.bust ? " bustd" : "") +
        '" style="transform:translateY(' + drop + 'px)">' +
        '<div class="spot"><div class="mini">' + (() => {
          const b = freshFrom("seat" + i, s.cards.length);
          return s.cards.map((c, j) => miniEl(c, j >= b, j - b)).join("");
        })() + "</div></div>" +
        '<div class="slab">SEAT ' + (i + 1) + "</div>" +
        '<div class="stot">' + (s.cards.length ? (s.bust ? "bust" : seatTotal(s)) : "—") +
        "</div></div>";
    }).join("") + "</div>";
  }

  /* your spots */
  h += '<div class="hero' + (S.hands.length > 1 ? " many" : "") + '">';
  if (S.hands.length) {
    h += S.hands.map((x, i) => {
      let head = "";
      if (S.hands.length > 1) head += "<span>HAND " + (i + 1) + "</span>";
      head += "<span>" + money(x.bet) + (x.doubled ? " DOUBLED" : "") + "</span>";
      if (x.result) head += '<span class="res ' + x.result + '">' + x.result.toUpperCase() + "</span>";
      const waiting = x.pending && !x.active;
      return '<div class="spot' + (x.active ? " live" : "") + (x.result ? " over" : "") +
        (waiting ? " waiting" : "") + '">' +
        '<div class="spot-head">' + head + "</div>" +
        '<div class="hand-row">' + (() => {
          const b = freshFrom("hand" + i, x.cards.length);
          return x.cards.map((c, j) => cardEl(c, false, j >= b, j - b)).join("");
        })() +
        (waiting ? backEl() : "") + "</div>" +
        '<div style="text-align:center">' +
        (waiting
          ? '<span class="total pend">waiting<em>DEALT WHEN ITS TURN COMES</em></span>'
          : heroTotal(x)) +
        "</div></div>";
    }).join("");
  } else {
    h += '<div class="spot"><div class="circle">' + money(PENDING_BET) + "</div></div>";
  }
  h += "</div></div></div>";

  h += countResult();

  /* verdict */
  const v = S.verdict;
  if (v) {
    if (v.kind === "insurance") {
      /* Insurance is the most valuable index play there is, and the one place
         a counter and a basic-strategy player give opposite answers often
         enough to matter. Graded on the count. */
      const iok = v.count_correct != null ? v.count_correct : v.correct;
      const wanted = v.index_deviation;          // the count called for taking it
      h += '<div class="verdict ' + (iok ? "yes" : "no") + '"><h3>' +
        (iok
          ? (wanted ? "Right — insurance is on at this count"
                    : "Right call — you turned it down")
          : (wanted ? "You should have taken it"
                    : v.even_money ? "Even money is the same bad bet"
                                   : "Never take insurance")) + "</h3>" +
        "<p>It is a side bet on the dealer’s face-down card, not on your hand. " +
        (wanted
          ? "It needs the hole card to be a ten more than a third of the time, and the shoe is " +
            "ten-rich enough right now that it is. This is the one bet on the table that a count " +
            "turns from bad to good, and it is worth more than every playing deviation combined."
          : "It needs the hole card to be a ten more than a third of the time, and only four ranks " +
            "in thirteen are. Without a count rich enough to change that, it is the worst bet here.") +
        (v.even_money
          ? " Taking even money on a blackjack is insurance wearing a different hat: it trades a hand "
            + "that wins 1.5 times most of the time for one that wins 1 time always, and comes out behind."
          : "") + "</p></div>";
    } else {
      /* Graded against the count, not the chart. On the squares where a high
         or low count moves the answer, playing the chart IS the mistake, and
         marking a correct deviation wrong would teach the opposite of the
         thing this is for. */
      const ok = v.count_correct != null ? v.count_correct : v.correct;
      const should = v.count_should || v.should;
      const dev = !!v.index_deviation;
      h += '<div class="verdict ' + (ok ? "yes" : "no") + '"><h3>' +
        (ok ? "Right — " + MOVE[v.chosen] + (dev ? ", against the chart" : "")
            : "You should have " + PAST[should]) + "</h3>" +
        "<p>" + (v.hand_count > 1 ? "Hand " + (v.hand_index + 1) + " of " + v.hand_count + ": " : "") +
        cap(v.row) + " against a dealer " + v.up + " → <kbd>" + MOVE[should] + "</kbd>" +
        (ok ? "" : ". You chose <kbd>" + MOVE[v.chosen] + "</kbd>") + "." +
        (dev
          ? " The chart says <kbd>" + MOVE[v.should] + "</kbd> here, but this is an index " +
            "play and the count has moved it."
          : "") +
        (v.fallback ? " The chart wants a double here, but you can only double on your first two cards." : "") +
        "</p></div>";
    }
    h += indexVerdict();
  }

  /* controls */
  h += '<div class="controls">';
  if (S.broke && S.phase !== "play") {
    h += '<div class="note bad"><b>You are below the table minimum.</b> The session is over ' +
      "— stand up, and earn the next buy-in on the Quiz tab.</div>" +
      '<button class="mv go" style="width:100%;margin-top:10px" onclick="standUp()">Stand up</button>';
  } else if (S.phase === "bet") {
    const denoms = [5, 25, 50, 100].filter((v) => v <= S.bankroll);
    h += '<div class="tray">' +
      denoms.map((v) => '<button class="chip" data-v="' + v + '" onclick="addBet(' + v + ')"><span>' + v + "</span></button>").join("") +
      '<button class="mv" style="flex:0 0 auto;padding:9px 14px" onclick="clearBet()">Reset</button></div>' +
      '<div class="betline">Betting <b>' + money(PENDING_BET) + "</b> of " + money(S.bankroll) +
      " — that is " + pct(PENDING_BET / S.bankroll) + " of what you brought, " +
      (S.bankroll / PENDING_BET).toFixed(1) + " bets deep.</div>" +
      '<button class="mv go" style="width:100%" onclick="doBet()">Deal<small>SPACE</small></button>';
  } else if (S.phase === "insurance") {
    h += '<div class="insline">' + (S.even_money
      ? "You have a blackjack and the dealer shows an ace. They are offering you <b>even money</b>."
      : "Dealer shows an ace. Insurance costs half your bet and pays two to one.") + "</div>" +
      '<div class="moves"><button class="mv" onclick="doIns(true)">' +
      (S.even_money ? "Take even money" : "Take insurance") + "</button>" +
      '<button class="mv go" onclick="doIns(false)">No thanks</button></div>';
  } else if (S.phase === "play") {
    h += '<div class="moves">' +
      '<button class="mv" onclick="doMove(\'H\')"' + (S.can_hit ? "" : " disabled") + ">Hit<small>H</small></button>" +
      '<button class="mv" onclick="doMove(\'S\')">Stand<small>S</small></button>' +
      '<button class="mv" onclick="doMove(\'D\')"' + (S.can_double ? "" : " disabled") + ">Double<small>D</small></button>" +
      '<button class="mv" onclick="doMove(\'P\')"' + (S.can_split ? "" : " disabled") + ">Split<small>P</small></button></div>";
  } else {
    h += '<button class="mv go" style="width:100%" onclick="doNext()">Next hand<small>SPACE</small></button>';
  }
  h += "</div>";
  $("mid").innerHTML = h;
}

/* ---------------- intuition (left) ---------------- */
function drawIntu() {
  const box = $("intu"), lab = $("uc"), e = S.explanation, a = S.analysis;
  if (lab) lab.textContent = a ? a.unseen + " cards unseen" : "";
  if (!e) {
    box.innerHTML =
      '<p class="idle">This side is the version you can carry to a real table — the picture, the ' +
      "comparison, and one line worth memorising. It fills in the moment you act, so it cannot " +
      "give you the answer in advance." +
      "<br><br>Anything <span class=\"gt\" data-term=\"house edge\">underlined like this</span> is " +
      "explained if you click it.</p>";
    return;
  }
  const terms = e.terms || [];
  box.innerHTML =
    (e.rule_note ? '<div class="note">' + esc(e.rule_note) + "</div>" : "") +
    '<div class="hook">' + link(e.hook, terms) + "</div>" +
    '<div class="prose">' + e.paragraphs.map((p) => "<p>" + link(p, terms) + "</p>").join("") + "</div>" +
    '<div class="pic">' + e.picture + "</div>" +
    (a && a.deviation
      ? '<div class="note"><b>Right now the cards disagree with the chart.</b> With the count at ' +
        (a.true_count >= 0 ? "+" : "−") + Math.abs(a.true_count).toFixed(1) + ", what is left makes <b>" +
        MOVE[a.best_move] + "</b> better by " + a.dev_gap.toFixed(3) +
        ' per dollar. Learn the chart first — these <span class="gt" data-term="deviation">deviations</span> ' +
        "are worth a fraction of a percent, and only if you are tracking the cards properly.</div>"
      : "") +
    '<div class="recall"><span>WORTH MEMORISING</span><p>' + e.remember + "</p></div>";
}

/* ---------------- session panel (right) ---------------- */
function drawSide() {
  const s = S.session || {}, at = S.all_time || {};
  const acc = s.decisions ? s.correct / s.decisions : null;
  const net = s.net || 0;
  const swing = (s.peak || 0) - (s.trough || 0);
  const streak = s.streak || 0;

  $("side").innerHTML =
    '<div class="panel"><div class="phead"><h2>THIS SESSION</h2><em>#' + (s.number || 1) + "</em></div>" +
    '<div class="pbody">' +
    '<div class="two"><div><div class="big ' + cls(net) + '">' + money(net) + '</div>' +
    '<div class="sub">up or down, this session</div></div>' +
    '<div><div class="big">' + num(s.hands || 0) + '</div><div class="sub">hands played</div></div></div>' +

    '<div class="bar3">' + sessionBar(s) + "</div>" +
    '<div class="kv"><span>Bought in for</span><b>' + money(s.start || 0) + "</b></div>" +
    '<div class="kv"><span>On the table now</span><b>' + money(S.bankroll) + "</b></div>" +
    '<div class="kv"><span>High / low this session</span><b>' + money(s.peak || 0) +
    " / " + money(s.trough || 0) + "</b></div>" +
    '<div class="kv"><span>Biggest swing</span><b>' + money(swing) + "</b></div>" +
    '<div class="kv"><span>Total put out</span><b>' + money(s.wagered || 0) + "</b></div>" +

    '<h3 class="mini-h">HOW YOU ARE PLAYING</h3>' +
    '<div class="kv"><span>Decisions right</span><b class="' +
    (acc == null ? "" : acc >= 0.95 ? "up" : acc < 0.8 ? "down" : "") + '">' +
    (acc == null ? "—" : Math.round(acc * 100) + "%") + "</b></div>" +
    '<div class="kv"><span>Decisions made</span><b>' + (s.decisions || 0) + "</b></div>" +
    '<div class="kv"><span>Given away by mistakes</span><b class="' +
    ((s.ev_lost || 0) > 0.5 ? "down" : "") + '">' + money(s.ev_lost || 0) + "</b></div>" +

    '<h3 class="mini-h">WHAT THE CARDS DID</h3>' +
    '<div class="kv"><span>Won / lost / pushed</span><b>' + (s.wins || 0) + " · " +
    (s.losses || 0) + " · " + (s.pushes || 0) + "</b></div>" +
    '<div class="kv"><span>Blackjacks</span><b>' + (s.blackjacks || 0) + "</b></div>" +
    '<div class="kv"><span>Times you busted</span><b>' + (s.busts || 0) + "</b></div>" +
    '<div class="kv"><span>Current run</span><b class="' + cls(streak) + '">' +
    (streak === 0 ? "—" : Math.abs(streak) + " " + (streak > 0 ? "won" : "lost") + " in a row") +
    "</b></div>" +
    '<div class="kv"><span>Best run this session</span><b>' + (s.best_streak || 0) + "</b></div>" +
    '<div class="kv"><span>Shuffles</span><b>' + (s.shuffles || 0) + "</b></div>" +
    '<button class="mv" style="width:100%;margin-top:14px" onclick="standUp()">Stand up and cash out</button>' +
    "</div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>ALL TIME</h2><em>' +
    (at.sessions || 0) + " sessions</em></div><div class=\"pbody\">" +
    '<div class="two"><div><div class="big ' + cls(at.lifetime) + '">' + money(at.lifetime) +
    '</div><div class="sub">everything you have, minus everything you were given</div></div>' +
    '<div><div class="big">' + num(at.hands || 0) + '</div><div class="sub">hands, ever</div></div></div>' +
    '<div class="kv" style="margin-top:10px"><span>Best session</span><b class="' +
    cls(at.best_session) + '">' + (at.best_session == null ? "—" : money(at.best_session)) + "</b></div>" +
    '<div class="kv"><span>Worst session</span><b class="' + cls(at.worst_session) + '">' +
    (at.worst_session == null ? "—" : money(at.worst_session)) + "</b></div>" +
    '<div class="kv"><span>Highest you have ever been</span><b>' +
    (at.high_water == null ? "—" : money(at.high_water)) + "</b></div>" +
    '<div class="kv"><span>Accuracy, all time</span><b>' +
    (at.accuracy == null ? "—" : Math.round(at.accuracy * 100) + "%") + "</b></div>" +
    '<div class="kv"><span>Chips in the rack</span><b>' + money(at.chips) + "</b></div>" +
    '<div class="kv"><span>Everything you are worth</span><b>' + money(at.worth) + "</b></div>" +
    "</div></div>";
}

function sessionBar(s) {
  const start = s.start || 1, now = S.bankroll;
  const hi = Math.max(s.peak || start, start), lo = Math.min(s.trough || start, start);
  const range = hi - lo || 1;
  const pos = ((now - lo) / range) * 100, zero = ((start - lo) / range) * 100;
  return '<i class="' + (now >= start ? "good" : "bad") + '" style="left:' +
    Math.min(zero, pos) + "%;width:" + Math.abs(pos - zero) + '%"></i>' +
    '<u style="left:' + zero + '%"></u><s style="left:' + pos + '%"></s>';
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

/* =======================================================================
   BETTING
   ======================================================================= */
const step = (n, title, body) => '<div class="step"><h4><i>' + n + "</i>" + title + "</h4>" + body + "</div>";


/* What to bet at each count, in units. Shown when the count is hidden, because
   the ramp is the thing you can act on without being told where you are. */
function rampTable(spread) {
  const rows = [];
  for (let t = 0; t <= 8; t++) {
    const u = t < 1 ? 1 : Math.max(1, Math.min(spread, t - 1 + 1));
    rows.push([t, u]);
  }
  return '<div class="ramp">' + rows.map(([t, u]) =>
    '<div class="rr"><span>' + (t === 0 ? "≤ +0" : "+" + t) + "</span><b>" + u +
    (u === 1 ? " unit" : " units") + "</b></div>").join("") + "</div>" +
    '<p class="fine">Spread 1 to ' + spread + ", set in Setup. Below +1 you have no edge and " +
    "the only correct bet is the smallest one the table allows.</p>";
}

function viewBetting() {
  if (S.phase === "idle") return emptyTab("betting",
    "Bet sizing is scored while you are playing. Sit down on the Table tab and it fills in.");
  const b = S.bet_check;
  const st = STATS || {};
  const tot = st.totals || {};
  const names = { chase: "Raised the bet after losing", press: "Doubled up after winning",
    over: "Bet more than 15% of your money", big: "Bet more than 5% of your money",
    undercap: "Table is too expensive for your bankroll", watch: "Bet small on a good count" };
  /* The count is hidden unless you have earned it, so this tab cannot assume a
     number. It used to read S.true_count straight out and render null as
     "+0.0" — a count nobody had, and an edge computed from it. */
  const known = S.true_count != null;
  const tc = known ? S.true_count : null;
  const edge = known ? -0.005 + 0.005 * Math.max(0, tc - 1) : null;
  const bankroll = S.bankroll || 1;

  $("wrap").innerHTML =
    '<div class="cols">' +
    '<div><div class="panel"><div class="phead"><h2>HOW MUCH TO PUT OUT</h2></div><div class="pbody">' +
    step(1, "Do you have any advantage right now?",
      (known
        ? '<div class="eq">count per deck <b>' + (tc >= 0 ? "+" : "−") + Math.abs(tc).toFixed(1) + "</b><br>" +
          'your edge ≈ <b class="' + (edge >= 0 ? "pos" : "neg") + '">' + (edge * 100).toFixed(2) +
          "%</b> of every dollar</div>"
        : '<div class="eq">count per deck <b>—</b><br>your edge ≈ <b>—</b></div>' +
          '<p class="idle">The count is hidden, so this tab will not put a number here. ' +
          "You are the one keeping it: work out your own true count, and the guidance below " +
          "is in units so it applies to whatever you have. Press <b>REVEAL COUNT</b> on the " +
          "Table tab if you want it checked.</p>") +
      "<p>The rule of thumb: you start about half a percent behind, and each " +
      'point of <span class="gt" data-term="true count">count per deck</span> above +1 gives you back ' +
      "roughly half a percent. Below that, you are a losing bettor no matter how well you play the cards.</p>" +
      (known ? "" : rampTable(S.config.spread || 8))) +
    step(2, "So what size does that justify?",
      !known
        ? '<div class="eq">one unit is the table minimum, <b>' + money(S.config.table_min) +
          "</b></div><p>Without the count on screen the honest answer is a ramp rather than a " +
          "number: bet one unit until your count is genuinely positive, then roughly one unit " +
          "per point above +1, up to your spread. The table above is that ramp at the spread " +
          "you have set in <b>Setup</b>.</p>"
        : edge > 0
        ? '<div class="eq">edge ÷ swing = ' + edge.toFixed(4) + " ÷ 1.30 = <b>" +
          pct(edge / 1.3, 2) + "</b> of your money<br>= <b>" + money(bankroll * (edge / 1.3)) + "</b></div>" +
          '<p>This is the <span class="gt" data-term="kelly">Kelly</span> size, which grows money fastest ' +
          "but swings hard. Most people who do this seriously bet a half or a third of it.</p>"
        : '<div class="eq">no advantage → the size that grows money fastest is <b>$0</b></div>' +
          "<p>That is the honest answer, and a useless one if you came here to play. So the least-bad " +
          "size is the table minimum, <b>" + money(S.config.table_min) + "</b>, because it keeps the " +
          'amount you are handing over per hour as small as possible.</p>') +
    step(3, "Can you survive that size?",
      '<div class="eq">your money = <b>' + (bankroll / (b ? b.amount : S.config.table_min)).toFixed(1) +
      "</b> bets<br>a typical hand swings about <b>1.14 bets</b> either way</div>" +
      (b
        ? '<div class="kv"><span>Chance you double your money before losing it</span><b>' + pct(b.p_double) + "</b></div>" +
          '<div class="kv"><span>Chance you eventually lose it all if you keep playing</span><b>' +
          (b.edge > 0 ? pct(b.p_ruin) : !known ? "—" : "100%") + "</b></div>"
        : '<p class="idle">Place a bet and these fill in.</p>') +
      "<p style=\"margin-top:8px\">" + (b && b.edge > 0
        ? "Having a real advantage is the only thing that makes going broke avoidable at all."
        : !known
        ? "Whether going broke is avoidable depends on whether you actually have an edge, which " +
          "depends on the count you are keeping. Flat-betting without one, it is a certainty " +
          "given enough hands."
        : 'With no advantage, going broke is not a risk — it is a certainty given enough hands. ' +
          'The only questions are how long it takes and whether you enjoyed it. That is what ' +
          '<span class="gt" data-term="risk of ruin">risk of ruin</span> means. The ' +
          '<b>Analysis</b> tab will work out how much you need to survive a given number of hands.') + "</p>") +
    "</div></div></div>" +

    '<div class="mid"><div class="panel"><div class="phead"><h2>YOUR LAST BET</h2><em>' +
    (b ? money(b.amount) : "none yet") + "</em></div><div class=\"pbody\">" +
    (b
      ? '<div class="two"><div><div class="big ' + (b.ok ? "up" : "down") + '">' +
        (b.ok ? "Fine" : "Too big") + '</div><div class="sub">verdict on the size</div></div>' +
        '<div><div class="big">' + (b.suggested == null ? "—" : money(b.suggested)) +
        '</div><div class="sub">' + (b.suggested == null ? "hidden with the count" : "what the maths supports") +
        "</div></div></div>" +
        '<div class="bar2"><i class="' + (b.share > 0.15 ? "b" : b.share > 0.05 ? "w" : "") +
        '" style="width:' + Math.min(100, b.share * 400) + '%"></i></div>' +
        '<div class="kv"><span>Share of your money</span><b>' + pct(b.share, 1) + "</b></div>" +
        '<div class="kv"><span>How many bets deep you are</span><b>' + b.units.toFixed(1) + "</b></div>" +
        b.flags.map((f) => '<div class="note ' + (f.level === "bad" ? "bad" : f.level === "info" ? "ok" : "") + '">' + f.text + "</div>").join("") +
        (b.flags.some((f) => f.level !== "info") ? "" :
          '<div class="note ok">Nothing to flag. Sensible against your bankroll, and not driven by what happened last hand.</div>')
      : '<p class="idle">Place a bet on the Table tab and it gets scored here — how big it is next to ' +
        "your money, whether it is reacting to the last result, and what it does to your chances of lasting the session.</p>") +
    "</div></div></div>" +

    '<div><div class="panel"><div class="phead"><h2>YOUR BETTING RECORD</h2></div><div class="pbody">' +
    '<div class="big">' + (tot.bet_accuracy == null ? "—" : Math.round(tot.bet_accuracy * 100) + "%") +
    '</div><div class="sub">sensible bets, out of ' + (tot.bets || 0) + "</div>" +
    (tot.bet_flags && Object.keys(tot.bet_flags).length
      ? '<div style="margin-top:14px">' + Object.entries(tot.bet_flags).sort((a, c) => c[1] - a[1])
          .map(([k, n]) => '<div class="miss"><div>' + (names[k] || k) + "</div><span>" + n + "×</span></div>").join("") + "</div>"
      : '<p class="idle" style="margin-top:12px">No sizing problems recorded yet.</p>') +
    '<div class="pic" style="margin-top:16px">There are two ways to lose money at this game: ' +
    "<b>playing the cards wrong</b> and <b>betting the wrong amount</b>. The first costs about half a " +
    "percent. The second is what actually empties wallets — it is the difference between losing " +
    "slowly and losing everything in twenty minutes.</div>" +
    '<div class="recall"><span>WORTH MEMORISING</span><p>Bet size should follow the cards, never the last result.</p></div>' +
    "</div></div></div></div>";
  $("foot").innerHTML =
    "The survival numbers use a standard random-walk approximation with a swing of 1.14 bets per hand, " +
    "which is the usual figure for blackjack played by the chart including doubles and splits.";
  statsThenRedraw("betting");
}

function emptyTab(name, text) {
  $("wrap").innerHTML = '<div class="single"><div class="panel"><div class="phead"><h2>' +
    name.toUpperCase() + '</h2></div><div class="pbody"><p class="idle">' + text +
    '</p><button class="mv go" style="margin-top:14px" onclick="go(\'table\')">Go to the table</button>' +
    "</div></div></div>";
  $("foot").innerHTML = "";
}

/* =======================================================================
   CHART
   ======================================================================= */
async function viewChart() {
  const c = await needChart();
  if (TAB !== "chart") return;
  const secs = [
    ["hard", "HARD TOTALS", "No ace, or an ace that has to count as one."],
    ["soft", "SOFT TOTALS", "An ace counting as eleven. You cannot break with one card."],
    ["pair", "PAIRS", "Two cards of the same value, before you do anything else."],
  ];
  $("wrap").innerHTML =
    '<div class="chartwrap">' +
    '<div class="panel"><div class="phead"><h2>BASIC STRATEGY</h2><em>' +
    c.rules.decks + " decks · " + ruleLine(c.rules) + "</em></div>" +
    '<div class="pbody">' +
    '<div class="chartbar">' + legend() +
    '<label class="tick"><input type="checkbox" id="ov"' + (CHART_OVERLAY ? " checked" : "") +
    ' onchange="CHART_OVERLAY=this.checked;draw()"> Shade by how often I get it right</label>' +
    "</div>" +
    secs.map(([key, title, blurb]) => chartSection(c, key, title, blurb)).join("") +
    '<p class="fine">Read a row to your total and a column to the dealer’s upcard. ' +
    "<b>17+</b> and <b>8−</b> are single rows because nothing in them varies: every hard total " +
    "from 17 up stands against everything, and every total of 8 or less hits against everything, " +
    "under all four rule sets. Clicking one opens the band. Every square here is checked against " +
    "the odds computed from a full shoe — the chart is not typed in from a book, it is the play " +
    "with the highest expected value, and it changes with the rules above. Change the rules in " +
    "<b>Setup</b> and the squares that move will move.</p>" +
    "</div></div>" + indexPanel(c) + cellDetail(c) + "</div>";
  $("foot").innerHTML =
    "D means double if the table lets you, otherwise hit. Ds means double if you can, otherwise stand " +
    "— it only appears on soft 18 and soft 19, where the hand is good enough to keep. " +
    "Click any square for what it means and your own record on it.";
}

/* ---------------- the deviation chart ----------------
   The basic strategy grid above assumes you are not counting. This is the other
   half: the squares where a big enough count changes the answer, and the number
   at which it changes. Laid out the same way so the two read as one thing. */

const IX_ROWS = [
  ["hard", 9], ["hard", 10], ["hard", 11], ["hard", 12],
  ["hard", 13], ["hard", 15], ["hard", 16], ["pair", 10],
];

function indexPanel(c) {
  const ix = c.indices || [];
  if (!ix.length) return "";
  const rec = c.index_record || {};
  const ins = ix.find((p) => p.key === "insurance");

  /* index plays keyed by section+row+upcard, for the grid */
  const at = {};
  ix.forEach((p) => {
    if (p.kind === "insurance") return;
    const row = p.kind === "pair" ? p.pair : p.total;
    at[p.kind + ":" + row + ":" + p.up] = p;
  });

  let grid = '<div class="cscroll"><table class="chart ixchart"><tr><th class="rh"></th>' +
    c.upcards.map((u) => "<th>" + upLabel(u) + "</th>").join("") + "</tr>";
  for (const [kind, row] of IX_ROWS) {
    grid += '<tr><th class="rh">' + (kind === "pair" ? "T,T" : row) + "</th>";
    c.upcards.forEach((u) => {
      const p = at[kind + ":" + row + ":" + u];
      if (!p) { grid += '<td class="ixnone"></td>'; return; }
      const r = rec[p.key];
      grid += '<td class="ixcell m' + p.at_or_above + (CHART_CELL === p.key ? " sel" : "") +
        '" onclick="pickIndex(\'' + p.key + '\')" title="' +
        esc(ixTitle(p)) + '"><b>' + ixNum(p.index) + "</b><i>" + p.at_or_above + "</i>" +
        (r ? "<u>" + r.right + "/" + r.seen + "</u>" : "") + "</td>";
    });
    grid += "</tr>";
  }
  grid += "</table></div>";

  /* the order to learn them in — the list is ranked by what it is worth */
  const list = '<ol class="ixlist">' + ix.map((p) =>
    '<li' + (CHART_CELL === p.key ? ' class="sel"' : "") +
    ' onclick="pickIndex(\'' + p.key + '\')"><b>' + ixNum(p.index) + "</b>" +
    "<span>" + esc(ixLabel(p)) + "</span><em>" +
    (p.at_or_above === "take" ? "take it" : CODE_NAME[p.at_or_above] || p.at_or_above) +
    " at " + ixNum(p.index) + " or above</em></li>").join("") + "</ol>";

  return '<div class="panel" style="margin-top:16px"><div class="phead">' +
    "<h2>INDEX PLAYS · THE ILLUSTRIOUS 18</h2><em>Hi-Lo · " + c.rules.decks + " decks · " +
    (c.rules.hit_soft_17 ? "H17" : "S17") + "</em></div><div class="+ '"pbody">' +
    '<div class="note"><b>Insurance is the big one.</b> ' + esc(ins ? ins.why : "") +
    " Take it at <kbd>" + ixNum(ins ? ins.index : 3) + "</kbd> or above, decline it below. " +
    "It is worth more than every playing deviation on this chart put together.</div>" +
    '<h3 class="csec">WHERE THE COUNT MOVES THE CHART<span>The number is the true count at ' +
    "which the square changes. At or above it, play the letter. Below it, play the chart." +
    "</span></h3>" + grid +
    '<h3 class="csec">IN THE ORDER WORTH LEARNING THEM<span>Ranked by what each one is ' +
    "actually worth. The first six carry most of the value.</span></h3>" + list +
    '<p class="fine">Surrender indices are not here, because this game has no surrender. ' +
    "Every number was re-derived from this app's own engine rather than copied — click any " +
    "square to see where the maths puts the crossing.</p>" +
    "</div></div>";
}

/* Which side of an index is the deviation cannot be read off the sign of it:
   16 v 10 and 12 v 4 both have an index of 0, and the deviation is above on one
   and below on the other. It has to come from the chart. */
function chartSideOf(c, p) {
  if (p.kind === "insurance") return "below";          // you never insure by default
  const section = p.kind === "pair" ? "pair" : "hard";
  const row = p.kind === "pair" ? p.pair : p.total;
  const cell = ((c.grid[section] || {})[row] || [])[c.upcards.indexOf(p.up)];
  const chart = cell === "Ds" ? "S" : cell;            // as played when doubling is allowed
  if (chart === p.at_or_above) return "above";
  if (chart === p.below) return "below";
  return "below";
}

function indexDetail(c, p) {
  const rec = (c.index_record || {})[p.key];
  const name = (m) => m === "take" ? "take insurance" : m === "decline" ? "decline it"
                    : (CODE_NAME[m] || m);
  const chartSide = chartSideOf(c, p);
  const tag = (side) => side === chartSide
    ? " — what the chart already says" : " — the deviation";
  return '<div class="panel side"><div class="phead"><h2>' + esc(ixLabel(p).toUpperCase()) +
    "</h2><em>#" + p.rank + " of 18</em></div><div class=" + '"pbody">' +
    '<div class="ixbig">' + ixNum(p.index) + '<span>TRUE COUNT</span></div>' +
    "<p>At <b>" + ixNum(p.index) + "</b> or above: <kbd>" + esc(name(p.at_or_above)) +
    "</kbd>" + tag("above") + ".<br>" +
    "Below it: <kbd>" + esc(name(p.below)) + "</kbd>" + tag("below") + ".</p>" +
    "<p>" + esc(p.why) + "</p>" +
    '<div class="note"><b>Where the number comes from.</b> Dealing six thousand shoes and ' +
    "sampling what was left every time the count passed here, this engine puts the actual " +
    "crossing at <b>" + ixNum(p.crossing, 2) + "</b>. The published index is <b>" +
    ixNum(p.index) + "</b>" +
    (Math.abs(p.crossing - p.index) > 0.4
      ? ", a little apart from it — the expected value either side is near enough identical " +
        "that the rounding could fall either way, so the published number is used."
      : ", which is where it rounds to.") + "</div>" +
    (rec
      ? '<div class="rec"><b>' + rec.right + " of " + rec.seen +
        "</b><span>right, when this has come up</span></div>"
      : '<p class="fine">This one has not come up yet.</p>') +
    "</div></div>";
}

function ixLabel(p) {
  if (p.kind === "insurance") return "Insurance";
  if (p.kind === "pair") return "T,T v " + upLabel(p.up);
  return p.total + " v " + upLabel(p.up);
}

function ixTitle(p) {
  return ixLabel(p) + " → " + (CODE_NAME[p.at_or_above] || p.at_or_above) +
    " at true count " + ixNum(p.index) + " or above, otherwise " +
    (CODE_NAME[p.below] || p.below);
}

function pickIndex(key) {
  CHART_CELL = CHART_CELL === key ? null : key;
  draw();
}

function legend() {
  return '<div class="legend">' +
    [["H", "Hit"], ["S", "Stand"], ["D", "Double"], ["Ds", "Double / stand"], ["P", "Split"]]
      .map(([k, label]) => '<span class="lg"><i class="m' + k + '">' + k + "</i>" + label + "</span>")
      .join("") + "</div>";
}

/* Hard 17 through 21 all stand against everything, and 8 down to 5 all hit
   against everything — under every rule set, which is asserted in test_game.
   Drawing nine rows to say two things buries the part of the chart that
   actually varies, so each band collapses to a single row. The underlying
   squares are untouched: the record shown is summed across the band, and
   clicking opens the representative square. */
function chartRows(c, key) {
  const rows = Object.keys(c.grid[key]).map(Number).sort((a, b) => b - a);
  if (key !== "hard") return rows.map((r) => ({ label: rowLabel(key, r), row: r, covers: [r] }));
  const out = [];
  const top = rows.filter((r) => r >= 17);
  const low = rows.filter((r) => r <= 8);
  if (top.length) out.push({ label: "17+", row: Math.min(...top), covers: top });
  rows.filter((r) => r > 8 && r < 17).forEach((r) => out.push({ label: String(r), row: r, covers: [r] }));
  if (low.length) out.push({ label: "8−", row: Math.max(...low), covers: low });
  return out;
}

function chartSection(c, key, title, blurb) {
  const heat = c.heatmap || {};
  let h = '<h3 class="csec">' + title + '<span>' + blurb + "</span></h3>" +
    '<div class="cscroll"><table class="chart"><tr><th class="rh"></th>' +
    c.upcards.map((u) => "<th>" + upLabel(u) + "</th>").join("") + "</tr>";
  for (const r of chartRows(c, key)) {
    h += '<tr><th class="rh">' + r.label + "</th>";
    c.grid[key][r.row].forEach((mv, i) => {
      const up = c.upcards[i];
      const name = cellName(key, r.row, up);
      /* a collapsed band's record is everything in it, added up */
      let seen = 0, right = 0;
      r.covers.forEach((cr) => {
        const x = heat[cellName(key, cr, up)];
        if (x) { seen += x.seen; right += x.seen * x.accuracy; }
      });
      let shade = "";
      if (CHART_OVERLAY && seen) {
        const a = right / seen;
        shade = a >= 0.9 ? " k3" : a >= 0.7 ? " k2" : a >= 0.4 ? " k1" : " k0";
      }
      const sel = CHART_CELL === name ? " sel" : "";
      h += '<td class="m' + mv + shade + sel + '" onclick="pickCell(\'' + key + "'," + r.row + "," + up + ')" ' +
        'title="' + esc(bandName(key, r, up) + " → " + CODE_NAME[mv]) + '">' + mv +
        (seen ? "<u>" + seen + "</u>" : "") + "</td>";
    });
    h += "</tr>";
  }
  return h + "</table></div>";
}

function bandName(key, r, up) {
  if (r.covers.length === 1) return cellName(key, r.row, up);
  return "hard " + r.label + " vs " + upLabel(up);
}

function rowLabel(key, row) {
  if (key === "pair") return row === 11 ? "A,A" : row + "," + row;
  if (key === "soft") return "A," + row;
  return String(row);
}
function cellName(key, row, up) {
  if (key === "pair") return "pair of " + (row === 11 ? "aces" : row + "s") + " vs " + upLabel(up);
  if (key === "soft") return "soft " + (row + 11) + " (A," + row + ") vs " + upLabel(up);
  return "hard " + row + " vs " + upLabel(up);
}
function pickCell(key, row, up) {
  CHART_CELL = cellName(key, row, up);
  draw();
}

function cellDetail(c) {
  if (!CHART_CELL) {
    return '<div class="panel side"><div class="phead"><h2>PICK A SQUARE</h2></div>' +
      '<div class="pbody"><p class="idle">Click any square in the chart and this shows what it ' +
      "means in words, how often the hand actually turns up, and your own record on it.</p>" +
      '<div class="pic" style="margin-top:14px">The chart is twenty minutes of memorising that is ' +
      "worth more than everything else in this app combined. It is also only about half a percent " +
      "better than playing sensibly by instinct — which tells you something useful about how " +
      "small the edges in this game are.</div></div></div>";
  }
  /* CHART_CELL doubles as the selection for the index chart below, where it
     holds an index key rather than a square name. */
  const ix = (c.indices || []).find((p) => p.key === CHART_CELL);
  if (ix) return indexDetail(c, ix);

  const parsed = parseCell(CHART_CELL);
  if (!parsed) return "";
  const [key, row, up] = parsed;
  const mv = c.grid[key][row][c.upcards.indexOf(up)];
  const rec = (c.heatmap || {})[CHART_CELL];
  return '<div class="panel side"><div class="phead"><h2>' + esc(CHART_CELL.toUpperCase()) +
    "</h2></div><div class=\"pbody\">" +
    '<div class="answer m' + mv + '">' + CODE_NAME[mv] + "</div>" +
    "<p>" + cellProse(key, row, up, mv) + "</p>" +
    '<h3 class="mini-h">YOUR RECORD HERE</h3>' +
    (rec
      ? '<div class="two"><div><div class="big ' +
        (rec.accuracy >= 0.9 ? "up" : rec.accuracy < 0.6 ? "down" : "") + '">' +
        Math.round(rec.accuracy * 100) + '%</div><div class="sub">' + rec.correct + " of " +
        rec.seen + " right</div></div><div><div class=\"big\">" + Math.round(rec.mastery * 100) +
        '%</div><div class="sub">weighted for recency</div></div></div>'
      : '<p class="idle">You have never been asked this one. That is not the same as knowing it.</p>') +
    '<div class="moves" style="margin-top:14px">' +
    '<button class="mv" onclick="drillCell()">Quiz me on this</button></div>' +
    "</div></div>";
}

function parseCell(name) {
  const m = name.match(/^(.*) vs (A|\d+)$/);
  if (!m) return null;
  const up = m[2] === "A" ? 11 : +m[2];
  const hand = m[1];
  if (hand.startsWith("pair of ")) {
    const rest = hand.slice(8);
    return ["pair", rest.startsWith("ace") ? 11 : parseInt(rest, 10), up];
  }
  if (hand.startsWith("soft ")) return ["soft", +hand.split("(A,")[1].replace(")", ""), up];
  if (hand.startsWith("hard ")) return ["hard", +hand.split(" ")[1], up];
  return null;
}

function cellProse(key, row, up, mv) {
  const dealer = up === 11 ? "an ace" : "a " + up;
  const weak = up >= 2 && up <= 6;
  if (key === "pair") {
    if (mv === "P") return "Split. Two separate hands starting from " + (row === 11 ? "an ace" : "a " + row) +
      " are worth more than the one hand they make together, against " + dealer + ".";
    if (mv === "S") return "Do not split. The hand you already have is better than the two you would get.";
    return "Do not split — play it as the total it makes. " +
      (row === 5 ? "Two fives are an eleven, and eleven is the best doubling hand in the game." : "");
  }
  if (key === "soft") {
    const t = row + 11;
    if (mv === "D" || mv === "Ds") return "Double. You hold a soft " + t + ", so no single card can break you, " +
      "and " + dealer + " is weak enough that putting more money out is worth more than the hand you have.";
    if (mv === "S") return "Stand on soft " + t + ". It is already a good total and the dealer is not weak enough to push.";
    return "Hit. Soft " + t + " cannot be broken by one card, so taking one is free — standing on it " +
      "just hands " + dealer + " the hand.";
  }
  if (mv === "D") return "Double. Eleven or close to it against " + dealer +
    " is the one moment the house lets you put more money out with the odds on your side.";
  if (mv === "S" && row <= 16) return "Stand. You will probably lose this hand either way, but " + dealer +
    " breaks often enough that letting them draw loses less than drawing yourself.";
  if (mv === "S") return "Stand. " + row + " is a made hand; drawing to it loses far more often than it helps.";
  if (row >= 12) return "Hit. " + row + " loses to almost everything " + dealer +
    " will finish with, so standing is the worse of two bad options.";
  return "Hit. At " + row + " " + (row <= 11 ? "no card can break you, so taking one is free." :
    "you are too far behind to stand.");
}

function drillCell() {
  const parsed = parseCell(CHART_CELL);
  if (!parsed) return;
  QUIZ_SETUP = { mode: "custom", length: 10, sections: [parsed[0]],
                 upcards: [parsed[2]], only: "all" };
  TAB = "quiz"; QUIZ = null; draw();
  startQuiz();
}

/* =======================================================================
   QUIZ
   ======================================================================= */
function viewQuiz() {
  if (QUIZ) return drawQuizRunner();
  const modes = [
    ["weak", "Your weak spots", "Drawn from wherever your record is worst, with the squares you keep missing coming up most.", "◉"],
    ["missed", "Recently missed", "Only the hands you have actually got wrong at the table.", "✗"],
    ["rare", "Hands you never see", "The splits and soft doubles that turn up once an evening — the part everyone is worst at, for exactly that reason.", "⚑"],
    ["deviations", "The index plays", "The eighteen squares a count moves, asked from both sides of the index so the answer is never the one you expected.", "±"],
    ["counting", "Keeping the count", "Running counts, true counts and insurance. The arithmetic, drilled where there is time to be slow.", "#"],
    ["everything", "Everything", "Chart, counting and deviations mixed together, which is the only way they ever arrive at a table.", "✦"],
    ["chips", "Play for chips", "Ten questions. Every right answer is $10 in chips you can take to the table.", "$"],
    ["custom", "Build your own", "Pick exactly which part of the chart to drill.", "⚙"],
  ];
  $("wrap").innerHTML =
    '<div class="single">' +
    (ACCOUNT.chips < (S.config.table_min || 15)
      ? '<div class="note" style="margin-bottom:16px"><b>You are out of chips.</b> Ten correct ' +
        "answers is $100 — enough to sit back down at a " + money(S.config.table_min) + " table.</div>"
      : "") +
    '<div class="modes">' + modes.map(([key, title, blurb, icon]) =>
      '<div class="mode' + (QUIZ_SETUP.mode === key ? " on" : "") + '" onclick="QUIZ_SETUP.mode=\'' + key + "';draw()\">" +
      '<div class="mi">' + icon + "</div><b>" + title + "</b><span>" + blurb + "</span>" +
      (key === "chips" ? '<em class="tagline">$10 a question</em>' : "") + "</div>").join("") + "</div>" +
    (QUIZ_SETUP.mode === "custom" ? customBuilder() : "") +
    '<div class="panel" style="margin-top:16px"><div class="pbody">' +
    (QUIZ_SETUP.mode !== "chips"
      ? '<div class="field"><label>HOW MANY QUESTIONS</label>' +
        '<div class="pills">' + [5, 10, 20, 30].map((n) =>
          '<button class="pill' + (QUIZ_SETUP.length === n ? " on" : "") + '" onclick="QUIZ_SETUP.length=' +
          n + ';draw()">' + n + "</button>").join("") + "</div></div>"
      : "") +
    '<button class="mv go" style="width:100%" onclick="startQuiz()">Start</button>' +
    "</div></div>" + quizHistoryCard() + "</div>";
  $("foot").innerHTML =
    "Chart and index questions count towards how well the app thinks you know the chart, the same " +
    "as hands you actually play. Running and true count drills do not \u2014 they have no square " +
    "behind them. None of it touches your money \u2014 except the chips quiz, which is the only way " +
    "to get more once you have lost what you had.";
  statsThenRedraw("quiz", () => !QUIZ);
}

function customBuilder() {
  const secs = [["hard", "Hard totals"], ["soft", "Soft totals"], ["pair", "Pairs & splits"]];
  const onlys = [["all", "Everything"], ["splits", "Only hands the chart splits"],
                 ["doubles", "Only hands the chart doubles"], ["stand_or_hit", "Only hit-or-stand"]];
  return '<div class="panel" style="margin-top:16px"><div class="phead"><h2>WHAT TO DRILL</h2></div>' +
    '<div class="pbody">' +
    '<div class="field"><label>PARTS OF THE CHART</label><div class="pills">' +
    secs.map(([k, l]) => '<button class="pill' + (QUIZ_SETUP.sections.indexOf(k) >= 0 ? " on" : "") +
      '" onclick="toggleSec(\'' + k + '\')">' + l + "</button>").join("") + "</div></div>" +
    '<div class="field"><label>DEALER SHOWING <em class="hint">' +
    (QUIZ_SETUP.upcards.length ? QUIZ_SETUP.upcards.map(upLabel).join(", ") : "any") +
    "</em></label><div class=\"pills\">" +
    [2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((u) => '<button class="pill sq' +
      (QUIZ_SETUP.upcards.indexOf(u) >= 0 ? " on" : "") + '" onclick="toggleUp(' + u + ')">' +
      upLabel(u) + "</button>").join("") +
    '<button class="pill" onclick="QUIZ_SETUP.upcards=[];draw()">Any</button></div></div>' +
    '<div class="field"><label>NARROW IT DOWN</label><div class="pills">' +
    onlys.map(([k, l]) => '<button class="pill' + (QUIZ_SETUP.only === k ? " on" : "") +
      '" onclick="QUIZ_SETUP.only=\'' + k + "';draw()\">" + l + "</button>").join("") + "</div></div>" +
    '<p class="fine">A pair of aces against a 4 turns up about once every two thousand hands. ' +
    "Everything in this app that is hard to learn is hard for that reason and no other, which is " +
    "why drilling the rare corners is worth more per minute than playing.</p>" +
    "</div></div>";
}
function toggleSec(k) {
  const i = QUIZ_SETUP.sections.indexOf(k);
  if (i >= 0) { if (QUIZ_SETUP.sections.length > 1) QUIZ_SETUP.sections.splice(i, 1); }
  else QUIZ_SETUP.sections.push(k);
  draw();
}
function toggleUp(u) {
  const i = QUIZ_SETUP.upcards.indexOf(u);
  if (i >= 0) QUIZ_SETUP.upcards.splice(i, 1); else QUIZ_SETUP.upcards.push(u);
  draw();
}

function quizHistoryCard() {
  const list = (STATS && STATS.quizzes) || [];
  if (!list.length) return "";
  return '<div class="panel" style="margin-top:16px"><div class="phead"><h2>PAST QUIZZES</h2></div>' +
    '<div class="pbody"><table class="t wide"><tr><th>when</th><th>kind</th><th>score</th><th>chips</th></tr>' +
    list.slice(0, 10).map((q) => "<tr><td>" + day(q.at) + "</td><td>" + q.mode + "</td><td>" +
      q.correct + " / " + q.length + "</td><td>" + (q.chips_earned ? money(q.chips_earned) : "—") +
      "</td></tr>").join("") + "</table></div></div>";
}

async function startQuiz() {
  const body = { mode: QUIZ_SETUP.mode, length: QUIZ_SETUP.length };
  if (QUIZ_SETUP.mode === "custom") {
    body.filters = { sections: QUIZ_SETUP.sections, only: QUIZ_SETUP.only };
    if (QUIZ_SETUP.upcards.length) body.filters.upcards = QUIZ_SETUP.upcards;
  }
  const q = await api("/api/quiz/start", Object.assign({ account: ACCOUNT.id }, body));
  if (q.error) return toast(q.error);
  QUIZ = q; QUIZ.last = null;
  draw();
}

async function answerQuiz(move) {
  if (!QUIZ || QUIZ.last) return;
  const r = await api("/api/quiz/answer", { account: ACCOUNT.id, quiz: QUIZ.quiz, move });
  if (r.error) return toast(r.error);
  const asked = QUIZ.question;
  QUIZ = Object.assign({}, QUIZ, r);
  QUIZ.last = Object.assign({ asked }, r.result);
  if (r.done) {
    // the merge above keeps whatever the previous response held, and the last
    // response carries no question at all -- clear it or the runner shows the
    // question you have already answered instead of the summary
    QUIZ.question = null;
    QUIZ.legal = [];
    ACCOUNT.chips = r.chips;
    STATS = null;
    if (r.earned) toast("You won " + money(r.earned) + " in chips.");
  }
  draw();
}

function nextQuiz() {
  if (!QUIZ) return;
  QUIZ.last = null;
  draw();
}

function drawQuizRunner() {
  const q = QUIZ;
  const last = q.last;
  const pctDone = q.length ? (q.answered / q.length) * 100 : 0;

  if (q.done && !last) return drawQuizSummary();

  $("wrap").innerHTML =
    '<div class="single"><div class="panel"><div class="phead"><h2>' +
    esc((q.title || "Quiz").toUpperCase()) + "</h2><em>" + q.answered + " of " + q.length +
    " · " + q.correct + " right" + (q.for_chips ? " · " + money(q.correct * q.reward) + " earned" : "") +
    "</em></div>" +
    '<div class="qprog"><i style="width:' + pctDone + '%"></i></div>' +
    '<div class="pbody">' +
    (last ? quizFeedback(last, q) : quizQuestion(q)) +
    "</div></div>" +
    '<button class="mv" style="width:100%;margin-top:12px" onclick="abandonQuiz()">Leave the quiz</button>' +
    "</div>";
  $("foot").innerHTML = q.blurb || "";
}

function quizQuestion(q) {
  const x = q.question;
  const kind = x.kind || "play";
  if (kind === "running") return quizRunning(q, x);
  if (kind === "true") return quizTrue(q, x);
  if (kind === "insurance") return quizInsurance(q, x);
  return quizHand(q, x);
}

/* Count these cards. The starting count is given, because a count you cannot
   start from is not a count. */
function quizRunning(q, x) {
  return '<div class="qcount"><div class="zlab">RUNNING COUNT BEFORE</div>' +
    '<div class="qbig">' + (x.start >= 0 ? "+" : "−") + Math.abs(x.start) + "</div>" +
    '<div class="zlab" style="margin-top:14px">THESE COME OUT</div>' +
    '<div class="hand-row qrun">' + x.cards.map((c) => cardEl(c)).join("") + "</div>" +
    "</div>" + quizNumberEntry("What is the running count now?", "+0");
}

/* The division. Decks remaining are given here — judging the tray is practised
   at the table, where there is a tray to judge. */
function quizTrue(q, x) {
  return '<div class="qcount"><div class="pairq">' +
    '<div><div class="zlab">RUNNING COUNT</div><div class="qbig">' +
    (x.running >= 0 ? "+" : "−") + Math.abs(x.running) + "</div></div>" +
    '<div><div class="zlab">DECKS LEFT</div><div class="qbig">' + x.decks_left + "</div></div>" +
    "</div></div>" + quizNumberEntry("What is the true count?", "+0.0");
}

function quizInsurance(q, x) {
  return '<div class="qcount"><div class="zlab">DEALER SHOWS AN ACE · INSURANCE OFFERED</div>' +
    '<div class="hand-row" style="margin:10px 0 16px">' +
    cardEl({ rank: "A", suit: "♠", red: false }) + '<div class="card down"></div></div>' +
    '<div class="zlab">TRUE COUNT</div><div class="qbig">' +
    (x.true_count >= 0 ? "+" : "−") + Math.abs(x.true_count).toFixed(1) + "</div></div>" +
    '<div class="moves" style="margin-top:18px">' +
    '<button class="mv" onclick="answerQuiz(\'take\')">Take it<small>INSURANCE</small></button>' +
    '<button class="mv" onclick="answerQuiz(\'decline\')">No thanks<small>DECLINE</small></button>' +
    "</div>";
}

function quizNumberEntry(label, ph) {
  return '<div class="qnum"><label>' + esc(label) + "</label>" +
    '<input id="qn" type="text" inputmode="text" autocomplete="off" placeholder="' + ph +
    '" onkeydown="if(event.key===\'Enter\'){event.preventDefault();submitNumber();}">' +
    '<button class="mv go" onclick="submitNumber()">Answer</button></div>';
}

function submitNumber() {
  const el = $("qn");
  if (!el || !el.value.trim()) return;
  answerQuiz(el.value.trim());
}

function quizHand(q, x) {
  return (x.true_count != null
      ? '<div class="qtc">TRUE COUNT <b>' +
        (x.true_count >= 0 ? "+" : "−") + Math.abs(x.true_count).toFixed(1) + "</b></div>"
      : "") +
    '<div class="qtable">' +
    '<div class="qside"><div class="zlab">DEALER SHOWS</div>' +
    '<div class="hand-row">' + cardEl(x.up_card) + '<div class="card down"></div></div></div>' +
    '<div class="qside"><div class="zlab">YOU HAVE</div>' +
    '<div class="hand-row">' + x.cards.map((c) => cardEl(c)).join("") + "</div>" +
    '<div class="total">' + x.total + (x.soft ? "<em>SOFT</em>" : "") + "</div></div></div>" +
    '<div class="moves" style="margin-top:18px">' +
    (q.legal || []).map((m) => '<button class="mv" onclick="answerQuiz(\'' + m + "')\">" +
      cap(MOVE[m]) + "<small>" + m + "</small></button>").join("") + "</div>" +
    '<p class="fine" style="margin-top:14px">' +
    (x.rarity < 0.0015
      ? "This one comes up about once every " + Math.round(1 / Math.max(x.rarity, 1e-6)) +
        " hands at a real table."
      : "Answer from the chart, not from the odds — the chart is what you can actually recall at speed.") +
    "</p>";
}

/* Answers come in three shapes now: a chart move, a typed number, and
   take/decline. Naming them is the only part that differs. */
function answerName(last, v) {
  const kind = (last.asked && last.asked.kind) || "play";
  if (kind === "running" || kind === "true")
    return String(v).replace(/^-/, "\u2212");
  if (kind === "insurance") return v === "take" ? "take it" : "decline";
  return MOVE[v] || String(v);
}

function quizFeedback(last, q) {
  const e = last.explanation;
  const terms = (e && e.terms) || [];
  const kind = (last.asked && last.asked.kind) || "play";
  const numeric = kind === "running" || kind === "true";
  return '<div class="verdict ' + (last.correct ? "yes" : "no") + '"><h3>' +
    (last.correct ? "Right — " + answerName(last, last.answer)
                  : "No — " + cap(answerName(last, last.answer))) +
    "</h3><p>" + (last.detail ? esc(last.detail) + " " : esc(last.cell) + " → <kbd>" +
      answerName(last, last.answer) + "</kbd>") +
    (last.correct ? "" : " You said <kbd>" + esc(String(last.chose)) + "</kbd>" +
      (numeric || !last.cost ? "" : ", which gives up <b>" + last.cost.toFixed(3) +
        "</b> per dollar")) + "</p></div>" +
    (e && e.rule_note ? '<div class="note">' + esc(e.rule_note) + "</div>" : "") +
    (e
      ? '<div class="hook" style="margin-top:14px">' + link(e.hook, terms) + "</div>" +
        '<div class="prose">' + e.paragraphs.map((p) => "<p>" + link(p, terms) + "</p>").join("") + "</div>" +
        '<div class="recall"><span>WORTH MEMORISING</span><p>' + e.remember + "</p></div>"
      : "") +
    (last.evs
      ? '<div class="evrows" style="margin-top:14px">' +
        Object.entries(last.evs).sort((a, b) => b[1] - a[1]).map(([m, v]) =>
          '<div class="evrow' + (m === last.best ? " win" : "") + '"><div class="nm">' + cap(MOVE[m]) +
          '</div><div class="vl">' + ev(v) + "</div></div>").join("") + "</div>"
      : "") +
    '<button class="mv go" style="width:100%;margin-top:16px" onclick="' +
    (q.done ? "showQuizSummary()" : "nextQuiz()") + '">' +
    (q.done ? "See how you did" : "Next question") + "<small>SPACE</small></button>";
}

function showQuizSummary() { QUIZ.last = null; draw(); }

function drawQuizSummary() {
  const q = QUIZ;
  const score = q.length ? q.correct / q.length : 0;
  $("wrap").innerHTML =
    '<div class="single"><div class="panel"><div class="phead"><h2>DONE</h2><em>' +
    esc(q.title || "") + "</em></div><div class=\"pbody\">" +
    '<div class="two"><div><div class="big ' + (score >= 0.9 ? "up" : score < 0.6 ? "down" : "") + '">' +
    q.correct + " / " + q.length + '</div><div class="sub">correct</div></div>' +
    (q.for_chips
      ? '<div><div class="big up">' + money(q.earned || 0) + '</div><div class="sub">chips won · ' +
        money(q.chips) + " total</div></div>"
      : '<div><div class="big">' + Math.round(score * 100) + '%</div><div class="sub">this quiz</div></div>') +
    "</div>" +
    ((q.review || []).length
      ? '<h3 class="mini-h">EVERY QUESTION</h3><table class="t wide">' +
        '<tr><th>hand</th><th>you said</th><th>answer</th><th>cost</th></tr>' +
        q.review.map((r) => '<tr class="' + (r.correct ? "" : "wrong") + '"><td>' + esc(r.cell) +
          "</td><td>" + (r.chose ? MOVE[r.chose] : "—") + "</td><td>" + MOVE[r.answer] +
          "</td><td>" + (r.cost ? r.cost.toFixed(3) : "—") + "</td></tr>").join("") + "</table>"
      : "") +
    '<div class="moves" style="margin-top:16px">' +
    '<button class="mv go" onclick="QUIZ=null;startQuiz()">Go again</button>' +
    '<button class="mv" onclick="QUIZ=null;draw()">Pick another kind</button>' +
    (q.for_chips && q.chips >= (S.config.table_min || 15)
      ? '<button class="mv" onclick="QUIZ=null;go(\'table\')">Take it to the table</button>' : "") +
    "</div></div></div></div>";
  $("foot").innerHTML = "";
}

async function abandonQuiz() {
  if (QUIZ && QUIZ.answered < QUIZ.length) {
    const yes = await ask("Leave this quiz?",
      "Your answers so far are kept, but an unfinished chips quiz pays nothing.",
      "Leave");
    if (!yes) return;
  }
  QUIZ = null; STATS = null; draw();
}

/* =======================================================================
   ANALYSIS
   ======================================================================= */
let ANA = "skill";
let SIMFORM = { runs: 20, hands: 500, table_min: null, bankroll: null, ramp: "flat", skill: "perfect" };
let CALCFORM = { table_min: null, hands: 400, ruin_target: 0.05 };


/* ---------------- how the counting is going ----------------
   Three separate skills, reported separately, because they fail for different
   reasons: keeping the running count is arithmetic, judging the tray is a
   guess, and the index plays are memory. One number would hide which. */
function countingPanel(st) {
  const c = st.counting || {};
  const ch = c.checks || {};
  const rec = c.indices || {};
  const plays = c.plays || [];

  const seen = plays.filter((p) => rec[p.key]);
  const right = seen.reduce((n, p) => n + rec[p.key].right, 0);
  const total = seen.reduce((n, p) => n + rec[p.key].seen, 0);

  const worst = plays
    .filter((p) => rec[p.key] && rec[p.key].seen >= 2)
    .map((p) => ({ p, r: rec[p.key], rate: rec[p.key].right / rec[p.key].seen }))
    .sort((a, b) => a.rate - b.rate)
    .slice(0, 6);

  return '<div class="panel"><div class="phead"><h2>THE COUNTING</h2><em>' +
    (ch.asked ? ch.asked + " checks · " + total + " index plays" : "nothing recorded yet") +
    "</em></div><div class=\"pbody\">" +

    '<div class="two">' +
    '<div><div class="big ' + (ch.accuracy == null ? "" : ch.accuracy >= 80 ? "up" : "down") + '">' +
    (ch.accuracy == null ? "—" : ch.accuracy + "%") +
    '</div><div class="sub">running counts kept</div></div>' +
    '<div><div class="big ' + (!total ? "" : right / total >= 0.8 ? "up" : "down") + '">' +
    (total ? Math.round((right / total) * 100) + "%" : "—") +
    '</div><div class="sub">index plays right</div></div></div>' +

    (ch.asked
      ? '<div class="kv"><span>Checks you asked for yourself</span><b>' +
        (ch.asked - (ch.interrupted || 0)) + "</b></div>" +
        '<div class="kv"><span>Checks that interrupted you</span><b>' + (ch.interrupted || 0) +
        (ch.interrupted ? " · " + (ch.interrupted_right || 0) + " right" : "") + "</b></div>" +
        '<div class="kv"><span>Typical error when you were wrong</span><b>' +
        (ch.avg_drift == null ? "—" : "±" + ch.avg_drift) + "</b></div>" +
        '<div class="kv"><span>Worst you have ever been out</span><b>' +
        (ch.worst_drift ? "±" + ch.worst_drift : "—") + "</b></div>"
      : '<p class="idle" style="margin-top:12px">Press <b>REVEAL COUNT</b> at the table, or ' +
        "let a check interrupt you, and this fills in.</p>") +

    (worst.length
      ? '<div style="margin-top:14px"><p class="small">The index plays you are getting wrong. ' +
        "These are worth more than any square on the basic chart, because they only come up " +
        "when the money is already big.</p>" +
        worst.map((w) => '<div class="miss"><div>' + esc(ixLabel(w.p)) + " · index " +
          ixNum(w.p.index) + "</div><span>" + w.r.right + "/" + w.r.seen + "</span></div>").join("") +
        "</div>"
      : "") +

    '<div class="pic" style="margin-top:14px">A running count you cannot keep makes every ' +
    "index play below it worthless, and an index you have not learned wastes a count you kept " +
    "perfectly. They are worth practising in that order.</div>" +
    "</div></div>";
}

async function viewAnalysis() {
  const st = await needStats();
  if (TAB !== "analysis") return;
  if (SIMFORM.table_min == null) {
    SIMFORM.table_min = st.config.table_min;
    SIMFORM.bankroll = st.config.table_min * 40;
    CALCFORM.table_min = st.config.table_min;
  }
  const tabs = [["skill", "How you play"], ["sim", "Simulator"], ["calc", "Bankroll calculator"],
                ["ledger", "All-time ledger"]];
  $("wrap").innerHTML =
    '<div class="single wide9">' +
    '<div class="subtabs">' + tabs.map(([k, l]) =>
      '<button class="' + (ANA === k ? "on" : "") + '" onclick="ANA=\'' + k + "';draw()\">" + l +
      "</button>").join("") + "</div>" +
    '<div id="anabody"></div></div>';
  ({ skill: anaSkill, sim: anaSim, calc: anaCalc, ledger: anaLedger }[ANA])(st);
}

/* ---- how you play ---- */
function anaSkill(st) {
  const sk = st.skill, cov = sk.coverage, tr = sk.trend;
  const perHand = sk.cost_per_hand;
  const min = st.config.table_min;
  const hourly = perHand == null ? null : perHand * min * 80;

  $("anabody").innerHTML =
    '<div class="grid2">' +
    '<div class="panel"><div class="phead"><h2>THE TWO NUMBERS</h2><em>' + num(sk.decisions) +
    " decisions</em></div><div class=\"pbody\">" +
    '<div class="two"><div><div class="big">' + pct(sk.accuracy) + '</div>' +
    '<div class="sub">accuracy — decisions you got right, plainly counted</div></div>' +
    '<div><div class="big ' + (sk.sharpness >= 0.9 ? "up" : sk.sharpness < 0.6 ? "down" : "") + '">' +
    pct(sk.sharpness) + '</div><div class="sub">sharpness — weighted so mastered hands stop ' +
    "propping it up</div></div></div>" +
    '<div class="bandline"><span class="band ' + sk.band + '">' + sk.band + "</span></div>" +
    (sk.confidence < 1
      ? '<div class="note"><b>Still warming up.</b> Sharpness needs about ' + sk.ramp +
        " decisions before it means much; you have " + num(sk.decisions) + ". Until then it is blended " +
        "towards plain accuracy so it does not jump around. <b>" +
        Math.round(sk.confidence * 100) + "%</b> of the way there." +
        '<div class="bar2" style="margin-top:8px"><i style="width:' +
        Math.round(sk.confidence * 100) + '%"></i></div></div>'
      : "") +
    '<h3 class="mini-h">WHY THEY DIFFER</h3>' +
    '<p class="small">Every square of the chart carries a weight. Play one right a few times running ' +
    "and its weight decays — a hard 20 against a 6 stops counting once you have proved you know " +
    "it. Miss one and the weight springs back, and squares where a mistake is expensive count double. " +
    "So accuracy measures how many decisions you made; sharpness measures how much of the chart you " +
    "actually know. The gap between them is the part you are still getting away with.</p>" +
    (tr
      ? '<div class="kv" style="margin-top:10px"><span>Last ' + tr.window + " decisions</span><b>" +
        pct(tr.recent) + "</b></div>" +
        (tr.previous != null
          ? '<div class="kv"><span>The ' + tr.window + " before that</span><b>" + pct(tr.previous) +
            "</b></div>" +
            '<div class="kv"><span>Moving</span><b class="' + cls(tr.recent - tr.previous) + '">' +
            (tr.recent >= tr.previous ? "↑ " : "↓ ") +
            pct(Math.abs(tr.recent - tr.previous), 1) + "</b></div>"
          : "")
      : "") +
    "</div></div>" +

    '<div class="panel"><div class="phead"><h2>WHAT IT COSTS</h2></div><div class="pbody">' +
    (perHand == null
      ? '<p class="idle">Play some hands and this fills in.</p>'
      : '<div class="big ' + (hourly < 1 ? "" : "down") + '">' + money(hourly) + '</div>' +
        '<div class="sub">an hour, at a ' + money(min) + " table — on top of the house edge</div>" +
        '<p class="small" style="margin-top:12px">Worked out square by square: how often you get each ' +
        "one wrong, times what that particular mistake gives away, times how often the hand turns up. " +
        "About 80 hands an hour at a full table.</p>" +
        '<div class="kv" style="margin-top:10px"><span>Given away per hand</span><b>' +
        perHand.toFixed(4) + " bets</b></div>" +
        '<div class="kv"><span>The house edge itself</span><b>0.0050 bets</b></div>' +
        '<div class="kv"><span>So your mistakes are</span><b class="' +
        (perHand > 0.005 ? "down" : "up") + '">' + (perHand / 0.005).toFixed(1) +
        "× the house edge</b></div>" +
        '<div class="note ' + (perHand > 0.005 ? "bad" : "ok") + '">' +
        (perHand > 0.005
          ? "Your mistakes currently cost you more than the casino does. That is the good news — " +
            "the house edge is fixed and this part is not."
          : "Your mistakes now cost less than the house edge, which is about as good as this gets. " +
            "Beyond here the game is what it is.") + "</div>") +
    '<h3 class="mini-h">HOW MUCH OF THE CHART YOU HAVE BEEN TESTED ON</h3>' +
    '<div class="covbar"><i class="solid" style="width:' + (cov.solid / cov.total * 100) + '%"></i>' +
    '<i class="seen" style="width:' + ((cov.seen - cov.solid) / cov.total * 100) + '%"></i></div>' +
    '<div class="kv"><span>Solid</span><b>' + cov.solid + " of " + cov.total + "</b></div>" +
    '<div class="kv"><span>Seen but shaky</span><b>' + (cov.seen - cov.solid) + "</b></div>" +
    '<div class="kv"><span>Never come up</span><b>' + cov.unseen + "</b></div>" +
    (cov.unseen > 0
      ? '<button class="mv" style="width:100%;margin-top:12px" onclick="quizRare()">Quiz me on the ' +
        cov.unseen + " I have never seen</button>"
      : "") +
    "</div></div></div>" +

    '<div class="grid2" style="margin-top:16px">' +
    '<div class="panel"><div class="phead"><h2>HABITS, NOT SQUARES</h2></div><div class="pbody">' +
    (st.leaks.length
      ? st.leaks.map((l) => '<div class="leak"><div class="lh"><b>' +
          Math.round(l.rate * 100) + "% wrong</b><span>" + l.misses + " of " + l.seen + "</span></div>" +
          "<p>" + l.text + "</p>" +
          '<div class="chips2">' + l.cells.map((c) => "<span>" + esc(c) + "</span>").join("") + "</div></div>").join("")
      : '<p class="idle">No pattern yet — either you are playing well or there is not enough ' +
        "here to see one. A pattern needs eight sightings of the same kind of hand before it counts.</p>") +
    '<div class="pic" style="margin-top:14px">A list of squares tells you what you got wrong. A ' +
    "pattern tells you why, and one idea is easier to fix than forty corrections.</div>" +
    "</div></div>" +

    countingPanel(st) +

    '<div class="panel"><div class="phead"><h2>WHAT TO WORK ON NEXT</h2></div><div class="pbody">' +
    '<p class="small">Ordered by how much each one is holding your score down — how often you ' +
    "miss it, how much the miss costs, and how sure we are it was not a fluke.</p>" +
    (st.drill.length
      ? '<table class="t wide" style="margin-top:10px"><tr><th>hand</th><th>right</th>' +
        "<th>should</th><th>holding you back</th></tr>" +
        st.drill.map((d) => "<tr><td>" + esc(d.cell) + "</td><td>" + d.correct + " / " + d.seen +
          "</td><td>" + (d.should ? CODE_NAME[d.should] : "—") + '</td><td><div class="leakbar">' +
          '<i style="width:' + Math.min(100, d.leak / (st.drill[0].leak || 1) * 100) + '%"></i></div></td></tr>')
          .join("") + "</table>" +
        '<button class="mv go" style="width:100%;margin-top:14px" onclick="quizWeak()">Quiz me on these</button>'
      : '<p class="idle">Nothing to work on yet.</p>') +
    "</div></div></div>" +

    '<div class="grid2" style="margin-top:16px">' +
    sectionCard("BY KIND OF HAND", sk.by_section) +
    upcardCard(sk.by_upcard) +
    "</div>";
  $("foot").innerHTML =
    "Quiz answers and hands played both feed these numbers. Sharpness is the one to watch: it is the " +
    "only one that can go down when you get worse at something you used to know.";
}

function sectionCard(title, by) {
  const names = { hard: "Hard totals", soft: "Soft totals", pair: "Pairs and splits" };
  return '<div class="panel"><div class="phead"><h2>' + title + "</h2></div><div class=\"pbody\">" +
    ["hard", "soft", "pair"].map((k) => {
      const d = by[k];
      if (!d) return '<div class="kv"><span>' + names[k] + "</span><b>never come up</b></div>";
      return '<div class="secrow"><div class="sh"><b>' + names[k] + "</b><span>" + d.seen +
        " decisions across " + d.cells + " squares</span></div>" +
        '<div class="dual"><div class="db"><i style="width:' + d.accuracy * 100 + '%"></i></div>' +
        "<em>" + pct(d.accuracy) + "</em></div></div>";
    }).join("") +
    '<p class="fine">Pairs are where almost everyone is worst, because they are the rarest and the ' +
    "chart for them looks the least like common sense.</p></div></div>";
}

function upcardCard(by) {
  const max = Math.max(1, ...Object.values(by).map((d) => d.seen || 0));
  return '<div class="panel"><div class="phead"><h2>BY WHAT THE DEALER SHOWS</h2></div>' +
    '<div class="pbody"><div class="upgrid">' +
    Object.entries(by).map(([label, d]) =>
      '<div class="upcell' + (d.accuracy == null ? " none" : d.accuracy >= 0.9 ? " good" :
        d.accuracy < 0.7 ? " bad" : "") + '"><b>' + label + "</b>" +
      "<em>" + (d.accuracy == null ? "—" : Math.round(d.accuracy * 100) + "%") + "</em>" +
      '<u style="height:' + Math.round((d.seen / max) * 26) + 'px"></u>' +
      "<span>" + d.seen + "</span></div>").join("") +
    "</div>" +
    '<p class="fine">Bar height is how often you have faced it, the percentage is how often you were ' +
    "right. A weak spot against one upcard usually means one row of the chart, not a general problem.</p>" +
    "</div></div>";
}

function quizWeak() { QUIZ_SETUP = { mode: "weak", length: 20, sections: ["hard", "soft", "pair"], upcards: [], only: "all" }; TAB = "quiz"; QUIZ = null; draw(); startQuiz(); }
function quizRare() { QUIZ_SETUP = { mode: "rare", length: 20, sections: ["hard", "soft", "pair"], upcards: [], only: "all" }; TAB = "quiz"; QUIZ = null; draw(); startQuiz(); }
function quizMissed() { QUIZ_SETUP = { mode: "missed", length: 15, sections: ["hard", "soft", "pair"], upcards: [], only: "all" }; TAB = "quiz"; QUIZ = null; draw(); startQuiz(); }

/* ---- simulator ---- */
function anaSim(st) {
  const f = SIMFORM;
  $("anabody").innerHTML =
    '<div class="panel"><div class="phead"><h2>RUN THE GAME MANY TIMES</h2>' +
    "<em>independent sessions, same rules</em></div><div class=\"pbody\">" +
    '<div class="formgrid">' +
    numField("Smallest bet", "table_min", f.table_min, [5, 10, 15, 25, 50, 100]) +
    numField("Bankroll you sit down with", "bankroll", f.bankroll,
             [f.table_min * 10, f.table_min * 20, f.table_min * 40, f.table_min * 100]) +
    numField("Hands per session", "hands", f.hands, [100, 250, 500, 1000, 2000, 5000]) +
    numField("How many sessions", "runs", f.runs, [1, 5, 20, 50, 100]) +
    '<div class="field"><label>BET SIZING</label><div class="pills">' +
    [["flat", "Flat"], ["mild", "Spread 1–4 by count"], ["steep", "Spread 1–12 by count"]]
      .map(([k, l]) => '<button class="pill' + (f.ramp === k ? " on" : "") + '" onclick="SIMFORM.ramp=\'' +
        k + "';draw()\">" + l + "</button>").join("") + "</div></div>" +
    '<div class="field"><label>WHO IS PLAYING</label><div class="pills">' +
    [["perfect", "Perfect basic strategy"], ["mine", "Me, with my current error rate"],
     ["custom", "A 5% error rate"]]
      .map(([k, l]) => '<button class="pill' + (f.skill === k ? " on" : "") + '" onclick="SIMFORM.skill=\'' +
        k + "';draw()\">" + l + "</button>").join("") + "</div></div>" +
    "</div>" +
    '<button class="mv go" style="width:100%;margin-top:6px" onclick="runSim()"' +
    (SIM_BUSY ? " disabled" : "") + ">" + (SIM_BUSY ? "Dealing…" : "Run it") + "</button>" +
    '<p class="fine">Same shoe rules, same chart, same penetration as the table you have set up. ' +
    "Each session uses its own shuffle and its own luck, so they are genuinely independent — " +
    "which is the point. One session tells you nothing.</p>" +
    "</div></div>" +
    (SIM ? simResults(SIM) : "");
  $("foot").innerHTML = SIM
    ? "Each faint line is one session. The shaded band covers the middle eighty percent of them at " +
      "each point, and the solid line is the median. The spread is not noise in the measurement — " +
      "it is the game."
    : "";
}

function numField(label, key, value, presets, form) {
  form = form || "SIMFORM";
  return '<div class="field"><label>' + label.toUpperCase() + "</label>" +
    '<div class="pills">' + presets.filter((p, i, a) => p > 0 && a.indexOf(p) === i).map((p) =>
      '<button class="pill' + (value === p ? " on" : "") + '" onclick="' + form + "." + key + "=" + p +
      ';draw()">' + (key === "bankroll" || key === "table_min" ? money(p) : num(p)) + "</button>").join("") +
    "</div></div>";
}

async function runSim() {
  SIM_BUSY = true; draw();
  const body = Object.assign({ account: ACCOUNT.id }, SIMFORM);
  SIM = await api("/api/simulate", body);
  SIM_BUSY = false;
  draw();
}

function simResults(m) {
  const s = m.settings;
  const lo = Math.min(0, m.worst), hi = Math.max(m.best, m.start);
  return '<div class="panel" style="margin-top:16px"><div class="phead"><h2>' + m.runs +
    " SESSIONS OF " + num(s.hands) + " HANDS</h2><em>" + money(s.bankroll) + " at a " +
    money(s.table_min) + " table</em></div><div class=\"pbody\">" +
    curveChart(m, lo, hi) +
    '<div class="statgrid">' +
    stat("Median finish", money(m.median_final), cls(m.median_net)) +
    stat("Median result", money(m.median_net), cls(m.median_net)) +
    stat("Best finish", money(m.best), "up") +
    stat("Worst finish", money(m.worst), "down") +
    stat("Sessions finishing up", m.up_sessions + " of " + m.runs, m.up_sessions * 2 > m.runs ? "up" : "down") +
    stat("Ran out of money", Math.round(m.bust_rate * 100) + "%", m.bust_rate > 0.2 ? "down" : "") +
    stat("Typical worst drawdown", money(m.median_drawdown), "") +
    stat("Deepest drawdown seen", money(m.worst_drawdown), "down") +
    stat("Edge over " + money(Math.round(m.wagered)) + " wagered",
         ((m.edge || 0) * 100).toFixed(3) + "%", cls(m.edge)) +
    "</div>" +
    '<h3 class="mini-h">WHERE THE ' + m.runs + " SESSIONS ENDED UP</h3>" +
    histogram(m.histogram) +
    '<div class="note">The middle of that spread is what "the house edge is half a percent" actually ' +
    "means over " + num(s.hands) + " hands: a median result of <b>" + money(m.median_net) +
    "</b> hidden inside a range from <b>" + money(m.worst - m.start) + "</b> to <b>" +
    money(m.best - m.start) + "</b>. Anyone telling you what happened to them last night is quoting " +
    "one line off this chart.</div>" +
    (s.skill === "mine"
      ? '<div class="note bad">This run used your own error rate, square by square. Set it to ' +
        "perfect basic strategy and run it again — the difference is what the chart is worth to you.</div>"
      : "") +
    (m.theory && m.theory.length ? survivalTable(m, s) : "") +
    '<h3 class="mini-h">EVERY SESSION</h3>' +
    '<div class="cscroll"><table class="t wide"><tr><th>#</th><th>hands</th><th>finished</th>' +
    "<th>result</th><th>high</th><th>low</th><th>worst drawdown</th></tr>" +
    m.sessions.map((x, i) => '<tr class="' + (x.busted ? "wrong" : "") + '"><td>' + (i + 1) +
      "</td><td>" + num(x.hands) + "</td><td>" + money(x.final) + '</td><td class="' + cls(x.net) +
      '">' + money(x.net) + "</td><td>" + money(x.peak) + "</td><td>" + money(x.trough) +
      "</td><td>" + money(x.max_drawdown) + "</td></tr>").join("") + "</table></div>" +
    "</div></div>";
}

/* The closed-form answer next to the simulated one. Two different methods on the
   same question is the only cheap way to notice when one of them is wrong. */
function survivalTable(m, s) {
  return '<h3 class="mini-h">WHAT THE MATHS SAYS, NEXT TO WHAT HAPPENED</h3>' +
    '<div class="cscroll"><table class="t wide"><tr><th>after</th><th>hours</th>' +
    "<th>chance you still have money</th><th>where the average sits</th></tr>" +
    m.theory.map((r) => "<tr><td>" + num(r.hands) + " hands</td><td>" + r.hours +
      "</td><td>" + pct(r.survive, 1) + "</td><td>" + money(r.expected) + "</td></tr>").join("") +
    "</table></div>" +
    '<p class="fine">Worked out from a random walk with the measured edge and a 1.14-bet ' +
    "swing per hand — no dealing involved. " + compareSurvival(m, s) +
    " The formula leans pessimistic, which is the direction you want an estimate of " +
    "going broke to lean.</p>";
}

function compareSurvival(m, s) {
  // the theory row closest to the length actually simulated
  const row = m.theory.reduce((best, r) =>
    Math.abs(r.hands - s.hands) < Math.abs(best.hands - s.hands) ? r : best, m.theory[0]);
  return "At " + num(row.hands) + " hands it puts survival at " + pct(row.survive, 0) +
    "; of the " + m.runs + " sessions actually dealt over " + num(s.hands) + " hands, " +
    pct(1 - m.bust_rate, 0) + " still had money.";
}

function stat(label, value, klass) {
  return '<div class="sc"><b class="' + (klass || "") + '">' + value + "</b><span>" + label + "</span></div>";
}

function curveChart(m, lo, hi) {
  const W = 900, H = 260, PAD = 44;
  const n = m.bands.length;
  const range = (hi - lo) || 1;
  const x = (i) => PAD + (i / Math.max(1, n - 1)) * (W - PAD - 12);
  const y = (v) => H - 22 - ((v - lo) / range) * (H - 40);

  const bandPath =
    m.bands.map((b, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(b.hi).toFixed(1)).join("") +
    m.bands.slice().reverse().map((b, i) =>
      "L" + x(n - 1 - i).toFixed(1) + "," + y(b.lo).toFixed(1)).join("") + "Z";
  const midPath = m.bands.map((b, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(b.mid).toFixed(1)).join("");

  const ticks = [lo, lo + range / 2, hi].map((v) =>
    '<line x1="' + PAD + '" y1="' + y(v) + '" x2="' + (W - 12) + '" y2="' + y(v) +
    '" stroke="#25302f"/><text x="4" y="' + (y(v) + 4) + '" class="ax">' + money(v) + "</text>");

  return '<div class="cscroll"><svg viewBox="0 0 ' + W + " " + H + '" class="chartsvg" ' +
    'role="img" aria-label="Bankroll over ' + m.runs + ' simulated sessions">' +
    ticks.join("") +
    '<line x1="' + PAD + '" y1="' + y(m.start) + '" x2="' + (W - 12) + '" y2="' + y(m.start) +
    '" stroke="#c9a961" stroke-dasharray="3 3" opacity=".6"/>' +
    '<text x="' + (W - 14) + '" y="' + (y(m.start) - 5) + '" class="ax" text-anchor="end">bought in at ' +
    money(m.start) + "</text>" +
    m.curves.map((c) => '<polyline points="' + c.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1)).join(" ") +
      '" fill="none" stroke="#4a5c56" stroke-width="1" opacity=".35"/>').join("") +
    '<path d="' + bandPath + '" fill="#4bbd83" opacity=".13"/>' +
    '<path d="' + midPath + '" fill="none" stroke="#4bbd83" stroke-width="2"/>' +
    '<text x="' + PAD + '" y="' + (H - 5) + '" class="ax">hand 0</text>' +
    '<text x="' + (W - 12) + '" y="' + (H - 5) + '" class="ax" text-anchor="end">hand ' +
    num(m.settings.hands) + "</text>" +
    "</svg></div>";
}

function histogram(h) {
  if (!h || !h.counts) return "";
  const max = Math.max(...h.counts);
  const step = h.step || 1;
  return '<div class="hist">' + h.counts.map((c, i) => {
    const from = h.lo + i * step;
    const win = from + step / 2 >= h.start;
    return '<div class="hb' + (win ? " win" : "") + '" title="' + money(from) + "–" +
      money(from + step) + ": " + c + ' session' + (c === 1 ? "" : "s") + '">' +
      '<i style="height:' + Math.round((c / max) * 100) + '%"></i></div>';
  }).join("") + "</div>" +
    '<div class="histax"><span>' + money(h.lo) + "</span><span>bought in at " + money(h.start) +
    "</span><span>" + money(h.hi) + "</span></div>";
}

/* ---- bankroll calculator ---- */
function anaCalc(st) {
  const f = CALCFORM;
  $("anabody").innerHTML =
    '<div class="grid2">' +
    '<div class="panel"><div class="phead"><h2>HOW MUCH DO I NEED?</h2></div><div class="pbody">' +
    '<p class="small">Pick the smallest bet you are willing to play and how long you want to last. ' +
    "This works out the bankroll that survives it, and tells you how likely it is to survive anyway.</p>" +
    '<div class="field" style="margin-top:14px"><label>SMALLEST BET AT THE TABLE</label>' +
    '<div class="pills">' + [5, 10, 15, 25, 50, 100].map((v) =>
      '<button class="pill' + (f.table_min === v ? " on" : "") + '" onclick="CALCFORM.table_min=' + v +
      ';runCalc()">' + money(v) + "</button>").join("") + "</div></div>" +
    '<div class="field"><label>HANDS YOU WANT TO LAST</label><div class="pills">' +
    [100, 200, 400, 800, 1600, 3200].map((v) =>
      '<button class="pill' + (f.hands === v ? " on" : "") + '" onclick="CALCFORM.hands=' + v +
      ';runCalc()">' + num(v) + "<em> · " + Math.round(v / 80) + "h</em></button>").join("") +
    "</div></div>" +
    '<div class="field"><label>CHANCE OF BUSTING OUT YOU WILL ACCEPT</label><div class="pills">' +
    [[0.20, "1 in 5"], [0.10, "1 in 10"], [0.05, "1 in 20"], [0.01, "1 in 100"]].map(([v, l]) =>
      '<button class="pill' + (Math.abs(f.ruin_target - v) < 1e-9 ? " on" : "") +
      '" onclick="CALCFORM.ruin_target=' + v + ';runCalc()">' + l + "</button>").join("") +
    "</div></div>" +
    '<button class="mv go" style="width:100%" onclick="runCalc()">Work it out</button>' +
    "</div></div>" +
    (CALC ? calcResult(CALC) : '<div class="panel"><div class="pbody"><p class="idle">' +
      "Set the three numbers and press the button.</p></div></div>") +
    "</div>";
  $("foot").innerHTML =
    "Based on a random walk with a half-percent drift against you and a 1.14-bet swing per hand, " +
    "which is blackjack played by the chart. It is slightly pessimistic compared with an actual " +
    "simulation, which is the direction you want an estimate like this to lean.";
  if (!CALC) runCalc();
}

async function runCalc() {
  CALC = await api("/api/calculator", Object.assign({ account: ACCOUNT.id }, CALCFORM));
  if (TAB === "analysis") draw();
}

function calcResult(c) {
  return '<div class="panel"><div class="phead"><h2>THE ANSWER</h2><em>' + money(c.table_min) +
    " table · " + num(c.hands) + " hands · " + c.hours + " hours</em></div><div class=\"pbody\">" +
    '<div class="big">' + money(c.bankroll) + '</div><div class="sub">to have only a ' +
    Math.round(c.ruin_target * 100) + "% chance of busting out before " + num(c.hands) + " hands</div>" +
    '<div class="kv" style="margin-top:14px"><span>That is</span><b>' + c.units + " minimum bets</b></div>" +
    '<div class="kv"><span>Expect to lose, on average</span><b class="down">' + money(c.expected_loss) + "</b></div>" +
    '<div class="kv"><span>Typical swing either way</span><b>±' + money(c.swing) + "</b></div>" +
    '<div class="kv"><span>Roughly</span><b>' + c.hours + " hours of play</b></div>" +
    '<h3 class="mini-h">IF YOU ARE WILLING TO RISK MORE</h3>' +
    '<table class="t wide"><tr><th>chance of busting</th><th>bankroll needed</th><th>bets</th></tr>' +
    c.alternatives.map((a) => "<tr><td>" + Math.round(a.ruin_target * 100) + "%</td><td>" +
      money(a.bankroll) + "</td><td>" + a.units + "</td></tr>").join("") + "</table>" +
    '<h3 class="mini-h">OR IF YOU WANT TO PLAY LONGER</h3>' +
    '<table class="t wide"><tr><th>hands</th><th>hours</th><th>bankroll needed</th></tr>' +
    c.by_hands.map((a) => "<tr><td>" + num(a.hands) + "</td><td>" + Math.round(a.hands / 80) +
      "</td><td>" + money(a.bankroll) + "</td></tr>").join("") + "</table>" +
    '<div class="note">Notice the shape: doubling the hands does not double the money. Ruin is driven ' +
    "by the swing, which grows with the square root of the hands, not by the slow drift of the house " +
    "edge. That is why a bankroll that lasts an hour usually lasts most of an evening — and why " +
    "the edge still takes it in the end.</div>" +
    "</div></div>";
}

/* ---- all-time ledger ---- */
function anaLedger(st) {
  const t = st.totals;
  $("anabody").innerHTML =
    '<div class="panel"><div class="phead"><h2>ALL-TIME ACCOUNTING</h2><em>' + esc(ACCOUNT.name) +
    "</em></div><div class=\"pbody\">" +
    '<div class="statgrid">' +
    stat("Chips in the rack", money(t.chips), "") +
    stat("On the table", money(st.on_table), "") +
    stat("Everything you are worth", money(st.worth), "") +
    stat("Given to you, ever", money(t.granted), "") +
    stat("Won answering questions", money(t.earned), "up") +
    stat("All-time profit and loss", money(t.lifetime), cls(t.lifetime)) +
    "</div>" +
    '<div class="eq" style="margin-top:14px">' + money(st.worth) + " worth − " +
    money(t.granted) + " given − " + money(t.earned) + ' earned = <b class="' +
    (t.lifetime >= 0 ? "pos" : "neg") + '">' + money(t.lifetime) + "</b></div>" +
    '<p class="small">That subtraction is the whole point. Chips handed to you and chips won at the ' +
    "quiz are not winnings, so they come off. What is left can only have come from the table, and it " +
    "is the only number here that cannot flatter you.</p>" +
    moneyChart(st.money_curve) +
    '<div class="statgrid" style="margin-top:16px">' +
    stat("Sessions played", t.sessions, "") +
    stat("Of those, still open", t.sessions_live, "") +
    stat("Ended by running out", t.busted_out, t.busted_out ? "down" : "") +
    stat("Hands dealt to you", num(t.hands), "") +
    stat("Money put across the table", money(t.wagered), "") +
    stat("Kept per dollar bet", t.return_per_dollar == null ? "—" : pct(t.return_per_dollar, 2),
         cls(t.return_per_dollar)) +
    "</div>" +
    "</div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>EVERY MOVEMENT OF MONEY</h2>' +
    "<em>newest first</em></div><div class=\"pbody\"><div class=\"cscroll\">" +
    '<table class="t wide"><tr><th>when</th><th>what</th><th>amount</th><th>chips after</th><th></th></tr>' +
    st.ledger.map((l) => '<tr><td>' + when(l.at) + '</td><td><span class="tag ' + l.kind + '">' +
      l.kind + '</span></td><td class="' + cls(l.amount) + '">' + money(l.amount) + "</td><td>" +
      money(l.balance) + "</td><td>" + esc(l.note) + "</td></tr>").join("") +
    "</table></div></div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>SESSION BY SESSION</h2></div>' +
    '<div class="pbody"><div class="cscroll">' + sessionTable(st.sessions) + "</div></div></div>";
  $("foot").innerHTML = "";
}

function sessionTable(list) {
  if (!list || !list.length) return '<p class="idle">No sessions yet.</p>';
  return '<table class="t wide"><tr><th>#</th><th>started</th><th>hands</th><th>bought in</th>' +
    "<th>cashed out</th><th>result</th><th>accuracy</th><th></th></tr>" +
    list.map((s) => "<tr><td>" + s.number + "</td><td>" + when(s.started) + "</td><td>" +
      num(s.hands) + "</td><td>" + money(s.buy_in) + "</td><td>" +
      (s.cash_out == null ? "—" : money(s.cash_out)) + '</td><td class="' + cls(s.net) + '">' +
      money(s.net) + "</td><td>" + (s.accuracy == null ? "—" : Math.round(s.accuracy * 100) + "%") +
      "</td><td>" + (s.live ? '<span class="tag live">open</span>' :
        s.busted ? '<span class="tag bust">busted</span>' : "") + "</td></tr>").join("") + "</table>";
}

function moneyChart(curve) {
  if (!curve || curve.length < 2) return "";
  const W = 860, H = 130, PAD = 46;
  const vals = curve.map((c) => c.balance);
  const lo = Math.min(0, ...vals), hi = Math.max(...vals), range = hi - lo || 1;
  const x = (i) => PAD + (i / (curve.length - 1)) * (W - PAD - 10);
  const y = (v) => H - 20 - ((v - lo) / range) * (H - 34);
  return '<h3 class="mini-h">CHIPS OVER TIME</h3><div class="cscroll">' +
    '<svg viewBox="0 0 ' + W + " " + H + '" class="chartsvg" role="img" aria-label="Chip balance over time">' +
    '<line x1="' + PAD + '" y1="' + y(0) + '" x2="' + (W - 10) + '" y2="' + y(0) + '" stroke="#25302f"/>' +
    '<text x="4" y="' + (y(hi) + 4) + '" class="ax">' + money(hi) + "</text>" +
    '<text x="4" y="' + (y(lo) + 4) + '" class="ax">' + money(lo) + "</text>" +
    '<polyline points="' + curve.map((c, i) => x(i).toFixed(1) + "," + y(c.balance).toFixed(1)).join(" ") +
    '" fill="none" stroke="#c9a961" stroke-width="1.6"/>' +
    curve.map((c, i) => c.kind === "grant"
      ? '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(c.balance).toFixed(1) + '" r="2.5" fill="#d9a441"/>'
      : "").join("") +
    "</svg></div>";
}

/* =======================================================================
   ACCOUNT
   ======================================================================= */
async function viewAccount() {
  const st = await needStats();
  if (TAB !== "account") return;
  const t = st.totals, sk = st.skill;
  $("wrap").innerHTML =
    '<div class="single wide9"><div class="grid2">' +

    '<div class="panel"><div class="phead"><h2>WHO YOU ARE</h2></div><div class="pbody">' +
    '<div class="field"><label>NAME</label><input type="text" id="rn" value="' +
    esc(ACCOUNT.name) + '" maxlength="32"></div>' +
    '<button class="mv" style="width:100%" onclick="rename()">Save the name</button>' +
    '<div class="kv" style="margin-top:14px"><span>Account opened</span><b>' +
    day(ACCOUNT.created) + "</b></div>" +
    '<div class="kv"><span>Sessions played</span><b>' + t.sessions + "</b></div>" +
    '<div class="kv"><span>Hands dealt to you</span><b>' + num(t.hands) + "</b></div>" +
    '<div class="kv"><span>Decisions scored</span><b>' + num(t.decisions) + "</b></div>" +
    '<div class="kv"><span>Quizzes taken</span><b>' + t.quizzes + "</b></div>" +
    '<div class="kv"><span>Stored in</span><b>blackjack.db, on this machine</b></div>' +
    '<div class="moves" style="margin-top:16px">' +
    '<button class="mv" onclick="logout()">Log out</button>' +
    '<button class="mv" onclick="wipe()">Delete this account</button></div>' +
    "</div></div>" +

    '<div class="panel"><div class="phead"><h2>THE LEDGER</h2><em>all time</em></div><div class="pbody">' +
    '<div class="big ' + cls(t.lifetime) + '">' + money(t.lifetime) + "</div>" +
    '<div class="sub">everything you are worth, minus everything you were handed</div>' +
    '<div class="kv" style="margin-top:14px"><span>Chips in the rack</span><b>' + money(t.chips) + "</b></div>" +
    '<div class="kv"><span>On the table right now</span><b>' + money(st.on_table) + "</b></div>" +
    '<div class="kv"><span>Given to you as starting chips</span><b>' + money(t.granted) + "</b></div>" +
    '<div class="kv"><span>Won answering questions</span><b class="up">' + money(t.earned) + "</b></div>" +
    '<div class="kv"><span>Sessions you ran dry in</span><b class="' +
    (t.busted_out ? "down" : "") + '">' + t.busted_out + " of " + t.sessions + "</b></div>" +
    '<div class="kv"><span>Best session</span><b class="' + cls(t.best_session) + '">' +
    (t.best_session == null ? "—" : money(t.best_session)) + "</b></div>" +
    '<div class="kv"><span>Worst session</span><b class="' + cls(t.worst_session) + '">' +
    (t.worst_session == null ? "—" : money(t.worst_session)) + "</b></div>" +
    '<button class="mv" style="width:100%;margin-top:14px" onclick="ANA=\'ledger\';go(\'analysis\')">' +
    "See every movement of money</button>" +
    "</div></div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>HOW YOU ARE DOING</h2>' +
    "<em>" + sk.band + "</em></div><div class=\"pbody\"><div class=\"grid2\">" +
    "<div>" +
    '<div class="two"><div><div class="big">' + pct(sk.accuracy) + '</div>' +
    '<div class="sub">plain accuracy</div></div>' +
    '<div><div class="big ' + (sk.sharpness >= 0.9 ? "up" : sk.sharpness < 0.6 ? "down" : "") + '">' +
    pct(sk.sharpness) + '</div><div class="sub">sharpness, weighted</div></div></div>' +
    '<p class="small" style="margin-top:12px">' + reflection(st) + "</p>" +
    "</div><div>" +
    '<h3 class="mini-h" style="margin-top:0">WHAT YOU KEEP MISSING</h3>' +
    (st.drill.filter((d) => d.missed).length
      ? st.drill.filter((d) => d.missed).slice(0, 8).map((d) =>
          '<div class="miss"><div>' + esc(d.cell) + " — should " +
          (d.should ? CODE_NAME[d.should].toLowerCase() : "?") + "</div><span>" + d.missed +
          " wrong of " + d.seen + "</span></div>").join("")
      : '<p class="idle">Nothing you have got wrong more than once yet.</p>') +
    '<div class="moves" style="margin-top:14px">' +
    '<button class="mv go" onclick="quizMissed()">Quiz me on what I miss</button>' +
    '<button class="mv" onclick="quizWeak()">Quiz my weak spots</button></div>' +
    "</div></div></div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>YOUR SESSIONS</h2></div>' +
    '<div class="pbody"><div class="cscroll">' + sessionTable(st.sessions) + "</div></div></div>" +
    "</div>";
  $("foot").innerHTML =
    "Logging out just returns you to the list of players on this machine — nothing is sent " +
    "anywhere and there is no password, because there is nothing here to protect from anyone who " +
    "already has your computer.";
}

function reflection(st) {
  const sk = st.skill, t = st.totals;
  const bits = [];
  if (!t.decisions) return "Nothing to reflect on yet. Play a few hands.";
  if (sk.confidence < 1) {
    bits.push("You are " + num(t.decisions) + " decisions in, so these numbers are still settling — " +
      "about " + sk.ramp + " is where sharpness starts meaning something.");
  }
  const gap = (sk.accuracy || 0) - (sk.sharpness || 0);
  if (gap > 0.1) {
    bits.push("Your plain accuracy is " + pct(sk.accuracy) + " but your sharpness is " + pct(sk.sharpness) +
      ". That gap is the easy hands carrying you: you are getting the obvious ones right and losing " +
      "the same few awkward ones over and over.");
  } else if (sk.sharpness >= 0.9) {
    bits.push("Sharpness and accuracy are close and both high, which is the sign that you actually know " +
      "the chart rather than just the common half of it.");
  }
  if (sk.coverage.unseen > sk.coverage.total * 0.4) {
    bits.push("You have never been tested on " + sk.coverage.unseen + " of the " + sk.coverage.total +
      " squares. An untested square is not a known one — the quiz is much faster than waiting " +
      "for them to be dealt.");
  }
  if (st.leaks.length) {
    bits.push("The pattern to fix first: " + st.leaks[0].text.split(".")[0].toLowerCase() + ".");
  }
  if (t.busted_out > 0) {
    bits.push("You have run out of money " + t.busted_out + " time" + (t.busted_out === 1 ? "" : "s") +
      ". That is usually bet sizing rather than card play — the bankroll calculator on the " +
      "Analysis tab will tell you what you actually needed.");
  }
  return bits.join(" ");
}

async function rename() {
  const r = await api("/api/accounts/rename", { account: ACCOUNT.id, name: $("rn").value });
  if (!r.ok) return toast("That name is taken, or empty.");
  ACCOUNT = r.account; S.account = r.account; STATS = null;
  toast("Name saved.");
  draw();
}

async function wipe() {
  const yes = await ask("Delete " + ACCOUNT.name + "?",
    "Every session, decision and chip goes with it. This cannot be undone.",
    "Delete for good", true);
  if (!yes) return;
  await api("/api/accounts/delete", { account: ACCOUNT.id });
  logout();
}

/* =======================================================================
   SETUP
   ======================================================================= */
function viewSetup() {
  const c = S.config;
  const locked = S.phase !== "idle";
  const opt = (v, cur, label) =>
    '<option value="' + v + '"' + (String(cur) === String(v) ? " selected" : "") + ">" + label + "</option>";
  const sel = (id, cur, items) =>
    '<select id="' + id + '"' + (locked ? " disabled" : "") + ">" +
    items.map(([v, l]) => opt(v, cur, l)).join("") + "</select>";

  $("wrap").innerHTML =
    '<div class="single"><div class="grid2">' +

    '<div class="panel"><div class="phead"><h2>THE ROOM</h2></div><div class="pbody">' +
    (locked ? '<div class="note bad">You are sitting at a table. Stand up before changing anything ' +
      "here — the rules cannot change halfway through a session.</div>" : "") +
    '<div class="field"><label>OTHER PEOPLE AT THE TABLE</label>' +
    sel("s_others", c.others, [0, 1, 2, 3, 4, 5].map((n) =>
      [n, n === 0 ? "Just you" : n + " other" + (n > 1 ? "s" : "")])) + "</div>" +
    '<div class="field"><label>SMALLEST BET ALLOWED</label>' +
    sel("s_min", c.table_min, [5, 10, 15, 25, 50, 100].map((n) => [n, "$" + n])) + "</div>" +
    '<div class="field"><label>BIGGEST BET ALLOWED</label>' +
    sel("s_max", c.table_max, [100, 200, 500, 1000, 5000].map((n) => [n, "$" + num(n)])) + "</div>" +
    '<div class="field"><label>DECKS IN THE SHOE</label>' +
    sel("s_decks", c.decks, [1, 2, 4, 6, 8].map((n) => [n, n + (n === 1 ? " deck" : " decks")])) + "</div>" +
    '<div class="field"><label>HOW DEEP THEY DEAL BEFORE RESHUFFLING</label>' +
    sel("s_pen", c.penetration, [[0.5, "Half the shoe — shallow"],
      [0.75, "Three quarters — typical"], [0.9, "Nearly all of it — deep"],
      [0.02, "Reshuffled every hand — a shuffling machine"]]) + "</div>" +
    "</div></div>" +

    '<div class="panel"><div class="phead"><h2>THE RULES</h2><em>these change the chart</em></div>' +
    '<div class="pbody">' +
    '<div class="field"><label>WHAT A BLACKJACK PAYS</label>' +
    sel("s_bj", c.blackjack_pays, [[1.5, "3 to 2 — what it should be"],
      [1.2, "6 to 5 — walk away from this table"]]) + "</div>" +
    '<div class="field"><label>THE DEALER ON A SOFT 17</label>' +
    sel("s_h17", c.hit_soft_17 ? 1 : 0, [[0, "Stands on all 17s — better for you"],
      [1, "Hits soft 17 — costs you about 0.2%"]]) + "</div>" +
    '<div class="field"><label>DOUBLING AFTER A SPLIT</label>' +
    sel("s_das", c.das ? 1 : 0, [[1, "Allowed"], [0, "Not allowed"]]) + "</div>" +
    '<div class="field"><label>SPLIT ACES</label>' +
    sel("s_ra", c.resplit_aces ? 1 : 0, [[0, "One card each, no re-splitting"],
      [1, "May be re-split"]]) + "</div>" +
    '<div class="field"><label>HOW MANY HANDS YOU MAY SPLIT TO</label>' +
    sel("s_mh", c.max_hands, [2, 3, 4].map((n) => [n, n + " hands"])) + "</div>" +
    '<button class="mv go" style="width:100%"' + (locked ? " disabled" : "") +
    ' onclick="saveSetup()">Apply</button>' +
    "</div></div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="phead"><h2>COUNTING</h2></div>' +
    '<div class="pbody">' +
    '<div class="field"><label>DECKS REMAINING</label>' +
    sel("s_sdl", c.show_decks_left ? 1 : 0, [
      [0, "Judge it from the discard tray — like a real table"],
      [1, "Tell me the number"]]) + "</div>" +
    '<div class="field"><label>TRUE COUNT</label>' +
    sel("s_stc", c.show_true_count ? 1 : 0, [
      [0, "I'll do the division myself"],
      [1, "Work it out for me"]]) + "</div>" +
    '<div class="field"><label>HAND TOTALS</label>' +
    sel("s_stot", c.show_totals ? 1 : 0, [
      [0, "Nobody's \u2014 read the cards yourself"],
      [1, "Print them while the round is live"]]) + "</div>" +
    '<div class="field"><label>COUNT CHECKS</label>' +
    sel("s_rc", c.random_checks ? 1 : 0, [
      [1, "Interrupt me now and then"],
      [0, "Only when I ask"]]) + "</div>" +
    '<div class="field"><label>HOW OFTEN</label>' +
    sel("s_cr", c.check_rate, [[0.06, "Rarely — about one round in sixteen"],
      [0.12, "Now and then — about one in eight"],
      [0.25, "Often — about one in four"]]) + "</div>" +
    '<div class="field"><label>BET SPREAD</label>' +
    sel("s_spread", c.spread, [[4, "1 to 4 — quiet"], [8, "1 to 8 — standard"],
      [12, "1 to 12 — aggressive"], [20, "1 to 20 — you will be asked to leave"]]) + "</div>" +
    '<button class="mv go" style="width:100%"' + (locked ? " disabled" : "") +
    ' onclick="saveSetup()">Apply</button>' +
    '<div class="note" style="margin-top:14px"><b>Every default here is the hard one on purpose.</b> ' +
    "A real table tells you none of it: not how deep the shoe is, not the true count, and not what " +
    "anybody is holding. You judge the discard tray by eye, divide in your head, and read the cards " +
    "off the felt. Handed those numbers, you remove the three things most likely to go wrong \u2014 " +
    "and the practice stops resembling the thing you are practising for.</div>" +
    '<p class="fine">Totals come back the moment the round settles, where they are feedback rather ' +
    "than help. Busts always show: they are called out loud at a real table and you can see the cards " +
    "anyway. The Quiz tab still prints the total, because a flashcard that makes you add up first is " +
    "drilling arithmetic rather than the chart.</p>" +
    "</div></div>" +

    '<div class="panel" style="margin-top:16px"><div class="pbody">' +
    '<div class="note"><b>What the number of players actually changes.</b> ' +
    "Not your correct play. Other people’s cards never affect which move is right for your hand " +
    "— if anyone tells you a bad player at third base cost them the hand, they are wrong. What it " +
    "does change is how quickly the shoe gets used up, and therefore how far the mix of remaining cards " +
    'drifts from normal. That drift is the whole basis of <span class="gt" data-term="true count">counting</span>. ' +
    "Set the reshuffling option to a shuffling machine and it stops mattering entirely, which is exactly " +
    "why casinos bought them.</div>" +
    '<div class="note bad" style="margin-top:12px"><b>6 to 5 is the one that matters.</b> It sounds ' +
    "like a small change and it adds about 1.4% to the house edge — roughly tripling it. No amount " +
    "of correct play makes that back. Set it here and run the simulator on the Analysis tab if you want " +
    "to watch what it does.</div>" +
    '<p class="fine">The chart on the <b>Chart</b> tab redraws itself for whatever you choose here, ' +
    "and your decisions are graded against that chart, so the two can never disagree.</p>" +
    "</div></div></div>";
  $("foot").innerHTML = "";
}

async function saveSetup() {
  await send("/api/config", {
    others: +$("s_others").value, table_min: +$("s_min").value, table_max: +$("s_max").value,
    decks: +$("s_decks").value, penetration: +$("s_pen").value,
    blackjack_pays: +$("s_bj").value, hit_soft_17: !!+$("s_h17").value,
    das: !!+$("s_das").value, resplit_aces: !!+$("s_ra").value, max_hands: +$("s_mh").value,
    show_decks_left: !!+$("s_sdl").value, show_true_count: !!+$("s_stc").value,
    show_totals: !!+$("s_stot").value,
    random_checks: !!+$("s_rc").value, check_rate: +$("s_cr").value,
    spread: +$("s_spread").value,
  });
  CHART = null;
  PENDING_BET = S.config.table_min;
  TAB = "table"; draw();
}

/* ---------------- keyboard ---------------- */
document.addEventListener("keydown", (e) => {
  if (!S || e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  // a question is on screen; space would otherwise deal a hand behind it
  if (document.querySelector(".modal")) return;
  const k = e.key.toLowerCase();

  if (TAB === "quiz" && QUIZ) {
    if (!QUIZ.last && $("qn")) return;      // a typed answer is waiting; leave the keys alone
    if (QUIZ.last) {
      if (e.code === "Space" || e.key === "Enter") {
        e.preventDefault();
        QUIZ.done ? showQuizSummary() : nextQuiz();
      }
      return;
    }
    const m = { h: "H", s: "S", d: "D", p: "P" }[k];
    if (m && (QUIZ.legal || []).indexOf(m) >= 0) answerQuiz(m);
    return;
  }

  if (TAB !== "table") return;
  if (S.phase === "play") {
    if (k === "h" && S.can_hit) doMove("H");
    if (k === "s") doMove("S");
    if (k === "d" && S.can_double) doMove("D");
    if (k === "p" && S.can_split) doMove("P");
  } else if (e.code === "Space") {
    e.preventDefault();
    if (S.phase === "bet" && !S.broke) doBet();
    else if (S.phase === "settled") doNext();
    else if (S.phase === "idle") sitDown();
  }
});

boot();
