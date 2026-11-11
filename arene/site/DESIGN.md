# Dashboard de l'arène : décisions de design

Dashboard privé, un seul lecteur (le propriétaire), servi sur `127.0.0.1:8787`. Mode Impeccable : **Operate** (UI de travail).
La question du premier écran : où en est l'expérience, les modèles jouent-ils, quand a lieu le prochain cycle.

## Décisions

| Sujet | Décision | Raison |
|---|---|---|
| Langue | Français seul, typographie française (espace fine insécable avant `; : ? !`, dans les guillemets) appliquée par `render.typo_fr` | Un seul lecteur francophone |
| Thème | Clair et sombre, suivant `prefers-color-scheme`, jetons dans `:root` | Lecture le matin et le soir |
| Police | IBM Plex Sans et Mono, sous-ensemble latin, auto-hébergées (`fonts/`, OFL-1.1, sommes dans `SHA256SUMS`) | Chiffres tabulaires nets, aucune ressource externe |
| CSP | `style-src 'self'`, `script-src 'self'`, sans `unsafe-inline` ; aucun attribut `style` dans le HTML (jauges et barres en SVG à attributs) | Le site affiche du texte produit par des modèles |
| Indexation | `noindex, nofollow` ; SEO Lighthouse à 54 assumé | Dashboard privé |
| Motion | Retours de survol et de focus (150 ms, `cubic-bezier(0.22, 1, 0.36, 1)`) ; pas d'entrée animée, pas de boucle | Mode Operate ; les chiffres doivent être lisibles tout de suite |
| Loader, WebGL, élément partagé, service worker | Non | Sans objet pour une page de données statique |
| Graphique | uPlot (vendored), un point par cycle, axe en écart au départ (%) ; styles des courbes calculés une fois (`render._styles`) et partagés par la légende HTML et `chart.js` | Légende lisible sans JS, au clavier, sans décalage de mise en page |
| Équivalent texte du graphique | `aria-label` avec les valeurs du dernier cycle, légende HTML avec valeurs, tableaux | Le graphique n'est jamais la seule source |
| Fraîcheur | `assets/site.js` compare l'heure du prochain cycle à l'heure du lecteur (« dans 3 h 06 », « en retard ») | La page est statique ; un minuteur arrêté doit se voir |
| Modèle qui n'a jamais décidé | Pastille « n'a jamais décidé », ni rang ni coût, alerte sur sa page | Un portefeuille resté en cash « bat » le hasard qui paie des frais : chiffre trompeur |
| Impression | Navigation et légende masquées, bandeau Simulation conservé | Le statut simulé doit rester sur papier |

## Exceptions au détecteur Impeccable

- `low-contrast` sur le scan statique de `var/site/` : faux positifs, le scan croise les couleurs du thème sombre avec le fond clair. Le scan des pages rendues, clair et sombre, et axe-core donnent 0.
- `cramped-padding` sur `.table-scroll` (scan statique) : les cellules ont 11 px de marge intérieure ; le texte n'est pas collé au bord.
- `em-dash-overuse` (avis) : ce sont les cellules vides « — » des tableaux, pas de la prose.
