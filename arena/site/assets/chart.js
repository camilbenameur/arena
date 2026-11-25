/* Cumulative return chart (uPlot). The data, in base 100, is read from <script id="equity-data">.
   - one point per cycle, plus the previous day's snapshots (every 30 min and the last one): real-time axis,
     ticks on round UTC hours (4 h, 12 h, 1 day...) chosen according to the width;
   - vertical axis as the gap from the start ("-0.5%"), like the table;
   - HTML legend with buttons (keyboard, touch, screen readers) that shows the values of the latest cycle
     or of the hovered cycle, in place of the uPlot legend. */
(function () {
  "use strict";
  var node = document.getElementById("equity-data");
  var host = document.getElementById("chart");
  var legendEl = document.getElementById("legend");
  if (!node || !host || typeof uPlot === "undefined") return;
  var data;
  try { data = JSON.parse(node.textContent); } catch (err) { return; }
  var plot = null;
  var currentCompact = null;
  var hidden = {};
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var LAST = data.x.length - 1;

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function num(v, d) { return v.toFixed(d); }
  function delta(v, d) {
    if (v == null) return "—";
    var x = v - 100;
    var r = Number(num(Math.abs(x), d));
    var s = r === 0 ? "" : (x > 0 ? "+" : "−");
    return s + num(Math.abs(x), d) + "%";
  }
  function dayLabel(d) { return MONTHS[d.getUTCMonth()] + " " + d.getUTCDate(); }
  function hourLabel(d) { return pad(d.getUTCHours()) + ":00"; }
  var KINDS = data.kinds || [];
  var PAUSES = data.pauses || []; /* [[from, to], ...]: league paused for absence (site/pauses.py) */
  function paused(t) {
    for (var k = 0; k < PAUSES.length; k++) if (t >= PAUSES[k][0] && t <= PAUSES[k][1]) return true;
    return false;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function hm(d) { var m = d.getUTCMinutes(); return pad(d.getUTCHours()) + ":" + (m < 10 ? "0" : "") + m; }
  function whenLabel(i) {
    var w = whenText(i);
    return paused(data.x[i]) && KINDS[i] !== "direct" ? w + " · league paused" : w;
  }
  function whenText(i) {
    if (i === 0 && KINDS[0] === "inception") return "Start";
    var d = new Date(data.x[i] * 1000);
    if (KINDS[i] === "direct") return "Live, Kraken price at " + hm(d) + ":" + pad(d.getUTCSeconds()) + " UTC";
    if (KINDS[i] === "watch") return (i === LAST ? (data.last || "Live") + ": " : "Snapshot of ") + dayLabel(d) + ", " + hm(d) + " UTC";
    return (i === LAST ? "Latest cycle: " : "Cycle of ") + dayLabel(d) + ", " + hourLabel(d) + " UTC";
  }

  /* Series styles: computed server-side (render._styles), a single source shared with the HTML legend. */
  function styles() {
    return data.styles.map(function (st, i) {
      return {
        stroke: css(st.color), width: st.width, dash: st.dash, visible: st.visible,
        isLlm: data.series[i].kind === "llm" || data.series[i].kind === "council", focused: st.width >= 3 && !st.halo, archive: !!st.archive, halo: !!st.halo
      };
    });
  }

  /* Ticks on round UTC hours: the smallest step (4 h, 8 h, 12 h, 1 d, 2 d, 7 d) that leaves enough room. */
  var STEPS = [14400, 28800, 43200, 86400, 172800, 604800];
  function splits(u) {
    var xs = data.x, n = xs.length;
    if (n < 2) return xs.slice();
    var lo = xs[0], hi = xs[LAST], span = Math.max(1, hi - lo);
    var width = u.bbox.width / uPlot.pxRatio;
    var minPx = width < 420 ? 70 : 90;
    var step = STEPS[STEPS.length - 1];
    for (var k = 0; k < STEPS.length; k++) {
      if (width * STEPS[k] / span >= minPx) { step = STEPS[k]; break; }
    }
    var out = [];
    for (var t = Math.ceil(lo / step) * step; t <= hi; t += step) out.push(t);
    // The start keeps its tick: added if there is room, otherwise it replaces the first one (season start).
    if (!out.length || (out[0] - lo) * width / span >= minPx * 0.8) out.unshift(lo);
    else if (KINDS[0] === "inception") out[0] = lo;
    return out;
  }

  /* The legend is already in the HTML (values of the latest cycle): we enable its buttons. */
  var valueNodes = [];
  var whenNode = document.getElementById("legend-when");
  function wireLegend() {
    if (!legendEl) return;
    valueNodes = data.series.map(function () { return null; });
    Array.prototype.forEach.call(legendEl.querySelectorAll("button[data-series]"), function (b) {
      var i = Number(b.getAttribute("data-series"));
      var id = data.series[i].id;
      valueNodes[i] = b.querySelector(".legend-val");
      b.disabled = false;
      b.addEventListener("click", function () {
        var off = b.getAttribute("aria-pressed") === "true";
        b.setAttribute("aria-pressed", off ? "false" : "true");
        hidden[id] = off;
        if (plot) plot.setSeries(i + 1, { show: !off });
      });
    });
  }

  function showValues(idx) {
    if (idx == null) idx = LAST;
    if (whenNode) whenNode.textContent = whenLabel(idx);
    data.series.forEach(function (s, i) {
      var v = valueNodes[i];
      if (!v) return;
      var x = s.values[idx];
      if (x == null && s.archive_ts) { var k = s.values.length - 1; while (k >= 0 && s.values[k] == null) k--; x = k >= 0 ? s.values[k] : null; }
      v.textContent = delta(x, 2);
      v.classList.toggle("gain", x != null && x >= 100.005);
      v.classList.toggle("loss", x != null && x <= 99.995);
    });
  }

  /* Labels at the end of each curve (value and short name), instead of a legend to decode.
     Curves that end at the same value share a label; the others are spread out vertically. */
  function endLabels(u) {
    var r = uPlot.pxRatio, ctx = u.ctx, gap = 16 * r;
    var groups = [];
    data.series.forEach(function (s, i) {
      if (!u.series[i + 1].show || s.archive_ts) return; /* an archived council has no "end" left to label */
      var j = s.values.length - 1;
      while (j >= 0 && s.values[j] == null) j--;
      if (j < 0) return;
      var txt = delta(s.values[j], 2);
      var y = u.valToPos(s.values[j], "y", true);
      var g = null;
      for (var k = 0; k < groups.length; k++) {
        if (groups[k].txt === txt && Math.abs(groups[k].y - y) < 2 * r) { g = groups[k]; break; }
      }
      var llm = s.kind === "llm" || s.kind === "council";
      var c = llm ? css(data.styles[i].color) : css("--muted");
      if (g) { g.names.push(data.short[i]); g.colors.push(c); g.llm = g.llm || llm; g.color = css("--text"); }
      else groups.push({ txt: txt, y: y, names: [data.short[i]], colors: [c], llm: llm, color: c });
    });
    groups.sort(function (a, b) { return a.y - b.y; });
    for (var k = 1; k < groups.length; k++) {
      if (groups[k].y - groups[k - 1].y < gap) groups[k].y = groups[k - 1].y + gap;
    }
    var x = u.bbox.left + u.bbox.width + 10 * r;
    var compact = u.bbox.width / r < 360;
    ctx.save();
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    groups.forEach(function (g) {
      ctx.fillStyle = g.color;
      ctx.font = (g.llm ? "600 " : "400 ") + Math.round(12 * r) + "px " + css("--mono");
      ctx.fillText(g.txt, x, g.y);
      var w = ctx.measureText(g.txt + " ").width;
      ctx.font = (g.llm ? "600 " : "400 ") + Math.round(12 * r) + "px " + css("--sans");
      var trim = function (n) { return n.replace(/ \d+(\.\d+)?$/, ""); };
      var names = g.names.length > 1 || compact ? g.names.map(trim) : g.names;
      var colors = g.colors;
      if (compact && names.length > 1) { names = [names.length + (g.llm ? " AI" : " curves")]; colors = [g.color]; }
      // Whatever does not fit in the right margin becomes "+N" (the full names stay in the legend).
      var room = ctx.canvas.width - x - w - 4 * r;
      var widthOf = function (names, rest) {
        return ctx.measureText(names.join(", ") + (rest ? ", +" + rest : "")).width;
      };
      var keep = names.length;
      while (keep > 1 && widthOf(names.slice(0, keep), names.length - keep) > room) keep--;
      if (keep < names.length) {
        var rest = names.length - keep;
        names = names.slice(0, keep).concat(["+" + rest]);
        colors = colors.slice(0, keep).concat([css("--muted")]);
      }
      var cx = x + w;
      names.forEach(function (n, k) {
        var piece = n + (k < names.length - 1 ? ", " : "");
        ctx.fillStyle = colors[k];
        ctx.fillText(piece, cx, g.y);
        cx += ctx.measureText(piece).width;
      });
    });
    ctx.restore();
  }

  function build() {
    if (plot) { plot.destroy(); plot = null; }
    var width = host.clientWidth || 600;
    var compact = width < 520;
    currentCompact = compact;
    var sts = styles();
    var many = data.x.length > 60;
    var series = [{ label: "Cycle" }];
    var columns = [data.x];
    data.series.forEach(function (s, i) {
      var st = sts[i];
      series.push({
        label: s.name,
        spanGaps: true,
        stroke: st.stroke,
        width: st.width,
        dash: st.dash || undefined,
        cap: st.archive ? "round" : undefined,
        show: st.visible && !hidden[s.id],
        points: { show: !many && !st.archive && !st.halo, size: st.focused || st.isLlm ? 7 : 5, width: 1.5, stroke: st.stroke, fill: css("--surface") }
      });
      columns.push(s.values);
    });
    var axisStroke = css("--muted");
    var grid = { stroke: css("--grid"), width: 1 };
    var font = "12px " + css("--sans");
    var opts = {
      width: width,
      height: compact ? 280 : (host.closest(".front-curve") ? 380 : 320),
      series: series,
      legend: { show: false },
      padding: [12, compact ? 112 : 190, 0, 0],
      cursor: { drag: { x: false, y: false }, points: { size: 9 } },
      scales: {
        x: { time: false },
        y: { range: function (u, min, max) {
          // Bounds hugging the data, 0% always visible, minimum span of 0.4 points.
          if (min == null || max == null) return [99.6, 100.4];
          var lo = Math.min(min, 100), hi = Math.max(max, 100);
          if (hi - lo < 0.4) { var mid = (hi + lo) / 2; lo = Math.min(lo, mid - 0.2); hi = Math.max(hi, mid + 0.2); }
          var pad = (hi - lo) * 0.1;
          return [lo - pad, hi + pad];
        } }
      },
      axes: [
        { stroke: axisStroke, grid: grid, ticks: { stroke: css("--grid"), size: 4 }, font: font, gap: 6, size: 46,
          splits: splits,
          values: function (u, vals) {
            var prevDay = null;
            return vals.map(function (v) {
              if (v === data.x[0] && KINDS[0] === "inception") { return "start"; }
              var d = new Date(v * 1000);
              var day = dayLabel(d);
              var label = day === prevDay ? hourLabel(d) : hourLabel(d) + "\n" + day;
              prevDay = day;
              return label;
            });
          } },
        { stroke: axisStroke, grid: grid, ticks: { show: false }, size: 58, font: font,
          values: function (u, vals) { return vals.map(function (v) { return delta(v, 1); }); } }
      ],
      hooks: {
        drawAxes: [function (u) {
          // Pause bands (absence), then the start line (0%), all under the curves.
          var r = uPlot.pxRatio;
          if (PAUSES.length) {
            var c = u.ctx, top = u.bbox.top, h = u.bbox.height;
            c.save();
            c.beginPath();
            c.rect(u.bbox.left, top, u.bbox.width, h);
            c.clip();
            PAUSES.forEach(function (p) {
              var x0 = u.valToPos(p[0], "x", true), x1 = u.valToPos(p[1], "x", true);
              if (x1 - x0 < 1) return;
              c.fillStyle = css("--sunken");
              c.fillRect(x0, top, x1 - x0, h);
              if (x1 - x0 > 56 * r) {
                c.fillStyle = css("--muted");
                c.font = Math.round(11 * r) + "px " + css("--sans");
                c.textBaseline = "top";
                c.textAlign = "left";
                c.fillText("paused", x0 + 6 * r, top + 6 * r);
              }
            });
            c.restore();
          }
          var y = Math.round(u.valToPos(100, "y", true)) + 0.5;
          var ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = css("--muted");
          ctx.lineWidth = 1 * r;
          ctx.setLineDash([4 * r, 4 * r]);
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(u.bbox.left + u.bbox.width, y);
          ctx.stroke();
          ctx.restore();
        }],
        draw: [endLabels],
        setCursor: [function (u) { showValues(u.cursor.idx); }]
      }
    };
    plot = new uPlot(opts, columns, host);
    showValues(LAST);
  }

  /* Live point (direct.js): a last point at the current Kraken price, removed when the feed goes quiet.
     A series without an estimate keeps its last published value. */
  var live = false;
  function currentColumns() { return [data.x].concat(data.series.map(function (s) { return s.values; })); }
  document.addEventListener("arena:direct", function (ev) {
    var d = ev.detail, before = live ? data.x[LAST] + "|" + data.series.map(function (s) { return s.values[LAST]; }).join(",") : "";
    if (live) { data.x.pop(); KINDS.pop(); data.series.forEach(function (s) { s.values.pop(); }); live = false; }
    if (d && d.v && d.t > data.x[data.x.length - 1]) {
      data.x.push(d.t); KINDS.push("direct");
      data.series.forEach(function (s) {
        var v = s.slug ? d.v[s.slug] : undefined, j = s.values.length - 1;
        while (j >= 0 && s.values[j] == null) j--;
        if (s.archive_ts) { s.values.push(null); return; } /* frozen at its withdrawal: never a live point */
        s.values.push(typeof v === "number" && isFinite(v) ? v : (j >= 0 ? s.values[j] : null));
      });
      live = true;
    }
    LAST = data.x.length - 1;
    var after = live ? data.x[LAST] + "|" + data.series.map(function (s) { return s.values[LAST]; }).join(",") : "";
    if (after === before || !plot) return;
    var hover = plot.cursor.idx;
    plot.setData(currentColumns());
    if (hover == null) showValues(LAST);
  });

  wireLegend();
  build();
  var timer = null;
  function onResize() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var w = host.clientWidth;
      if (!plot || !w) return;
      if ((w < 520) !== currentCompact) build();
      else plot.setSize({ width: w, height: w < 520 ? 280 : (host.closest(".front-curve") ? 380 : 320) });
    }, 120);
  }
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(onResize).observe(host.parentNode);
  else window.addEventListener("resize", onResize);
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", build);
  }
})();
