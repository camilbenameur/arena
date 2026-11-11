/* Graphique d'equity en base 100 (uPlot). Les données sont lues dans <script id="equity-data">. */
(function () {
  "use strict";
  var node = document.getElementById("equity-data");
  var host = document.getElementById("chart");
  if (!node || !host || typeof uPlot === "undefined") return;
  var data = JSON.parse(node.textContent);
  var plot = null;
  var MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  var DASHES = [[7, 4], [2, 3], [10, 3, 2, 3], [1, 4]];

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function build() {
    if (plot) { plot.destroy(); plot = null; }
    var width = host.clientWidth || 600;
    var compact = width < 520;
    var llm = 0, tem = 0;
    var series = [{ label: "Date (UTC)" }];
    var columns = [data.x];
    data.series.forEach(function (s) {
      var isLlm = s.kind === "llm";
      var o = { label: s.name, spanGaps: true, points: { show: false } };
      if (isLlm) {
        o.stroke = css("--llm" + (llm++ % 3));
        o.width = 2.5;
      } else {
        o.stroke = css("--tem" + (tem % 4));
        o.dash = DASHES[tem % DASHES.length];
        o.width = 1.5;
        tem++;
      }
      if (data.focus && s.id !== data.focus && !(data.focus && s.id === "temoin:panier")) {
        o.show = false;
      }
      if (data.focus && s.id === data.focus) { o.width = 3; o.stroke = css("--focus"); o.dash = undefined; }
      series.push(o);
      columns.push(s.values);
    });
    var axisStroke = css("--muted");
    var grid = { stroke: css("--border"), width: 1 };
    var opts = {
      width: width,
      height: compact ? 260 : 360,
      series: series,
      cursor: { drag: { x: false, y: false } },
      scales: {
        x: { time: true },
        y: { range: function (u, min, max) {
          var lo = Math.min(min, 100), hi = Math.max(max, 100);
          var pad = Math.max((hi - lo) * 0.08, 0.5);
          return [lo - pad, hi + pad];
        } }
      },
      tzDate: function (ts) { return uPlot.tzDate(new Date(ts * 1000), "UTC"); },
      axes: [
        { stroke: axisStroke, grid: grid, ticks: { stroke: css("--border") }, font: "12px system-ui, sans-serif",
          values: function (u, vals, space) {
            var short = (vals[vals.length - 1] - vals[0]) < 3 * 86400;
            return vals.map(function (v) {
              var d = new Date(v * 1000);
              var h = d.getUTCHours();
              if (h !== 0 && !short) return h + " h";
              var t = d.getUTCDate() + " " + MOIS[d.getUTCMonth()];
              if (short && h !== 0) t = h + " h";
              return t;
            });
          } },
        { stroke: axisStroke, grid: grid, ticks: { stroke: css("--border") }, size: 48, font: "12px system-ui, sans-serif",
          values: function (u, vals) { return vals.map(function (v) { return v.toFixed(1).replace(".", ","); }); } }
      ],
      legend: { live: !compact }
    };
    // Ligne de référence à 100 : un petit hook de dessin.
    opts.hooks = { draw: [function (u) {
      var y = u.valToPos(100, "y", true);
      var ctx = u.ctx;
      ctx.save();
      ctx.strokeStyle = css("--muted");
      ctx.globalAlpha = 0.6;
      ctx.setLineDash([2, 4]);
      ctx.beginPath();
      ctx.moveTo(u.bbox.left, y);
      ctx.lineTo(u.bbox.left + u.bbox.width, y);
      ctx.stroke();
      ctx.restore();
    }] };
    plot = new uPlot(opts, columns, host);
  }

  build();
  var timer = null;
  window.addEventListener("resize", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (plot) plot.setSize({ width: host.clientWidth, height: host.clientWidth < 520 ? 260 : 360 });
    }, 100);
  });
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var rebuild = function () { build(); };
    if (mq.addEventListener) mq.addEventListener("change", rebuild);
  }
})();
