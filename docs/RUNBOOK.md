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
3. Arrêt total : `systemctl --user disable --now arene-cycle.timer`. Pour repartir : `arene unkill` puis `systemctl --user enable --now arene-cycle.timer`.

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

## Journal cassé (`arene verify` échoue)
1. **Ne rien supprimer, ne rien éditer.** Copier le fichier : `cp var/journal/events.jsonl /chemin/sauvegarde/`.
2. `arene verify` indique la ligne et le code. `truncated_tail` = crash pendant une écriture (dernière ligne coupée) ; `hash_mismatch` / `prev_hash_mismatch` = ligne modifiée ou perdue.
3. Une réparation est une décision humaine, jamais automatique : tronquer à la dernière ligne valide (`head -n <N> events.jsonl > propre.jsonl`), vérifier avec `verify`, noter l'incident, puis remplacer. Les événements perdus sont perdus : le cycle en cours sera repris au prochain `arene cycle`.
4. `var/ledger.sqlite` et `var/site/` sont dérivés : `arene rebuild-ledger`, `arene build-site`.

## Contrôles ponctuels
- `arene smoke-llm <portefeuille>` : un appel réel unique (coût de quelques centimes), sans ordre ni journal. Refuse s'il n'y a pas de clé.
- Rien n'est jamais envoyé à une plateforme : les secrets de plateforme n'existent pas dans le MVP.
