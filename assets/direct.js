/* Live prices of the derivatives league: an estimate in the browser, from Kraken Futures' public feed.
   The published page keeps the official figures of the journal (sampled every 5 min). This script only
   revalues the published positions at the current mark; if the feed goes quiet, the published figures come back. */
(function () {
  "use strict";
  var src = document.getElementById("direct-data");
  if (!src || typeof WebSocket === "undefined") return;
  var D;
  try { D = JSON.parse(src.textContent); } catch (err) { return; }
  if (!D || !D.flow || !D.products || !D.products.length) return;

  var MINUS = "−";
  var FRESH_S = 15;        // a price older than 15 s is no longer "live"
  var MAX_GAP = 0.25;      // a mark more than 25% away from the published price is ignored
  var marks = {};          // product -> {m: µUSD, t: seconds (reader's clock), k: ms (Kraken's clock)}
  var SILENT_S = 30;       // a connection with no message for 30 s is reopened
  var ws = null, attempts = 0, dirty = false, seen = 0;

  var statusEl = document.querySelector("[data-direct-status]");
  var wordEl = document.querySelector("[data-direct-word]");
  var originalWord = wordEl ? wordEl.textContent : "";
  var cells = Array.prototype.slice.call(document.querySelectorAll("[data-direct]"));
  cells.forEach(function (c) { c.setAttribute("data-official", c.textContent); c.setAttribute("data-tone", c.className); });

  function groupDigits(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function eur(u, signed) {
    var c = Math.round(Math.abs(u) / 10000), w = Math.floor(c / 100), f = c % 100;
    var s = u < 0 && c > 0 ? MINUS : (signed && c > 0 ? "+" : "");
    return s + "€" + groupDigits(w) + "." + (f < 10 ? "0" : "") + f;
  }
  function pct(x) {
    var v = Math.round(x * 10000) / 100, s = v < 0 ? MINUS : (v > 0 ? "+" : "");
    return s + Math.abs(v).toFixed(2) + "%";
  }
  function usdPrice(u) {
    var d = Math.abs(u) >= 100000000 ? 2 : 4, v = (Math.abs(u) / 1e6).toFixed(d).split(".");
    return "$" + groupDigits(v[0]) + "." + v[1];
  }
  function tone(v) { return v > 0 ? "gain" : (v < 0 ? "loss" : ""); }
  function hms(ms) {
    var d = new Date(ms), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + " UTC";
  }

  function fresh(p) {
    var x = marks[p];
    return x && Date.now() / 1000 - x.t <= FRESH_S ? x : null;
  }

  // Estimated value of a portfolio: published value, minus the published unrealized P&L, plus the unrealized P&L at the current mark.
  function estimate(pf) {
    var eq = pf.eq, live = false, pos = {};
    pf.pos.forEach(function (x) {
      var f = fresh(x.p);
      if (!f) return;
      var usd = (x.q > 0 ? 1 : -1) * (f.m - x.e) * Math.abs(x.q) / 1e8;
      var lat = usd >= 0 ? usd * 1e6 / pf.fx[1] : usd * 1e6 / pf.fx[0];
      eq += lat - x.l;
      pos[x.p] = {m: f.m, l: lat};
      live = true;
    });
    return live ? {eq: eq, pos: pos} : null;
  }

  function setCell(c, txt, cls) {
    if (c.textContent !== txt) c.textContent = txt;
    var base = (c.getAttribute("data-tone") || "").replace(/\b(gain|loss)\b/g, "").trim();
    var nextClass = (base + " " + (cls || "") + " est").trim();
    if (c.className !== nextClass) c.className = nextClass;
    c.title = "Live estimate";
  }
  function restore(c) {
    c.textContent = c.getAttribute("data-official");
    c.className = c.getAttribute("data-tone");
    c.removeAttribute("title");
  }

  function render() {
    dirty = false;
    var latest = 0, active = false, ests = {};
    Object.keys(D.pf).forEach(function (slug) { ests[slug] = estimate(D.pf[slug]); });
    cells.forEach(function (c) {
      var est = ests[c.getAttribute("data-pf")], k = c.getAttribute("data-direct"), pf = D.pf[c.getAttribute("data-pf")];
      if (!est) { restore(c); return; }
      if (k === "val") setCell(c, eur(est.eq, false), "");
      else if (k === "ret") setCell(c, pct(est.eq / pf.c - 1), tone(est.eq - pf.c));
      else {
        var x = est.pos[c.getAttribute("data-p")];
        if (!x) { restore(c); return; }
        if (k === "mark") setCell(c, usdPrice(x.m), "");
        else if (k === "lat") setCell(c, eur(x.l, true), tone(Math.round(x.l / 10000)));
      }
      active = true;
    });
    D.products.forEach(function (p) { var f = fresh(p); if (f && f.k > latest) latest = f.k; });
    if (statusEl) {
      if (active && latest) {
        statusEl.textContent = "Live estimate, Kraken price at " + hms(latest) + (statusEl.hasAttribute("data-short") ? "" : " · official at the snapshot of " + D.statement);
        statusEl.hidden = false;
      } else {
        statusEl.hidden = true;
      }
    }
    if (wordEl) wordEl.textContent = active && latest ? "Official figures as of" : originalWord;
    // The curve (chart.js) adds a last live point: return in base 100 at capital, per series.
    var vals = {}, n = 0;
    Object.keys(ests).forEach(function (slug) {
      if (ests[slug]) { vals[slug] = Math.round(ests[slug].eq / D.pf[slug].c * 1e6) / 1e4; n++; }
    });
    try {
      document.dispatchEvent(new CustomEvent("arena:direct", {detail: n && latest ? {t: Math.floor(latest / 1000), v: vals} : null}));
    } catch (err) { /* browser without CustomEvent: the curve keeps the last snapshot */ }
  }

  function onMessage(m) {
    var d;
    try { d = JSON.parse(m.data); } catch (err) { return; }
    if (!d || d.feed !== "ticker" || D.products.indexOf(d.product_id) < 0) return;
    var px = Number(d.markPrice);
    if (!isFinite(px) || px <= 0) return;
    var u = Math.round(px * 1e6), ref = D.ref[d.product_id];
    if (ref && Math.abs(u / ref - 1) > MAX_GAP) return;
    attempts = 0;
    marks[d.product_id] = {m: u, t: Date.now() / 1000, k: Number(d.time) || Date.now()};
    dirty = true;
  }

  function connect() {
    if (ws || document.hidden) return;
    try { ws = new WebSocket(D.flow); } catch (err) { ws = null; return; } // CSP or network: we keep the published page
    seen = Date.now() / 1000;
    ws.onopen = function () {
      this.send(JSON.stringify({event: "subscribe", feed: "ticker", product_ids: D.products}));
    };
    ws.onmessage = function (m) { seen = Date.now() / 1000; onMessage(m); };
    ws.onclose = function () {
      ws = null;
      if (!document.hidden) reconnect();
    };
    ws.onerror = function () { /* onclose follows */ };
  }
  function disconnect() {
    if (!ws) return;
    var w = ws;
    ws = null;
    w.onclose = null;
    try { w.close(); } catch (err) { /* already closed */ }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) disconnect(); else connect();
  });
  function reconnect() {
    disconnect();
    attempts += 1;
    setTimeout(connect, Math.min(60, Math.pow(2, attempts)) * 1000);
  }
  setInterval(function () {
    if (ws && Date.now() / 1000 - seen > SILENT_S) reconnect();
    // Also without a new message: a price that ages beyond 15 s must give the published figures back.
    if (dirty || Object.keys(marks).length) render();
  }, 1000);
  connect();
})();
