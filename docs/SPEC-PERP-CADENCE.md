# Ligue dérivés : cadence et consigne de trader (v6, puis v7)

**Depuis le 14/11, voir le §5 :** cadence de 10 min devenue un plafond, 260 rondes par jour, consigne v7, budgets revus. Les §1 à §3 décrivent l'état du 13/11 (15 min, rappel demandé qui remplace la cadence).

Spec du 13/11/2026. Demande du propriétaire, vers 18:00 UTC : « Les llms s'activent trop peu souvent à mon goût, j'aimerais plusieurs fois par heure même + et surtout toujours aucun trade ».

Ne concerne que la ligue dérivés ; le spot reste gelé. Complète `docs/SPEC-PERP-REVEILS-LIBRES.md`, dont elle change le §1 (bornes du réveil demandé) et la consigne (v5 remplacée par v6).

## 0. Le constat (journal du 13/11, 02:00 à 18:03 UTC)

- **24 décisions, 0 entrée.** Toutes concluent « pas d'avantage clair, je reste à plat », souvent en citant le coût aller-retour.
- **0 rappel demandé** depuis la mise en service des réveils libres (16:00 UTC). Le rappel était facultatif, et la consigne v5 le décourageait (« Chaque ronde coûte… sinon, n'en demande pas »). Les agents n'ont joué qu'aux rendez-vous et à 2 réveils de marché : 6 rondes en 16 h.
- La consigne v5 poussait à ne rien faire : « Ne rien faire est une décision valide, et souvent la meilleure », « cherche la meilleure décision, pas la plus active ».

## 1. La cadence par défaut

Nouvelle clé `cadence_min` de `config/perp-llm.toml` : **15**. 0 la coupe ; sinon de 5 à 60.

- Un agent qui n'a **aucun rappel en attente** est rappelé `cadence_min` après **sa dernière ronde**, quelle qu'elle soit (rendez-vous, réveil, alerte, rappel, cadence, ronde sans décision valide comprise). Il est servi par la vérification de la veille qui commence au plus 2 min 30 avant cette heure.
- Il joue dans une **ronde privée**, avec le déclencheur `{"kind": "cadence", "every_min": 15, "last_round_ts": …}` ; le type d'appel qu'il voit est `cadence`. Plusieurs agents dus au même tick partagent la ronde privée, chacun avec son déclencheur.
- Une ronde dont la préparation a échoué (`perp_llm_skipped`) compte comme une ronde pour la cadence : elle n'est pas retentée à chaque tick.
- `wakeups = false` coupe les réveils de marché, pas la cadence : la cadence se coupe avec `cadence_min = 0`.
- **Un rappel qu'il a demandé remplace la cadence** tant qu'il est en attente : `next_wakeup_min` va maintenant de **5 à 60** (au lieu de 240), si bien qu'un agent est toujours rappelé au moins une fois par heure. Une décision valide sans `next_wakeup_min` annule le rappel en attente : l'agent revient à la cadence.
- Les mêmes conditions que les autres rondes privées s'appliquent : agent non arrêté, budget du jour, rondes du jour, une ronde par tick, rien dans les 5 min avant un rendez-vous, file derrière la ligue spot. Un réveil de marché passe avant, et sert aussi la cadence (c'est une ronde).

## 2. Les rondes du jour et les budgets

- `rounds_per_day` : **144** (au lieu de 48), soit une ronde toutes les 10 min en moyenne : les 96 de la cadence, plus les alertes, les réveils de marché et les rappels plus rapprochés. Les rendez-vous restants du jour sont toujours gardés.
- Budgets journaliers, pour que le quota passe avant eux : Haiku 0,50 $, Sonnet 8,00 $, Opus 16,00 $, Fable 36,00 $ (coûts mesurés le 13/11 sur des rondes sans trade : 0,002, 0,033, 0,072 et 0,166 $ par ronde ; marge d'environ 1,5x pour les rondes qui tradent).
- **Coût attendu**, en équivalent API sur l'abonnement du propriétaire : environ 27 $ par jour à la cadence seule (≈ 100 rondes par agent) au coût des rondes sans trade, davantage quand les agents tradent ; 60 $ au plus (les budgets). Fable en fait plus de la moitié. Un modèle à court de budget n'est plus appelé jusqu'à minuit UTC, rendez-vous mis à part.

## 3. La consigne v6

- L'agent est **trader** : il est là pour prendre des positions et les gérer.
- **Pas besoin de certitude**, seulement une espérance positive après les coûts : un avis modeste justifie une petite position (5 à 15 % de l'equity) avec un stop serré, plutôt que rien.
- Le long et le short se valent.
- **Rester à plat est un pari comme un autre**, jugé comme les autres : il ne rapporte rien et ne peut battre aucun témoin. L'agent ne reste à plat que s'il n'a aucun avis sur aucun des six contrats, et il dit pourquoi.
- À chaque appel, il gère ce qui est ouvert. Il utilise ses ouvertures (le garde-fou en limite le nombre) et ses ordres d'entrée.
- Elle donne le seuil du garde-fou sur les coûts (mouvement attendu d'au moins 0,8 % environ) et la limite des frais du mois, pour que « petite position » ne finisse pas en refus.
- Retirés : « souvent la meilleure », « pas la plus active », « Chaque ronde coûte ».

**Rien n'oblige un agent à trader** : aucune exposition minimale n'est imposée, et le garde-fou (riskd) ne change pas. Il limite toujours à 4 ouvertures par 24 h, avec 4 h entre deux ouvertures sur un même contrat, levier 2x au plus.

## 4. Ce qui ne change pas

riskd, stops, levier, rondes privées, idempotence, `max_parallel` 4, aucun déclenchement exécuté au-delà de 15 min, rendez-vous toutes les 4 h, témoins, spot gelé.

## 5. Cadence de 10 min, plafond de l'écart (14/11/2026)

Demande du propriétaire, le 14/11 vers 01:45 UTC : « Augmente la cadence on s'autorise deux fois plus de conso qu'actuellement ». Consigne v7.

- **Le constat :** de 18:28 à 01:40 UTC, environ 2,3 $ en équivalent API, soit à peu près 8 $ par jour. Trois agents demandaient d'eux-mêmes un rappel à 30 min, ce qui les mettait à 2 ou 3 rondes par heure.
- **`cadence_min` = 10, et la cadence devient un plafond :** un agent est rappelé **au plus tard** 10 min après sa dernière ronde. Un rappel qu'il a demandé ne peut qu'avancer cet appel (à 5 min) : demandé plus tard que la cadence, il ne le retarde plus. Les valeurs de `next_wakeup_min` restent acceptées de 5 à 60, mais seules 5 à 7 avancent l'appel d'un tick ; la consigne ne propose que 5.
- **6 rondes par heure et par agent**, au lieu de 2 à 3. `rounds_per_day` : 260 (la cadence seule en fait 144 ; un agent qui demanderait 5 min à chaque ronde en jouerait 288).
- **Coût attendu :** environ 20 $ par jour (Haiku 0,2, Sonnet 2,1, Opus 5,3, Fable 12 $ pour 144 rondes ; 28 $ à 200 rondes), au coût moyen par ronde mesuré cette nuit (0,0014, 0,014, 0,037 et 0,084 $), soit 2 à 2,5 fois la conso d'avant. Fable en fait plus de la moitié.
- **Budgets journaliers**, plafonds contre un emballement et non objectifs, à environ deux fois le coût attendu : Haiku 0,50 $, Sonnet 5 $, Opus 14 $, Fable 30 $.
