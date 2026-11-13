# Ligue dérivés : alertes et ordres d'entrée posés par les agents

Spec du 13/11/2026. Décision du propriétaire du 13/11 (« 1 et 2 ») : les réveils LLM tout de suite (fait), et des alertes et ordres d'entrée que chaque agent pose lui-même, gérés par la veille entre les rondes, sans appel LLM. Hors du gel de la Saison 1 : le spot n'est pas touché.

## 1. Ce que l'agent peut laisser à chaque ronde

La sortie structurée gagne deux champs **facultatifs** :

- `alerts` : au plus 3 alertes de prix. Une alerte réveille son propriétaire, et lui seul, quand le mark franchit un niveau.
  `{"instrument", "condition": "above"|"below", "price_usd", "note" (≤ 120 car., facultatif), "expires_h" (1-24, facultatif, 4 par défaut)}`
- `entry_orders` : au plus 3 ordres conditionnels d'entrée. Quand le mark franchit le niveau, la veille soumet l'entrée au garde-fou puis l'exécute, sans appeler le modèle.
  `{"instrument", "side": "long"|"short", "condition": "above"|"below", "price_usd", "size_pct", "stop_pct", "take_profit_pct"?, "horizon_h"?, "expected_move_pct"?, "confidence_pct"?, "invalidation"?, "expires_h"?}`
  Mêmes bornes que les actions d'ouverture (`BOUNDS`, horizon 1-168) ; `size_pct`, `stop_pct`, `horizon_h` et `expected_move_pct` obligatoires (sans les deux derniers, le garde-fou refuserait toujours). Un nombre envoyé en texte est rejeté.

**Chaque décision valide remplace l'ensemble.** Tous les éléments encore en attente de l'ensemble précédent sont terminés (`replaced`) ; un élément repris à l'identique devient un nouvel élément du nouvel ensemble. Une décision absente ou invalide (échec, délai, ronde sautée) ne touche à rien : ce qui est posé court jusqu'à son expiration.

**Validation à la création**, élément par élément (un élément invalide est rejeté et noté, les autres restent), sur le marché **au moment où la décision est appliquée** (la vue relue après l'appel), et les éléments comptent à partir de ce moment (`created_ts`) : un niveau franchi pendant la réflexion du modèle est rejeté comme déjà franchi.
- le niveau est à au plus 25 % du mark de l'instantané ;
- le niveau n'est pas déjà franchi : `above` exige un niveau au-dessus du mark, `below` en dessous. Sinon, une entrée immédiate contournerait la ronde ;
- un ordre d'entrée `long` + `above` est un achat sur cassure, `long` + `below` un achat sur repli : les deux sont permis.

L'identifiant de chaque élément est un sha256 de (portefeuille, ronde, type, rang, contenu), comme les intents.

## 2. Ce que fait la veille

À chaque tick, une fois les minutes traitées (avant `_controls` et `_rounds`), **même si la vue de marché est périmée** : les minutes traitées ne sont jamais réexaminées par le tick suivant. Le balayage part de la dernière minute du dernier `perp_tick` (pas d'un `perp_checkpoint`) : un tick tué en plein rattrapage rebalaie ses minutes, et un franchissement déjà journalisé ne l'est jamais deux fois. Chaque étape, et chaque franchissement, a son propre garde-fou d'erreur.

1. **Reprise** (vue fraîche seulement) : les ordres d'entrée déclenchés et pas encore résolus (points 6 et 7).
2. **Arrêt :** un portefeuille arrêté voit tous ses éléments terminés (`portfolio_halted`), avant tout franchissement.
3. **Franchissement**, sur les bougies mark 1 min closes nouvellement traitées, dans l'ordre : `below` est franchi quand le plus bas ≤ niveau, `above` quand le plus haut ≥ niveau. Seules comptent les minutes qui commencent à partir de la création et avant l'échéance, même si le tick qui les voit vient après l'échéance.
4. **Expiration :** un élément dont `expires_ts` est passé est expiré (`expired`).
5. **Alerte franchie :** `agent_alert_triggered`. Elle est consommée (une alerte ne sert qu'une fois).
6. **Ordre d'entrée franchi :**
   - `agent_entry_triggered`, puis, avec une vue fraîche (sinon au premier tick frais), si la minute du franchissement a moins de 15 min (`ENTRY_MAX_LAG_S`) : un `PerpIntent` `open_long`/`open_short` avec les champs de l'ordre et `intent_id` = id de l'ordre, jugé par `evaluate_perp` sur la vue fraîche et les compteurs du moment (levier, stop obligatoire, tailles, gel, coupe-circuit) ; `perp_verdict` ; s'il est approuvé, exécution par `_execute` d'`agent_round` (ordre au marché au prix du moment, glissement et frais, puis stop et objectif ; fermeture si le stop ne peut pas être posé) ;
   - si la minute est plus vieille (rattrapage après une coupure) : `perp_execution` `not_executed_stale_trigger`, jamais exécuté en retard.
   - L'ordre est consommé dans tous les cas. Un refus est rendu à l'agent à sa ronde suivante.
7. **Idempotence après un crash :** un ordre déclenché sans `perp_verdict` est jugé au tick suivant (ou noté `not_executed_stale_trigger` s'il a dépassé 15 min) ; un verdict approuvé sans `perp_fill` est rejugé sur la vue fraîche puis exécuté (`not_executed_refused_on_resume` si le garde-fou refuse désormais), l'ordre au marché étant idempotent par son id ; un `perp_fill` sans `perp_execution` n'est jamais rejoué : si le stop manque, la position est fermée (`closed_without_stop`). Rien n'est exécuté deux fois, et aucune position ne reste sans stop.

## 3. Le réveil privé

Une alerte franchie demande une **ronde `alert`** pour son seul propriétaire :
- `perp_round` `{round, kind: "alert", portfolios: [<propriétaire>], trigger: {alert_id, instrument, condition, price_usd, note}, ts}` ;
- seul ce portefeuille LLM joue. Ni les témoins ni les autres modèles ne jouent, et rien ne leur est montré ;
- **limites :** 1 h depuis la dernière ronde de ce portefeuille, 4 rondes `alert` au plus par portefeuille et par jour UTC, aucune dans les 30 min avant un rendez-vous ni près d'un cycle spot (`near_spot_cycle`), budget du jour (D7) comme toute ronde. Une alerte franchie qui attend plus d'1 h n'est plus servie par un réveil ;
- une seule ronde par tick : un rendez-vous ou un réveil de marché passent avant ; une ronde `alert` attend alors le tick suivant ;
- **toute ronde jouée par le propriétaire sert** ses alertes franchies en attente : elles figurent dans son instantané ;
- les rondes `alert` ne comptent ni dans le délai ni dans le plafond des réveils de marché (qui restent communs à tous).

## 4. Confidentialité

Aucun agent ne voit les niveaux, les déclenchements ni les rondes `alert` d'un rival :
- l'instantané et `round.json` ne contiennent que les éléments du portefeuille appelé ;
- les outils MCP (`historique` compris) ne lisent que les événements du portefeuille appelé ;
- le déclencheur d'un réveil de marché reste un mouvement de marché, jamais l'alerte de quelqu'un.

Le site public peut tout afficher : les modèles ne le lisent pas.

## 5. Ce que l'agent voit à la ronde suivante

Dans l'instantané, sous `compte` :
- `alertes_en_attente` et `ordres_d_entree_en_attente` : ses éléments en cours, avec niveau, échéance (heure UTC) et ce qu'il a écrit ;
- `depuis_ta_derniere_ronde` : ses alertes déclenchées, ses ordres déclenchés (avec le verdict, les raisons de refus et le prix de remplissage), ses éléments expirés, et ses éléments rejetés à la création.

La consigne (v4) décrit les deux champs en quelques lignes, sans pousser à trader : ne rien poser est une décision valide.

## 6. Événements (journal `var-perp`)

| Type | Payload |
|---|---|
| `agent_orders_set` | `portfolio, round, alerts[], entry_orders[], rejected[] {kind, k, error}` (les éléments remplacés ont chacun leur `agent_order_ended`) ; chaque alerte `{id, instrument, condition, price_uusd, note, expires_ts}`, chaque ordre `{id, instrument, side, condition, price_uusd, size_bp, stop_bp, take_profit_bp, horizon_h, expected_move_bp, confidence_pct, invalidation, expires_ts}` |
| `agent_alert_triggered` | `portfolio, id, instrument, condition, price_uusd, minute, mark_high_uusd, mark_low_uusd` |
| `agent_entry_triggered` | `portfolio, id, instrument, side, condition, price_uusd, minute, mark_high_uusd, mark_low_uusd` |
| `agent_order_ended` | `portfolio, id, kind (alert|entry), reason (expired|replaced|portfolio_halted)` |
| `perp_round` | `kind: "alert"`, `portfolios: [nom]` en plus |
| `perp_verdict`, `perp_execution`, `perp_fill`, `conditional_order` | inchangés ; `intent_id` = id de l'ordre d'entrée |

`agent_orders_set` n'est écrit que si la décision est valide. L'état en attente se recalcule depuis le journal : dernier `agent_orders_set` du portefeuille, moins les éléments déclenchés ou terminés depuis.
