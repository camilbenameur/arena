# Le « Chasseur de mèches » : spécification

Origine : la recherche v5 du 18/11/2026 (docs/RECHERCHE-V5-AGRESSIF-2026-11-18.md).

Recherche et contrôle scellé : `docs/RECHERCHE-V5-AGRESSIF-2026-11-18.md`. La règle gelée est dans `docs/recherche-v5/finalistes/chocs_fade-mecheS.py`.

## 1. La règle (gelée, ne pas la modifier)

Pour chaque contrat (XBT, ETH, SOL, XRP, LTC, LINK) :
- **choc** : `log(prix_maintenant / prix_il_y_a_w_min) < −4,5 %` pour w ∈ {5, 15, 30}, ce qui donne un achat ; ou `> +4,5 %`, ce qui donne une vente. On joue donc contre la mèche ;
- **entrée** : position de **2x l'équité** en notionnel (200 %), dans le sens contraire au choc, avec un **stop à 5 %** ;
- **sortie** : à la clôture **60 minutes** après l'entrée, ou au stop ;
- **blocage** : pas de nouvelle entrée sur ce contrat pendant **60 minutes** après la sortie prévue (entrée + 120 min) ;
- **une position à la fois par contrat** : pendant qu'une position est tenue, un nouveau choc est ignoré.

Sur le banc, le gain disparaît avec le retard : +37,6 % sur le contrôle en entrant à la minute suivante, +13,9 % avec 1 minute de retard, −8,1 % avec 5 minutes. **La vitesse est toute la stratégie.**

## 2. Les deux portefeuilles

- **`robot-perp:chasseur`**, « Chasseur de mèches », 1 000 €. Un processus dédié lit les prix toutes les **5 s** et agit dès qu'un choc est vu.
- **`benchmark-perp:chasseur-5min`**, « Chasseur au rythme de 5 min », 1 000 €. C'est le témoin : la même règle, par le même chemin d'exécution, mais il ne décide qu'au rythme du watcher, une fois par tranche de 5 minutes, sur le premier relevé à HH:MM:30 ou plus (MM multiple de 5, plus 3). L'écart entre les deux mesure ce que la vitesse rapporte.

Les deux sont dans la ligue dérivés.

## 3. Le processus `python -m arene.perp.hunter run`

C'est un service systemd utilisateur `arene-perp-hunter.service` (`Type=simple`, `Restart=always`, `RestartSec=10`) qui tourne depuis le checkout principal, comme le watcher. Sa boucle, toutes les 5 s :

1. **Les prix :** un seul appel `KrakenFuturesClient.tickers(...)` pour les 6 contrats. Le prix de la règle est le **dernier prix échangé** (`last`) quand il existe, sinon le milieu bid/ask.
   - L'historique en mémoire garde les relevés des 35 dernières minutes.
   - Au démarrage, il est amorcé par les bougies d'une minute `trade` des 35 dernières minutes (`client.candles`), pour qu'un redémarrage ne rende pas le chasseur aveugle pendant 30 minutes.
   - Le prix d'il y a w minutes est le dernier relevé ou la dernière clôture d'une minute à `t − w·60` ou avant. S'il n'y en a pas, ou s'il a plus de 90 s d'écart avec `t − w·60`, cette fenêtre ne compte pas.
2. **La vue de marché :** une `PerpMarketView` construite à partir de ces tickers frais (bid, ask, mark, index, funding, ts). L'EUR/USD vient du dernier relevé du store (`market_view`), ou de `client.eurusd`, s'il est assez frais pour riskd. Le spread médian vient du store (`market_view`).
3. **Les décisions** :
   - un choc sur un contrat libre et non bloqué donne une entrée ;
   - une position dont les 60 minutes sont écoulées donne une clôture.
4. **L'exécution :** par le chemin standard des autres joueurs : `parse_decision`, puis `run_intents(..., shrink=True)`, avec une `PerpSimulator` sur le journal de la ligue. Les écritures du journal sont déjà sérialisées par le verrou du simulateur, et le chasseur ne prend **pas** le verrou du watcher : un tick du watcher bloqué par un appel LLM ne doit jamais retarder une entrée.
   - Une entrée porte `stop_pct = 5`, `horizon_h = 1` et `expected_move_pct = 1,13`. Ce mouvement attendu est mesuré : sur la conception du banc, la règle fait 53 trades, avec un mouvement brut moyen de +113 bp. La source est écrite dans la config, comme `expected_move_source` dans `config/perp-conseil-tendance.toml`.
   - Les identifiants d'ordre sont déterministes (portefeuille, contrat, ts du choc) : une décision rejouée après un crash ne passe jamais deux fois.
5. **Le témoin 5 min :** il est joué par le même processus. Il n'évalue la règle qu'au premier relevé de chaque tranche de 5 minutes. Il utilise le même historique, mais seulement les prix connus à cet instant.
6. **Les garde-fous :**
   - le kill switch (`arene.ops.killswitch`) et la dormance bloquent les entrées, comme pour le watcher ;
   - un portefeuille arrêté (`halted`) ne joue plus ;
   - une erreur réseau ou une donnée manquante n'arrête pas la boucle : elle est comptée, et un relevé `hunter_heartbeat` est journalisé au plus une fois par heure (relevés réussis, erreurs, chocs vus, ordres).

   On ne journalise **pas** chaque relevé de prix.

## 4. Le journal

- **`hunter_signal`** (portefeuille, contrat, sens, fenêtre, mouvement en bp, prix, ts) : à chaque choc retenu, avant l'ordre.
- **Les ordres et les verdicts :** les événements standards de `run_intents` (`perp_verdict`, `perp_fill`, `conditional_order`, ...).
- **`hunter_exit`** : à la clôture prévue.

## 5. La politique de risque

`config/policy-perp-chasseur.toml`, profil `aggressive`, sur le modèle de `config/policy-perp-conseil-v4.toml` :
- un ordre ≤ 200 % de l'équité, une position ≤ 300 %, un levier brut ≤ 10x ;
- les mêmes bornes de stop, de perte au stop par position (≤ 25 %) et de risque ouvert total (≤ 59 %). Si 5 ou 6 contrats choquent en même temps, les dernières entrées sont réduites (`shrink=True`) ;
- la règle d'edge est gardée (coût ≤ 33 % du mouvement attendu de 113 bp) ;
- au plus 48 ouvertures par jour, sans délai minimal ;
- pas de gel journalier ; arrêt à −60 % depuis le plus haut ;
- **les contrôles de marché sont gardés tels quels** (écart mark/index, spread, âge des données). Ils peuvent refuser une entrée au milieu d'une mèche : c'est le marché réel, et le refus est journalisé comme pour tout joueur.

Config du joueur : `config/perp-chasseur.toml` (portefeuilles, noms, paramètres de la règle, mouvement attendu et sa source, intervalle de relevé). Elle est hachée et journalisée au démarrage.

## 6. L'intégration au watcher

Le watcher reste maître des minutes (stops dans la minute, funding, appels de marge, `perp_equity`). Pour les deux portefeuilles du chasseur, il :
- applique la politique du chasseur (`policy_for`) ;
- **ne ferme pas** leurs positions pour une tenue maximale, ne les gèle pas et ne les arrête pas selon les règles de la ligue (−15 %) : c'est le chasseur qui gère ses sorties, comme `_trend_names` pour le Conseil Tendance. L'arrêt à −60 % de sa politique s'applique ;
- les ouvre au premier tick si le chasseur ne l'a pas déjà fait (`open_portfolio`, idempotent).

## 7. Le site

La ligue dérivés affiche les deux portefeuilles, dans un groupe « Robots » (sans IA). Leur ligne dit :
- la règle en une phrase ;
- les chocs vus ;
- les trades.

La courbe les montre avec les autres. Le nom du propriétaire n'apparaît nulle part.

## 8. Les tests (sans réseau)

- **Détection :** un choc de −5 % en 10 minutes donne un achat, un de +5 % une vente. Un mouvement de 4 % ne donne rien. Une fenêtre sans prix de référence ne compte pas.
- **Exécution :** entrée à 2x avec stop, clôture à 60 minutes, blocage de 60 minutes, une position à la fois.
- **Idempotence :** la même décision rejouée ne crée pas de second ordre.
- **Le témoin 5 min :** il ne décide qu'une fois par tranche, avec les prix connus à cet instant.
- **Le watcher :** il ne ferme pas une position du chasseur à la tenue maximale et lui applique la bonne politique.
- **Les garde-fous :** le kill switch bloque les entrées ; une erreur réseau ne casse pas la boucle.
- **La règle :** sur une série de minutes synthétique, les décisions du chasseur (à cadence de minute) reproduisent celles de `docs/recherche-v5/finalistes/chocs_fade-mecheS.py`.
