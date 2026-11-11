# Pipeline de recherche de stratégies : protocole recherche-v1

Écrit le 11/11/2026, avant tout essai. Révisé le même jour après la revue adverse en quatre regards (statisticien, tricheur, ingénieur, chercheur quantitatif ; sorties brutes dans `recherche/revue-protocole-v1.json`, arbitrage au §11). Les valeurs chiffrées sont dans `recherche/criteres.yaml`, qui fait foi. Ce protocole prolonge celui du labo léger (`~/dev/labo-trading/protocole/`, issue B le 11/11/2026). Il est plus strict que lui, jamais plus lâche.

## 1. Question, issues, et ce que rien ici ne prouve

Un système qui « teste toutes les possibilités » trouve toujours un gagnant sur l'historique. Ce pipeline **filtre**, il ne prouve pas.

- **Issue A** : 1 à 3 candidats gelés (code haché). Un candidat spot est branché comme portefeuille paper `strategie:<id>` dans l'arène. Un candidat carry (jambe perpétuelle) est gelé mais **non promu** : l'arène n'a pas encore de ledger perpétuel, et l'accès du propriétaire aux perpétuels Kraken n'est pas confirmé.
- **Issue B** : aucun candidat. Un rapport publie tous les essais, perdants compris. C'est un succès si le protocole est tenu.
- **Probabilité a priori de l'issue A : moins de 5 %.** Le DSR exige un Sharpe net d'environ 1,9 (N = 726, §5). Les familles long seul n'ont pas de chemin réaliste vers C1 et C6 à la fois : au labo, 0 essai sur 125. L'espace réaliste est celui des familles couvertes.
- **Aucune porte ne contrôle la mémoire des modèles**, qui ont vu toute la fenêtre 2018-2026. Seules des données postérieures à juin 2026 le font : le paper en avant (§9) et, si the owner le décide, le holdout scellé du labo (§10).
- **Le paper de 8 à 12 semaines ne prouve rien** : l'erreur type du Sharpe annualisé est de 2,6 à 56 jours et de 2,1 à 84 jours. Il peut seulement réfuter (§9). Une confirmation demande que l'intervalle de confiance à 90 % du Sharpe en avant soit au-dessus de 0, soit environ 300 jours pour un Sharpe de 1,8 et environ 1 000 jours pour un Sharpe de 1. Aucun passage au réel n'est décidé sur le paper seul ; c'est une décision du propriétaire (plan, §5 d).

## 2. Pare-feu des données (non négociable)

- **Date de coupure : 2026-07-01T00:00:00Z exclue.** Aucune donnée de marché d'une date ultérieure n'entre dans la recherche, sous aucune forme. Du 01/07 au 09/11/2026 s'étend le **holdout scellé du labo** (`~/dev/_labo-trading-scelle/`), que rien ici ne lit. Le cache de l'arène (`var/data/`) contient des prix récents : il est interdit à la recherche.
- **Sources autorisées**, toutes copiées dans `var/recherche/donnees/`, puis hachées dans un manifeste figé au tag `recherche-moteur-v1` :
  1. les bougies in-sample du labo (15 paires USDT, 1 j et 1 h, du 01/01/2018 au 30/06/2026), vérifiées contre `MANIFESTE.json` du labo ;
  2. les archives mensuelles publiques de Binance (`data.binance.vision`), **mois ≤ 2026-06** : funding et bougies 1 h des perpétuels USDT-M des 15 paires ;
  3. les bougies spot 1 j d'un **univers de contrôle** de 20 symboles, mois ≤ 2026-06, choisi par une règle mécanique avant la vague 1. La règle : les plus gros volumes en quote de janvier 2020 hors des 15 paires, délistés compris, pour contrer le biais du survivant (C16).
- **Contrôles du pare-feu** :
  - **chargeur** : il ne lit que `var/recherche/donnees/`, vérifie le manifeste et lève une erreur sur toute ligne dont `connue_a` (§3) est postérieure ou égale à la coupure ; il ne tronque jamais en silence ;
  - **téléchargeur** : il refuse tout mois postérieur à 2026-06 ;
  - **exécution des stratégies** : elle tourne sous `bwrap`, avec une liste blanche de montages (venv et bibliothèque standard en lecture seule, un tmpfs), aucun réseau et aucun accès au dépôt, à `var/`, à `~/.config` ni au dossier scellé ;
  - **canari au démarrage** : le moteur refuse de démarrer si le bac à sable laisse passer un `connect()`, une lecture hors liste blanche ou une écriture hors du tmpfs.
- **Agents** : les chercheurs n'ont aucun accès réseau aux marchés et ne lisent aucune actualité de marché. Leurs recherches web portent sur la littérature, et chaque requête est consignée. Les programmeurs ne voient **jamais** les données réelles : ils n'ont que des séries synthétiques seedées et des tests.
- **Limite connue** : les sessions d'agents tournent sous l'utilisateur du propriétaire, qui peut lire tout son dossier personnel. Une séparation par utilisateur Unix dédié (`rech-moteur`) demanderait une modification du système avec sudo, donc l'accord du propriétaire ; elle est proposée, pas faite. En attendant, la parade est l'ancrage externe du journal (§4), plus des consignes et des vérifications.

## 3. Mesure

- **Fenêtre.** La fenêtre d'évaluation va du 01/01/2020 au 30/06/2026 ; 2018-2019 ne sert qu'à l'échauffement. Le Sharpe, le DSR (T), C5, C13 et le panier se calculent sur les jours où au moins une paire de la stratégie est éligible. Une famille carry commence au premier jour où le funding de sa paire existe. Les fenêtres perp se terminent le 2026-06-29 inclus.
- **Données.** Les tolérances sont celles du labo :
  - 1 j : aucun trou ;
  - 1 h : au plus 0,1 % de barres manquantes et 6 barres consécutives ;
  - remplissage : close = dernier close, volume nul, rendement nul ;
  - poids nul avant la cotation d'une paire.
- **Connaissance de l'information.** Chaque ligne porte `connue_a` :
  - barre : `open_time + durée` ;
  - funding : `fundingTime + 1 s`.
  Une ligne n'est visible à l'instant t que si `connue_a ≤ t`.
- **Funding.** Une échéance est **payée** par la position décidée à une clôture ≤ `fundingTime`. Le moteur somme les échéances réelles présentes et ne suppose jamais 3 par jour.
- **Contrat de stratégie (fuite impossible par construction).**
  - **Flux.** Le moteur envoie au worker isolé, par tube, une barre journalière à la fois. Avec elle viennent ses 24 barres de 1 h et les échéances de funding de la journée ; le worker ne reçoit **jamais** le futur.
  - **Sortie.** À chaque clôture de 00:00 UTC, la stratégie rend un vecteur de poids cibles par (paire, jambe). La jambe est `spot`, ou `perp` en couverture seulement.
  - **Anonymisation.** La stratégie ne voit ni date, ni nom de paire : un index entier, et des colonnes `P01…P15` dans un ordre tiré au hasard à chaque appel.
- **Invariances testées sur des données synthétiques**, jamais sur les réelles :
  - la permutation des colonnes permute les poids (à 1e-9 près) ;
  - les poids ne changent pas si l'on multiplie les prix d'une paire par un facteur tiré entre 0,1 et 10, et les volumes par l'inverse ;
  - la troncature (§6, C9) ne change rien.
- **Cadence.** Une décision par jour à 00:00 UTC. Les barres de 1 h ne servent qu'en entrée de signaux agrégés. Une cadence de 4 h est hors de recherche-v1.
- **Portefeuille et rotation.** Le moteur tient le portefeuille en quantités. La rotation se calcule ainsi : rotation = Σ |w_cible − w_dérivé|, avec w_dérivé = w_{t−1}(1+r)/(1+r_p).
- **Test d'acceptation du moteur.** Avec des poids de 1/15 constants, il doit retrouver la rotation et le Sharpe net du panier calculés indépendamment, et reproduire le labo à 1e-9 près sur E0065 avec les coûts du labo.
- **Coûts**, alignés sur l'arène (`config/arene.toml` : 50 pb de frais taker, 5 pb de glissement), plus 5 pb de demi-spread :
  - **spot** : 0,60 % par unité de rotation ;
  - **perp** : 0,10 % par unité de rotation, plus le funding réel ;
  - **stress** : coûts doublés.
  Un test vérifie la cohérence entre `criteres.yaml` et `arene.toml`.
- **Marchés.**
  - **Classe `directionnel`** : spot long seul, poids dans [0, 1], somme ≤ 1, le reste en cash à rendement nul.
  - **Classe `couvert`** : long spot et short perp sur la même paire, avec short perp ≤ long spot. Le capital immobilisé est le notionnel spot plus une marge perp de 50 % du notionnel court. Rendement = w_spot·r_spot − w_perp·r_perp + funding reçu.
  - Les perps directionnels et neutres sont hors de recherche-v1.
  - Le moteur **lève une erreur** sur un poids hors bornes ; il ne le rogne jamais.
- **Paramètres.** Ils sont fixes, sans walk-forward en recherche-v1 : un point de grille est une règle, et sa série sur toute la fenêtre est la série testée.
- **Un seul moteur.** `recherche/moteur/`, figé au tag `recherche-moteur-v1` avec le sha256 de `criteres.yaml`. Aucun calcul de performance hors du moteur, statistique descriptive comprise. Le moteur ne rend aux agents qu'un **code fermé** (`OK`, `CAUSALITE`, `TIMEOUT`, `SOURCE_REFUSEE`, `FORME_POIDS`, `ERREUR`), jamais une trace ni un chiffre. Le détail va dans un journal technique, lu par l'orchestrateur et par the owner.

## 4. Journal, comptage, ancrage

- **Journal chaîné.** `recherche/essais.jsonl` est chaîné, en enveloppe de `arene/journal.py`. Les métriques y sont en chaînes décimales à 12 chiffres significatifs, recalculées à la relecture.
  - **Première ligne** : `genese_labo`, qui porte la tête et le nombre de lignes du journal du labo au tag `gel-final`.
  - **Par essai** : une ligne `debut` **avant** le calcul (code_sha256, fiche_sha256, paramètres), puis une ligne `fin`. Un essai sans `fin` compte.
- **Ancrage externe.** Après chaque essai, la tête et le nombre de lignes sont écrits dans le journal de l'arène (événement `research_anchor`). Le moteur refuse de démarrer si son journal est plus court que le dernier ancrage, ou si la tête ancrée n'y figure pas.
- **N.** Le DSR de tout candidat se calcule avec **N = 726** (126 essais du labo + 600, le plafond de recherche-v1), quel que soit le moment, jamais avec un N courant. On rapporte aussi le N réel, pour information.
- **Plafonds.**
  - **Recherche-v1** : 600 essais au total.
  - **Vague 1** : 120 essais au plus, soit 6 familles au plus et 20 variantes par famille au plus. Chaque règle a de 2 à 4 paramètres.
  - **Règle d'arrêt** : si le meilleur DSR de la vague 1 est inférieur à 0,5, la vague 2 n'est pas lancée sans décision écrite du propriétaire.

## 5. Correction des essais multiples

Le Sharpe déflaté (Bailey et López de Prado, 2014) est calculé comme au labo (formules de son `dsr.py`, testées sur l'exemple publié), avec N = 726.

**Variance V.** Elle se calcule **par classe** (`directionnel`, `couvert`, déclarée dans la fiche avant tout essai), en prenant la plus grande de deux valeurs :
- la variance des `sr_jour` des essais de recherche de cette classe, calculée par famille puis moyennée, pondérée par le nombre d'essais ;
- 1/(T_candidat − 1).

Les `sr_jour` du labo comptent dans N, mais pas dans V : leurs coûts étaient différents. On rapporte aussi, pour information, le DSR avec un V commun.

**Sharpe net requis pour DSR ≥ 0,95**, recalculé par le statisticien de la revue (T = 2 373, asymétrie nulle, kurtosis de 3 ; ajouter environ 0,02 pour des queues épaisses) :

| N | V au plancher | écart-type des Sharpe de 0,5 | écart-type des Sharpe de 0,7 |
|---|---|---|---|
| 326 | 1,79 | ≈ 2,2 | 2,69 |
| 726 | 1,89 | ≈ 2,3 | 2,86 |

## 6. Critères de sélection (tous requis, nets de coûts)

**Portes réelles :**

| Code | Critère |
|---|---|
| C1 | DSR ≥ 0,95 (N = 726, V de la classe) |
| C5 | Années civiles 2020 à 2025 : aucune sous un Sharpe de −1, au moins 4 positives |
| C6 | Drawdown maximal ≤ 45 % (classe directionnel) ou ≤ 20 % (classe couvert), sur la valeur liquidative composée en clôtures journalières |
| C7 | Grille géométrique déclarée (au moins 3 valeurs par paramètre, rapport ≥ 1,25 entre valeurs voisines). Au moins 75 % des voisins directs (±1 pas) doivent avoir un Sharpe net ≥ 0,6 × celui du candidat et ≥ 0,5. Un candidat au bord de grille ou non évaluable échoue |
| C8 | **Directionnel** : bat le panier équipondéré de son univers (rebalancé le 1er de chaque mois, mêmes coûts, même fenêtre), au bootstrap apparié par blocs de 20 jours sur la différence des rendements, avec p unilatéral ≤ 0,05. **Couvert** : régression des rendements sur le panier, alpha annualisé avec t de Newey-West ≥ 2 et \|β\| ≤ 0,3. La branche alternative sur le drawdown est supprimée |
| C9 | Causalité : flux par construction, plus 20 coupures aléatoires et 3 fixes sur `connue_a`, dont au moins 40 % à une heure non pleine, et les tests d'invariance du §3, sur des données synthétiques |
| C11 | Extrêmes : Sharpe ≥ max(0,5 ; 0,5 × Sharpe complet) après retrait des 1 % meilleurs jours (24 jours), et > 0 après retrait de 2 % |
| C12 | Coût total payé ≤ 50 % du rendement brut annualisé. Rotation annuelle ≤ 15 (directionnel) ou ≤ 40 (couvert, chaque jambe comptée) |
| C13 | Sharpe net > 0 dans chacune des deux moitiés de la fenêtre |
| C14 | Matérialité : rendement annualisé net géométrique ≥ 4 % sur le capital immobilisé (marge comprise) |
| C15 | Compatibilité arène (spot seulement) : stratégie rejouée sur les 6 paires de l'arène, à 00:00 UTC, à travers le vrai `riskd` et le simulateur de l'arène, avec la politique `config/policy-strategie.toml` hachée ; Sharpe net > 0 et drawdown ≤ 1,3 × C6 |
| C16 | Hors univers : la stratégie inchangée, sur l'univers de contrôle de 20 symboles (§2), a un Sharpe net > 0 sur au moins 60 % des symboles où elle est applicable (rapporté si non applicable) |

**Contrôles de cohérence**, qui détectent des bugs et ne comptent pas comme portes indépendantes : C2 (Sharpe net ≥ 0,5), C3 (t de Newey-West ≥ 2), C4 (Sharpe > 0 à coûts doublés), C10 (bootstrap du Sharpe par blocs de 20 jours, p ≤ 0,05). Ils restent requis.

**Sélection.** Les essais qui passent tout sont classés par DSR, 3 au plus. Deux candidats dont les rendements en excès du panier sont corrélés à plus de 0,7 (Pearson, journalier) : seul celui de plus haut DSR est gardé. Plus aucune modification de code après la sélection. Le rapport donne la probabilité qu'au moins un candidat soit « non réfuté » en paper sous H0 (environ 85 % pour 3).

## 7. Rôles et séparation des pouvoirs

- **Chercheurs (agents Sonnet).** Vagues aveugles : toutes les fiches d'une vague sont écrites et hachées avant que la vague précédente soit visible. Des vagues passées, ils ne reçoivent que le nom, le mécanisme et un verdict binaire (écartée ou non), jamais un Sharpe, un graphique ou un rang. Ils reçoivent les fiches du labo, sans aucun résultat, pour éviter les doublons.
- **Contenu d'une fiche** : classe ; mécanisme ; qui perd de l'autre côté ; prédiction falsifiable ; ce qui la réfuterait ; grille exacte ; mouvement brut attendu par trade ; « C1 et C6 accessibles ensemble : oui ou non, pourquoi » ; risque d'anticipation par la mémoire. **Aucun chiffre tiré des données, aucune date, aucun événement nommé.**
- **Auditeur de fiche (agent distinct).** Il refuse une fiche dans l'un de ces cas :
  - doublon d'une famille déjà testée (labo compris) sans mécanisme nouveau ;
  - date ou événement nommé ;
  - plus de 4 paramètres, ou plus de 20 variantes en vague 1 ;
  - grille non géométrique ;
  - donnée non autorisée ;
  - fiche infalsifiable ;
  - rendement espéré par unité de rotation inférieur à 3 fois le coût aller-retour de la jambe.
- **Programmeur (agent distinct).** Il écrit `strategie.py` selon le contrat du §3, sans import hors de la liste blanche (contrôle de l'AST hérité du labo). Il ne voit que des données synthétiques et les codes fermés du moteur.
- **Moteur (code, pas un LLM).** Il exécute la grille, journalise et calcule les critères. **Aucun LLM ne décide d'un passage.**
- **Orchestrateur (la session principale).** Il lance le moteur, lit les verdicts et écrit le rapport de vague.
- **Auditeur final (agent distinct).** Avant le gel, il relit chaque candidat ; sa sortie est consignée telle quelle.
- **the owner.** Il décide de toute révision du protocole, de toute vague après une règle d'arrêt, de tout dépassement de 600 essais, du sort du holdout du labo (§10) et de tout passage au réel.

## 8. Biais reconnus

- Mémoire des modèles sur 2018-2026 (§1).
- Fenêtre déjà lue par 126 essais du labo, d'où le N cumulé.
- Une seule classe d'actifs, fortement corrélée ; biais du survivant, en partie contré par C16.
- Données Binance en USDT et exécution chez Kraken en EUR : écart de base, de change et de liquidité. Les coûts majorés n'en couvrent qu'une partie.
- Funding Binance et funding Kraken diffèrent ; l'éligibilité du propriétaire aux perpétuels n'est pas confirmée.
- Exécution supposée à la clôture de 00:00 UTC, alors que l'arène exécute à 00:05.

## 9. Paper en avant : règles écrites avant le premier cycle

Ces règles sont hachées dans le journal de l'arène au moment de la promotion. Le résultat est l'une de trois étiquettes : **réfuté**, **non réfuté (aucune preuve)** ou **défaut technique**. « Prouvé » n'existe pas dans ce protocole.

- **Réplication.** À la fin de la période, le moteur gelé est rejoué sur les mêmes jours (les données postérieures sont alors autorisées pour ce seul usage). Il y a **défaut technique** si la corrélation quotidienne avec le paper est inférieure à 0,95, ou si l'écart cumulé dépasse 1,5 fois le coût stressé.
- **Réfutation**, calibrée à 5 % de fausse réfutation pour un Sharpe vrai de 1 :
  - rendement cumulé ≤ −0,5 × la volatilité annualisée du backtest à 56 jours, ou ≤ −0,6 × cette volatilité à 84 jours ;
  - ou drawdown du paper supérieur à 1,3 fois le drawdown du backtest contraint (C15).
- **Rythme.** Un seul regard par semaine, avec une dépense d'alpha de type O'Brien-Fleming de 5 % au total.
- **Halte propre.** La politique `config/policy-strategie.toml` applique la halte au seuil de réfutation, et non aux 20 % de la politique des LLM.

## 10. Holdout du labo : décision réservée au propriétaire

Le holdout du labo (01/07 au 09/11/2026, environ 132 jours) est la seule donnée propre déjà disponible. Le statu quo est qu'il reste scellé pour un éventuel second tour du labo. the owner peut décider à la place qu'il sert **une fois** à tester un candidat gelé de cette recherche, par l'évaluateur scellé, avec la règle de non-réfutation du §9. Sans décision écrite de sa part, il reste scellé.

## 11. Arbitrage de la revue adverse

**Retenu :**
- règles du paper et étiquettes ;
- N fixé à 726 et V par classe ;
- table de puissance et probabilité a priori ;
- contrat de flux, anonymisation et invariances ;
- `connue_a` et convention de funding ;
- pare-feu par liste blanche, canari et ancrage externe ;
- codes fermés ;
- paramètres fixes ;
- C7 réécrit ;
- C8 sans branche de drawdown, et alpha pour la classe couvert ;
- C11 à 1 % et 2 % ;
- C12 sur les coûts ;
- C14 matérialité, C15 compatibilité arène, C16 hors univers ;
- coûts de 0,60 % ;
- vague 1 ≤ 120 et règle d'arrêt ;
- classe couvert ;
- univers de contrôle ;
- programmeurs sur données synthétiques ;
- vagues aveugles.

**Écarté ou différé :**
- **Utilisateur Unix dédié avec sudoers** : modification du système, à proposer au propriétaire (§2).
- **Classe neutre perp et perp directionnel** : pas de ledger perp dans l'arène ; reportés à recherche-v2.
- **Cadence de 4 h** : reportée.
- **Critère « retrait des 24 pires jours ≤ 3 × Sharpe »** : trop dépendant du profil ; rapporté pour information seulement.
- **C15 avec drawdown ≤ 20 %** : remplacé par une politique propre aux stratégies, car la halte des LLM n'a pas de sens pour une règle à drawdown connu.

## 12. Historique

- recherche-v1 : 11/11/2026, version figée avant tout essai, après la revue adverse.
