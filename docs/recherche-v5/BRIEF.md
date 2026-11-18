# Consigne des chercheurs : agent de trading agressif (recherche v5, 18/11/2026)

## Le but

Trouver une stratégie de trading **agressive et rentable vite** sur 6 contrats perpétuels de Kraken Futures (XBT, ETH, SOL, XRP, LTC, LINK, en paper). Toutes les méthodes sont permises. Le levier va jusqu'à 10x brut.

On cherche le meilleur **rendement composé** possible, sous trois contraintes :
- jamais de ruine ;
- un drawdown max d'au plus 50 % ;
- un résultat positif sur au moins 3 des 4 blocs de la période de conception.

Le moteur de référence est le suivi de tendance gelé (`arene/perp/lab/trend.py`, `FROZEN`, à l'échelle 2x) : il faut le battre. Sur la période de conception, il **perd 20,8 %** (drawdown −62 %, blocs +40,6 / −49,7 / +3,1 / +8,7) : il n'a gagné que sur l'épisode d'août à novembre 2026. Mesure-le quand même toi-même d'abord, avec `trend.targets(d, TrendParams(scale=2.0))` et un stop à 5 %, et journalise-le comme premier essai (`name: "reference-trend-2x"`).

## Les règles (non négociables)

1. **Données :** uniquement `design()` du harnais, `docs/recherche-v5/harness.py`. Elle contient les 245 premiers jours d'une année de bougies d'une minute, de novembre 2025 à juillet 2026. N'ouvre **jamais** `data/`, `full.pkl`, `var-perp/` ni aucune autre source de prix : la suite est un contrôle scellé, lu une seule fois par le coordinateur. Une fuite rend tout le travail inutilisable.
2. **Causalité :** la cible décidée à la minute i n'utilise que les données ≤ i. Le coordinateur le vérifie en recalculant tes cibles sur des données tronquées. Tout regard vers l'avenir disqualifie la stratégie.
3. **Coûts réels :** le banc `evaluate()` compte 24 bp par aller-retour, le funding horaire et les stops dans la minute. Il exécute à l'ouverture de la minute suivante. Ne contourne pas le banc.
4. **Journal :** chaque essai, y compris les échecs, passe par `log_trial(<famille>, <nom>, params, res)`. **40 essais au plus.** Plus on en fait, plus on risque de trouver un hasard : préfère des idées qui ont une raison économique à un balayage de paramètres.
5. **Robustesse :** une stratégie retenue doit avoir au moins 3 blocs sur 4 positifs, et ne pas tenir à un seul réglage (ses voisins proches doivent aussi gagner).
6. **Contraintes du simulateur :** au plus 48 ordres par jour sur l'ensemble des contrats. `evaluate()` ne le vérifie pas : calcule-le toi-même (le nombre de changements de cible par jour).
7. **Ressources :** la machine est partagée, avec 8 cœurs et peu de mémoire libre. Lance un seul processus de banc à la fois, et charge `design()` une fois par script. Pour trier des idées, tu peux faire un pré-calcul vectorisé rapide, mais tout chiffre rapporté vient d'`evaluate()`.
8. Travaille dans `docs/recherche-v5/<famille>/`. Ne modifie rien dans le dépôt de l'arène.

## Ce que tu rends

- **1 ou 2 finalistes gelés**, chacun dans un fichier `docs/recherche-v5/finalistes/<famille>_<nom>.py`. Ce fichier expose `targets(d) -> np.ndarray` (de taille N × 6, NaN = garder) et `STOP_PCT` (un float ou None). Les paramètres y sont écrits en dur. Il est autonome : il importe seulement numpy, pandas et `arene.perp.lab.backtest`.
- **En réponse finale, en texte court :**
  - chaque finaliste : l'idée en une phrase, sa raison économique, son résultat de conception (total, par jour, drawdown max, blocs, ordres par jour, rotation) ;
  - le résultat de la référence de tendance 2x sur la même période ;
  - ce qui a échoué, en une ligne par idée ;
  - si rien ne bat la référence, dis-le simplement. Un « rien de mieux » honnête vaut mieux qu'un finaliste fragile.
