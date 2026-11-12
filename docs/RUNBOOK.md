# Runbook de l'arène (paper)

Tout se lance depuis `~/dev/arene-trading` avec `uv run arene <commande>`. État dans `var/`, secrets dans
`~/.config/arene/secrets/` (jamais dans le dépôt). Tout est en **paper** : aucune alerte ne concerne de l'argent réel.

## Lire l'état
- `arene status` : dernier cycle, equity par portefeuille (au bid), gels/arrêts, coupe-circuit, dormance, dernière alerte, verify du journal.
- `arene verify` : chaîne du journal intacte ? (code de sortie 0 = OK). Tête de chaîne = empreinte de tout l'historique.
- `journalctl --user -u arene-cycle.service -n 80` : sortie du dernier cycle. `systemctl --user list-timers arene-cycle.timer`.

## Tout arrêter
1. `arene kill` : plus aucun achat ; au prochain cycle les portefeuilles LLM et aléatoire sont mis à plat.
2. `arene kill --now` : pareil, avec mise à plat immédiate (moins d'une minute). Le fichier `~/.config/arene/KILL` a le même effet que `var/KILL`.
3. Arrêt total : `systemctl --user disable --now arene-cycle.timer arene-veille.timer`. Pour repartir : `arene unkill` puis `systemctl --user enable --now arene-cycle.timer arene-veille.timer`. (Arrêter seulement la veille : voir « Veille et réveils ».)

## Tout mettre à plat
`arene kill --now`, puis `arene status` (positions = 0 pour les LLM et l'aléatoire). Les témoins de référence (panier, 6040, E0065) restent investis : ce sont des références, pas des décideurs.

## Confirmer ta présence (dormance)
`arene ack` au moins une fois tous les 7 jours : sans ack depuis 7 j, plus aucune entrée ; depuis 9 j, mise à plat des LLM et de l'aléatoire. (Sans aucun ack, le compte part du premier lancement.)

## Reprendre un portefeuille
- **Gelé** (perte ≥ 5 % en 24 h) : il repart tout seul après 24 h. Pour le forcer : `arene resume <portefeuille>`.
- **Arrêté** (drawdown ≥ 20 %, déjà mis à plat) : comprendre d'abord (`arene status`, journal), puis `arene resume llm:claude-haiku-5-5` (exemple). Le plus haut d'equity repart de l'equity à plat.

## Que faire sur chaque alerte (ntfy ; toujours aussi dans le journal)
| code | niveau | action |
|---|---|---|
| `cycle_exception` | panique | Cycle interrompu. `journalctl` pour la cause, `arene verify`, puis relancer `arene cycle` : il **reprend** sans double fill. |
| `journal_casse` | panique | Voir « Journal cassé ». Aucun cycle ne tourne tant que `verify` échoue. |
| `config_invalide` | panique | `config/arene.toml` ou `policy.toml` refusé : corriger (message dans l'alerte), relancer. |
| `data_stale`, `data_error` | action | Kraken indisponible ou en retard. Relancer `arene cycle` dans le même créneau de 4 h ; sinon le cycle est perdu (trou dans les courbes, rien de cassé). |
| `binance_data`, `e0065_data` | action | Données 1 j Binance absentes : E0065 saute ce cycle. Se corrige seul. |
| `portfolio_halted` | action | Arrêt drawdown : voir « Reprendre un portefeuille ». |
| `portfolio_frozen` | info | Gel 24 h (perte, ou ordre UNKNOWN > 2 cycles). Rien à faire sauf si `unknown_order` : lire le journal. |
| `kill_switch` | action/info | Coupe-circuit armé / levé (par toi, normalement). |
| `dormance_no_entries`, `dormance_flatten` | action | `arene ack`. |
| `model_mismatch` | action | L'API a répondu avec un autre modèle que demandé : les décisions de ce cycle ne sont plus comparables, vérifier la config des modèles. |
| `llm_api_error`, `llm_budget` | action/info | Appel LLM en échec ou budget du jour atteint (décision sautée, le reste tourne). |
| `site_build` | action | Le dashboard n'a pas pu être reconstruit ; `arene build-site` pour voir l'erreur. Sans effet sur le journal. |
| `heartbeat_absent` | info | Pas de `healthcheck_url` : aucun heartbeat externe. À installer. |
| aucun ping reçu en 4 h 30 (Healthchecks) | — | the host ou le timer est tombé : `systemctl --user status arene-cycle.timer`, `loginctl show-user $USER -p Linger`. |

## Veille et réveils
Spécification : `docs/VEILLE.md`. Le rendez-vous de 4 h ne change pas ; `arene-veille.timer` ajoute un tick toutes les 5 min (HH:MM:30 UTC), sans LLM sauf réveil.

**Ce que fait un tick** (`arene veille`) : prend le verrou du cycle sans attendre (cycle ou réveil en cours : il sort sans rien écrire, code 0), lit les quotes Kraken et écarte ceux qui sont douteux (symbole par symbole), vend au bid (glissement et frais compris) toute position dont le bid est sous le stop deux ticks de suite, écrit un événement `veille` (quotes, `rejets`, equity au bid, stops du tick, réveil, `refus`), puis lance un réveil si un mouvement d'au moins 3 % sur 1 h, confirmé sur deux ticks, passe tous les garde-fous. Un réveil est une ronde de décision pour tous les LLM et `temoin:aleatoire` ; il écrit `reveil_started` (avant l'événement `veille`), les événements de décision (champ `cycle` = l'identifiant du réveil, un multiple de 300 s qui n'est pas un rendez-vous), des `quote_reveil`, puis `reveil_completed`, et jamais d'`equity`. Après un réveil terminé, `arene veille` demande à systemd de reconstruire le site (`arene-site-build.service`) ; `--no-site` l'évite.

**Lire**
- `journalctl --user -u arene-veille.service -n 40` : une ligne par tick (`veille <heure> : done  événements=1 ...`, avec `stops=`, `quotes écartés=`, `declencheur=` et `reveil=` quand ils existent). `systemctl --user list-timers arene-veille.timer`. Le site : `journalctl --user -u arene-site-build.service -n 20`.
- Dans le journal : `grep -E '"type":"(reveil_started|reveil_completed|reveil_abandonne)"' var/journal/events.jsonl | tail`. Un `reveil_started` sans `reveil_completed` est un réveil en cours ou interrompu : le tick suivant le reprend (30 min, si aucun cycle n'a été terminé depuis), sinon il est réparé puis abandonné.
- Un déclencheur refusé laisse sa trace dans le champ `refus` de l'événement `veille` (`delai`, `plafond`, `avant_cycle`, `cycle_incomplet`, `cycle`) et dans la sortie du tick : `declencheur=mouvement (refusé : delai)`.
- `arene status` ne montre pas la veille ; `arene verify` la vérifie comme le reste (environ 290 événements `veille` par jour).
- Fichiers d'état hors journal : `var/veille_echecs` (nombre de ticks consécutifs sans aucun quote valide ; supprimé au premier tick réussi ; ne pas l'éditer, on peut le supprimer) et `var/veille_journal_casse` (heure de la dernière alerte `journal_casse` de la veille, pour n'en envoyer qu'une par heure).

**Arrêter**
- Plus de réveils, stops en direct conservés : mettre `max_reveils_jour = 0` dans `[veille]` de `config/arene.toml` (effet au tick suivant ; `config_loaded` est journalisé).
- Plus de veille du tout : `systemctl --user disable --now arene-veille.timer`. Le filet des stops sur barres de 4 h au cycle reste actif, comme avant. Le cycle enverra l'alerte `veille_absente` une fois, puisque la veille a déjà tourné.
- `arene kill` / `arene kill --now` agissent sur les réveils comme sur les cycles : un réveil sous coupe-circuit met à plat les LLM et l'aléatoire et refuse toute entrée ; un KILL armé pendant un appel LLM bloque l'achat qui suit. La veille elle-même ne met jamais à plat.
- Réglages (`[veille]`) : `seuil_mouvement_bp` (300 = 3 %), `fenetre_mouvement_s` (3600), `cooldown_s` (3600), `max_reveils_jour` (6), `garde_avant_cycle_s` (1800), `tick_s` (300, doit diviser `interval_s`). Toute modification change le hash de la config.

**Nouvelles alertes**
| code | niveau | action |
|---|---|---|
| `veille_data` | action puis info | Action : aucun symbole n'a de quote exploitable (tous invalides ou illisibles) depuis 3 ticks consécutifs (une seule alerte au début de la panne ; les ticks en échec n'écrivent rien, code de sortie 1). Les stops en direct ne tournent pas : le filet des barres de 4 h reste actif. Info « rétabli » au premier tick réussi. |
| `veille_symbole_ecarte` | action puis info | Les quotes d'un symbole sont rejetés (`spread` ou `saut`, voir `rejets` des événements `veille`) depuis 3 ticks consécutifs sans qu'une rupture cohérente se confirme : quotes erratiques de Kraken. Pas de stop ni de déclencheur sur lui, equity à son dernier quote accepté. Se lève seul ; info au retour. |
| `veille_absente` | action | Posée par le cycle : plus aucun événement `veille` depuis plus de 30 min. `systemctl --user status arene-veille.timer`, `journalctl --user -u arene-veille.service`. Une alerte par absence. |
| `journal_casse` (veille) | panique | La veille refuse de tourner sur un journal cassé (une alerte par heure au plus, ntfy seulement). Voir « Journal cassé ». |
| `reveil_resumed` | info | Un réveil interrompu a été repris par un tick suivant (sans double décision ni double fill). Rien à faire. |
| `reveil_abandonne` | action | Un réveil incomplet a été réparé puis abandonné (plus de 30 min, ou un cycle terminé entre-temps). Voir `reveil_exception` ou `data_stale` juste avant ; les décisions déjà reçues restent journalisées. Il compte dans le plafond du jour et dans le délai. |
| `reveil_exception` | panique | Réveil interrompu par une exception : `journalctl --user -u arene-veille.service`, puis `arene verify`. Les ticks suivants le reprennent (jusqu'à 30 min). Une seule alerte par réveil et par code. |
| `data_stale`, `data_error`, `llm_api_error`, `llm_budget`, `model_mismatch`, `kill_switch`, `dormance_*` | — | Mêmes codes et mêmes actions qu'au cycle ; ils peuvent aussi venir d'un réveil (message préfixé `[réveil N]`, une seule alerte par réveil et par code). Le budget quotidien (`daily_budget_usd`) est partagé entre cycles et réveils. |

Un cycle attend le verrou jusqu'à 600 s (`LOCK_WAIT_S`) : si un réveil le tient, le cycle de HH:05 démarre quand le réveil se termine (`arene-cycle.service` : `TimeoutStartSec=1500`).

## Saison 1
Décision du propriétaire : une saison de 8 semaines (56 jours) gelée, sans changement de cadence, de modèles, de consigne ni de politique de risque. Le rodage d'avant est exclu des classements. Table `[saison]` de `config/arene.toml` (facultative : sans elle, rien ne change) : `numero`, `nom`, `debut_ts` (13/11/2026 à 00:05 UTC, l'exécution du cycle de 00:00), `duree_jours`.

**Événements** (tous dans le journal) :
- `saison_debut` : écrit au premier cycle dont l'instant de décision `t` est >= `debut_ts - cycle_delay_s`, avant ses décisions. Il fige `config_sha256`, `policy_sha256`, `prompt_sha256`, `git_head` et la liste des portefeuilles, et fixe `fin_prevue_cycle = t + 56 jours`.
- `saison_reference` : après les `equity` de ce cycle, `{numero, cycle, equity: {portefeuille: µEUR}}`. C'est la base des classements ; rien n'est remis à zéro.
- `saison_fin` : au premier cycle avec `t >= fin_prevue_cycle`, après ses `equity`. Le gel est levé ensuite.
- `saison_derogation` : voir plus bas.

**Ce qui est gelé** (de `saison_debut` à `fin_prevue_cycle`) : trois hashes. Si l'un diffère de celui du `saison_debut`, le cycle ET les réveils refusent de tourner (`panique/saison_gelee`, le message nomme le hash : config, politique de risque ou consigne système). Les correctifs de code qui ne touchent ni la config, ni la politique, ni la consigne restent permis ; `git_head` n'est pas gelé (il est journalisé dans `config_loaded`).
- `config_sha256` est le sha256 du fichier `config/arene.toml` **sans la table `[saison]`** : on retire la ligne `[saison]` et tout ce qui suit jusqu'à la ligne qui précède le prochain en-tête de table. Modifier `[saison]` (ou un commentaire placé dedans) n'est donc pas un changement gelé ; tout autre octet du fichier l'est (calcul : `arene.config.sha256_hors_saison`). `config_loaded` garde le hash complet du fichier.
- `policy_sha256` : `config/policy.toml` ; `prompt_sha256` : `arene/deciders/prompt/v1.md`.

**Déroger.** Écrire une raison dans `var/SAISON_DEROGATION` (`echo "raison" > var/SAISON_DEROGATION`) : le cycle journalise alors `saison_derogation {numero, raison, hashes_avant, hashes_apres}` (une fois par changement de hash, `hashes_avant` = l'état gelé précédent) puis tourne ; un réveil tourne aussi. Fichier vide ou absent : le gel s'applique. Supprimer le fichier une fois la dérogation terminée ; toute dérogation est visible dans `arene status` et sur le site.

**Lire les classements.** `arene status` affiche la saison (en attente, en cours : jour N sur 56, ou terminée), le nombre de dérogations et la performance de chaque portefeuille depuis `saison_reference` (equity au bid, courante ou de `saison_fin`). Les classements se font depuis `saison_reference`, jamais depuis le capital initial ; le rodage (avant `saison_debut`) est présenté à part.

## Journal cassé (`arene verify` échoue)
1. **Ne rien supprimer, ne rien éditer.** Copier le fichier : `cp var/journal/events.jsonl /chemin/sauvegarde/`.
2. `arene verify` indique la ligne et le code. `truncated_tail` = crash pendant une écriture (dernière ligne coupée) ; `hash_mismatch` / `prev_hash_mismatch` = ligne modifiée ou perdue.
3. Une réparation est une décision humaine, jamais automatique : tronquer à la dernière ligne valide (`head -n <N> events.jsonl > propre.jsonl`), vérifier avec `verify`, noter l'incident, puis remplacer. Les événements perdus sont perdus : le cycle en cours sera repris au prochain `arene cycle`.
4. `var/ledger.sqlite` et `var/site/` sont dérivés : `arene rebuild-ledger`, `arene build-site`.

## Contrôles ponctuels
- `arene smoke-llm <portefeuille>` : un appel réel unique (coût de quelques centimes), sans ordre ni journal. Refuse s'il n'y a pas de clé.
- Rien n'est jamais envoyé à une plateforme : les secrets de plateforme n'existent pas dans le MVP.
