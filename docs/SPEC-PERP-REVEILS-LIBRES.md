# Ligue dérivés : réveils libres des LLM

Spec du 13/11/2026. Demande du propriétaire, vers 14:10 UTC, relayée par la session moteur : « j'aimerais enlevé les restrictions de temps pour les llms pour qu'ils se réveillent plus souvent et quand ils veulent vraiment avec beaucoup moins de contrainte ».

**Modifiée le 13/11 vers 18 h par `docs/SPEC-PERP-CADENCE.md`** : rappel demandé de 5 à 60 min, 144 rondes par jour, cadence par défaut de 15 min, consigne v6.

Ne concerne que la ligue dérivés. Le spot reste gelé (Saison 1) et n'est pas modifié. Complète `docs/SPEC-PERP-ALERTES-ORDRES.md`, dont les §3 (limites du réveil par alerte) et la consigne v4 sont remplacés par ce qui suit.

## 1. Le réveil demandé par l'agent

La sortie structurée gagne un champ facultatif, `next_wakeup_min` : un entier de 5 à 240, ou `null`.

- L'heure demandée se compte depuis l'application de la décision (`due_ts` = heure d'application + minutes).
- **Un seul réveil en attente par agent.** Chaque décision valide, appliquée sur une vue fraîche, le remplace, ou l'annule si elle n'en demande pas. Une décision absente ou invalide n'y touche pas.
- Une valeur invalide (hors bornes, décimale non entière, booléen, texte) est rejetée seule, comme un ordre rejeté (`rejected` de `agent_orders_set`, `kind: "wakeup"`). Le reste de la décision tient, et **le réveil en attente aussi** : une valeur invalide ne demande rien et n'annule rien. `60.0` vaut 60 (le schéma JSON du CLI le compte comme un entier).
- Le réveil est **servi** par la première ronde du propriétaire qui commence au plus 5 min avant l'heure demandée : sa ronde privée, mais aussi un rendez-vous ou un réveil de marché.
- La veille sert un réveil à la première vérification (toutes les 5 min) qui commence au plus 2 min 30 avant l'heure demandée. Un réveil qui n'a pas pu être servi dans l'heure tombe : il n'est jamais servi en retard.

## 2. Les rondes privées

Une ronde **privée** (`kind: "private"`) sert, en une fois, tous les agents qui ont une alerte franchie ou un réveil demandé à servir à ce tick :

- `perp_round` `{round, kind: "private", portfolios: [...], triggers: {portefeuille: déclencheur}, trigger: null, ts}` ;
- le déclencheur de chacun : `{"kind": "alert", alert_id, instrument, condition, price_usd, note}`, plus `asked_wakeup_ts` si un réveil demandé tombe aussi ; ou `{"kind": "scheduled", asked_at_round, due_ts}` ;
- chaque agent joue seul, avec son déclencheur, et ne voit rien de ceux des autres. Le type d'appel qu'il voit (`appel.type`, `kind` de `round_data` et d'`agent_decision`) est `alert` ou `scheduled` ;
- ni les témoins ni les autres modèles ne jouent.

Les rondes `alert` d'avant ce changement (un seul propriétaire, `trigger` commun) restent lisibles et reprises de la même façon.

**Plus aucune limite de temps propre aux alertes et aux réveils demandés.** Le maximum de 4 par jour, le délai d'1 h et la garde de 30 min avant un rendez-vous sont retirés. Restent :

- **une ronde par tick** : un agent ne joue jamais deux fois à moins de 5 min d'intervalle ;
- **un rendez-vous dans les 5 min** : aucune ronde hors rendez-vous ; c'est le rendez-vous qui sert alertes et réveils ;
- **le quota de rondes** (§4) et le budget du jour (D7) ;
- un portefeuille arrêté n'est jamais réveillé.

## 3. Les réveils de marché

- Seuil : **2 %** en 1 h au lieu de 3 % (oubli à 1,5 % au lieu de 2 %).
- **15 min** entre deux réveils de marché au lieu d'1 h ; **plus de maximum par jour**.
- Garde avant un rendez-vous : 5 min au lieu de 30.
- Les rondes privées ne comptent pas dans ce délai.
- Les modèles qui n'ont plus de ronde hors rendez-vous ce jour-là, ou plus de budget, ou arrêtés, ne jouent pas ce réveil : `portfolios` liste alors ceux qui jouent. Si aucun modèle ne peut jouer, pas de réveil. Le témoin aléatoire joue les réveils de marché comme avant.
- Un franchissement est noté (`perp_wake_pending`) à chaque tick, même quand aucune ronde ne peut partir (rendez-vous, cycle spot) : il reste servable une heure.

## 4. Le quota de rondes, seule limite de temps

- `rounds_per_day = 48` par modèle et par jour UTC, rendez-vous compris (`config/perp-llm.toml`), le même pour les 4 agents. En moyenne une ronde toutes les 30 min, que l'agent répartit comme il veut.
- Une ronde jouée est un `round_data` du portefeuille ce jour-là.
- **Les rendez-vous restants du jour sont réservés** : une ronde hors rendez-vous n'est jouée que s'il reste au moins une ronde une fois ces rendez-vous décomptés. Un rendez-vous est toujours joué.
- L'agent voit son quota dans son instantané, sous `compte.rondes` : `rondes_par_jour`, `rondes_jouees_aujourd_hui`, `rendez_vous_restants_aujourd_hui`, `rondes_hors_rendez_vous_restantes` (après celle-ci) et `reveil_demande_utc`.
- **Budgets D7 relevés** pour ne jamais bloquer avant le quota, aux coûts mesurés le 13/11 à 14:03 (Haiku 0,002 $, Sonnet 0,037 $, Opus 0,077 $, Fable 0,164 $ par ronde) : Haiku 0,20 $, Sonnet 2,00 $, Opus 4,00 $, Fable 8,50 $ par jour. Si les 4 agents prennent tout leur quota, c'est environ 15 $ par jour en équivalent API, sur l'abonnement.

## 5. Le cycle spot

La plage interdite (de 5 min avant à 30 min après un cycle spot) devient une file :

- aucune ronde hors rendez-vous ne commence dans les 5 min avant un cycle spot (HH:05 à 00, 04, … UTC) : une ronde dure au plus 4 min environ ;
- aucune ne commence tant que la ligue spot tient son verrou de cycle (`var/cycle.lock`, pris par un cycle ou par une vérification de la veille spot et son réveil). Elle attend le tick suivant ;
- la ligue dérivés ne fait que **tester** ce verrou, et seulement quand une ronde est sur le point de partir : elle le prend quelques microsecondes et le rend aussitôt. La veille spot tourne à :00:30, :05:30…, la veille dérivés à :03:30, :08:30… : les deux ne se croisent pas en pratique, et le cycle spot attend le verrou jusqu'à 10 min ;
- une ronde interrompue qui attend la ligue spot n'empêche pas un rendez-vous dû de partir ;
- les rendez-vous dérivés (02, 06, …, 22 UTC) sont à 2 h des cycles spot et n'attendent pas.

**Ce qui n'est pas couvert :** un réveil de la ligue spot qui part pendant une ronde dérivés. L'empêcher demanderait de modifier la veille spot, qui est gelée. C'est au propriétaire de décider d'une dérogation.

## 6. Ce qui ne change pas

riskd ; stops obligatoires ; levier ≤ 2x ; confidentialité entre agents ; idempotence ; `max_parallel = 4`. Un déclenchement d'ordre d'entrée vieux de plus de 15 min n'est jamais exécuté.

La consigne v5 décrit le réveil demandé et le quota, sans pousser à se réveiller ni à trader : « Demande un rappel quand tu as une raison précise de regarder à nouveau à ce moment-là ; sinon, n'en demande pas. »

## 7. Événements (journal `var-perp`)

| Type | Payload |
|---|---|
| `agent_wakeup_set` | `portfolio, round, minutes, due_ts` ; `minutes` et `due_ts` à `null` : le réveil en attente est annulé (écrit seulement s'il y en avait un) |
| `perp_round` | `kind: "private"`, `portfolios`, `triggers` (§2) ; `kind: "wakeup"` peut porter `portfolios` quand des modèles n'ont plus de ronde |
| `round_data`, `agent_decision` | `kind` : `rendezvous`, `wakeup`, `alert`, `scheduled` |
| `agent_orders_set` | `rejected` peut contenir `{kind: "wakeup", k: 0, error}` |

L'état se recalcule depuis le journal : réveil en attente = dernier `agent_wakeup_set` du portefeuille, s'il a un `due_ts` et qu'aucune ronde du portefeuille commençant au plus 5 min avant ne l'a servi.
