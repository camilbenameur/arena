/* Graphique du rendement cumulé (uPlot). Les données, en base 100, sont lues dans <script id="equity-data">.
   - un point par cycle réel, graduations de l'axe des temps posées sur les cycles, jamais entre deux ;
   - axe vertical en écart au départ (« −0,5 % »), comme le tableau ;
   - légende HTML à boutons (clavier, tactile, lecteurs d'écran) qui montre les valeurs du dernier cycle
     ou du cycle survolé, à la place de la légende uPlot. */
(function () {
  "use strict";
  var node = document.getElementById("equity-data");
  var host = document.getElementById("chart");
  var legende = document.getElementById("legende");
  if (!node || !host || typeof uPlot === "undefined") return;
  var data;
  try { data = JSON.parse(node.textContent); } catch (err) { return; }
  var plot = null;
  var compactActuel = null;
  var masques = {};
  var MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  var LAST = data.x.length - 1;

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function fr(v, d) { return v.toFixed(d).replace(".", ","); }
  function ecart(v, d) {
    if (v == null) return "—";
    var x = v - 100;
    var r = Number(fr(Math.abs(x), d).replace(",", "."));
    var s = r === 0 ? "" : (x > 0 ? "+" : "−");
    return s + fr(Math.abs(x), d) + " %";
  }
  function jour(d) { return d.getUTCDate() + " " + MOIS[d.getUTCMonth()]; }
  function heure(d) { return d.getUTCHours() + " h"; }
  function quand(i) {
    if (i === 0) return "Départ (capital initial)";
    var d = new Date(data.x[i] * 1000);
    return (i === LAST ? "Dernier cycle : " : "Cycle du ") + jour(d) + ", " + heure(d) + " UTC";
  }

  /* Styles des séries : calculés côté serveur (render._styles), source unique avec la légende HTML. */
  function styles() {
    return data.styles.map(function (st, i) {
      return {
        stroke: css(st.color), width: st.width, dash: st.dash, visible: st.visible,
        isLlm: data.series[i].kind === "llm", focused: st.width >= 3
      };
    });
  }

  function splits(u) {
    var xs = data.x, n = xs.length;
    if (n < 2) return xs.slice();
    var width = u.bbox.width / uPlot.pxRatio;
    var minPx = width < 420 ? 70 : 90;
    var every = Math.max(1, Math.ceil(minPx / (width / (n - 1))));
    var out = [];
    for (var i = LAST; i >= 0; i -= every) out.unshift(xs[i]);
    return out;
  }

  /* La légende est déjà dans le HTML (valeurs du dernier cycle) : on active ses boutons. */
  var valeurs = [];
  var quandNode = document.getElementById("legende-quand");
  function brancherLegende() {
    if (!legende) return;
    valeurs = data.series.map(function () { return null; });
    Array.prototype.forEach.call(legende.querySelectorAll("button[data-serie]"), function (b) {
      var i = Number(b.getAttribute("data-serie"));
      var id = data.series[i].id;
      valeurs[i] = b.querySelector(".legende-val");
      b.disabled = false;
      b.addEventListener("click", function () {
        var off = b.getAttribute("aria-pressed") === "true";
        b.setAttribute("aria-pressed", off ? "false" : "true");
        masques[id] = off;
        if (plot) plot.setSeries(i + 1, { show: !off });
      });
    });
  }

  function afficherValeurs(idx) {
    if (idx == null) idx = LAST;
    if (quandNode) quandNode.textContent = quand(idx);
    data.series.forEach(function (s, i) {
      var v = valeurs[i];
      if (!v) return;
      var x = s.values[idx];
      v.textContent = ecart(x, 2);
      v.classList.toggle("gain", x != null && x >= 100.005);
      v.classList.toggle("perte", x != null && x <= 99.995);
    });
  }

  function build() {
    if (plot) { plot.destroy(); plot = null; }
    var width = host.clientWidth || 600;
    var compact = width < 520;
    compactActuel = compact;
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
        show: st.visible && !masques[s.id],
        points: { show: !many, size: st.focused || st.isLlm ? 7 : 5, width: 1.5, stroke: st.stroke, fill: css("--surface") }
      });
      columns.push(s.values);
    });
    var axisStroke = css("--muted");
    var grid = { stroke: css("--grid"), width: 1 };
    var font = "12px " + css("--sans");
    var opts = {
      width: width,
      height: compact ? 240 : 320,
      series: series,
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, points: { size: 9 } },
      scales: {
        x: { time: false },
        y: { range: function (u, min, max) {
          // Bornes collées aux données, 0 % toujours visible, amplitude minimale de 0,4 point.
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
              if (v === data.x[0]) { return "départ"; }
              var d = new Date(v * 1000);
              var day = jour(d);
              var label = day === prevDay ? heure(d) : heure(d) + "\n" + day;
              prevDay = day;
              return label;
            });
          } },
        { stroke: axisStroke, grid: grid, ticks: { show: false }, size: 58, font: font,
          values: function (u, vals) { return vals.map(function (v) { return ecart(v, 1); }); } }
      ],
      hooks: {
        drawAxes: [function (u) {
          // Ligne du départ (0 %), sous les courbes.
          var r = uPlot.pxRatio;
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
        setCursor: [function (u) { afficherValeurs(u.cursor.idx); }]
      }
    };
    plot = new uPlot(opts, columns, host);
    afficherValeurs(LAST);
  }

  brancherLegende();
  build();
  var timer = null;
  function onResize() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var w = host.clientWidth;
      if (!plot || !w) return;
      if ((w < 520) !== compactActuel) build();
      else plot.setSize({ width: w, height: w < 520 ? 240 : 320 });
    }, 120);
  }
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(onResize).observe(host.parentNode);
  else window.addEventListener("resize", onResize);
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", build);
  }
})();
