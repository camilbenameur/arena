# Conseil v4 « Conseil Tendance » : spécification

Demande du propriétaire (17/11/2026) : « refonte avec tout permis du conseil [...] Avoir un conseil qui génére du revenu net, l'ordre de 10% par jour ».

Recherche et choix du moteur : `docs/CONSEIL-V4-RECHERCHE.md`.

## 1. Le principe

Ce que l'audit a montré de l'ancien conseil :
- des avis de personas LLM sans avantage ;
- des tailles énormes ;
- une re-décision toutes les 10 min, d'où 140x de rotation.

Le conseil v4 inverse les rôles :
- **le moteur décide** : la tendance gelée (`arene/perp/lab/trend.py`, `FROZEN`, à l'échelle 2x) donne la cible de chaque contrat à chaque clôture de barre de 4 h ;
- **les LLM peuvent seulement freiner** : chaque contrat reçoit un coefficient de 1, 0,5 ou 0, appliqué à la cible du moteur. Ils ne peuvent ni augmenter, ni inverser, ni ouvrir une position que le moteur n'a pas ;
- **le code exécute** : il calcule l'écart entre la cible finale et la position, et n'envoie un ordre que si l'écart dépasse 5 % de l'équité (la bande du banc). Les ordres passent par riskd comme pour tous les autres joueurs.

## 2. Le portefeuille

- `council-perp:tendance`, nom « Conseil Tendance », `kind = "council"` (ligue des conseils), 1 000 €.
- Fichier de config `config/perp-conseil-tendance.toml`, listé seul dans `config/ligue-conseils.toml`. Les anciens conseils sont retirés (`portfolio_retired`, voir la branche de retrait).
- Politique `config/policy-perp-conseil-v4.toml`, profil `aggressive`, avec ces changements :
  - **levier brut ≤ 10x**. Celui du moteur : 0,7x en moyenne à 1x, donc environ 1,4x à 2x, avec des pointes vers 4 à 6x ;
  - **taille d'un ordre ≤ 400 % de l'équité** : le moteur plafonne à 2 par contrat, fois l'échelle 2 ;
  - **stop de protection à 5 %** posé par le code sur chaque position (testé sur le banc : sans effet sur le résultat). La perte au stop doit rester ≤ 25 % par position et ≤ 60 % au total, comme aujourd'hui. Si riskd refuse, le code réduit la taille jusqu'à ce qu'elle passe, au lieu d'abandonner l'ordre ;
  - **règle d'edge** (coût ≤ 33 % du mouvement attendu) : le mouvement attendu d'un ordre du moteur est mesuré hors ligne, pas déclaré. On prend le mouvement brut moyen par trade du moteur sur l'entraînement, calculé une fois et écrit dans la config avec sa source. Le moteur ne doit pas être bloqué par une règle faite pour des LLM qui déclarent leur propre mouvement attendu ;
  - **48 ouvertures ou ajustements par jour** au plus (6 contrats × 6 barres), sans délai minimal : le moteur ne décide que toutes les 4 h ;
  - **arrêt à −60 %**, avec reprise manuelle par le propriétaire.

## 3. Le rythme

- **Une ronde par clôture de barre de 4 h** : 00:00, 04:00, 08:00, 12:00, 16:00 et 20:00 UTC, au premier tick du watcher après HH:00. Les bougies utilisées sont les bougies d'une minute fermées jusqu'à HH:59 de la barre précédente. Le banc a montré que le calage des barres n'importe pas (de +6 à +14 % sur le contrôle).
- **Une ronde de veto en plus**, seulement sur une actualité (`news_item` de Kraken, publication macro du calendrier) ou un réveil de marché à 2 % en 1 h. Elle ne peut que baisser les coefficients en cours, jamais remonter au-dessus de la cible du moteur.
- Le conseil ne suit pas la cadence de 10 min ni les rappels demandés par l'agent. Il garde le quota de rondes de la ligue.

## 4. Le moteur en direct

- **Les données :** il charge depuis le store (`arene/perp/store.py`) les 30 derniers jours de bougies d'une minute (trade) des 6 contrats, sur la grille de minutes, avec les trous comblés comme dans `backtest.load`. La grille est calée pour qu'une barre se termine à HH:59 de 03, 07, 11, 15, 19 et 23 h UTC.
- **Le calcul :** il appelle `trend.latest(data, TrendParams(scale=2.0))`, qui renvoie la cible de chaque contrat en notionnel signé rapporté à l'équité.
- **La garde des données :** si les données de la barre sont incomplètes (plus de 5 % de minutes manquantes sur les dernières 24 h d'un contrat), ce contrat garde sa position et l'incident est journalisé.
- **Le journal :** il reçoit `trend_engine_target` (portefeuille, ts de la barre, cibles par contrat, z, volatilité, version et sha256 des paramètres). L'événement est écrit avant la délibération.

## 5. Le conseil (les LLM)

Il compte 3 membres Haiku et 1 Président Opus (`claude-opus-5-5`). Chacun reçoit :
- l'instantané habituel : positions, équité, levier, actualités, calendrier, `bilan_du_conseil` ;
- la cible du moteur ;
- le bilan du moteur sur le banc : ce qu'il gagne en tendance, ce qu'il perd en fourchette.

Les membres :
1. **Le Veilleur d'actualités :** une annonce de Kraken (incident, maintenance, contrat en mode spécial) ou une publication macro dans l'heure qui vient justifie 0,5 ou 0 sur les contrats touchés, pour la durée de l'événement.
2. **Le Contrôleur de données :** des prix incohérents entre sources, des trous ou une vue périmée justifient 0.
3. **L'Avocat du risque :** il signale quand toutes les positions vont dans le même sens, parce que les 6 contrats sont corrélés et ne font en pratique qu'un seul pari, et quand le drawdown approche de l'arrêt. Il peut proposer 0,5. Il ne peut jamais proposer de couper une tendance parce qu'il « pense qu'elle va se retourner » : c'est le moteur qui en juge.
4. **Le Président :** il tranche, avec un coefficient par contrat dans {0, 0,5, 1} et une durée de validité (au plus jusqu'à la barre suivante). Le coefficient par défaut est **1**. Il justifie chaque coefficient différent de 1 en une phrase factuelle.

Consignes neutres :
- aucun objectif de doublement ;
- aucune incitation à trader ;
- le rôle du conseil est d'éviter les accidents, pas de prédire.

Si le Président échoue ou dépasse son délai, les coefficients valent 1 : on applique le moteur seul.

## 6. Le témoin « moteur seul »

`benchmark-perp:moteur-tendance` joue la même cible du moteur à 2x, sans les LLM, par le même chemin d'exécution, sur les mêmes rondes de 4 h. L'écart entre ce témoin et le Conseil Tendance mesure ce que les LLM ajoutent ou retirent. Il apparaît dans la ligue des conseils.

## 7. Le site

- La ligue des conseils montre :
  - le Conseil Tendance et son témoin moteur, en trait plein ;
  - les anciens conseils (Haiku, Opus) en pointillé, « retirés le 17/11 ».
- Sur la page du conseil, la ligne de chaque ronde dit :
  - la cible du moteur par contrat ;
  - les coefficients du conseil et leur raison ;
  - les ordres passés.
- Il affiche, côte à côte et sans fard, l'objectif fixé (10 %/j) et le rendement par jour réalisé.

## 8. Le coût

Une ronde, c'est 3 appels Haiku et 1 Opus, environ 0,06 à 0,10 $. Avec 6 à 10 rondes par jour, cela fait moins de 1 $/jour. Budget journalier : 5 $.
