# Ligue dérivés : le Conseil Haiku

## 0. La demande

the owner, le 14/11/2026 à 16:54 UTC :

> « ajoute un council de haiku qui ont chacun la personnalité d'une étape des meilleurs skills de trading, le council haiku sera en ligue dérivé, 10 agent au total, et ils traderont aggressivement objectif doubler la mise en qq jours »

Lecture retenue (cahier des charges relayé par la session « Arène de trading autonome : plan de conception ») :
- **un** nouveau portefeuille, `council-perp:haiku` (« Conseil Haiku »), de 1 000 €, dans la ligue dérivés ;
- il est décidé par **10 membres Haiku** : 9 voix, plus 1 Président qui tranche ;
- les 4 portefeuilles `llm-perp:*` ne changent pas : leur consigne (v7), leur schéma de décision et leur politique de risque restent ceux d'avant.

## 1. Les dix membres et leurs sources

Les rôles sont tirés de trois dépôts publics. Les URL et les étoiles ont été vérifiées le 14/11 par la session de conception.

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) (122 k étoiles) : analystes, chercheurs haussier et baissier, trader, risque, gérant.
- [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) (4,6 k étoiles) : de vrais SKILL.md (crypto-regime-analyzer, contrarian-setup-gate, position-sizer, futures-position-sizer, drawdown-circuit-breaker, pre-trade-discipline-gate, signal-postmortem, breakout-trade-planner).
- [galleonlabs/hypergrok-trading-desk](https://github.com/galleonlabs/hypergrok-trading-desk) (516 étoiles) : un desk de perpétuels (chef de desk, analystes, risk manager, exécution, relecteur).

| # | Membre | Étape | Rôle | Sources |
|---|---|---|---|---|
| 1 | Le Cartographe | A | régime de chaque contrat (tendance, range, volatilité) ; filtre | crypto-regime-analyzer ; Technical Analyst de TradingAgents |
| 2 | Le Suiveur | A | la tendance exploitable maintenant ; continuation | breakout-trade-planner ; Market Wizards |
| 3 | Le Chasseur de cassures | A | le mouvement explosif qui démarre, le point d'entrée ; continuation | breakout-trade-planner (momentum burst) |
| 4 | Le Contrarien | A | consensus surchargé (funding, OI, RSI) ; à contre-courant | contrarian-setup-gate (Shapiro) ; chercheur baissier |
| 5 | Le Lecteur de carnet | A | le carnet soutient-il l'entrée, et à quel coût ; filtre | HyperGrok (analystes, exécution) |
| 6 | Le Trésorier du levier | A | taille et levier pour l'objectif, sans liquidation ; dimensionne | position-sizer, futures-position-sizer ; Kelly ; Van Tharp |
| 7 | L'Avocat du diable | B | la meilleure raison de ne pas faire le trade le plus fort ; à contre-courant | chercheur baissier et débat de TradingAgents |
| 8 | Le Gardien du risque | A | stops, exposition cumulée, distance à la ruine ; borne | drawdown-circuit-breaker, pre-trade-discipline-gate ; risk manager de HyperGrok |
| 9 | Le Mémorialiste | A | ce que le conseil a déjà raté ou réussi (taux de réussite, gain sur perte) | signal-postmortem ; espérance de Van Tharp ; Trade Reviewer de HyperGrok |
| 10 | Le Président | C | tranche, fixe ordres, stops, tailles, alertes et rappel ; refuse le consensus mou | Portfolio Manager de TradingAgents ; Desk Lead de HyperGrok |

Le désaccord est voulu dans les rôles : 2 et 3 jouent la continuation, 4 et 7 vont à contre-courant, 6 et 8 dimensionnent ou bornent, 1 et 5 filtrent. Chaque consigne cite ses sources.

**Les consignes :** `arene/perp/prompt/conseil/v1/`.
- La consigne d'un membre est faite de trois parties : `commun.md` (le conseil, le mandat agressif, les règles, les outils, l'honnêteté), `roles/NN-<membre>.md` (son rôle), puis `avis.md` (le format d'un avis), ou `president.md` (les règles et le format de la décision) pour le Président.
- Chaque consigne complète a son empreinte (`persona_sha256`) dans chaque avis. L'empreinte de celle du Président est le `prompt_sha256` de la décision, et `council.prompts_sha256` réunit les dix.

## 2. Une ronde du conseil

Le conseil joue les **mêmes déclencheurs** que les quatre LLM :
- le rendez-vous de 4 h ;
- la cadence de 10 min ;
- les réveils de marché ;
- ses propres alertes et les rappels demandés par son Président.

Il a son propre quota de rondes (`rounds_per_day` de `config/perp-llm.toml`, 260), et une ronde du conseil compte pour **une** ronde, pas dix. Pour la ligue, c'est un cinquième joueur (`LlmLeague.players`) qui occupe une place du pool de 4 appels parallèles. Ses dix appels tournent dans cette place.

- **Étape A : 8 membres en parallèle** (1 à 6, 8 et 9), **sans se voir**, 4 à la fois (`members_parallel`).
  - Chaque membre a son propre processus `claude -p`, son propre serveur MCP (avec son budget de 3 appels d'outils), et son propre répertoire `rounds/<ronde>/council-perp_haiku/membres/<membre>/`, qui contient une copie de `round.json`.
  - Tous reçoivent le **même message** : l'instantané du portefeuille, avec `bilan_du_conseil` en plus. Ce message ne contient aucun avis, et c'est son empreinte qui est dans `round_data.message_sha256`.
  - Chacun rend un avis JSON court : pour chaque contrat, `long`, `short` ou `plat`, une conviction de 0 à 100, et en option une taille, un stop et un niveau clé ; puis un argument de 3 phrases au plus.
- **Étape B : l'Avocat du diable** reçoit l'instantané et les avis valides de l'étape A. Il désigne sa `cible` (le trade le plus fort) et l'attaque.
- **Étape C : le Président** reçoit l'instantané et les avis valides des étapes A et B. Il rend la décision au **format standard** (actions, alertes, ordres d'entrée, `next_wakeup_min`, justification), avec des tailles d'entrée jusqu'à 500 %. Elle passe par le pipeline existant sans changement : `agent_decision`, riskd, exécution simulée, puis les alertes, les ordres d'entrée et le rappel.

**Journal :**
- un événement `council_opinion` par membre des étapes A et B (9), **avant** la décision ; il porte `member`, `name`, `stage`, `persona_sha256`, `opinion` (ou `null` et `error`), `cost_uusd`, les jetons, `latency_ms`, `tool_calls` et `stream_sha256` ;
- la décision du Président dans `agent_decision`, comme pour les autres, avec en plus `council` : l'empreinte des consignes, celle de la configuration, les membres réussis et échoués, et le coût, le temps et les appels d'outils du Président ;
- les appels d'outils de tous les membres dans `tool_call`, avec `member` ;
- `round_data.council_config_sha256`.

**Pannes :**
- Un membre qui échoue est laissé de côté : son avis est journalisé avec son erreur, la ronde continue, et les suivants ne le voient pas.
- Si le Président échoue, la ronde ne fait rien : l'`agent_decision` porte `parse_error`, et les positions, stops et ordres en place restent.
- **Coupure** (courant, processus tué) : comme pour les LLM, une ronde qui a son `round_data` n'est jamais rejouée. `stream.jsonl` est écrit dès le début de la ronde, si bien que la reprise la marque `interrupted_after_call`. Ce que les appels coupés ont coûté est relu dans leurs flux (`stream.jsonl` de chaque membre) et compté dans le budget du jour (`perp_llm_skipped.cost_uusd`), pour le conseil comme pour les LLM. Une erreur du conseil lui-même (disque plein, fichier illisible) ne perd jamais le coût des appels faits : la ronde finit sans décision, avec ce coût.

## 3. Coût et charge

- **Le coût d'une ronde** est la somme de ses dix appels.
  - Un appel qui a utilisé le modèle sans dire combien (expiration du délai, réponse coupée) compte pour son plafond : un dixième du plafond de la ronde, soit 0,10 $.
  - Le plafond de la ronde vient de la ligue (`max_budget_usd` = 1 $, ou ce qui reste du budget du jour).
- **Le budget** journalier du conseil est de **10 $**, un plafond. Mesuré sur la ligue le 14/11, un appel Haiku coûte environ 0,0014 $ et prend 8 s en médiane (11 s au plus). Une ronde du conseil coûte donc environ 0,015 à 0,02 $, soit 2 à 5 $ par jour à 150 à 260 rondes.
- **Le temps d'une ronde** est d'environ 1 min en attendu : deux vagues de 4 membres, puis l'Avocat, puis le Président. Au pire, avec chaque appel coupé à 90 s, elle prend 6 min ; elle commence dès qu'une place du pool se libère, en général après Haiku seul, et au pire après 4 min. Cela fait 10 min au plus, sous les 15 min que systemd accorde à la veille.
- **La mémoire** de the host est le facteur limitant : environ 3 Go libres, et 300 Mo par processus `claude`. Avec `members_parallel = 4`, il y a au plus 7 processus à la fois : 3 LLM et 4 membres.

## 4. La politique de risque du conseil

Elle est dans `config/policy-perp-conseil.toml`, avec le profil `aggressive`, et ne s'applique qu'au conseil.

Doubler est impossible avec la politique de la ligue : 2x, 3 % de perte par trade, gel à −5 % sur 24 h, arrêt à −15 %. La politique du conseil est hachée, journalisée et copiée dans chaque verdict comme celle de la ligue.

| Règle | Ligue (4 LLM, témoins) | Conseil |
|---|---|---|
| Levier total | ≤ 2x (marge AMF de 50 %) | ≤ 10x, avec les marges de Kraken |
| Une entrée | ≤ 50 % de l'equity | ≤ 500 % |
| Une position | ≤ 100 % | ≤ 1 000 % |
| Stop | obligatoire, 1 à 15 % | obligatoire, 1 à 15 %, **avant la liquidation** |
| Perte au stop d'un trade | ≤ 3 % | ≤ 25 % |
| Perte si tous les stops sont touchés | ≤ 7,5 % | ≤ 60 % |
| Ouvertures | 4 par 24 h, 4 h entre deux sur un contrat | 24 par 24 h, sans délai |
| Gel quotidien | −5 % sur 24 h : 24 h de gel | aucun |
| Budget de frais | 3 % par mois | aucun (les frais restent réels) |
| Arrêt | −15 % depuis le plus haut | −90 % (la « ruine ») ; the owner relance avec `resume` |
| Clôture de marge | equity < 25 % de l'exposition | equity < marge de maintenance de Kraken, puis 1 h sans entrée |
| Coût ≤ 1/3 du mouvement, mouvement ≤ 30 %, funding extrême, contrôles de données et de marché | oui | oui, inchangés |

- **Le profil `aggressive`** (`arene/perp/policy.py`) a ses propres bornes de cohérence :
  - levier ≤ 10x ;
  - perte d'un trade ≤ perte de tous les stops < arrêt ≤ 95 % ;
  - gel, budget de frais et délai entre deux entrées peuvent valoir 0, ce qui les coupe.

  Les deux fichiers ne se chargent jamais l'un à la place de l'autre : chacun déclare son profil, et le chargeur vérifie que c'est celui qu'il attend.
- **La liquidation simulée est réaliste à 10x** (`arene/perp/margin.py`). Pour le conseil, le simulateur et riskd utilisent la grille de marges de chaque contrat, telle que Kraken la publie (`marginLevels` de `/instruments`) :
  - pour ouvrir, la marge initiale : 1 % du notionnel pour BTC, ETH et SOL, 2 % pour XRP, LINK et LTC, aux tailles du conseil (le premier palier va jusqu'à 200 000 $ pour SOL, et jusqu'à 0,5 à 2 M$ pour les autres) ;
  - pour la clôture de marge, la marge de maintenance, qui en vaut la moitié ; elle est testée chaque minute, au pire prix de la minute, avec 5 % de frais de liquidation en plus.

  Un contrat sans grille est margé à 100 % : aucun levier. La règle AMF (50 % et 25 %) aurait liquidé une position de 10x dès son ouverture.
- **Le stop avant la liquidation** (`LIQUIDATION_BEFORE_STOP`) : l'equity qui reste quand le stop de la position est touché (les autres au prix actuel) couvre la marge de maintenance, et c'est vrai aussi quand tous les stops sont touchés en même temps. Avec les plafonds de 25 % et 60 %, cette règle ne mord pas aujourd'hui. Elle garantit le principe si la politique change.
- **C'est le nom qui désigne le portefeuille margé chez Kraken** (`council-perp:`), jamais la configuration. Si la configuration du conseil ne se charge pas, le conseil ne joue plus, mais une position de 10x déjà ouverte garde la liquidation de Kraken : la règle AMF la liquiderait d'un coup. Sa politique devient alors celle de la ligue, plus stricte : pas d'entrée au-delà de 2x, arrêt à −15 %.
- **Hors de la règle des particuliers :** ce portefeuille dépasse le levier de 2x que l'AMF impose aux particuliers pour les CFD sur crypto (décision D2). C'est une **démonstration paper** : elle ne pourrait pas passer au réel telle quelle. La consigne le dit au conseil, et le site doit le dire aussi (§6).

**Relancer après la ruine :**

```bash
cd ~/dev/arene-trading && .venv/bin/python -m arene.perp.council resume
```

Cette commande écrit `portfolio_resumed` dans le journal. C'est une décision du propriétaire seul.

## 5. Ce qui ne change pas

- Les 4 portefeuilles `llm-perp:*` gardent :
  - la consigne v7 (même empreinte) ;
  - le même schéma de décision, octet pour octet, avec `size_pct` ≤ 100 ;
  - la politique de `config/policy-perp.toml` (même empreinte) ;
  - la règle AMF dans le simulateur ;
  - la même ligne de règles dans leur instantané.
- Les témoins (panier, tendance, hasard) ne changent pas.
- La seule trace dans leurs données : `round.json` porte désormais `policy.profile = "standard"`.

## 6. Le site (session « Dashboard polish »)

Demande écrite dans `docs/COORDINATION-dashboard.md` :
- le conseil est une **catégorie à part**, marquée « agressif · levier ≤ 10x · objectif ×2 », et il n'est **pas classé** avec les LLM neutres ;
- sa page montre la délibération de chaque ronde : les 9 avis (`council_opinion`), puis la décision du Président.

## 7. Configuration

- `config/perp-conseil.toml`, haché, son empreinte est dans chaque `round_data` du conseil. Il contient :
  - `enabled` ;
  - le portefeuille et le modèle (Haiku seulement) ;
  - `daily_budget_usd = "10.00"` ;
  - `members_parallel = 4`, `member_timeout_s = 90`, `member_max_tool_calls = 3` ;
  - le nom du fichier de politique.
- **Une configuration invalide coupe le conseil seulement**, avec une alerte `perp_council_config_invalid`, et jamais les LLM ni le moteur de risque. `enabled = false` le coupe aussi : ses positions gardent leurs stops et la veille continue de les surveiller.
