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

C'est un service systemd utilisateur `arene-perp-hunter.service` (`Type=simple`) qui tourne depuis le checkout principal, comme le watcher.

**Cycle de vie :**
- `Restart=on-failure`, `RestartSec=10`, `RestartPreventExitStatus=2`, et `StartLimitIntervalSec=600` / `StartLimitBurst=10` dans `[Unit]` : au plus 10 relances en 10 minutes. `After=network-online.target`, `MemoryMax=1G`, `Nice=0`.
- `RuntimeMaxSec=86400` : un redémarrage par jour, qui recharge les specs et la config. À l'échéance, systemd arrête l'unité avec le résultat `timeout`, un échec pour `Restart=on-failure`, qui la relance (vérifié avec une unité transitoire : `systemd-run --user -p RuntimeMaxSec=3 -p Restart=on-failure sleep 1000` redémarre toutes les 3 s).
- `enabled = false` dans la config : sortie 0, pas de relance. Config invalide ou chasseur déjà lancé : sortie 2, pas de relance.
- **Un seul processus :** au démarrage, `flock` non bloquant sur `var-perp/hunter.lock`. S'il est déjà pris : message et sortie 2. Deux chasseurs jouerait chaque entrée deux fois.
- Si la config du chasseur ne charge pas, le watcher le dit (alerte `perp_hunter_config_invalid`) et **retombe sur la politique de la ligue** (2x, arrêt à −15 %, gel journalier, fermeture à 7 jours) pour les deux portefeuilles, sans les contrôles du chasseur : plus strict, jamais plus lâche. Le processus du chasseur, lui, ne démarre pas.

Sa boucle, toutes les 5 s :

1. **Les prix :** un seul appel `KrakenFuturesClient.tickers(...)` pour les 6 contrats. Le prix de la règle est le **dernier prix échangé** (`last`) quand il existe et qu'il est à **100 bp ou moins du milieu bid/ask**, sinon le milieu.
   - L'historique en mémoire garde les relevés des 35 dernières minutes.
   - Au démarrage, il est amorcé par les bougies d'une minute `trade` des 35 dernières minutes (`client.candles`), pour qu'un redémarrage ne rende pas le chasseur aveugle pendant 30 minutes.
   - Le prix d'il y a w minutes est le dernier relevé ou la dernière clôture d'une minute à `t − w·60` ou avant. S'il n'y en a pas, ou s'il a plus de 90 s d'écart avec `t − w·60`, cette fenêtre ne compte pas.
2. **La vue de marché :** une `PerpMarketView` construite à partir de ces tickers frais (bid, ask, mark, index, funding, ts). L'EUR/USD vient du dernier relevé du store (`market_view`), ou de `client.eurusd`, s'il est assez frais pour riskd. Le spread médian vient du store (`market_view`).
3. **Les décisions** :
   - un choc sur un contrat libre et non bloqué donne une entrée, sauf les cas « pas d'entrée tardive » ci-dessous ;
   - une position dont les 60 minutes sont écoulées donne une clôture.
4. **L'exécution :** par le chemin standard des autres joueurs : `parse_decision`, puis `run_intents(..., shrink=True)`, avec une `PerpSimulator` sur le journal de la ligue. Les écritures du journal sont déjà sérialisées par le verrou du simulateur, et le chasseur ne prend **pas** le verrou du watcher : un tick du watcher bloqué par un appel LLM ne doit jamais retarder une entrée.
   - **Le fill reflète la latence réelle.** Juste avant chaque entrée, le chasseur relit le ticker frais du contrat (un appel `tickers` pour ce symbole). Ce ticker (et non celui du relevé) fait la vue de marché, et l'ordre est daté de l'heure réelle (`int(horloge())`). Sans ticker frais utilisable, pas d'ordre : on réessaie si on est encore dans les temps.
   - **Pas de long rejeu :** `run_intents(..., max_shrink_tries=2)` : un ordre refusé pour sa taille est réessayé plus petit deux fois au plus (le défaut des autres joueurs reste `SHRINK_TRIES`, 8).
   - Une entrée porte `stop_pct = 5`, `horizon_h = 1` et `expected_move_pct = 1,13`. Ce mouvement attendu est mesuré : sur la conception du banc, la règle fait 53 trades, avec un mouvement brut moyen de +113 bp. La source est écrite dans la config, comme `expected_move_source` dans `config/perp-conseil-tendance.toml`.
   - Les identifiants d'ordre sont déterministes (portefeuille, contrat, ts du relevé qui a vu le choc). Ce n'est **pas** cela qui empêche une seconde entrée : la protection réelle est la position tenue (`held`, relue dans le registre avant chaque entrée) et le verrou du processus unique.
   - **Pas d'entrée tardive.** Aucune entrée (ni chasseur ni témoin) quand le relevé réussi précédent date de plus de 30 s, ni sur le premier relevé après le démarrage. Un choc vu sur un tel relevé fait un épisode sans entrée : il n'est jamais joué. Une nouvelle tentative après un refus (spread d'une mèche...) n'est permise que dans les **120 s** qui suivent la première détection du choc (le banc perd à partir de 5 min de retard). Elle ne compte pas comme un nouveau choc (`stats.shocks`). Un épisode (contrat, `first_seen_ts`) finit au premier relevé qui ne montre plus le choc.
   - **Le blocage** est posé dès qu'un `perp_fill` d'entrée existe pour l'intent, même si la position a déjà été fermée (fermeture sans stop) : même logique que `_restore`.
5. **Le témoin 5 min :** il est joué par le même processus. Il n'évalue la règle qu'au premier relevé de chaque tranche de 5 minutes. Il utilise le même historique, mais seulement les prix connus à cet instant. Il raisonne **en tranches**, sans tolérance de secondes : sa sortie a lieu 12 tranches après la tranche de son entrée, son blocage dure jusqu'à 24 tranches après elle. Une exception pendant sa décision ne consomme pas la tranche : le relevé suivant la rejoue.
6. **Les garde-fous :**
   - le kill switch (`arene.ops.killswitch`) et la dormance bloquent les entrées, comme pour le watcher ;
   - un portefeuille arrêté (`halted`) ne joue plus ;
   - une erreur réseau ou une donnée manquante n'arrête pas la boucle : elle est comptée, et un relevé `hunter_heartbeat` est journalisé au plus une fois par heure (relevés réussis, erreurs, chocs vus, ordres) ;
   - l'alerte « chasseur aveugle » (`perp_hunter_blind`, aucun relevé depuis 10 minutes, au plus une par 6 h) est journalisée **et envoyée par le notifier** (`arene/ops/notify.py`), comme les alertes du watcher ;
   - au démarrage, une erreur de lecture du journal est réessayée (10 fois, toutes les 5 s) au lieu de faire planter ; si elle persiste, le processus s'arrête (l'unité le relance) plutôt que de jouer sans son état.

   On ne journalise **pas** chaque relevé de prix.

## 4. Le journal

- **`hunter_signal`** (portefeuille, contrat, sens, fenêtre, mouvement en bp, prix, `ts` et `read_ts` du relevé qui a vu le choc, `first_seen_ts` de la première détection de l'épisode) : à chaque tentative d'entrée, avant l'ordre. Le site compte les « chocs vus » par `(portefeuille, contrat, first_seen_ts)` distincts : les nouvelles tentatives ne comptent pas.
- **`hunter_entry`** (portefeuille, contrat, intent, `read_ts`, `latency_ms` entre ce relevé et l'ordre, `status` `filled` ou `refused`) : après l'exécution.
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
- les ouvre au premier tick si le chasseur ne l'a pas déjà fait (`open_portfolio`, idempotent) ;
- **filet de sécurité :** ferme toute position du chasseur tenue depuis plus de **3 h** (le chasseur sort normalement à 60 min), par `close_expired` avec ce seuil (raison `max_holding`) ;
- **le stop des deux portefeuilles ne regarde pas la minute de l'entrée** (`sim.py`, `HUNTER_NAMES` défini dans `arene/perp/margin.py`) : la bougie de cette minute contient la mèche jouée à contre-courant, et le stop ne s'applique qu'aux minutes qui commencent après son armement. Les autres portefeuilles gardent le comportement pessimiste habituel.

**Limite connue :** chaque lecture complète du journal (environ 1 s aujourd'hui) croît avec lui. Le chasseur en fait une par entrée (relevé du fill, `run_intents`, `_refresh` toutes les minutes), et la latence d'une entrée avec elle. À traiter (index ou lecture incrémentale) avant que le journal ne devienne lent.

## 7. Le site

La ligue dérivés affiche les deux portefeuilles, dans un groupe « Robots » (sans IA). Leur ligne dit :
- la règle en une phrase ;
- les chocs vus ;
- les trades.

La courbe les montre avec les autres. Le nom du propriétaire n'apparaît nulle part.

## 8. Les tests (sans réseau)

- **Détection :** un choc de −5 % en 10 minutes donne un achat, un de +5 % une vente. Un mouvement de 4 % ne donne rien. Une fenêtre sans prix de référence ne compte pas.
- **Exécution :** entrée à 2x avec stop, clôture à 60 minutes, blocage de 60 minutes, une position à la fois.
- **Pas de seconde entrée :** une position tenue empêche une nouvelle entrée sur le contrat, le blocage survit à un redémarrage (et à une position déjà fermée), et un second processus sort en code 2. (Un rejeu du même choc dans le même processus est sans effet, mais ce n'est pas la protection.)
- **Latence et entrées tardives :** ticker frais avant l'ordre, ordre daté de l'heure réelle, `hunter_entry` ; pas d'entrée après un trou de plus de 30 s, ni au premier relevé, ni plus de 120 s après la première vue du choc ; le stop ignore la minute de l'entrée ; le filet de 3 h du watcher ; le prix `last` filtré à 100 bp.
- **Le témoin 5 min :** il ne décide qu'une fois par tranche, avec les prix connus à cet instant.
- **Le watcher :** il ne ferme pas une position du chasseur à la tenue maximale et lui applique la bonne politique.
- **Les garde-fous :** le kill switch bloque les entrées ; une erreur réseau ne casse pas la boucle.
- **La règle :** sur une série de minutes synthétique, les décisions du chasseur (à cadence de minute) reproduisent celles de `docs/recherche-v5/finalistes/chocs_fade-mecheS.py`.
