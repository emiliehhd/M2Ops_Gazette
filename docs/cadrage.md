# La gazette — Note de cadrage

> Équipe : … · Dépôt : … · Version du 20/10/2026 (TD 1)
> Le détail de chaque sujet de veille est dans `docs/veille/`, les sources dans `sources.csv`.

## 1. Le besoin
Chaque matin, la presse régionale et nationale publie des centaines d'articles. Personne n'a le temps de tous les lire.
La gazette lit automatiquement les articles publiés par au moins 4 journaux régionaux (PQR) et 4 journaux nationaux (PQN), les regroupe par sujet, et publie à **7 h** une édition qui répond à trois questions : **de quoi parle la presse aujourd'hui, quels journaux en parlent, et où lire la suite**.
Le pipeline doit tourner **seul**, tous les matins, et on doit pouvoir **prouver** qu'il a tourné (métriques, alertes, journal de bord).

## 2. Périmètre
| Dedans | Dehors |
|---|---|
| Titre, extrait, lien, date des articles, lus dans les flux RSS publiés par les éditeurs | Texte intégral, images, commentaires, scraping des pages |
| 4 PQR et 4 PQN (voir section 3) | Résumé des articles par un LLM |
| Regroupement par thèmes, nommés par mots-clés | Un « beau » front |
| Une édition par jour à 7 h, archivée | Toute donnée personnelle (profils, abonnés, auteurs de commentaires, suivi) |
| Supervision : métriques, alertes, runbook, journal de bord | |

## 3. Les sources
| PQN | PQR |
|---|---|
| Le Monde | Ouest-France (Bretagne, Pays de la Loire, Normandie) |
| Le Figaro | La Voix du Nord (Hauts-de-France) |
| Libération | Sud Ouest (Nouvelle-Aquitaine) |
| La Croix | La Dépêche du Midi (Occitanie) |

Adresses des flux, conditions d'utilisation et observations : `sources.csv`. Les flux ont été ouverts à la main et vérifiés avec `verifier_sources.py` le 20/10/2026.

**Écartées après vérification :** Les Échos (pas de flux général, seulement des flux par rubrique) ; Le Parisien (flux sans date, sans extrait et sans identifiant : fraîcheur impossible à contrôler).

**Ce que la vérification nous a appris :**
- **Le rythme varie énormément d'une source à l'autre :** Ouest-France renouvelle ses 10 articles en environ 30 minutes, Sud Ouest ses 20 articles en 3 h, Le Monde ses 16 articles en 20 h. Une fréquence de collecte unique ne convient pas : elle doit être **réglée par source**.
- **Les flux contiennent des articles anciens :** 7 articles de plus de 24 h chez La Croix, 10 chez La Dépêche, dont un d'octobre 2025. Le **contrôle de fraîcheur** est indispensable avant l'édition.
- **Certains flux sont imparfaits :** un extrait manquant au Figaro, un XML mal formé à La Croix (lisible quand même). La collecte et le nettoyage doivent **tolérer ces défauts** sans planter.

## 4. Contraintes
- **Heure :** l'édition sort à 7 h (heure de Paris), une par jour.
- **Fraîcheur :** chaque article de l'édition a moins de 24 h.
- **Éditeurs :** leurs conditions d'utilisation sont respectées et notées dans `sources.csv`.
- **Données personnelles :** aucune.
- **Budget zéro :** nos machines pour l'instant, une infrastructure fournie au TD 4 ou 6. Tout doit donc tourner en local avec des outils gratuits.
- **Infra en code :** ce qui tourne est décrit dans des fichiers, jamais cliqué.

7 h et moins de 24 h sont nos **objectifs de service** : ils seront mesurés (voir la supervision).

## 5. Stack retenue et alternatives écartées
| Sujet | Retenu | Écartés | Pourquoi |
|---|---|---|---|
| **1. Récupérer la presse** | Flux **RSS**, avec une **fréquence de collecte réglée par source** (de 15 min pour Ouest-France à 1 h pour les flux lents), dédoublonnés par `guid`, dates en UTC | Sitemaps news (pas d'extrait, faits pour les moteurs de recherche, gardés en secours) ; scraping (interdit, fragile) | Format prévu par l'éditeur pour les machines, avec exactement les champs autorisés ; un seul format pour toutes les sources. Fréquence par source car un flux ne contient que les derniers articles et les rythmes mesurés vont de 30 min à 20 h |
| **2. Faire tourner chaque matin** | **Airflow** (fuseau Europe/Paris) | `cron` (ni reprise, ni historique, piège du fuseau UTC dans les conteneurs, tout à écrire soi-même) ; GitHub Actions `schedule` (heure non garantie, fait pour la CI, pas pour orchestrer un pipeline) | Décrit le pipeline comme un graphe d'étapes (collecte → nettoyage → thèmes → livraison), gère les dépendances, les reprises sur échec et l'historique des runs |
| **3. Stocker** | Architecture **médaillon** : brut en **Parquet** dans un stockage objet S3-compatible (**MinIO**), propre dans **PostgreSQL**, couche « gold » (thèmes et indicateurs de l'édition) dans PostgreSQL | Un service S3 cloud (payant, budget zéro) ; tout stocker dans une seule base (on perd le brut intact pour rejouer et auditer) | Le brut, jamais modifié, permet de rejouer le nettoyage après un bug et de savoir d'où vient chaque donnée ; MinIO imite S3 gratuitement en local, comme en production ; PostgreSQL apporte une contrainte d'unicité (hash de l'URL) pour le dédoublonnage |
| **4. Regrouper par thèmes** | **Embeddings** multilingues + **HDBSCAN** (via BERTopic) ; TF-IDF + K-Means gardé comme **baseline** | TF-IDF + K-Means comme approche principale (ne comprend pas les synonymes, nombre de thèmes fixé à l'avance) ; LLM (hors cadrage, coûteux, non reproductible) | Les extraits sont courts et deux journaux décrivent un même sujet avec des mots différents ; HDBSCAN trouve seul le nombre de thèmes du jour et écarte les articles isolés |
| **5. Surveiller** | Logs structurés JSON, Surveillance faite par **Airflow** + backup **Healthches.io**, | approche (Prometheus + Pushgateway + Grafana ) : trois services de plus alors qu'on utilise déjà AIrflow pour l'orchestration, qui garde l'historique de chasue exécution.| Historique chiffré de chaque run, tableau de bord et alertes ; standard du métier, gratuit |
| **6. Infra en code** | **Dockerfile + Docker Compose** (pipeline, Airflow, PostgreSQL, MinIO, Prometheus, Grafana) | Terraform, pour l'instant (rien à provisionner dans le cloud avant le TD 4/6 ; à reconsidérer pour la mise en production) | Rend le pipeline reproductible sur toutes nos machines ; cohérent avec le socle du TD 2 |
| **Conteneurs** | **Docker** | Podman (compatible, mais moins répandu et moins documenté pour Compose) | Standard, utilisé dans le TD 2 |

## 6. Architecture
(capture : `docs/img/schema.png`)

**Ce qui circule :** des items RSS (XML) → des articles bruts (titre, extrait, lien, date, source, date de collecte) → des articles propres → des thèmes du jour → l'édition. Les métriques de chaque étape partent vers la supervision.

**Quand :** la collecte tourne en continu, à une fréquence propre à chaque source (toutes les 15 min pour les flux rapides comme Ouest-France, toutes les heures pour les autres) ; la chaîne nettoyage → thèmes → livraison démarre chaque matin vers 5 h 30 (heure de Paris), pour une édition prête avant 7 h.

**Où ça tourne :** tous les services en conteneurs Docker, décrits dans `docker-compose.yml`, sur nos machines pour l'instant ; sur l'infrastructure fournie à partir du TD 4 ou 6.

## 7. Risques
| Risque | Conséquence | Parade |
|---|---|---|
| Un flux change d'adresse ou tombe (déjà vu : Les Échos, ancienne adresse de La Voix du Nord) | Une source manque dans l'édition | Métrique et alerte par source ; `verifier_sources.py` pour revérifier ; sources de réserve (Le Télégramme, Le Progrès) |
| Flux trop rapide pour la fréquence de collecte (Ouest-France : 10 articles en 30 min) | Articles perdus entre deux passages | Fréquence réglée par source ; alerte si les articles d'un passage ne recoupent plus ceux du précédent |
| Articles anciens dans les flux (jusqu'à un an à La Dépêche) | Article de plus de 24 h dans l'édition, objectif de service non tenu | Filtre de fraîcheur au nettoyage, contrôle avant publication, alerte dédiée |
| Flux imparfaits (XML mal formé, extrait manquant) | Plantage de la collecte ou article inexploitable | Lecture tolérante, une source en erreur n'arrête pas les autres, règles de qualité documentées |
| Nos PC sont éteints à 5 h 30 (avant l'infra fournie) | Pas d'édition | Accepté jusqu'au TD 4/6 ; l'alerte « édition non publiée à 7 h 05 » le rend visible ; noté au journal de bord |
| Fuseau horaire mal réglé (conteneurs en UTC, heure d'été) | Édition décalée d'une ou deux heures | Fuseau Europe/Paris dans Airflow, dates stockées en UTC, test au changement d'heure |
| Doublons (article republié ou lu à deux passages) | Thèmes faussés | Unicité sur le hash de l'URL dans PostgreSQL, `guid` à la collecte |
| Brut qui grossit sans limite | Disque plein | Mesurer la croissance quotidienne, fixer une durée de conservation (ex. 30 jours) |
| Airflow lourd pour nos machines | Lenteurs, plantages | Configuration minimale, base de métadonnées partagée avec PostgreSQL |
| Thèmes incohérents (modèle mal réglé) | Édition inutile | Baseline TF-IDF pour comparer, runs tracés, rubriques RSS comme étiquettes d'évaluation |
| Conditions d'un éditeur qui changent | Usage non autorisé | Conditions relues et datées dans `sources.csv` |

## 8. Rôles
| Personne | Rôle principal | Suppléant |
|---|---|---|
| … | Collecte et sources (1) | |
| … | Ordonnancement et exploitation (2) | |
| … | Stockage et qualité des données (3) | |
| … | Thèmes / MLOps (4) et supervision (5) | |

À partir du TD 7, un·e responsable d'exploitation par semaine tient le journal de bord.
