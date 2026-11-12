# Dashboard de l'arène : décisions de design

Dashboard servi en privé sur `127.0.0.1:8787` et publié en version publique sur GitHub Pages (`ops/publier.py`, en sortie seulement : aucun port ouvert sur l'hôte). Direction **« Carnet »** choisie par le propriétaire le 12/11/2026 : un journal d'expérience imprimé, inspiré d'Our World in Data. Mode Impeccable : **Read** pour la vue d'ensemble, **Operate** pour les pages de portefeuille.
La question du premier écran, pour un lecteur qui ne connaît rien au sujet : que fait ce site, où en est l'expérience, peut-on déjà conclure.

## Décisions

| Sujet | Décision | Raison |
|---|---|---|
| Langue | Français seul, typographie française (espace fine insécable avant `; : ? !`, dans les guillemets) appliquée par `render.typo_fr` | Un seul lecteur francophone |
| Thème | Clair et sombre, suivant `prefers-color-scheme`, jetons dans `:root` | Lecture le matin et le soir |
| Police | IBM Plex Serif (titres), Sans et Mono, sous-ensemble latin, auto-hébergées (`fonts/`, OFL-1.1, sommes dans `SHA256SUMS`) | Chiffres tabulaires nets, aucune ressource externe |
| CSP | `style-src 'self'`, `script-src 'self'`, sans `unsafe-inline` ; aucun attribut `style` dans le HTML (jauges et barres en SVG à attributs) | Le site affiche du texte produit par des modèles |
| Indexation | `noindex, nofollow` pour l'instant ; SEO Lighthouse à 54 | Décision d'indexation laissée au propriétaire |
| Motion | Retours de survol et de focus (150 ms, `cubic-bezier(0.22, 1, 0.36, 1)`) ; pas d'entrée animée, pas de boucle | Mode Operate ; les chiffres doivent être lisibles tout de suite |
| Loader, WebGL, élément partagé, service worker | Non | Sans objet pour une page de données statique |
| Graphique | uPlot (vendored), un point par cycle, axe en écart au départ (%) ; styles des courbes calculés une fois (`render._styles`) et partagés par la légende HTML et `chart.js` | Légende lisible sans JS, au clavier, sans décalage de mise en page |
| Équivalent texte du graphique | `aria-label` avec les valeurs du dernier cycle, légende HTML avec valeurs, tableaux | Le graphique n'est jamais la seule source |
| Fraîcheur | `assets/site.js` compare l'heure du prochain cycle à l'heure du lecteur (« dans 3 h 06 », « en retard ») | La page est statique ; un minuteur arrêté doit se voir |
| Modèle qui n'a jamais décidé | Pastille « n'a jamais décidé », ni rang ni coût, alerte sur sa page | Un portefeuille resté en cash « bat » le hasard qui paie des frais : chiffre trompeur |
| Version publique | `build(..., public=True, racine="/arene/")` : sans la ligne « à faire » de l'opérateur, avec une page 404 ; `ops/publier.py` bloque la publication si un chemin local, un jeton, une adresse e-mail ou un document interne apparaît | Seuls les chiffres de l'expérience sortent ; the owner veut tous les chiffres, euros compris |
| Signature | La frise des cycles : chaque cycle terminé avec le préfixe de l'empreinte de son événement `cycle_completed` dans le journal chaîné | Vérifiable, propre à ce projet, lisible sans connaître le sujet |
| Graphique d'accueil | Étiquettes en bout de courbe (valeur et nom, chaque nom dans sa couleur), courbes confondues signalées dans le sous-titre | Lecture directe, sans légende à décoder (OWID) |
| Impression | Navigation et légende masquées, bandeau Simulation conservé | Le statut simulé doit rester sur papier |
| Justifications | Publiées dès la décision (décision du propriétaire, 12/11/2026). Une décision avec ordres est une carte dépliée : le raisonnement du modèle à gauche, les ordres, le verdict du risque et l'exécution à droite (empilés sous 1024 px) ; les cycles « aucun ordre » restent repliés | Voir pourquoi un modèle ouvre ou ferme une position, sans noyer la page sous les « attendre » |
| Modèle arrivé en cours de route | Courbe qui commence à son premier cycle (aucun point à 100 avant), date d'entrée sous son nom et sur sa page, pas de rang face au hasard (calculé sur toute la période) | Ne pas le comparer aux autres sur une période où il n'existait pas |
| Couleurs des modèles | Haiku rouille, Sonnet bleu, Opus violet, Fable sarcelle (`--llm3`, 5,4:1 sur le fond clair) ; les témoins restent gris pointillé | Quatre teintes éloignées, aucune proche du vert des gains |
| Étiquettes groupées | Quand plusieurs courbes finissent à la même valeur, les noms qui ne tiennent pas dans la marge deviennent « +N » | Aucun texte coupé au bord du graphique |
| Cartes empilées (mobile) | Seules les cellules sans rien à lire (« — ») sont masquées ; « accepté », « refusé » et leurs motifs restent visibles | Un refus du contrôle de risque ne doit jamais disparaître sur téléphone |

## Exceptions au détecteur Impeccable

- `low-contrast` sur le scan statique de `var/site/` : faux positifs, le scan croise les couleurs du thème sombre avec le fond clair. Le scan des pages rendues, clair et sombre, et axe-core donnent 0.
- `cramped-padding` sur `.table-scroll` (scan statique) : les cellules ont 11 px de marge intérieure ; le texte n'est pas collé au bord.
- `em-dash-overuse` (avis) : ce sont les cellules vides « — » des tableaux, pas de la prose.
