# Spécification du ledger perp et du simulateur (étape 2)

Ce document est le contrat de `arene/perp/ledger.py` et `arene/perp/sim.py`. Les scénarios d'or sont calculés à la main **à partir de ce texte**, indépendamment du code.

Références :
- étude : `docs/ETUDE-AGENTS-TRADERS.md` §3 ;
- décisions : `docs/DECISION-OWNER-agents-traders.md` ;
- règle française : `docs/sources/2026-11-12/amf_cfd_2019.txt`, annexe I.

## 1. Unités et arrondis

Tout est en **entiers**, jamais en float.

| Grandeur | Unité |
|---|---|
| collatéral, frais, P&L et funding en euros | µEUR (1 EUR = 10^6) |
| prix des contrats | µUSD (1 USD = 10^6) |
| quantité | 1e-8 d'unité de l'actif de base ; **signée** : > 0 long, < 0 short |
| taux de funding absolu | nano-USD par unité d'actif et par heure (1 USD = 10^9) |
| cours EUR/USD | µUSD par EUR (`fx_bid` ≤ `fx_ask`) |
| taux | points de base (bp, 1/10 000) |

Notations : `ceil(a/b)` et `floor(a/b)` sont les divisions entières arrondies vers le haut et vers le bas (b > 0). `|x|` est la valeur absolue, et `sgn(q)` vaut +1 pour un long, −1 pour un short.

**R1, notionnel.**
- `notional_up(q, p) = ceil(|q| × p / 10^8)` (en µUSD) ;
- `notional_down(q, p) = floor(|q| × p / 10^8)`.

**R2, conversion USD → EUR, toujours défavorable au portefeuille :**
- un montant **à payer** (perte, frais, funding payé, exposition) : `cost_eur(u) = ceil(u × 10^6 / fx_bid)` ;
- un montant **reçu** (gain, funding reçu) : `gain_eur(u) = floor(u × 10^6 / fx_ask)`.

Diviser par le plus petit cours (`fx_bid`) donne plus d'euros, ce qui pénalise un coût. Diviser par le plus grand (`fx_ask`) en donne moins, ce qui pénalise un gain.

**R3, conversion d'un montant signé** (P&L latent ou réalisé) : `to_eur(u) = gain_eur(u)` si u ≥ 0, sinon `−cost_eur(−u)`.

**R4, tick.**
- `tick_up(p) = ceil(p / tick) × tick` ;
- `tick_down(p) = floor(p / tick) × tick`.

## 2. Paramètres (`config/perp.toml`, section `[simulation]`)

| clé | valeur | sens |
|---|---|---|
| `fill_model_version` | `"pessimiste-perp-v1"` | |
| `capital_eur` | 1000 | collatéral initial de chaque portefeuille |
| `taker_fee_bp` | 7 | 0,05 % de Kraken majoré de 25 %, arrondi vers le haut |
| `slippage_bp` | 5 | |
| `liquidation_fee_bp` | 500 | frais ajoutés en cas de clôture sur marge (prudence : Kraken en prendrait 2,5 %) |
| `closeout_margin_bp` | 2500 | clôture si l'equity passe sous 25 % de l'exposition brute (la moitié de la marge de 50 % de la règle AMF) |
| `initial_margin_bp` | 5000 | une entrée doit laisser une equity ≥ 50 % de l'exposition brute (règle AMF : 2:1 sur la crypto) |
| `max_holding_s` | 604800 | 7 jours |

## 3. État d'un portefeuille (`MarginAccount`)

- **`collateral_ueur`**. Au départ, il vaut le capital. Il n'est jamais négatif après un événement.
- **`positions`**, avec au plus une position par instrument. Une position porte :
  - `qty` (signée) et `entry_uusd` (prix d'entrée moyen) ;
  - `opened_ts` ;
  - `open_seq`, le seq du fill d'ouverture, qui l'identifie parmi les réouvertures ;
  - `stop_uusd` et `take_profit_uusd`, éventuellement nuls, chacun avec le ts de l'ordre qui l'a posé (`stop_armed_ts`, `take_profit_armed_ts`).
- **Historique des quantités** de chaque instrument : la liste des couples (ts du fill, quantité après le fill), qui sert au funding.
- **Cumuls** :
  - `fees_paid_ueur` ;
  - `funding_paid_ueur` (signé, > 0 = payé) ;
  - `realized_pnl_ueur` (P&L de prix seulement) ;
  - `absorbed_deficit_ueur` ;
  - le nombre d'heures sans taux publié (`missing_funding`).
- **Drapeaux** : `frozen_until_ts`, `halted`.

**Invariant :**

    collateral = capital + realized_pnl − fees_paid − funding_paid + absorbed_deficit

**Solde négatif.** Si un événement laisse `collateral < 0`, alors `absorbed_deficit += −collateral` et `collateral = 0`. C'est la protection contre le solde négatif.

## 4. Événements du journal de la ligue (`var-perp/journal/events.jsonl`)

Le journal est le même code que le journal spot, `arene.journal.Journal` : chaîné, sans float. Le ledger se reconstruit uniquement à partir de ces événements, dans l'ordre des `seq`.

**Il refuse :**
- un `order_id` déjà vu ;
- un funding déjà réglé pour (portefeuille, instrument, stamp) ;
- un résumé de clôture ou une mesure d'equity en double ;
- un fill dont le ts est **antérieur** au fill précédent du portefeuille, ou à un stamp de funding déjà réglé sur cet instrument.

Le simulateur valide chaque événement auprès du ledger **avant** de l'écrire : un événement refusé n'atteint jamais le journal.

### `portfolio_opened`

`{portfolio, kind, league: "perp", capital_ueur, venue_mode: "paper"}`

### `perp_fill`

`{order_id, portfolio, instrument, qty, price_uusd, fee_ueur, fx_bid, fx_ask, reason, fill_model_version, ts}`

- **`qty` est la variation signée** : > 0 achète, < 0 vend.
- **`reason`** vaut `intent`, `stop`, `take_profit`, `margin_closeout`, `max_holding`, `halt` ou `kill_switch`.

Application par le ledger (position avant le fill : `q`, `e` ; variation `d` au prix `p`) :

1. **Ouverture ou augmentation** : pas de position, ou `sgn(d) = sgn(q)`.
   - Nouvelle quantité : `q + d`.
   - Prix moyen :
     - long : `ceil((|q|×e + |d|×p) / (|q|+|d|))` ;
     - short : `floor(...)` de la même expression.
   - Défavorable dans les deux cas.
   - `opened_ts` et `open_seq` sont ceux du fill d'ouverture, et ne changent pas lors d'une augmentation.
2. **Réduction ou fermeture** : `sgn(d) ≠ sgn(q)` et `|d| ≤ |q|`.
   - P&L réalisé : `r = floor(sgn(q) × (p − e) × |d| / 10^8)` en µUSD, soit une division entière vers −∞.
   - Converti par R3, il s'ajoute à `realized_pnl` et au collatéral.
   - Si `|d| = |q|`, la position et ses ordres conditionnels disparaissent.
3. **Retournement** (`|d| > |q|` de sens opposé) : **refusé**. Il faut une fermeture, puis une ouverture.
4. **Frais** : `fee_ueur` est retiré du collatéral et ajouté à `fees_paid`. Le ledger refuse un frais négatif.
5. **Historique** : le couple (ts, quantité après le fill) s'ajoute à l'historique de l'instrument.
6. **Solde négatif** : règle du §3.

### `conditional_order`

`{portfolio, instrument, kind: "stop" | "take_profit", price_uusd | null, ts}`

- Pose, modifie ou annule (`null`) le stop ou l'objectif d'une position **existante**.
- Le prix doit être un entier > 0.
- Le `ts` de l'événement devient le moment où l'ordre est armé.

### `funding`

`{portfolio, instrument, stamp, qty_seconds, rate_nusd, fx_bid, fx_ask, amount_ueur}`

- **`stamp`** = H, une heure ronde. Le taux horodaté H par Kraken paie l'heure [H − 1 h, H).
- **`qty_seconds`** est l'intégrale de la quantité signée sur [H − 1 h, H), calculée sur l'historique du §3 :
  - pour chaque intervalle entre deux fills, la quantité tenue × la durée en secondes ;
  - une position ouverte ou fermée pendant l'heure ne paie donc que le temps où elle a été tenue.
  - Le ledger la recalcule et refuse un désaccord, ou une heure où aucune position n'a été tenue.
- **Montant payé**, en µUSD : `m = qty_seconds × rate_nusd / (10^8 × 10^3 × 3600)`. S'il est positif, il est payé : un long paie quand le taux est positif, un short paie quand il est négatif. Arrondis :
  - payé : `ceil(m)` µUSD, puis `cost_eur` ;
  - reçu : `floor(−m)` µUSD, puis `gain_eur`, compté négatif.
- **`amount_ueur`** (> 0 = payé) est recalculé par le ledger, qui refuse un désaccord.
- Effet : `collateral −= amount_ueur` et `funding_paid += amount_ueur`, puis la règle du solde négatif.
- **Une seule fois** par (portefeuille, instrument, stamp), et toujours dans l'ordre croissant des stamps.
- Un fill postérieur ne peut plus tomber dans une heure déjà réglée.
- Le règlement peut se faire en retard : `qty_seconds` vient de l'historique, pas de la position au moment du règlement.

### `funding_missing`

`{portfolio, instrument, stamp, qty_seconds}`

Une heure tenue pour laquelle Kraken n'a publié aucun taux.
- Rien n'est prélevé, mais l'heure est comptée.
- Elle compte aussi comme réglée : on ne peut plus la payer ensuite.

### `margin_closeout`

`{portfolio, minute, equity_ueur, threshold_ueur, gross_ueur, order_ids, resumed_after_crash}`

Résumé écrit **après** les `perp_fill` de raison `margin_closeout`, une seule fois par (portefeuille, minute).

### `minute_incomplete`

`{portfolio, minute, instruments}`

Une minute traitée sans la bougie d'un ou plusieurs instruments détenus (voir §5).

### `perp_equity`

`{portfolio, ts, collateral_ueur, unrealized_ueur, equity_ueur, gross_ueur, marks, fx_bid, fx_ask}`

Mesure écrite par le simulateur, une seule fois par (portefeuille, ts). Elle sert au pic d'equity et aux statistiques.

## 5. Simulateur (`pessimiste-perp-v1`)

### Ordre au marché sur un quote (bid, ask)

- **Prix :**
  - achat (`d > 0`) : `tick_up(ceil(ask × (10000 + slippage_bp) / 10000))` ;
  - vente (`d < 0`) : `tick_down(floor(bid × (10000 − slippage_bp) / 10000))`.
- **Frais :** `fee_uusd = ceil(notional_up(d, prix) × taker_fee_bp / 10000)`, puis `fee_ueur = cost_eur(fee_uusd)`.
  - Pour tout fill, stop, objectif et clôture compris, le notionnel des frais est pris **au prix d'exécution**.
- **Entrée** (raison `intent`, qui ouvre ou augmente une position) : elle est **refusée** dans quatre cas.
  - le portefeuille est arrêté ;
  - il est gelé (`ts < frozen_until_ts`) ;
  - il n'a plus de collatéral ;
  - **la marge initiale n'est pas couverte après l'ordre**, c'est-à-dire `equity × 10000 < initial_margin_bp × exposition brute`.
    - Ce calcul se fait sur l'état après le fill, frais compris.
    - L'instrument traité est valorisé au milieu du quote, et les autres au mark fourni par l'appelant.
    - Sans mark pour un instrument détenu, l'ordre est refusé.
- **Réductions et fermetures** : elles passent toujours.
- **Identifiant déjà utilisé :**
  - même portefeuille, instrument et quantité : rien n'est fait ;
  - autre demande : erreur.

### Valorisation

- **P&L latent** d'une position au mark `m` : `u = floor(sgn(q) × (m − e) × |q| / 10^8)` µUSD, converti par R3 **position par position**.
- **Equity** = collatéral + Σ des latents convertis.
- **Exposition brute** (EUR) = Σ `cost_eur(notional_up(q, m))`.

### Traitement d'une minute M (de M à M + 59 s)

Les minutes se traitent dans l'ordre chronologique, avec la bougie **mark** (et la bougie **trade** si elle existe) de chaque instrument détenu.

**Horodatage.** Les fills d'une minute sont horodatés **à sa fin**, `M + 59`, ou au dernier fill du portefeuille s'il est plus tard. Une minute ne peut donc pas être traitée après un fill plus récent : il faut traiter les minutes avant de passer de nouveaux ordres.

On applique trois étapes **dans cet ordre**.

1. **Clôture sur marge, sur le compte entier**, toutes positions comprises, même celles ouvertes pendant la minute (pessimiste).
   - Pire mark de la minute : `mark.low` pour un long, `mark.high` pour un short. Les pires cas de tous les instruments sont supposés simultanés.
   - On calcule l'equity et l'exposition brute à ces pires marks.
   - Si `equity × 10000 < closeout_margin_bp × exposition`, **toutes** les positions sont fermées :
     - prix, sur la bougie mark : vente à `tick_down(floor(mark.low × (10000 − slippage_bp)/10000))`, rachat à `tick_up(ceil(mark.high × (10000 + slippage_bp)/10000))` ;
     - au moins un tick ;
     - frais : `ceil(notional_up(q, prix) × (taker_fee_bp + liquidation_fee_bp) / 10000)`, convertis par `cost_eur`.
   - Puis l'événement `margin_closeout`. Le reste de la minute est ignoré pour ce portefeuille.
   - **Reprise après un crash :** si une clôture de cette minute est commencée (un fill `margin_closeout` existe sans son résumé), elle est **terminée** sans retester la marge. La décision est durable.
2. **Stops**, armés **avant la fin** de la minute (`stop_armed_ts < M + 60`). Un stop posé pendant la minute s'applique donc à toute la minute (pessimiste).
   - **Long de stop `s`** : déclenché si `mark.low ≤ s`.
     - Base : `min(s, trade.open)`, ou `mark.open` sans bougie trade.
     - Prix : `tick_down(floor(base × (10000 − slippage_bp)/10000))`.
   - **Short de stop `s`** : déclenché si `mark.high ≥ s`.
     - Base : `max(s, trade.open)`, ou `mark.open` sans bougie trade.
     - Prix : `tick_up(ceil(base × (10000 + slippage_bp)/10000))`.
   - Un prix nul devient un tick, et c'est signalé.
   - Fermeture complète, au tarif taker. Raison `stop`.
3. **Objectifs** des positions encore ouvertes, armés **et** ouverts au plus tard au début de la minute (`max(take_profit_armed_ts, opened_ts) ≤ M`). Un ordre limite ne peut pas profiter d'un prix antérieur à son existence.
   - **Long d'objectif `t`** : exécuté si `trade.high ≥ t + tick`, au prix `t`, sans glissement.
   - **Short d'objectif `t`** : exécuté si `trade.low ≤ t − tick`, au prix `t`.
   - Sans bougie trade, pas d'objectif. Fermeture complète, au tarif taker. Raison `take_profit`.

**Glissement de sortie.** L'appelant peut ajouter, par instrument, un glissement supplémentaire aux stops et aux clôtures : le pire demi-spread des 7 derniers jours, relevé par la veille. C'est l'optimisme résiduel R4 de l'étude.

**Bougie manquante** pour un instrument détenu :
- l'événement `minute_incomplete` est écrit ;
- son stop et son objectif ne sont pas évalués ;
- la clôture sur marge le valorise à son dernier mark connu, fourni par l'appelant. Sans ce mark, elle n'est pas testée, et c'est signalé.

**Isolement.** L'erreur d'un portefeuille n'empêche pas le traitement des autres.

### Taux de change, détention maximale, identifiants

- **EUR/USD.** Le taux utilisé est celui du dernier relevé à la minute ou avant. Il est écrit dans chaque événement.
- **Détention maximale.** Quand `ts − opened_ts ≥ max_holding_s`, la position est fermée au quote courant, comme un ordre au marché. Raison `max_holding`.
- **Mise à plat** (`halt`, `kill_switch`) : toutes les positions au marché. Sans quote pour un instrument détenu, c'est une erreur, jamais une absence silencieuse.
- **Identifiants**, qui portent l'identité de la position (`open_seq`) :
  - stop : `stop:<portefeuille>:<instrument>:<open_seq>:<minute>` ;
  - objectif : `take_profit:<portefeuille>:<instrument>:<open_seq>:<minute>` ;
  - clôture : `margin_closeout:<portefeuille>:<instrument>:<open_seq>:<minute>` ;
  - détention : `max_holding:<portefeuille>:<instrument>:<open_seq>` ;
  - mise à plat : `<raison>:<portefeuille>:<instrument>:<open_seq>`.
- **Écritures.** Elles se font sous un verrou exclusif (`<journal>.sim.lock`) : le contrôle d'idempotence et l'écriture sont atomiques.
