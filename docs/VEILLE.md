# Veille continue et réveils sur événement

Décision du propriétaire du 12/11/2026 : « vas-y pour la surveillance continue et les réveils sur événement ». Le rendez-vous fixe de 4 h ne change pas ; deux mécanismes s'y ajoutent.

## 1. Veille : un tick toutes les 5 minutes, sans LLM

`arene veille` est lancé par `arene-veille.timer` toutes les 5 min (`OnCalendar=*:00/5`, avec un décalage de 30 s pour ne pas tomber sur HH:05:00 pile).

1. **Verrou.** Le tick prend `cycle_lock` sans attendre. Si un cycle ou un réveil tourne déjà, il s'arrête sans rien écrire et rend le code 0.
2. **Journal cassé.** Il n'écrit rien et rend le code 1 (le cycle se charge de l'alerte).
3. **Identifiant du tick.** `tick = now // 300 * 300`. Un événement `veille` déjà journalisé pour ce tick fait sortir le tick sans rien écrire (idempotence).
4. **Quotes.** Le tick lit le ticker Kraken des instruments de la config. En cas d'échec, rien n'est écrit et le code de sortie est 1. Après 3 ticks consécutifs en échec, l'alerte `action/veille_data` part, au plus une fois par heure.
5. **Stops en direct.** Pour chaque position qui a un stop, si `bid ≤ stop`, la position est vendue tout de suite.
   - Prix : `market_fill` au bid, avec glissement et frais taker (pessimiste, comme une vente au marché).
   - `order_id` : `stop:{portefeuille}:{symbole}:veille:{tick}`.
   - La vente passe par `SimExecutor._forced_sell` (raison `stop`) ; elle est idempotente par `order_id`.
   - Le contrôle des stops sur les barres de 4 h, au cycle suivant, reste le filet de sécurité (veille arrêtée) : il part des positions rejouées, donc une position déjà vendue n'est pas revendue.
6. **Événement `veille`**, écrit APRÈS les stops et horodaté au tick :

   ```json
   {"tick": 1794500100,
    "quotes": {"BTC/EUR": [bid_ueur, ask_ueur], "...": [0, 0]},
    "equity": {"llm:claude-haiku-5-5": equity_ueur_au_bid, "...": 0},
    "stops": ["stop:llm:...:veille:1794500100"],
    "reveil": null}
   ```

   - `reveil` vaut `null` ou le déclencheur du réveil lancé par ce tick (§2).
   - Taille : environ 288 événements par jour.
   - Le ledger et le site ignorent ce type pour les positions ; le site s'en sert pour l'equity vivante.
   - Les `quote` du cycle ne changent pas : la médiane des spreads du cycle ne lit que les événements `quote`.
7. **Ce que la veille ne fait pas.** Pas de mise à plat sur coupe-circuit (`arene kill --now` le fait déjà). Pas de gel, ni d'arrêt sur drawdown, ni de détention maximale : tout cela reste au cycle et au réveil.

## 2. Réveils sur événement

Un réveil est une ronde de décision hors rendez-vous pour **les portefeuilles LLM et `temoin:aleatoire`**. L'aléatoire est le témoin nul des LLM : il garde le même nombre d'occasions de décider qu'eux. Les témoins de référence (panier, 6040, E0065) restent au rendez-vous de 4 h.

### Déclencheurs, évalués à chaque tick après les stops

- **Mouvement.** Pour au moins un instrument, `|mid_tick / mid_ref − 1| ≥ seuil_mouvement_bp`. `mid_ref` est le milieu du quote de l'événement `veille` de `tick − fenetre_mouvement_s`. Sans cet événement, il n'y a pas de déclencheur de mouvement. Payload : `{"type": "mouvement", "symbole": ..., "variation_bp": ..., "fenetre_s": ...}`. Si plusieurs instruments dépassent le seuil, le plus grand `|variation|` l'emporte.
- **Stop.** La veille vient d'exécuter un stop dans un portefeuille LLM. Payload : `{"type": "stop", "portefeuille": ..., "symbole": ...}`.

### Garde-fous, tous requis

- **Délai depuis la dernière ronde.** Il faut au moins `cooldown_s` depuis la dernière ronde de décision LLM, cycle ou réveil.
- **Plafond par jour.** Au plus `max_reveils_jour` réveils par jour UTC.
- **Avant le cycle.** Aucun réveil à moins de `garde_avant_cycle_s` du prochain rendez-vous.
- **Pendant un cycle.** Aucun réveil si un cycle est en cours ou incomplet (`cycle_started` sans `cycle_completed`).
- **Coupe-circuit et dormance.** Ils n'empêchent pas le réveil ; riskd y refuse les entrées, comme au cycle.

Paramètres dans `config/arene.toml`, table `[veille]` (valeurs par défaut) :

```toml
[veille]
tick_s = 300
seuil_mouvement_bp = 300      # 3 %
fenetre_mouvement_s = 3600    # sur 1 h
cooldown_s = 3600
max_reveils_jour = 6
garde_avant_cycle_s = 1800
```

### Déroulé, dans le même processus et sous le même verrou que le tick

- **Identifiant.** `reveil = tick`, un multiple de 300 qui n'est pas un multiple de `interval_s`. C'est lui qui remplit le champ `cycle` des événements de décision : `decision_received`, `decision_skipped`, `intent`, `risk_verdict`, ordres et fills.
- **Événements.** `reveil_started {"reveil": tick, "declencheur": {...}}`, puis la ronde, puis `reveil_completed {"reveil": tick}`.
- **Reprise.** Un `reveil_started` sans `reveil_completed` est repris par le tick suivant, s'il est dans les 30 min ; sinon il est abandonné avec `reveil_abandonne {"reveil": tick}`. Les décisions déjà reçues ne sont pas redemandées, et l'exécuteur est idempotent par `intent_id` (même mécanique que le cycle).
- **Données.**
  - Les barres de 4 h sont mises à jour. La dernière barre close doit être celle qui se termine à `floor(tick / interval) * interval`, sinon `data_stale`.
  - Les quotes du tick sont journalisées en `quote` avant la décision, exactement comme au cycle.
  - Les marks sont au milieu de ces quotes.
- **Avant de décider.** Résolution des ordres UNKNOWN, gel et arrêt (`_freeze_halt`), puis coupe-circuit et dormance.
- **Pas d'equity.** Aucun événement `equity` au réveil : les séries d'equity, Sharpe et statistiques restent aux rendez-vous de 4 h. L'equity vivante est dans `veille`.
- **Budget.** Le garde-fou de quota quotidien (`daily_budget_usd`) s'applique aux réveils comme aux cycles.

### Instantané donné au modèle

- `SCHEMA_VERSION` passe à `2`.
- Un nouveau champ `"contexte"` est ajouté :
  - au cycle : `{"type": "rendez_vous", "prochain_rendez_vous_ts": ...}` ;
  - au réveil : `{"type": "reveil", "declencheur": {...}, "prochain_rendez_vous_ts": ...}`.
- Le prompt système gagne une phrase. Elle dit que le modèle est appelé au rendez-vous fixe de 4 h et peut être réveillé entre deux rendez-vous quand le marché bouge fortement ou qu'un de ses stops est touché, et que rien ne l'oblige à agir. `prompt_sha256` change donc, et `config_loaded` est journalisé.
- `recent_decisions` inclut les décisions des réveils.

## 3. Le cycle

- **Verrou.** Le cycle attend le verrou jusqu'à 600 s (`LOCK_WAIT_S`), pour ne pas échouer si un réveil se termine.
- **Le reste ne change pas.**
  - `_stops` sur barres reste le filet de sécurité.
  - Les événements `veille`, `reveil_*` et les décisions de réveil ne comptent pas comme cycles.
  - Les compteurs de riskd (trades par 24 h, ordres par minute, frais du mois) les voient, puisqu'ils lisent le journal.

## 4. Ce qui est hors champ

- Les ordres limites et les stops côté plateforme : voir l'étude des agents traders (`docs/ETUDE-AGENTS-TRADERS.md`).
- La mise à plat sur drawdown entre deux cycles.
