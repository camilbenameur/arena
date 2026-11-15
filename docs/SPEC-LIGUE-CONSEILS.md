# La ligue des conseils

## 0. Les demandes

the owner, le 15/11/2026 :

> « Met un deuxième conseil, 10 Haiku et 1 président Opus, toujours inspiré du top skill, et modifie le conseil Haiku, passe a 10 Haiku et 1 président Haiku »

> « met les dans une ligue dédiée, ensuite, prépare aussi le dashboard en paralèlle »

Lecture retenue :
- **deux conseils**, chacun avec **10 conseillers Haiku et 1 Président** : le Conseil Haiku (`council-perp:haiku`, Président Haiku) et le Conseil Opus (`council-perp:opus`, Président Opus) ;
- les deux ont **les mêmes conseillers, les mêmes consignes et la même politique** : seul le modèle du Président change. L'expérience mesure ce que vaut un Président plus fort sur les mêmes avis ;
- les deux sortent de la ligue dérivés et forment la **ligue des conseils**. La ligue dérivés redevient : 4 IA seules et leurs témoins.

Le reste du fonctionnement d'un conseil (étapes, journal, pannes, politique agressive, liquidation de Kraken) est celui de `docs/SPEC-PERP-CONSEIL-HAIKU.md`, qui reste la référence. Ce document dit ce qui change.

## 1. Onze membres : un dixième conseiller

Le dixième conseiller est **l'Arbitragiste de paires** (étape A), tiré de `pair-trade-screener` de [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) (liste des skills relue le 15/11) :
- il joue **la valeur relative** entre les six contrats : long le fort, short le faible, ou l'inverse quand l'écart est étiré (ratio d'une paire et son écart à sa moyenne, en z-score) ;
- il dit aussi quand les positions ouvertes ou proposées ne sont qu'**un seul pari** sur la direction du marché : les six contrats bougent presque ensemble.

Il manquait au conseil : les neuf autres jugent chaque contrat seul, aucun ne regarde leur écart.

| # | Membre | Étape |
|---|---|---|
| 1 à 6, 8, 9 | les mêmes qu'avant | A |
| 7 | L'Avocat du diable | B |
| **10** | **L'Arbitragiste de paires** | **A** |
| 11 | Le Président | C |

**Les consignes v2** (`arene/perp/prompt/conseil/v2/`) :
- `commun.md` ne nomme plus le conseil ni le modèle : « un des onze membres d'un conseil de trading » ; le portefeuille est dans l'instantané. Les deux conseils ont donc des consignes identiques, octet pour octet, et les mêmes empreintes ;
- l'étape A compte 9 avis, l'Avocat lit les 9, le Président lit les 10 ;
- `roles/10-arbitragiste.md` est nouveau ; le Président passe en `roles/11-president.md` et connaît le dixième membre.

Les consignes v1 restent dans le dépôt : ce sont celles des rondes d'avant le 15/11.

## 2. Le Président Opus

- `president_model` de la configuration de chaque conseil : `claude-haiku-5-5` ou `claude-opus-5-5`. Les conseillers sont toujours Haiku (`model`).
- **Plafonds d'une ronde** (le plafond de la ronde vient de la ligue : 1 $, ou ce qui reste du budget du jour) : un vingtième par conseiller (0,05 $), la moitié pour le Président (0,50 $). Avant, chaque membre avait un dixième (0,10 $) ; un Président Opus aurait pu être coupé.
- **Délai :** `president_timeout_s`, 240 s pour Opus (comme le portefeuille Opus de la ligue dérivés), 90 s pour Haiku.
- `agent_decision.model_requested` est le modèle du Président.

## 3. Coût

- **Conseil Haiku :** environ 0,02 $ par ronde (11 appels Haiku), 3 à 5 $ par jour ; budget 10 $ par jour, inchangé.
- **Conseil Opus :** 10 appels Haiku (environ 0,02 $) et 1 appel Opus (environ 0,04 à 0,08 $ : le portefeuille Opus de la ligue dérivés coûte 0,037 $ par ronde en moyenne, et le Président lit dix avis en plus), soit environ 0,06 à 0,10 $ par ronde, 9 à 26 $ par jour à 150 à 260 rondes ; **budget de 25 $ par jour**, un plafond. Les montants sont des équivalents catalogue : les décideurs tournent sur l'abonnement.

## 4. La ligue

`config/ligue-conseils.toml`, haché ; son empreinte est dans chaque `round_data` d'un conseil (`councils_league_sha256`) :
- `enabled` ;
- `councils` : les fichiers de configuration de chaque conseil (`perp-conseil.toml`, `perp-conseil-opus.toml`) ;
- `max_member_processes = 4` : les processus `claude` des membres, **tous conseils confondus**, à un même moment. the host a environ 3 Go libres, et un processus en prend 300 Mo : avec les 4 LLM, au plus 7 processus, comme avec un seul conseil avant.

**Ce que la ligue partage avec la ligue dérivés :** le moteur, le journal (`var-perp/journal/events.jsonl`), les données de marché, la veille, les déclencheurs (rendez-vous, cadence de 10 min, réveils de marché, alertes, rappels) et le quota de rondes (`config/perp-llm.toml`). Chaque conseil a son quota, son budget, sa politique et occupe une place du pool de 4 appels. `portfolio_opened.league` reste `"perp"` (le registre des dérivés ne lit que celle-là) ; c'est `kind == "council"` qui classe un portefeuille dans la ligue des conseils, pour le site.

**Pannes :** un conseil dont le fichier est invalide est laissé de côté, avec une alerte `perp_council_config_invalid` ; l'autre joue. Un fichier de ligue invalide coupe les deux conseils, jamais les LLM ni le moteur de risque. Dans les deux cas, les positions d'un conseil coupé gardent leurs stops et la liquidation de Kraken.

**Relancer un conseil après la ruine** (décision du propriétaire seul) :

```bash
cd ~/dev/arene-trading && .venv/bin/python -m arene.perp.council resume --portfolio council-perp:opus
```

## 5. Le journal

- `council_opinion` : 10 par ronde (9 de l'étape A, puis l'Avocat), au lieu de 9. Nouveau membre : `member = "arbitragiste"`, `name = "L'Arbitragiste de paires"`.
- `agent_decision.council` gagne `name` (« Conseil Haiku », « Conseil Opus »), `members_model`, `president_model` et `prompts_version` (`"v2"`). Ces champs sont absents des décisions d'avant le 15/11 : lire Haiku et v1.
- Le Conseil Opus s'ouvre (`portfolio_opened`, `kind = "council"`) à sa première ronde, avec 1 000 €.

## 6. La durée d'une ronde

Attendu : 1 à 2 min par conseil (9 conseillers à 4 processus au plus, partagés entre les deux conseils, puis l'Avocat, puis le Président). Au pire, avec chaque appel coupé à son délai, une ronde des deux conseils dépasserait les 15 min que systemd accorde à la veille (`TimeoutStartSec=900`) : la veille serait tuée, et la ronde marquée `interrupted_after_call` au tick suivant, son coût relu dans les flux, sans être rejouée. Allonger ce délai est un changement de service : il attend l'accord du propriétaire.

## 7. Le site

Fait en parallèle dans `arene/site/` : la ligue des conseils a sa page, les conseils quittent la ligue dérivés, la délibération affiche le nombre réel d'avis et le modèle du Président.
