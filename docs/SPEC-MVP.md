# Spécification du MVP (paper, crypto spot)

Référence : `conception/01-plan-conception.md` (décisions validées par the owner le 11/11/2026 : 1 à 6 du §10).
Ce document est le contrat entre les modules. Un module qui a besoin d'un écart le signale au lieu de l'inventer.

## 0. Règles pour quiconque écrit du code ici (agents compris)

- **Aucun ordre réel, aucune clé de plateforme** dans le MVP. Tout est `venue_mode = "paper"`.
- **Ne jamais lire, afficher, copier ni créer** quoi que ce soit dans `~/.config/arene/secrets/` : c'est the owner qui y dépose les secrets. Le code lit ces fichiers à l'exécution ; les tests utilisent des faux.
- Ne rien écrire hors de ce dépôt. Ne pas toucher à `~/dev/labo-trading` (lecture seule permise) ni à `~/dev/_labo-trading-scelle` (ni lecture ni écriture).
- Pas de dépendance nouvelle sans la déclarer dans le compte rendu (le `pyproject.toml` est tenu par l'orchestrateur ; ne pas lancer `uv add`).
- Python 3.12, `uv run pytest`. Tests sans réseau par défaut ; un test réseau porte le marqueur `reseau`.
- Commentaires et docstrings en français, noms de code en anglais ou français cohérents avec `arene/types.py`.

## 1. Périmètre et promesse

Une arène de 3 modèles Claude (Haiku 5.5, Sonnet 5.5, Opus 5.5) et de témoins, qui décide toutes les 4 h sur la crypto spot EUR de Kraken, en paper avec des frais pessimistes. Chaque décision, chaque fill simulé et chaque chiffre est journalisé, rejouable et affiché sur un dashboard privé étiqueté SIMULÉ. Des alertes fonctionnent même si the host tombe. Pas de promesse de P&L, pas de classement.

Univers (6 paires, toutes cotées en EUR chez Kraken et en USDT chez Binance) :

| Symbole | Kraken (altname) | Binance (signal E0065 seulement) | tick | ordre min | coût min |
|---|---|---|---|---|---|
| BTC/EUR | XBTEUR | BTCUSDT | 0,1 € | 0,00006 | 0,45 € |
| ETH/EUR | ETHEUR | ETHUSDT | 0,01 € | 0,002 | 0,45 € |
| SOL/EUR | SOLEUR | SOLUSDT | 0,01 € | 0,05 | 0,45 € |
| XRP/EUR | XRPEUR | XRPUSDT | 0,00001 € | 4 | 0,45 € |
| LINK/EUR | LINKEUR | LINKUSDT | 0,00001 € | 0,35 | 0,45 € |
| LTC/EUR | LTCEUR | LTCUSDT | 0,01 € | 0,08 | 0,45 € |

(Valeurs relevées sur `https://api.kraken.com/0/public/AssetPairs` le 11/11/2026 ; à recharger au démarrage.)

## 2. Unités

Voir `arene/types.py` : µEUR entiers, quantités en 1e-8, timestamps en secondes UTC, arrondis défavorables. Aucun float dans le chemin de l'argent.

## 3. Arborescence

```
arene/
  types.py          contrats (orchestrateur)
  journal.py        journal JSONL chaîné, lecture, vérification, rejeu          [vague 1, A]
  ledger.py         état des portefeuilles dérivé du journal, P&L, SQLite dérivé [vague 1, A]
  data/kraken.py    bougies 4 h, ticker, AssetPairs (API publique)              [vague 1, B]
  data/binance.py   bougies 1 j publiques (taker_buy_base) pour E0065           [vague 1, B]
  data/store.py     cache local des bougies, détection des trous                 [vague 1, B]
  risk/policy.py    chargement et cohérence de config/policy.toml               [vague 1, C]
  risk/riskd.py     evaluate(intent, état, marché, politique, compteurs)        [vague 1, C]
  deciders/llm.py   harnais des décideurs LLM (instantané, prompt, schéma)      [vague 1, E]
  deciders/prompt/  prompt système versionné
  sim/fills.py      simulateur de fills pessimiste, stops, détention max        [vague 2, D]
  sim/executor.py   machine à états d'ordre, exécution simulée                  [vague 2, D]
  temoins/          panier, 60/40, E0065 adapté, aléatoire (vivant + 1 000 traj.) [vague 2, F]
  stats.py          rendements, drawdown, Sharpe et intervalle bootstrap par blocs [vague 3]
  cycle.py          un cycle de 4 h de bout en bout, idempotent                  [vague 3]
  ops/              heartbeat, ntfy, coupe-circuit, dormance                    [vague 3]
  site/             générateur du dashboard statique                            [vague 3]
  cli.py            `arene <commande>`                                          [vague 3]
config/policy.toml  politique de risque paper (hachée dans le journal à chaque chargement)
config/arene.toml   univers, capital, cadence, modèles, budgets
var/                état d'exécution, ignoré par git (journal, cache, site construit)
tests/              un fichier de test par module, scénarios d'or dans tests/golden/
```

## 4. Journal (source de vérité)

- Fichier `var/journal/events.jsonl`, une ligne par événement, append-only.
- Champs : `seq` (entier, depuis 0, sans trou), `ts` (s UTC), `type`, `payload` (objet), `prev_hash` (hex, `"0"*64` pour seq 0), `hash`.
- `hash = sha256(canonical(record sans "hash"))`, `canonical` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encodé en UTF-8. Aucun float dans un événement (entiers, chaînes, booléens, null, listes, objets).
- Écriture : verrou `fcntl.flock` exclusif sur un fichier `.lock`, relecture de la dernière ligne pour `seq`/`prev_hash`, écriture, `flush` + `os.fsync`. Une ligne tronquée en fin de fichier (crash) est détectée par `verify()` et signalée, jamais réparée en silence.
- `verify(path) -> VerifyReport` : chaîne intacte, seq continus, aucun float.
- Types d'événements (payload minimal ; un module peut ajouter des champs, jamais en retirer) :

| type | payload |
|---|---|
| `config_loaded` | `policy_sha256`, `config_sha256`, `prompt_sha256`, `git_head` |
| `cycle_started` / `cycle_completed` | `cycle` |
| `bar` | champs de `Bar` (seulement les barres utilisées par un cycle) |
| `quote` | champs de `Quote` |
| `portfolio_opened` | `portfolio`, `kind` (`llm`/`temoin`), `capital_ueur`, `venue_mode` |
| `decision_requested` | `portfolio`, `cycle`, `model`, `snapshot_sha256` |
| `decision_received` | `portfolio`, `cycle`, `model_requested`, `model_returned`, `raw_text`, `parsed` (ou null), `parse_error`, `input_tokens`, `output_tokens`, `cost_uusd` (micro-dollars) , `latency_ms` |
| `decision_skipped` | `portfolio`, `cycle`, `reason` (`no_key`, `budget`, `frozen`, `halted`, `kill_switch`, `api_error`) |
| `intent` | champs de `Intent` |
| `risk_verdict` | champs de `Verdict` |
| `order_state` | `order_id`, `state`, `detail` |
| `fill` | champs de `Fill` |
| `stop_set` | `portfolio`, `symbol`, `stop_ueur` |
| `equity` | `portfolio`, `cycle`, `cash_ueur`, `positions_value_ueur`, `equity_ueur` |
| `portfolio_frozen` / `portfolio_halted` / `portfolio_resumed` | `portfolio`, `reason`, `until_ts` |
| `kill_switch` | `active`, `source` |
| `alert` | `level` (`info`/`action`/`panique`), `code`, `message` |

- `ledger.replay(events) -> dict[str, PortfolioState]` reconstruit tout l'état uniquement à partir du journal. Le SQLite `var/ledger.sqlite` est une vue dérivée, reconstructible à tout moment (`arene rebuild-ledger`), jamais une source.

## 5. Données

- Kraken `GET /0/public/OHLC?pair=<altname>&interval=240&since=<ts>` : la dernière barre renvoyée est **en cours**, l'exclure. Conversion des prix texte en µEUR **sans passer par float** (`Decimal`). Volume en unités 1e-8.
- Kraken `GET /0/public/Ticker?pair=...` : `a[0]` ask, `b[0]` bid → `Quote`.
- Kraken `GET /0/public/AssetPairs` : tick, ordermin, costmin.
- Binance `GET /api/v3/klines?symbol=...&interval=1d` : seulement pour le signal du témoin E0065 (colonne 9 = taker_buy_base, colonne 5 = volume). Données publiques, aucun compte.
- Cache `var/data/<source>/<symbol>_<interval>.jsonl`, dédupliqué par `ts`. `gaps()` liste les barres manquantes. Respect des limites : 1 requête/s, 3 tentatives, backoff exponentiel, délai max 10 s.
- Le snapshot donné aux modèles ne contient **que** des barres closes avant le cycle : test d'absence de fuite du futur.

## 6. Portefeuilles

- Capital paper : **1 000 € par portefeuille** (proche du réel futur, pour que les frais pèsent comme en vrai).
- Portefeuilles : `llm:claude-haiku-5-5`, `llm:claude-sonnet-5-5`, `llm:claude-opus-5-5`, `temoin:panier`, `temoin:6040`, `temoin:e0065`, `temoin:aleatoire`.
- Long seulement, pas de levier, cash en EUR (pas d'intérêt).

## 7. Risque (`riskd`) : politique paper

`config/policy.toml` (valeurs paper ; la politique réelle sera plus stricte, voir le plan §4). Les témoins `panier`, `6040`, `e0065` sont des références et ne passent pas par les plafonds de taille ; `temoin:aleatoire` passe par **exactement** les mêmes règles que les LLM.

| clé | valeur | règle |
|---|---|---|
| `symbols` | les 6 | liste blanche (code `NOT_WHITELISTED`) |
| `max_order_bp` | 2000 | achat ≤ 20 % de l'equity (`MAX_ORDER_SIZE`) |
| `max_position_bp` | 4000 | position par symbole ≤ 40 % de l'equity après l'ordre (`MAX_POSITION`) |
| `max_exposure_bp` | 10000 | exposition totale ≤ 100 %, cash ≥ 0 après frais (`MAX_EXPOSURE`, `INSUFFICIENT_CASH`) |
| `max_trades_per_day` | 2 | par portefeuille, fenêtre glissante 24 h, ventes comprises (`DAILY_TRADES`) |
| `max_orders_per_minute` | 5 | tous portefeuilles (`ORDER_RATE`) |
| `min_interval_same_symbol_s` | 14400 | anti-oscillation (`TOO_SOON`) |
| `stop_bp_min` / `stop_bp_max` | 100 / 2500 | achat sans stop ou hors bornes → rejet (`STOP_REQUIRED`, `STOP_RANGE`) |
| `max_cost_to_expected_move_pct` | 33 | coût aller-retour estimé ≤ 33 % du mouvement attendu déclaré (`EDGE_TOO_SMALL`) ; mouvement absent → rejet |
| `max_holding_s` | 604800 | 7 jours, sortie forcée par le simulateur |
| `daily_loss_freeze_bp` | 500 | perte ≥ 5 % de l'equity sur 24 h → gel 24 h (`FROZEN`) |
| `drawdown_halt_bp` | 2000 | drawdown ≥ 20 % depuis le plus haut → mise à plat et arrêt jusqu'à `arene resume` (`HALTED`) |
| `monthly_fee_budget_bp` | 100 | frais du mois civil ≥ 1 % de l'equity de début de mois → gel jusqu'au mois suivant (`FEE_BUDGET`) |
| `max_quote_deviation_bp` | 300 | mid du quote à plus de 3 % de la dernière clôture → aucune entrée (`PRICE_SANITY`) |
| `max_spread_multiple` | 3 | spread > 3 × médiane des 20 derniers quotes → aucune entrée (`SPREAD_ANOMALY`) |
| `min_order_ueur` | max(costmin Kraken, 5 €) | (`ORDER_TOO_SMALL`) |

- `evaluate()` est une **fonction pure** : mêmes entrées → même verdict. Les compteurs (trades sur 24 h, ordres par minute, frais du mois) sont calculés **à partir du journal** et passés en argument.
- Une vente ne peut jamais dépasser la position détenue (pas de vente à découvert : `NO_SHORT`). Les ventes ne sont pas soumises à `EDGE_TOO_SMALL` ni aux plafonds de taille.
- Coupe-circuit (fichier `var/KILL` ou `~/.config/arene/KILL`) : aucune entrée, les portefeuilles LLM et aléatoire sont mis à plat au cycle suivant.
- `policy.py` vérifie la cohérence au chargement (bornes, `stop_bp_min < stop_bp_max`, budgets positifs, symboles connus) et refuse de démarrer sinon. Hash de la politique dans chaque verdict.

## 8. Exécution simulée (`fill_model_version = "pessimiste-v1"`)

- Ordres au marché uniquement (taker). Achat au `ask × (1 + 5 bp)`, vente au `bid × (1 − 5 bp)`, arrondi au tick défavorablement.
- Frais : `0,50 %` du notional (Kraken Pro taker de base 0,40 % majoré de 25 %), arrondis vers le haut.
- Quantité arrondie vers le bas à 1e-8 ; rejet si sous `lot_min_qty` ou `cost_min`.
- Stops : posés à l'entrée (`stop_ueur = prix d'entrée × (1 − stop_bp/10000)`). À chaque cycle, pour chaque barre 4 h close depuis le dernier cycle : si `low ≤ stop`, sortie au `min(stop, open)` (gap) moins 5 bp, frais compris (`reason = "stop"`).
- Détention maximale : sortie forcée au bid du cycle (`reason = "max_holding"`).
- Machine à états : `INTENT → RISK_APPROVED | RISK_REJECTED → SUBMITTING → ACKED → FILLED`, chaque transition journalisée. En paper `UNKNOWN` est simulable pour les tests (injection de faute) : on n'émet jamais de second ordre pour la même intention, on interroge l'état ; un ordre `UNKNOWN` plus de 2 cycles gèle le portefeuille.
- Idempotence : un `intent_id` déjà vu dans le journal n'est jamais réexécuté.

## 9. Décideurs LLM

- SDK `anthropic` (Python). Modèles : `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`. L'identifiant renvoyé par l'API est journalisé ; alerte s'il diffère du demandé.
- Clé lue à l'exécution dans `$CREDENTIALS_DIRECTORY/anthropic_api_key`, sinon `~/.config/arene/secrets/anthropic_api_key`. **Pas de clé → `decision_skipped` avec `no_key`**, le reste de l'arène tourne.
- Instantané (même pour les 3 modèles) : horodatage du cycle, pour chaque symbole les 42 dernières barres 4 h (7 jours) résumées en features calculées par le code (rendements 4 h / 24 h / 7 j, volatilité réalisée, position du prix dans la fourchette 7 j, volume relatif) + les 12 dernières clôtures ; positions, cash, equity, stops, P&L latent ; règles de risque en clair ; 5 dernières décisions du portefeuille (résumé court). Aucun texte web.
- Sortie demandée en JSON (outil ou sortie structurée du SDK) :
  `{"actions": [{"symbol", "side": "buy"|"sell", "size_pct": 0-20 (achat, % de l'equity) ou 0-100 (vente, % de la position), "stop_pct": 1-25, "horizon_h", "expected_move_pct", "confidence_pct"}], "justification": "≤ 1 200 caractères"}` ; 0 à 2 actions ; `actions: []` = ne rien faire.
- Conversion en `Intent` par le code (pourcentages → points de base, entiers). JSON invalide → `parse_error`, aucune intention, pas de nouvelle tentative au-delà de 1.
- Budget par modèle et par jour (USD) dans `config/arene.toml` : Haiku 0,10 ; Sonnet 0,50 ; Opus 0,90 (≈ 45 $/mois au total, sous la limite de 50 $ de la clé). Budget dépassé → `decision_skipped budget`. Coût calculé depuis les tokens et une table de tarifs dans la config (Opus 4/20, Sonnet 2/10, Haiku 0,10/0,50 $ par million de tokens, entrée/sortie).
- `max_tokens` borné, `temperature` par défaut, délai max 120 s, 2 tentatives sur erreur réseau ou 5xx/529, jamais sur 4xx.
- Prompt système versionné dans `arene/deciders/prompt/v1.md`, hash journalisé.
- Tests avec un client factice (aucun appel réseau) : JSON valide, invalide, hors liste, tailles négatives ou énormes, injection dans la justification, dépassement de budget, modèle renvoyé différent. 20 instantanés figés dans `tests/golden/snapshots/` vérifiés sur des invariants (pas de réponse exacte).

## 10. Témoins

- `temoin:panier` : au premier cycle, 1/6 de l'equity sur chaque symbole (frais compris), puis conservé (buy-and-hold).
- `temoin:6040` : 60 % BTC / 40 % cash, rééquilibré le premier cycle de chaque mois civil.
- `temoin:e0065` : règle F1 du labo (`~/dev/labo-trading/hypotheses/F1-pression-taker.md`), paramètres L = 20, k = 3, H = 10, **adaptée** : univers des 6 paires, ratio taker calculé sur les bougies 1 j Binance USDT, exécution au prix Kraken EUR ; reconstitution tous les H jours de données au premier cycle après 00:00 UTC. Mentionné « adapté » partout.
- `temoin:aleatoire` : à chaque cycle, avec une graine dérivée du cycle, tire 0 à 2 actions dans la même distribution d'espace d'actions que les LLM (symbole uniforme, côté uniforme parmi les possibles, taille uniforme 1-20 %, stop 2-10 %, mouvement attendu 5-15 %), passe par `riskd`. Hors ligne (au moment de construire le site), 1 000 trajectoires rejouées sur les mêmes cycles et les mêmes quotes donnent la distribution du rendement ; on affiche le rang de chaque LLM.

## 11. Cycle

`arene cycle` (lancé par un timer systemd utilisateur à HH:05 UTC pour HH ∈ {0,4,8,12,16,20}) :
1. Charger config et politique (hash), vérifier le journal (`verify`), refuser de tourner si la chaîne est cassée.
2. Cycle = début de la dernière barre 4 h close + 4 h. Si `cycle_completed` existe déjà pour ce cycle : sortir (idempotence). Si `cycle_started` sans `completed` : reprendre sans réexécuter les intentions déjà vues.
3. Données (barres, quotes), journaliser celles utilisées.
4. Stops et détention maximale.
5. Gel / arrêt / coupe-circuit / dormance.
6. Témoins, puis décideurs LLM en parallèle (délai max), puis `riskd`, puis exécution simulée.
7. Equity de chaque portefeuille, `cycle_completed`.
8. Construction du site, heartbeat externe, alertes.

## 12. Exploitation

- Unités systemd **utilisateur** (`~/.config/systemd/user/`, linger actif) : `arene-cycle.service` + `.timer`, `arene-site.service` (sert `var/site/` sur `127.0.0.1:8787`). Fichiers modèles dans `ops/systemd/`, installation par `scripts/install-user-units.sh` (pas de sudo).
- Heartbeat externe : URL lue dans `~/.config/arene/secrets/healthcheck_url` (Healthchecks.io ou équivalent, compte créé par the owner), pingée à chaque fin de cycle ; `/fail` si le cycle échoue. Le service externe alerte si aucun ping en 4 h 30.
- Alertes : ntfy, URL dans `~/.config/arene/secrets/ntfy_url` (+ `ntfy_token` facultatif). 3 niveaux ; seul `panique` est prioritaire. Absence de secret → alerte écrite dans le journal seulement.
- Coupe-circuit : `arene kill` / `arene unkill` (fichier sentinelle), effet au plus tard au cycle suivant ; `arene kill --now` lance un cycle de mise à plat immédiat.
- Dormance : si `var/ack` (écrit par `arene ack`) a plus de 7 jours, plus aucune entrée ; à 9 jours, mise à plat.
- `docs/RUNBOOK.md` : une page.

## 13. Dashboard (privé)

- Généré par `arene build-site` dans `var/site/` : `index.html`, `modele/<id>.html`, `methode.html`, `data/*.json`. HTML/CSS/JS sans chaîne de build ; graphiques uPlot copié dans `site/vendor/` avec son hash.
- Bandeau permanent **SIMULÉ (paper)**. Champ `venue_mode` obligatoire dans chaque JSON publié, validé par un test.
- Vue d'ensemble : equity des 7 portefeuilles en base 100, rendement net, drawdown max, frais, nombre de trades, coût d'API par modèle, rang dans la distribution aléatoire, mention « non distinguable du hasard » tant que l'écart n'est pas significatif.
- Page modèle : courbe, positions, journal des décisions (justification affichée **24 h après** la décision), rejets de `riskd` par code.
- Page méthode : règles, frais, politique, hash du journal (tête de chaîne), limites honnêtes.

## 14. Critères de passage du MVP

Tests verts ; `verify()` OK ; rejeu = ledger = site au µEUR près ; `riskd` n'accepte aucune violation sur 100 000 intentions générées (hypothesis) ; coupe-circuit effectif en < 1 min avec `--now` ; coupure simulée → alerte externe ; coût réel par décision mesuré.
