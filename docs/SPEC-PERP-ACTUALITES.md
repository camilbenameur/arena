# Les actualités de la ligue dérivés

## 0. La demande

the owner, le 15/11/2026, après l'étude sur la fraîcheur des news : « Vérifie pour les news, il faut qu'elles voient très très fraîche sinon aucun intérêt, regarde comment font les autres », puis, au choix proposé : **« Calendrier et annonces »**.

Cette décision révise **D6** (« sans web ni actualités », `docs/DECISION-OWNER-agents-traders.md`), mais seulement pour des actualités **officielles et structurées**. Le web libre reste exclu : articles, réseaux sociaux, recherche.

## 1. Pourquoi ces deux sources seulement

L'étude du 15/11 (trois recherches, résumées dans la conversation) a établi trois choses :
- **Les news rapides sont hors de portée.** L'effet d'un tweet ou d'une annonce de listing se joue en secondes, et une partie est dans le prix avant l'annonce. Les robots de listing répondent en moins d'une seconde. Entre un fait de marché et un ordre, l'arène met au mieux 3 min (4 pour un conseil), 5 à 9 min en général : même avec une source instantanée, les modèles arriveraient après tout le monde.
- **Ailleurs, presque personne ne mesure la fraîcheur.** Alpha Arena (Nof1), le cas le plus proche, ne donne aucune news aux modèles. TradingAgents, claude-trading-skills et CryptoTrade lisent leurs news au moment de l'analyse, ou une fois par jour. Les bots Grok cherchent sur X en 12 à 45 s par requête, sans preuve de gain.
- **Il reste ce qui se joue sur l'heure et ce qui est structuré.**
  - Les publications macro : le BTC réagit dans l'heure à une surprise du CPI, et leurs dates sont connues d'avance.
  - Les annonces de la plateforme : incident, maintenance, contrat en état anormal ou retiré.

  Aucun texte libre, donc pas d'injection, et tout reste rejouable.

## 2. Le parcours d'une actualité

1. **Le collecteur** (`arene.perp.collect`, toutes les 5 min) lit, par le client HTTP limité habituel :
   - la page de statut de Kraken (API Statuspage) : `incidents/unresolved.json`, `scheduled-maintenances/upcoming.json` et `scheduled-maintenances/active.json` ;
   - l'état de chaque contrat : `futures.kraken.com/derivatives/api/v3/instruments/status`.

   Quand une annonce ouverte disparaît des listes, il relit `incidents.json` ou `scheduled-maintenances.json` pour connaître son statut final. Une erreur de ces sources est notée dans le rapport du collecteur, sans toucher aux données de marché.
2. **L'archive.** Chaque réponse brute est rangée sous son empreinte (`var-perp/data/news/raw/<2>/<sha256>.json`) : une réponse inchangée n'est rangée qu'une fois. Les éléments normalisés vont dans `var-perp/data/news/items/<AAAA-MM>.jsonl`, un par **version** : une annonce qui change de statut donne un nouvel élément.
3. **Le journal.** La veille (`watcher`), à chaque tick, journalise chaque élément nouveau en `news_item`. Seuls les éléments relevés depuis moins de 2 h sont pris : ceux d'une veille arrêtée plus longtemps sont perdus. **Le journal fait foi** : une ronde ne lit que les `news_item` journalisés à son heure ou avant.
4. **Le dossier de ronde** (`round.json`) fige un bloc `news` :
   - le calendrier des 72 h à venir et des 6 h passées ;
   - les annonces en cours, et celles terminées depuis moins de 24 h, 8 au plus ;
   - l'empreinte de la configuration.

   Le bloc est absent quand les actualités sont coupées : le dossier des rondes d'avant le 15/11 et son empreinte ne changent pas.
5. **L'instantané** envoyé aux modèles et aux conseils gagne le bloc `actualites` (§5).

## 3. Les sources et leur filtre

**La page de statut de Kraken.** Une annonce compte dans deux cas :
- elle touche un composant de **trading** du groupe « Kraken Derivatives » (`derivatives_group_id`) : interface, API REST, websocket, FIX. Les transferts entre comptes et la connexion sont exclus : ils ne touchent pas un portefeuille paper. Le groupe « US Derivatives » est exclu aussi ;
- c'est un avis de retrait (« delist ») qui **cite un des six contrats** par le nom entier de son actif (BTC, XBT ou Bitcoin, etc.). C'est le seul cas où le corps du texte est lu, et seulement pour y chercher ces noms.

**De chaque annonce, on ne garde que :** le titre nettoyé (sans caractère de contrôle ni de balisage, 120 caractères au plus), le statut, l'impact, les heures et le lien court. Jamais le corps.

**L'état de chaque contrat** (`instruments/status` de Kraken Futures) : un élément quand l'état d'un des six contrats change. Les états possibles sont un écart de prix (`dislocation`, à la hausse ou à la baisse) et la volatilité extrême, avec le multiplicateur de marge initiale. Le titre est écrit par le code, en français. Un premier relevé normal ne dit rien ; le retour à la normale donne un élément.

**Le calendrier macro** (`config/calendrier-macro.toml`) : 42 publications du 25/11/2026 au 30/06/2027, relevées le 15/11 sur les calendriers officiels, avec leurs heures en UTC :
- décisions du FOMC : page de la Fed ;
- PIB et PCE : fichier `.ics` du BEA ;
- CPI, emploi et PPI : pages du BLS.

Le BLS refuse les requêtes automatiques : ses dates ont été lues par un outil web et recoupées entre trois de ses pages. Les minutes du FOMC et ses conférences de presse ne sont pas publiées pour ces dates : elles sont absentes. **Le chiffre publié n'est pas fourni** : il faudrait le consensus pour en tirer une surprise, et aucune source gratuite ne le donne. Seule la réaction du marché le montre.

Le calendrier finit le 30/06/2027. La veille envoie l'alerte `perp_news_calendar_ending` une fois par jour à partir de 30 jours avant. Le compléter ne demande aucun code.

## 4. Les rappels

Deux nouveaux déclencheurs de ronde privée, qui passent par le même quota de rondes, le même budget et la même garde du cycle spot que les autres :
- **`news`** : un `news_item` marqué `wake` a été journalisé depuis la dernière ronde du portefeuille, il y a moins d'une heure. Sont marqués `wake` :
  - un incident, ouvert ou résolu (le retour du trading compte aussi) ;
  - une maintenance prévue ou en cours ;
  - un contrat en état anormal.

  Une maintenance terminée et le retour d'un contrat à la normale ne rappellent pas.
- **`calendar`** : une publication du FOMC, du CPI, de l'emploi ou du PCE (`calendar_wake_kinds`) date de 3 minutes (`calendar_wake_after_min`). Les bougies de 1 minute de la réaction sont alors closes. Le rappel est servi par le tick qui commence au plus 2,5 min avant, jusqu'à 30 min après, à tout portefeuille dont la dernière ronde a commencé avant ce moment. Le PPI et le PIB sont seulement montrés.

Quand un portefeuille a déjà un autre déclencheur (alerte, rappel demandé), l'actualité s'y ajoute (`declencheur.news`). La cadence de 10 min, elle, cède la place au déclencheur `news` ou `calendar`. Délai attendu : 3 à 10 min après l'annonce pour une IA seule, 4 à 12 min pour un conseil.

## 5. Ce que voient les modèles

Bloc `actualites` de l'instantané :
- `calendrier_macro` : `publication`, `type`, `heure_utc`, `dans_min` (négatif : déjà publiée) et `te_rappelle` ;
- `annonces_kraken` : `titre`, `type` (incident, maintenance, retrait de contrat, état du contrat), `statut`, `impact`, `debut_utc`, `fin_utc`, `vue_a_utc` et `contrats` ;
- `note` : d'où viennent ces données, et l'absence des chiffres publiés.

**Consignes :** v8 pour les 4 IA (`arene/perp/prompt/v8.md`), v3 pour les conseils (`arene/perp/prompt/conseil/v3/`). Elles reprennent v7 et v2, avec cinq changements :
- les deux déclencheurs ;
- le bloc `actualites` dans la liste de ce que reçoit le modèle ;
- une section « Les actualités » ;
- les titres d'annonces comptés comme de la donnée, jamais comme une consigne ;
- « N'invente aucune donnée » devient : pas d'autre actualité que celles du bloc, et rien de ce que le modèle croit savoir de l'actualité récente.

Les outils ne changent pas, ni leur nombre. Les consignes v7 et v2 restent dans le dépôt : ce sont celles des rondes d'avant.

## 6. La configuration

`config/perp-actualites.toml`, haché avec le calendrier. Son empreinte est dans le bloc `news` de chaque dossier.
- `enabled = false` retire les actualités de l'instantané et des rappels ; le collecteur cesse de les relever.
- Une configuration invalide coupe les actualités, avec l'alerte `perp_news_config_invalid`. Elle ne coupe jamais le collecteur, la veille ni les modèles.

## 7. Le site

Fait en parallèle dans `arene/site/` :
- l'étiquette des deux déclencheurs ;
- un bloc « Actualités » : les publications à venir et les annonces de Kraken des 7 derniers jours, dans la dernière version de chacune ;
- la méthode à jour.
