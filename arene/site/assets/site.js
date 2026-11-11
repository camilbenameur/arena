/* Fraîcheur du dashboard : la page est statique, ce script compare l'heure du prochain cycle à l'heure du lecteur.
   Sans JavaScript, la date absolue reste affichée. */
(function () {
  "use strict";
  var t = document.querySelector("[data-prochain]");
  var detail = document.querySelector("[data-fraicheur]");
  if (!t || !detail) return;
  var prochain = Number(t.getAttribute("data-prochain"));
  var intervalle = Number(t.getAttribute("data-intervalle")) || 14400;
  var original = detail.textContent;

  function duree(s) {
    if (s < 60) return "moins d\u2019une minute";
    var m = Math.round(s / 60);
    if (m < 60) return m + " min";
    var h = Math.floor(m / 60), r = m % 60;
    return h + " h" + (r ? " " + (r < 10 ? "0" : "") + r : "");
  }

  function maj() {
    var now = Date.now() / 1000;
    var ecart = prochain - now;
    detail.classList.remove("warn-txt", "perte-txt");
    if (ecart > 0) {
      detail.textContent = "dans " + duree(ecart) + " · " + original;
    } else if (-ecart < 3600) {
      // Le minuteur tourne à HH:05 et la page est reconstruite à la fin du cycle.
      detail.textContent = "en cours ou imminent · " + original;
    } else {
      var manques = Math.floor(-ecart / intervalle) + 1;
      detail.textContent = "en retard de " + duree(-ecart) + " : " + manques + " cycle" + (manques > 1 ? "s" : "") +
        " sans mise à jour de cette page";
      detail.classList.add(-ecart > intervalle ? "perte-txt" : "warn-txt");
    }
  }

  // Heure locale du lecteur à côté de l'heure UTC (la page est générée en UTC).
  try {
    var d = new Date(prochain * 1000);
    var mm = d.getMinutes();
    var sfx = document.createElement("span");
    sfx.className = "heure-locale";
    sfx.textContent = (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (mm < 10 ? "0" : "") + mm + " heure locale";
    t.parentNode.appendChild(sfx);
  } catch (err) { /* navigateur sans Intl : l'heure UTC suffit */ }

  maj();
  setInterval(maj, 60000);
})();
