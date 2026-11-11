/* Graphique d'equity en base 100 (uPlot). Les données sont lues dans <script id="equity-data">.
   Un point par cycle réel : les graduations de l'axe des temps tombent sur les cycles, jamais entre deux. */
(function () {
  "use strict";
  var node = document.getElementById("equity-data");
  var host = document.getElementById("chart");
  if (!node || !host || typeof uPlot === "undefined") return;
  var data = JSON.parse(node.textContent);
  var plot = null;
  var MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  var DASHES = [[7, 4], [2, 3], [10, 3, 2, 3], [1, 4]];
  var LAST = data.x.length - 1;

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function fr(v, d) { return v.toFixed(d).replace(".", ",").replace("-", "−"); }
  function jour(d) { return d.getUTCDate() + " " + MOIS[d.getUTCMonth()]; }
  function heure(d) { return d.getUTCHours() + " h"; }
  function dateLongue(ts) {
    var d = new Date(ts * 1000);
    return jour(d) + ", " + heure(d) + " UTC";
  }

  /* Graduations : uniquement aux instants des cycles, espacées d'au moins `minPx` pixels. */
  function splits(u) {
    var xs = data.x, n = xs.length;
    if (n < 2) return xs.slice();
    var width = u.bbox.width / (window.devicePixelRatio || 1);
    var minPx = width < 420 ? 64 : 80;
    var perStep = width / (n - 1);
    var every = Math.max(1, Math.ceil(minPx / perStep));
    var out = [];
    for (var i = LAST; i >= 0; i -= every) out.unshift(xs[i]);
    return out;
  }

  function build() {
    if (plot) { plot.destroy(); plot = null; }
    var width = host.clientWidth || 600;
    var compact = width < 520;
    var llm = 0, tem = 0;
    var many = data.x.length > 60;
    var series = [{
      label: "Cycle",
      value: function (u, v) { return v == null ? "—" : dateLongue(v); }
    }];
    var columns = [data.x];
    data.series.forEach(function (s) {
      var isLlm = s.kind === "llm";
      var focused = data.focus && s.id === data.focus;
      var o = {
        label: s.name,
        spanGaps: true,
        value: function (u, v) { return v == null ? "—" : fr(v, 2); }
      };
      if (isLlm) {
        o.stroke = css("--llm" + (llm++ % 3));
        o.width = 2.5;
      } else {
        o.stroke = css("--tem" + (tem % 4));
        o.dash = DASHES[tem % DASHES.length];
        o.width = 1.75;
        tem++;
      }
      if (focused) {
        o.width = 3;
        o.dash = undefined;
        if (!isLlm) o.stroke = css("--text");
      }
      o.points = { show: !many, size: focused || isLlm ? 7 : 5, width: 1.5, fill: css("--surface") };
      if (data.focus && !focused && s.id !== "temoin:panier") o.show = false;
      series.push(o);
      columns.push(s.values);
    });
    var axisStroke = css("--muted");
    var grid = { stroke: css("--grid"), width: 1 };
    var font = "12px " + css("--sans");
    var opts = {
      width: width,
      height: compact ? 240 : 340,
      series: series,
      cursor: { drag: { x: false, y: false }, points: { size: 9 } },
      scales: {
        x: { time: false },
        y: { range: function (u, min, max) {
          var lo = Math.min(min, 100), hi = Math.max(max, 100);
          var pad = Math.max((hi - lo) * 0.12, 0.25);
          return [lo - pad, hi + pad];
        } }
      },
      axes: [
        { stroke: axisStroke, grid: grid, ticks: { stroke: css("--grid") }, font: font, gap: 6, size: 48,
          splits: splits,
          values: function (u, vals) {
            var prevDay = null;
            return vals.map(function (v) {
              var d = new Date(v * 1000);
              var day = jour(d);
              var label = day === prevDay ? heure(d) : heure(d) + "\n" + day;
              prevDay = day;
              return label;
            });
          } },
        { stroke: axisStroke, grid: grid, ticks: { show: false }, size: 52, font: font,
          values: function (u, vals) { return vals.map(function (v) { return fr(v, 1); }); } }
      ],
      legend: { live: true },
      hooks: {
        draw: [function (u) {
          // Ligne de référence à 100 (capital de départ).
          var y = Math.round(u.valToPos(100, "y", true)) + 0.5;
          var ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = css("--muted");
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 4]);
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(u.bbox.left + u.bbox.width, y);
          ctx.stroke();
          ctx.restore();
        }],
        // Hors survol, la légende montre le dernier cycle au lieu de « -- ».
        setCursor: [function (u) { if (u.cursor.idx == null) u.setLegend({ idx: LAST }); }]
      }
    };
    plot = new uPlot(opts, columns, host);
    plot.setLegend({ idx: LAST });
  }

  build();
  var timer = null;
  window.addEventListener("resize", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var w = host.clientWidth;
      if (plot && w) plot.setSize({ width: w, height: w < 520 ? 240 : 340 });
    }, 120);
  });
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", build);
  }
})();
