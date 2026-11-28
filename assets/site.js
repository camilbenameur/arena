/* Dashboard freshness: the page is static, this script compares the next cycle's time with the reader's clock.
   Without JavaScript, the absolute date stays displayed. */
(function () {
  "use strict";
  var t = document.querySelector("[data-next]");
  var detail = document.querySelector("[data-freshness]");
  if (!t || !detail) return;
  var next = Number(t.getAttribute("data-next"));
  var interval = Number(t.getAttribute("data-interval")) || 14400;
  var original = detail.textContent;

  function duration(s) {
    if (s < 60) return "less than a minute";
    var m = Math.round(s / 60);
    if (m < 60) return m + " min";
    var h = Math.floor(m / 60), r = m % 60;
    return h + " h" + (r ? " " + (r < 10 ? "0" : "") + r : "");
  }

  // The reader's local time next to the UTC time (the page is generated in UTC).
  var local = "";
  try {
    var d = new Date(next * 1000);
    var mm = d.getMinutes();
    local = (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (mm < 10 ? "0" : "") + mm + " local time";
  } catch (err) { /* the UTC time is enough */ }

  // The text replaces a placeholder that is already reserved (one line): no layout shift.
  function update() {
    var now = Date.now() / 1000;
    var gap = next - now;
    var parts = [];
    detail.classList.remove("warn-txt", "loss-txt");
    if (gap > 0) {
      parts.push("in " + duration(gap));
    } else if (-gap < 3600) {
      // The timer fires at HH:05 and the page is rebuilt at the end of the cycle.
      parts.push("running or imminent");
    } else {
      var missed = Math.floor(-gap / interval) + 1;
      parts.push("late by " + duration(-gap) + ": " + missed + " cycle" + (missed > 1 ? "s" : "") +
        " without an update of this page");
      detail.classList.add(-gap > interval ? "loss-txt" : "warn-txt");
    }
    if (local) parts.push(local);
    if (original) parts.push(original);
    detail.textContent = parts.join(" · ");
  }

  update();
  setInterval(update, 60000);
})();

/* An anchor to a collapsed passage (e.g. "Its rules" -> #m-councils) opens the fold that contains it. */
(function () {
  "use strict";
  function open() {
    var id = decodeURIComponent(location.hash.slice(1));
    var target = id && document.getElementById(id);
    if (!target) return;
    for (var n = target.parentElement; n; n = n.parentElement) {
      if (n.tagName === "DETAILS") n.open = true;
    }
    target.scrollIntoView();
  }
  window.addEventListener("hashchange", open);
  if (location.hash) open();
})();
