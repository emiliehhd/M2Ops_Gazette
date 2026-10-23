# Qualité des données

> Brouillon du TD 4, étape 1 · Analyse de la collecte du 23/10/2026 (une passe, 07:59 à 08:30 UTC) · 310 articles bruts

## 1. Reprise : ce que la collecte a produit

| Source | Articles | Rubrique renseignée | Plus de 24 h à la collecte | Extrait tronqué (« … ») |
|---|---|---|---|---|
| La Dépêche du Midi | 101 | oui | 8 | 87 |
| Libération | 55 | non | 0 | 0 |
| La Croix | 55 | non | 0 | 1 |
| Sud Ouest | 23 | non | 0 | 0 |
| Le Figaro | 22 | oui | 1 | 0 |
| Le Progrès | 21 | oui | 0 | 0 |
| Le Monde | 19 | non | 0 | 0 |
| Ouest-France | 14 | non | 0 | 0 |
| **Total** | **310** | | **9** | **88** |

La Voix du Nord est absente : elle répond 403 et est en sommeil (remplacée par Le Progrès).

**Ce que les données brutes ont de propre :** aucun titre vide, aucune date absente ou dans le futur, aucun balisage HTML, aucun encodage cassé (`Ã©`), aucun doublon exact (ni de lien, ni de titre). Toutes les dates sont déjà en UTC.

**Ce qu'elles ont de moins propre :**

- des espaces insécables (U+00A0) dans les titres, par exemple « jeux : » ;
- des extraits tronqués à environ 220 caractères chez La Dépêche du Midi ;
- des articles anciens dans les flux : 9 articles de plus de 24 h à la fin de la passe, dont un de 372 jours (La Dépêche du Midi) ;
- une rubrique disponible pour 3 sources seulement (La Dépêche du Midi, Le Figaro, Le Progrès) : une règle fondée sur la rubrique ne peut pas s'appliquer à toutes les sources ;
- des articles qui ne sont pas de l'actualité : voir section 2.

Limite de cet échantillon : une seule passe, un seul matin. Aucun horoscope, programme TV ni jeu classique n'y figure : ces catégories de l'énoncé devront être cherchées sur trois matins.

## 2. Les dix pollueurs (candidats à confirmer)

| # | Source · rubrique | Titre (début) | Pourquoi il n'a pas sa place dans la gazette |
|---|---|---|---|
| 1 | La Dépêche du Midi · Médias-Communication | La Dépêche du Midi lance son espace jeux : à vos neurones, prêts, jouez ! | Auto-promotion du journal ; publié il y a 372 jours |
| 2 | La Dépêche du Midi · Tourisme | Un voyage exceptionnel de Pékin à la Grande Muraille : découvrez la Chine avec La Dépêche du Midi | Offre commerciale du journal, pas de l'actualité |
| 3 | La Dépêche du Midi · Télé - médias | Wanted : concept, candidats, rôle du public… on vous présente le nouveau jeu de course-poursuite | Présentation d'un jeu télévisé |
| 4 | Le Progrès · Magazine Lifestyle | Témoignage. « J'ai peur de reprendre du poids » : Émilie raconte… | Témoignage d'une personne privée, sujet de santé : hors actualité et sensible pour les données personnelles |
| 5 | Le Progrès · Magazine Automobile | Automobile. Rouler au fioul à la place du gasoil : bonne ou mauvaise idée ? | Contenu « magazine » et conseil pratique |
| 6 | Le Progrès · People | Concours. Miss Univers : Garance Authié représentera la France… | Contenu people (à discuter : le mot « Concours » n'annonce pas ici un jeu) |
| 7 | La Dépêche du Midi · Manifestations | REPLAY. Manifestations du 24 octobre : Emmanuel Macron recevra les organisations lycéennes… | Rediffusion d'un « DIRECT. » sur le même événement : doublon |
| 8 | Le Figaro · Vox Société | L'éditorial du Figaro Magazine : « Ouvrir les yeux sur les émeutes du 17 octobre » | Éditorial : opinion, pas un fait (à décider) |
| 9 | La Croix | Notre sœur la Terre | Chronique, titre sans contexte (le titre seul ne dit rien du sujet) |
| 10 | La Dépêche du Midi | CARTE. Prix des carburants : tarifs, stations et bornes de recharge électrique | Outil de service publié il y a 36 jours : hors fraîcheur |

## 3. Pièges : des cas qui ressemblent à des pollueurs mais n'en sont pas

À garder en tête pour ne pas écrire de règles trop gourmandes.

- **« Carnet noir » (La Dépêche du Midi) et « Nécrologie » (Le Progrès)** : dans cet échantillon, ils portent sur la mort d'une personnalité publique (Jean-Paul Huchon), un vrai sujet d'actualité. Une règle sur ces rubriques rejetterait un article légitime. Elle est pourtant utile pour écarter de vrais avis de décès de particuliers (données personnelles).
- **« Concours. » dans un titre** : ne désigne pas toujours un jeu (voir le n° 6).
- **« DIRECT » et « EN DIRECT »** : 11 articles. Ce sont souvent des sujets d'actualité à garder ; seul un « REPLAY » doublonne un « DIRECT ».
- **Même sujet dans plusieurs journaux** : la mort de Jean-Paul Huchon est traitée par six sources, la tempête Austen par plusieurs. Ce n'est pas de la pollution : c'est ce que la gazette doit montrer (« quels journaux en parlent »). Un dédoublonnage approximatif **entre sources** supprimerait cette information ; il doit se faire **dans une même source**, le regroupement entre sources étant le travail du TD 5.
- **Seuil de similarité** : à 0,6 (Jaccard sur les mots du titre), deux articles différents de La Dépêche du Midi (« Manifestation du 24 octobre à Toulouse : … ») sont rapprochés à tort. Le seuil devra être plus haut (autour de 0,8, à calibrer).

## 4. Points de conformité relevés dans le brut

- Le champ `payload` contient un nom d'**auteur** pour 103 articles (Libération 55 sur 55, La Croix 48 sur 55). Un nom de journaliste est une donnée personnelle : il ne doit pas être recopié dans `articles_propres`, et son traitement dans le brut est à décider et à écrire dans `docs/donnees.md`.
- Le reste du `payload` (identifiant, titre, lien, résumé, date) est limité à ce qu'on a le droit de garder.

## 5. Règles d'exclusion (à compléter à l'étape 3)

| Identifiant | Ce qu'elle écarte | Pourquoi | Exemple | Statut |
|---|---|---|---|---|
| | | | | |

## 6. Ajustements après trois matins de collecte (à compléter pour la prochaine séance)

| Date | Règle modifiée | Ce qui a changé | Pourquoi |
|---|---|---|---|
| | | | |
