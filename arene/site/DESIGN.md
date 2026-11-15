# Dashboard de l'arène : décisions de design

Dashboard servi en privé sur `127.0.0.1:8787` et publié en version publique sur GitHub Pages (`ops/publier.py`, en sortie seulement : aucun port ouvert sur the host).

**Direction « Tableau des scores »**, choisie par the owner le 15/11/2026 (maquette A, contre B « Bureau de nuit »), en remplacement de « Carnet » (12/11). Sa remarque : « ce n'est pas lisible, on a des défilés sur des pavés de texte qu'on ne peut pas lire, le site de base n'est pas assez parlant, l'UI n'est pas user friendly ». Un classement sportif qu'on lit d'un coup d'œil : fond clair, une seule famille (Plex Sans, chiffres en Plex Mono), **pas de gros titre** (« Pas de gros titre c'est horrible », 15/11) : le titre est une phrase d'une ligne, et ce sont le classement et la courbe, côte à côte, qui portent le premier écran. Mode Impeccable : **Persuade** pour l'accueil et `conseils.html` (page du post LinkedIn du 24/11), **Operate** pour les pages de portefeuille.
La question du premier écran, pour un visiteur venu de LinkedIn qui ne connaît rien au sujet : qu'est-ce que c'est (des modèles Claude qui tradent en simulation contre des témoins), qui est en tête, où cliquer.

## Structure

| Page | Contenu, dans l'ordre |
|---|---|
| `index.html` (accueil) | Une phrase, puis une carte par ligue (conseils, IA seules, comptant) : ce qu'elle mesure, une petite courbe, le meneur, le deuxième et le témoin sans IA, un lien. Puis « Comment ça marche » en trois points. Décision du propriétaire du 15/11 : « Les 3 ligues ». |
| `conseils.html` | Phrase et chapeau, classement et courbe, « Comment un conseil décide » (3 étapes), dernières décisions en cartes, tableau détaillé, actualités, règles repliées. |
| `derives.html` (IA seules) | Même gabarit ; l'ancienne adresse `index.html` de la ligue dérivés est devenue l'accueil. |
| `comptant.html` | Même gabarit, avec l'état de la saison sous le classement. |
| Pages de portefeuille | Chiffres, courbe, positions, **décisions**, puis ordres en attente et opérations. |

## Composants

- **Classement** (`accueil.scores`) : rang (ex æquo au centième de pour cent), pastille de la couleur de la courbe (hachurée pour un témoin), nom en lien, sous-titre, rendement en grand. Le témoin sans IA est en dernier, rang « réf. ». Une IA qui n'a encore rien acheté le dit (« tout en cash »).
- **Carte de décision** (`render_perp._decision`, phrases dans `lisible.py`) : l'heure et le déclencheur, puis **ce qui a été décidé en une phrase sans jargon** (« Se prépare à parier sur la baisse de Solana »), puis **pourquoi en une phrase** : pour un conseil, le décompte réel des avis de l'étape A (« 7 conseillers sur 9 voient Solana baisser ; l'avocat du diable attaque… ») avec une marque par conseiller (▲ hausse, ▼ baisse, ● sans avis, ○ absent : la forme porte le sens, pas seulement la couleur) ; pour une IA seule, « En ses mots », la première phrase de son raisonnement d'au moins 9 mots, entre guillemets, les « bp » convertis en % (1 bp = 0,01 %), jamais réécrite. Le détail (raisonnement complet, avis, ordres, garde-fou, exécution) est replié derrière un lien qui dit ce qu'il contient.
- **Étiquette SIMULÉ** dans l'en-tête de chaque page (« SIMULÉ · argent fictif », rouge bordé), et « Simulation. » en tête du pied de page. Le bandeau jaune reste retiré (demande du 15/11) ; « ARGENT RÉEL » apparaîtrait si `venue_mode` n'était plus paper.

## Décisions

| Sujet | Décision | Raison |
|---|---|---|
| Langue | Français seul, typographie française (espace fine insécable avant `; : ? !`, dans les guillemets) appliquée par `render.typo_fr` | Un seul lecteur francophone |
| Thème | Clair et sombre, suivant `prefers-color-scheme`, jetons dans `:root` | Lecture le matin et le soir |
| Police | IBM Plex Sans (texte et titres) et Mono (chiffres), sous-ensemble latin, auto-hébergées (`fonts/`, OFL-1.1, sommes dans `SHA256SUMS`). Plex Serif n'est plus utilisée depuis le 15/11 (fichiers gardés) | Chiffres tabulaires nets, aucune ressource externe |
| CSP | `style-src 'self'`, `script-src 'self'`, sans `unsafe-inline` ; aucun attribut `style` dans le HTML (jauges et barres en SVG à attributs) | Le site affiche du texte produit par des modèles |
| Indexation | Version publique **indexée** (`index, follow`, `canonical`, `sitemap.xml`) ; le site privé reste `noindex, nofollow` | Décision du propriétaire du 15/11, pour le post LinkedIn du 24/11 |
| Partage | Balises `og:` et `twitter:` (carte grande image) sur chaque page publique ; images 1200×630 `assets/apercu.png` et `assets/apercu-conseils.png` (conseils et pages de conseil), schémas sans chiffres pour ne pas vieillir ; sources dans `apercu-src/` | Le post renvoie vers `conseils.html` |
| Motion | Retours de survol et de focus (150 à 200 ms, `cubic-bezier(0.22, 1, 0.36, 1)`) : soulignement qui se trace sous les noms du classement, carte de ligue qui se soulève de 2 px, flèche qui avance ; pas d'entrée animée, pas de boucle, rien sous `prefers-reduced-motion` | Les chiffres doivent être lisibles tout de suite ; le site affiche des données qui changent toutes les 5 min, pas une vitrine |
| Loader, WebGL, élément partagé, service worker | Non | Sans objet pour une page de données statique |
| Graphique | uPlot (vendored), un point par cycle, axe en écart au départ (%) ; styles des courbes calculés une fois (`render._styles`) et partagés par la légende HTML et `chart.js` | Légende lisible sans JS, au clavier, sans décalage de mise en page |
| Équivalent texte du graphique | `aria-label` avec les valeurs du dernier cycle, légende HTML avec valeurs, tableaux | Le graphique n'est jamais la seule source |
| Prix en direct (dérivés) | `assets/direct.js` lit le flux public `wss://futures.kraken.com/ws/v1` (feed `ticker`, sans clé) et revalorise les positions publiées au mark du moment : rendement, valeur, prix actuel, latent. Chiffres soulignés en pointillé, ligne « Estimation en direct, prix Kraken de HH:MM:SS UTC ». Flux muet 15 s : retour aux chiffres publiés ; reconnexion avec attente croissante (60 s au plus), socket fermé quand l'onglet est caché. La CSP n'ouvre `connect-src wss://futures.kraken.com` que sur les pages dérivés qui ont des positions (`CSP_DIRECT`). La courbe reste celle du journal (« Dernier relevé ») | Demande du propriétaire du 14/11 (« quelques secondes au plus ») ; seule ressource externe du site, en lecture, sans cookie ni clé |
| Fraîcheur | `assets/site.js` compare l'heure du prochain cycle à l'heure du lecteur (« dans 3 h 06 », « en retard ») | La page est statique ; un minuteur arrêté doit se voir |
| Modèle qui n'a jamais décidé | Pastille « n'a jamais décidé », ni rang ni coût, alerte sur sa page | Un portefeuille resté en cash « bat » le hasard qui paie des frais : chiffre trompeur |
| Version publique | `build(..., public=True, racine="/arene/")` : sans la ligne « à faire » de l'opérateur, avec une page 404 ; `ops/publier.py` bloque la publication si un chemin local, un jeton, une adresse e-mail ou un document interne apparaît | Seuls les chiffres de l'expérience sortent ; the owner veut tous les chiffres, euros compris |
| Signature | Le tableau des scores à côté de la courbe, en tête de chaque ligue, et le vote des conseillers (▲▼●) sur chaque décision d'un conseil | Propre à ce projet (une ligue d'IA), lisible sans connaître le sujet |
| Graphique d'accueil | Étiquettes en bout de courbe (valeur et nom, chaque nom dans sa couleur), courbes confondues signalées dans le sous-titre | Lecture directe, sans légende à décoder (OWID) |
| Impression | Navigation et légende masquées, avertissement de pied de page conservé | Le statut simulé doit rester sur papier |
| Justifications | Publiées dès la décision (décision du propriétaire, 12/11/2026), repliées derrière la carte de décision (voir Composants) depuis le 15/11 | Plus de pavés de texte au premier regard ; tout reste à un clic |
| Modèle arrivé en cours de route | Courbe qui commence à son premier cycle (aucun point à 100 avant), date d'entrée sous son nom et sur sa page, pas de rang face au hasard (calculé sur toute la période) | Ne pas le comparer aux autres sur une période où il n'existait pas |
| Couleurs des modèles | Haiku rouille, Sonnet bleu, Opus violet, Fable sarcelle (`--llm3`, 5,4:1 sur le fond clair) ; les témoins restent gris pointillé | Quatre teintes éloignées, aucune proche du vert des gains |
| Bandeau « Simulation » | Bandeau jaune retiré le 15/11 (demande du propriétaire) ; à la place, l'étiquette « SIMULÉ · argent fictif » dans l'en-tête de chaque page et « Simulation. » en tête du pied de page ; « ARGENT RÉEL » si `venue_mode` n'est plus paper | L'étiquette SIMULÉ reste visible partout sans bandeau criard |
| Ligue des conseils | Page `conseils.html` (même journal, mêmes marchés que les dérivés ; `kind == "council"` classe), une page par conseil dans `conseils/`, entrée « Conseils » de la navigation, lien sur l'accueil dérivés. Tableau : conseils (marque « agressif · levier ≤ 10x · objectif ×2 ») puis le témoin panier 1x en référence. Conseil Haiku (« 10 Haiku · président Haiku », teinte `--conseil` magenta) et Conseil Opus (« 10 Haiku · président Opus », `--conseil2` doré, 4,9:1 clair, 11:1 sombre) ; conseil inconnu : « Conseil <slug> ». Délibération repliée par ronde : étape A (avis réels du journal, jamais un nombre codé : 8 puis 9 avec l'Arbitragiste), B l'Avocat, C le Président (« Président · Opus », coût du Président à part s'il n'est pas Haiku). Avis publiés pour les 48 dernières rondes. Méthode dans la page de la ligue (`#m-conseils`) | Demande du propriétaire du 15/11 ; un levier de 10x ne se compare pas aux IA à 2x ; seul le Président change entre les deux conseils |
| Actualités | Bloc « Actualités » sur les accueils dérivés et conseils (`journal.news_item`, dernière version de chaque annonce ; calendrier macro de `arene.perp.news`, omis s'il est illisible) : publications des 7 prochains jours (pastille « rappelle les IA 3 min après »), annonces de Kraken des 7 derniers jours (nature, statut, plage, contrats, lien https seulement). Déclencheurs de ronde « annonce de Kraken » et « publication macro · après … », mention discrète « … jointe » sur les autres. Méthode : `methode.html#m-actualites` | Demande du moteur du 15/11 ; sources officielles et structurées seulement |
| Étiquettes groupées | Quand plusieurs courbes finissent à la même valeur, les noms qui ne tiennent pas dans la marge deviennent « +N » | Aucun texte coupé au bord du graphique |
| Cartes empilées (mobile) | Seules les cellules sans rien à lire (« — ») sont masquées ; « accepté », « refusé » et leurs motifs restent visibles | Un refus du contrôle de risque ne doit jamais disparaître sur téléphone |

## Exceptions au détecteur Impeccable

- `low-contrast` sur le scan statique de `var/site/` : faux positifs, le scan croise les couleurs du thème sombre avec le fond clair. Le scan des pages rendues, clair et sombre, et axe-core donnent 0.
- `cramped-padding` sur `.table-scroll` (scan statique) : les cellules ont 11 px de marge intérieure ; le texte n'est pas collé au bord.
- `em-dash-overuse` (avis) : ce sont les cellules vides « — » des tableaux, pas de la prose.
