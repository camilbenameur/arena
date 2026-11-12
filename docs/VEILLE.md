# Veille continue et réveils sur événement

Décision du propriétaire du 12/11/2026 : « vas-y pour la surveillance continue et les réveils sur événement ». Le rendez-vous fixe de 4 h ne change pas ; deux mécanismes s'y ajoutent.

## 1. Veille : un tick toutes les 5 minutes, sans LLM

`arene veille` est lancé par `arene-veille.timer` toutes les 5 min (`OnCalendar=*-*-* *:00/5:30 UTC`, décalage de 30 s pour ne pas tomber sur HH:05:00 pile).

1. **Verrou.** Le tick prend `cycle_lock` sans attendre. Si un cycle ou un réveil tourne déjà, il s'arrête sans rien écrire et rend le code 0.
2. **Journal cassé.** Il n'écrit rien dans le journal et rend le code 1. Une alerte `panique` (ntfy seulement) part au plus une fois par heure (état dans `var/veille_journal_casse`). Le cycle alerte aussi.
3. **Avant le premier cycle.** Statut `inactive`, rien n'est écrit : c'est le cycle qui ouvre le journal.
4. **Identifiant du tick.** `tick = now // 300 * 300`. Un événement `veille` déjà journalisé pour ce tick fait sortir le tick sans rien écrire (idempotence).
5. **Quotes, contrôlés symbole par symbole.** Le tick lit le ticker Kraken des instruments de la config. Règle, par symbole :
   - **`invalide`** (bid <= 0, ask < bid, valeur non entière ou non finie, erreur de lecture) : toujours rejeté, jamais journalisé dans `quotes_bruts`.
   - **`spread`** : spread > 5 fois la médiane des 20 derniers spreads **bruts** du symbole (au moins 5), c'est-à-dire ceux de `quotes_bruts` des événements `veille`, rejetés compris, pour que la médiane suive le régime.
   - **`saut`** : milieu à 15 % ou plus du milieu du dernier quote accepté de ce symbole s'il a moins de 30 min ; sinon (historique périmé ou absent) de la dernière clôture de 4 h du store de barres, avec la même tolérance.
   - **Confirmation de rupture.** Un quote rejeté pour `spread` ou `saut` est ACCEPTÉ si le tick précédent de ce symbole (à moins de 10 min) a lui aussi été rejeté pour `spread` ou `saut`, ou accepté par confirmation, et si les deux milieux bruts sont à moins de 2 % l'un de l'autre. Deux ticks cohérents ne sont plus un artefact. Le quote accepté devient la nouvelle référence du `saut` ; le symbole figure alors dans `confirmes`. L'acceptation en chaîne est plafonnée à 6 ticks consécutifs (30 min) : au-delà, le symbole est rejeté (`veille_symbole_ecarte` part au 3e rejet consécutif et l'equity reste au dernier quote accepté) tant que la médiane brute n'a pas rattrapé le nouveau régime. Exemple : un krach stable de -20 % est rejeté au 1er tick et accepté au 2e, où le stop part.
   - Un quote rejeté n'a ni stop ni déclencheur de mouvement ; l'equity le valorise à son dernier quote accepté.
   - Le tick n'est en échec que si aucun symbole n'a de quote exploitable (tous `invalide`) : rien n'est écrit et le code de sortie est 1. Si tous sont seulement rejetés (`spread`, `saut`), le tick est écrit (`quotes` vide, `quotes_bruts` plein) : sans cela la confirmation n'aurait jamais de tick précédent.
   - **Alertes.** `action/veille_symbole_ecarte` après 3 rejets consécutifs d'un même symbole (une fois par épisode), puis `info/veille_symbole_ecarte` quand il est de nouveau accepté.
   - Le nombre de ticks consécutifs en échec est dans `var/veille_echecs` (hors journal). L'alerte `action/veille_data` part une fois, au troisième échec consécutif (début de la panne) ; rien ensuite ; au premier tick réussi, une alerte `info/veille_data` « rétabli » et le fichier disparaît.
6. **Transactions et stops en direct.** Les stops et le mouvement se jugent sur les **transactions réelles**, jamais sur le ticker : à chaque tick, pour chaque symbole, le client Kraken lit l'OHLC à `interval=1` (bougies d'une minute, `since` = tick - 66 min). Seules les bougies closes au tick comptent (`ts + 60 <= tick`). Si la lecture échoue (ou ne renvoie rien) pour un symbole, ni stop ni déclencheur sur ce symbole à ce tick : le filet de barres du cycle reste en place et le tick l'indique dans `rejets` (`"ohlc"`, en plus de ses éventuels rejets de quote : un symbole dont le ticker est accepté garde son quote).
   - **Condition.** Une position qui a un stop est vendue si, parmi les bougies 1 min closes depuis `max(tick - 600, ouverture de la position)`, **au moins 2 bougies distinctes** ont un plus bas `<= stop`. Une bougie aberrante isolée ne suffit pas : on attend le tick suivant. Il n'y a plus de confirmation sur deux ticks : les transactions sont la confirmation.
   - **Prix.** Clôture de la dernière bougie 1 min close x (1 - glissement), arrondie au tick vers le bas, **jamais au-dessus du stop**, avec les frais taker (calculés sur le prix final). Un prix calculé `<= 0` est ignoré.
   - `order_id` : `stop:{portefeuille}:{symbole}:veille:{tick}` ; la vente passe par `SimExecutor._forced_sell` (raison `stop`, ts = tick), idempotente par `order_id`. Tout fill (`_forced_sell`) dont le prix ou la quantité est `<= 0` lève avant d'écrire.
   - Le contrôle des stops sur les barres de 4 h, au cycle suivant, reste le filet de sécurité : il part des positions rejouées, une position déjà vendue n'est pas revendue.
   - Un stop de veille ne réveille personne (voir §2).
   - **Le ticker** ne sert plus qu'à valoriser `veille.equity` (règle d'acceptation du point 5, inchangée) et aux `quote_reveil` d'exécution des intentions.
7. **Événement `veille`**, écrit APRÈS les stops (et après `reveil_started` s'il y a un réveil), horodaté au tick :

   ```json
   {"tick": 1794500100,
    "quotes": {"BTC/EUR": [bid_ueur, ask_ueur], "...": [0, 0]},
    "quotes_bruts": {"BTC/EUR": [bid_ueur, ask_ueur], "ETH/EUR": [bid_ueur, ask_ueur], "...": [0, 0]},
    "rejets": {"ETH/EUR": "saut", "XRP/EUR": "ohlc"},
    "confirmes": [],
    "variations_bp": {"BTC/EUR": 120, "...": 0},
    "clotures_1m": {"BTC/EUR": clôture_ueur_de_la_dernière_bougie_1_min_close, "...": 0},
    "equity": {"llm:claude-haiku-5-5": equity_ueur_au_bid, "...": 0},
    "stops": ["stop:llm:...:veille:1794500100"],
    "reveil": null,
    "refus": null}
   ```

   - `quotes` : les quotes acceptés. `quotes_bruts` : bid et ask de TOUS les symboles reçus, rejetés compris, hors `invalide`. `rejets` : `{symbole: motif}` des quotes écartés (`{}` sinon). `confirmes` : les symboles acceptés par confirmation de rupture. `variations_bp` : par symbole, la variation du tick courant mesurée sur les bougies 1 min (bp signés), pour les symboles dont la lecture OHLC a réussi. `clotures_1m` : la clôture de la dernière bougie 1 min close, par symbole (base de PRICE_SANITY au réveil). `rejets` peut contenir `"ohlc"` (lecture des bougies en échec).
   - `reveil` : le déclencheur du réveil effectivement démarré par ce tick (§2), sinon `null`. `refus` : le motif du garde-fou qui a refusé un déclencheur (`delai`, `plafond`, `avant_cycle`, `cycle_incomplet`, `cycle`), sinon `null`.
   - Taille : environ 288 événements par jour.
   - Le ledger ignore ce type ; le site s'en sert pour l'equity vivante.
   - Les `quote` du cycle ne changent pas : la médiane des spreads du cycle ne lit que les événements `quote`.
8. **Ce que la veille ne fait pas.** Pas de mise à plat sur coupe-circuit (`arene kill --now` le fait déjà). Pas de gel, ni d'arrêt sur drawdown, ni de détention maximale : tout cela reste au cycle et au réveil.

## 2. Réveils sur événement

Un réveil est une ronde de décision hors rendez-vous pour **tous les portefeuilles LLM de la config et `temoin:aleatoire`**. L'aléatoire est le témoin nul des LLM : il garde le même nombre d'occasions de décider qu'eux. Les témoins de référence (panier, 6040, E0065) restent au rendez-vous de 4 h.

### Déclencheur : le mouvement, et lui seul

Mesuré sur les **transactions** (bougies Kraken 1 min closes, le ticker n'intervient plus). Variation d'un instrument à un tick T = clôture de la dernière bougie 1 min close / clôture de la bougie 1 min la plus proche de `T - fenetre_mouvement_s` (à 2 min près, lue dans le même appel OHLC) - 1. Le déclencheur exige `|variation| >= seuil_mouvement_bp` **au tick courant ET au tick précédent (T - tick_s), dans le même sens**. Le tick précédent est rejugé avec ses propres bougies (même appel). Sans bougie de référence, ou sans bougie close de moins de 15 min, il n'y a pas de mesure ni de déclencheur ; un symbole dont la lecture OHLC échoue n'en a pas non plus.
- Payload : `{"type": "mouvement", "symbole": ..., "variation_bp": ..., "fenetre_s": ...}` (`variation_bp` signé, du tick courant). Si plusieurs instruments dépassent le seuil, le plus grand `|variation|` l'emporte. La variation mesurée de chaque symbole est dans `veille.variations_bp`.
- Il n'y a **plus de déclencheur « stop »** : il exposait la position d'un rival et laissait un seul modèle consommer le plafond de tous. Un stop touché est exécuté par la veille, point.

### Garde-fous, tous requis

Évalués dans cet ordre ; le premier qui refuse donne le motif de `veille.refus`.
- `cycle_incomplet` : un cycle est en cours ou incomplet (`cycle_started` sans `cycle_completed`, plus récent que le dernier terminé).
- `cycle` : le tick est un multiple de `interval_s` (l'identifiant du réveil se confondrait avec celui d'un cycle).
- `delai` : il faut au moins `cooldown_s` depuis la dernière ronde de décision LLM : le plus récent des `cycle_completed`, `reveil_started`, `reveil_completed` et `reveil_abandonne` (heure du mur).
- `plafond` : au plus `max_reveils_jour` réveils par jour UTC ; les réveils démarrés comptent, abandonnés compris.
- `avant_cycle` : aucun réveil à moins de `garde_avant_cycle_s` du prochain rendez-vous (l'exécution du prochain cycle, HH:05 UTC).
- Coupe-circuit et dormance n'empêchent pas le réveil ; riskd y refuse les entrées, comme au cycle.

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

- **Identifiant.** `reveil = tick`, un multiple de 300 qui n'est pas un multiple de `interval_s`. Il remplit le champ `cycle` de `decision_requested`, `decision_received`, `decision_skipped` et `intent`.
- **Le réveil est consigné d'abord.** `reveil_started {"reveil": tick, "declencheur": {...}}` est écrit AVANT l'événement `veille` et avant tout appel réseau du réveil ; puis `veille`, puis la ronde, puis `reveil_completed {"reveil": tick}`.
- **Reprise.** Un `reveil_started` sans `reveil_completed` est repris par les ticks suivants, tant qu'il date de 30 min au plus ET qu'aucun `cycle_completed` n'a été journalisé après lui. Les décisions déjà reçues ne sont pas redemandées, l'exécuteur est idempotent par `intent_id`. Les quotes viennent du tick d'origine : les `quote_reveil` déjà écrits pour ce réveil sont relus sans être réécrits, et les manquants (crash pendant l'écriture) sont complétés à partir des quotes acceptés de l'événement `veille` du tick d'origine ; les quotes du tick de reprise ne servent jamais (tous les modèles d'une ronde voient les mêmes quotes). Un symbole encore sans quote n'est jamais ignoré en silence : chaque intention qui le vise reçoit un `risk_verdict` rejeté `NO_QUOTE` et un ordre `RISK_REJECTED` (même règle au cycle). Une seule alerte par réveil et par code (`[réveil N]` dans le message). Un tick qui reprend un réveil ne lance pas de nouveau réveil (`veille.reveil` vaut `null`).
- **Abandon.** Sinon le réveil est abandonné : la ronde est d'abord réparée (un fill sans `stop_set` reçoit son stop depuis l'intention, via `_repair` de l'exécuteur ; les ordres SUBMITTING ou ACKED passent UNKNOWN puis CANCELED), puis `reveil_abandonne {"reveil": tick}` est écrit.
- **Données.**
  - Les barres de 4 h sont mises à jour. La dernière barre close doit être celle qui se termine à `floor(tick / interval) * interval`, sinon `data_stale`.
  - Les quotes acceptés du tick sont journalisés en **`quote_reveil`** (même payload que `quote`) avant la décision. Ils ne faussent ni la médiane des spreads du cycle (`_view` ne lit que `quote`) ni le site. Un symbole écarté n'est pas négociable au réveil ; ses positions sont valorisées à leur dernier quote accepté.
  - Les marks sont au milieu de ces quotes.
  - **PRICE_SANITY** : la « dernière clôture » donnée à riskd est la clôture de la dernière bougie 1 min close (`veille.clotures_1m` du tick du réveil), et non la clôture de 4 h (sinon un mouvement de plus de 3 % rendrait tout achat impossible) ni le ticker (un ticker erroné bloque ainsi les entrées). Au cycle, rien ne change.
- **Avant de décider.** Résolution des ordres UNKNOWN, gel et arrêt (`_freeze_halt`), puis coupe-circuit et dormance.
- **Coupe-circuit relu.** `killswitch.active_sources` est relu juste avant l'exécution de chaque intention, au réveil comme au cycle : un KILL armé pendant l'appel LLM bloque l'achat.
- **Pas d'equity.** Aucun événement `equity` au réveil : les séries d'equity, Sharpe et statistiques restent aux rendez-vous de 4 h. L'equity vivante est dans `veille`.
- **Budget.** Le garde-fou de quota quotidien (`daily_budget_usd`) s'applique aux réveils comme aux cycles.
- **Site.** Le processus de veille ne reconstruit plus le site. `systemctl start --no-block` d'un oneshot déjà actif n'enchaîne pas une seconde construction : un réveil terminé pendant une construction n'en déclenche pas de nouvelle (le site est rattrapé au réveil ou au cycle suivant). Après un réveil terminé, `arene veille` lance `systemctl --user start --no-block arene-site-build.service` (oneshot, `arene build-site`) ; un échec du lancement est ignoré et écrit dans les logs du processus, pas dans le journal. `--no-site` supprime ce lancement.

### Instantané donné au modèle

- `SCHEMA_VERSION` passe à `2`.
- Un nouveau champ `"contexte"` :
  - au cycle : `{"type": "rendez_vous", "prochain_rendez_vous_ts": ...}` ;
  - au réveil : `{"type": "reveil", "declencheur": {...}, "prochain_rendez_vous_ts": ...}`.
  - `prochain_rendez_vous_ts` est l'exécution du prochain cycle (HH:05 UTC) ; `smoke_snapshot` utilise la même valeur.
- Le prompt système dit que le modèle est appelé à un rendez-vous fixe toutes les 4 h, qu'il peut être réveillé entre deux rendez-vous quand un instrument bouge d'au moins le seuil en 1 h, que `contexte` dit lequel des deux, et que rien ne l'oblige à agir. `prompt_sha256` change donc, et `config_loaded` est journalisé.
- `recent_decisions` inclut les décisions des réveils ; chaque élément porte `"ronde": "reveil"` ou `"rendez_vous"`.

## 3. Le cycle

- **Verrou.** Le cycle attend le verrou jusqu'à 600 s (`LOCK_WAIT_S`), pour ne pas échouer si un réveil se termine ; `arene-cycle.service` passe à `TimeoutStartSec=1500`. `arene kill --now` (`flatten_now`) garde une attente de 120 s.
- **Alerte de veille absente.** Le cycle alerte (`action/veille_absente`, une fois par absence) si le dernier événement `veille` a plus de 30 min alors qu'il y en a déjà eu un.
- **Le reste ne change pas.**
  - `_stops` sur barres reste le filet de sécurité.
  - Les événements `veille`, `reveil_*` et les décisions de réveil ne comptent pas comme cycles.
  - Les compteurs de riskd (trades par 24 h, ordres par minute, frais du mois) les voient, puisqu'ils lisent le journal.

## 4. Ce qui est hors champ, et limites connues (non corrigées)

- Les ordres limites et les stops côté plateforme : voir l'étude des agents traders (`docs/ETUDE-AGENTS-TRADERS.md`).
- La mise à plat sur drawdown entre deux cycles.
- Le filet des barres de 4 h n'agit, pour une position ouverte par un réveil, qu'à partir de la barre suivante (les barres commencées avant l'entrée sont ignorées) ; entre-temps seul le stop en direct de la veille la protège.
- Le coût du tick croît avec le journal (relecture complète à chaque tick) : environ 1,4 s à 30 jours, environ 17 s à un an. Une lecture incrémentale est à faire après la Saison 1.
- La perte possible des ordres de l'aléatoire en cas de crash pendant l'écriture d'un lot d'intentions existait déjà au cycle.
- Pendant les 2 ticks d'une rupture du ticker (10 min), `veille.equity`, le gel et l'arrêt valorisent le symbole à son dernier quote accepté. Les stops, eux, ne dépendent pas du ticker : ils partent au premier tick où 2 bougies 1 min sont sous le stop.
- Une bougie d'une minute n'existe que s'il y a eu des transactions : un instrument sans transaction pendant la fenêtre n'a ni stop ni mesure de mouvement à ce tick. La bougie de la minute en cours n'est jamais lue.
