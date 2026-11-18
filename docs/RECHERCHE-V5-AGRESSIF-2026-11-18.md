# Recherche v5 : un agent de trading agressif, le 18/11/2026

Le but : un agent de trading agressif, quelle que soit la méthode, rentable vite.

Fichiers : `docs/recherche-v5/` (consigne, harnais, journaux des 90 essais, finalistes, script et résultat du contrôle).

## 1. Le protocole

- **Les données :** un an de bougies d'une minute des 6 contrats et de leur funding, du 17/11/2025 au 18/11/2026, téléchargé chez Kraken Futures dans un dossier de recherche à part (`fetch.py`). Les données de la ligue n'ont pas été touchées.
- **Le découpage :**
  - **conception** sur les 245 premiers jours (17/11/2025 → 20/07/2026), la seule partie que voyaient les chercheurs ;
  - **contrôle scellé** sur les 121 jours suivants (20/07 → 18/11/2026), lu une seule fois, pour tous les finalistes en même temps.
- **Le banc :** `arene/perp/lab/backtest.py`, modèle de fill pessimiste-perp-v1 : exécution à l'ouverture de la minute suivante, 24 bp par aller-retour, funding horaire, levier brut ≤ 10x.
- **Les chercheurs :** cinq agents en parallèle, un par famille, avec 40 essais au plus chacun, tous journalisés. Une stratégie retenue devait :
  - viser le rendement composé maximal ;
  - ne jamais être ruinée ;
  - avoir un drawdown d'au plus 50 % ;
  - être positive sur au moins 3 blocs sur 4.
- **La causalité de chaque finaliste :** vérifiée en recalculant ses cibles sur des données tronquées (écart nul pour les 4).

## 2. Le moteur de tendance en service perd sur l'année

Le moteur gelé à 2x, celui du Conseil Tendance et de son témoin, a été rejoué sur l'année :

| Période | Rendement | Drawdown max |
|---|---|---|
| Conception (215 j, de novembre 2025 à juillet 2026) | **−20,8 %** | **−62,5 %** |
| Contrôle (121 j, de juillet à novembre 2026) | +69,2 % | −26,8 % |
| Année | +36,3 % | −62,5 % |

Entre février et avril 2026, il a perdu 50 %, dans un marché en fourchette avec des retournements rapides. Son drawdown sur l'année dépasse l'arrêt de la politique, fixé à −60 %. Son bon résultat de la recherche v4 venait d'un seul épisode de tendance, celui d'août à novembre.

## 3. Les cinq familles

| Famille | Essais | Résultat |
|---|---|---|
| Tendance agressive (Donchian, ensembles, momentum) | 9 | Aucun finaliste. Pas d'effet de tendance sur 3 des 4 blocs, même à coût nul. |
| Intraday (5 min à 1 jour : sessions, heure, jour, volume) | 15 | Aucun finaliste. Le gain brut par trade reste sous les 24 bp de coût. |
| Transversal (avance-retard, paires, momentum relatif) | 16 | Un candidat faible : +7,6 % en conception, fragile. |
| Funding (portage, foule, transversal) | 24 | Deux finalistes : +114 % et +161 % en conception, positifs sur 4 blocs sur 4. |
| Chocs (mèches de liquidation) | 26 | Un finaliste : +187 % en conception, 3 blocs positifs sur 4. |

## 4. Le contrôle scellé

| Finaliste | Conception | **Contrôle (121 j)** | Drawdown sur le contrôle | Année |
|---|---|---|---|---|
| Chocs : retour après une mèche de plus de 4,5 % | +187 % | **+37,6 %** | −23,5 % | +296 % (dd −37 %) |
| Transversal : retournement + faible volatilité | +7,6 % | +20,8 % | −26,3 % | +30 % |
| Funding : bascule au funding lissé sur 16 h | +114 % | **−45,2 %** | −66,9 % | +18 % |
| Funding : bascule au funding lissé sur 12 h | +161 % | **−64,7 %** | −83,1 % | −7 % |
| (Référence : tendance 2x) | −20,8 % | +69,2 % | −26,8 % | +36 % (dd −62 %) |

- **Le funding s'effondre :** c'était du surajustement. Le plateau de réglages étroit le laissait craindre, et le contrôle le confirme.
- **Les chocs tiennent :**
  - 39 trades sur le contrôle, répartis sur 18 jours différents, avec 69 % de gagnants et aucune dépendance à un seul épisode ;
  - la règle : quand un contrat bouge de plus de 4,5 % (en log) en 5, 15 ou 30 minutes, on prend le sens inverse à 2x pendant 60 minutes, avec un stop à 5 % ;
  - la raison : une cascade de liquidations dépasse le prix d'équilibre, puis se corrige.

## 5. La condition décisive : la vitesse

Le banc entre à l'ouverture de la minute qui suit le choc. Avec un retard d'exécution :

| Retard d'entrée | Conception | Contrôle |
|---|---|---|
| 0 min | +187 % | **+37,6 %** |
| 1 min | +140 % | +13,9 % |
| 2 à 3 min | +105 à +109 % | +5,7 % |
| 5 min | +111 % | **−8,1 %** |
| 10 min | +55 % | −13,6 % |

Le watcher de la ligue ne tourne que toutes les 5 minutes : à cette cadence, la stratégie perd. Il lui faut **un processus dédié qui réagit en moins d'une minute** : il lit les prix toutes les quelques secondes et n'envoie l'ordre que sur un choc. Le gain se fait dans la première minute de la correction.

## 6. Ce qu'on peut en attendre, honnêtement

- **Au mieux :** environ +0,26 %/jour sur le contrôle, soit +38 % en 4 mois, avec des reculs de 25 à 37 %.
- Le gain arrive par à-coups : un choc tous les quelques jours, rien entre deux.
- Le résultat repose sur peu d'événements : environ 60 jours de choc sur l'année.
- En réel, une mèche de liquidation s'accompagne d'un carnet vide : le glissement de 5 bp du banc y est optimiste. En paper, le simulateur de la ligue applique le même modèle que le banc.
- Les 10 %/jour restent hors de portée. Aucune des 90 stratégies essayées n'en approche sur la durée.

## 7. La suite proposée

1. **Construire le « chasseur de mèches » en paper**, comme portefeuille de la ligue dérivés :
   - un processus rapide lit les prix toutes les 5 à 10 s, repère un mouvement de plus de 4,5 % sur 5, 15 ou 30 min, et entre à contre-sens à 2x pendant 60 minutes, avec un stop à 5 % ;
   - les ordres passent par riskd, comme pour les autres joueurs ;
   - un témoin « chasseur au rythme de 5 min » mesure ce que la vitesse rapporte.
2. **Revoir le Conseil Tendance :** son moteur a un recul de −62 % sur l'année. On peut le garder tel quel, en sachant qu'il peut atteindre son arrêt à −60 %, ou le réduire à 1x.
