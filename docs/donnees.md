# Données — dictionnaire

Ce que la collecte produit et ce qu'elle retient. Début du dictionnaire de données (TD 3) ;
complété au fil des TD (articles propres, rejets, métriques et contrôles au TD 4, thèmes au TD 5).

Règles communes :
- **Dates** : ISO 8601 en **UTC** (`2026-10-22T08:45:41+00:00`). La date telle que publiée
  par l'éditeur reste dans `payload`.
- **Jamais** : texte intégral, images, commentaires, données personnelles.

## 1. Articles bruts — `data/articles_bruts/<source>/<id>.json`

Un fichier JSON par article, écrit **une seule fois** : la clé naturelle est `(source, lien)`.
Un article déjà présent n'est jamais réécrit (création exclusive du fichier), donc relancer
la collecte ne crée aucun doublon. `<source>` est le nom de la source sans accents
(`la_depeche_du_midi`). Le dossier n'est pas versionné (`.gitignore`).

| Champ | Type | Toujours rempli | Description | Origine dans le flux (RSS 2.0 / Atom) |
|---|---|---|---|---|
| `id` | texte (20 car.) | oui | Empreinte SHA-256 de `source` + `lien`, tronquée. Stable : même article, même `id` | calculé |
| `source` | texte | oui | Nom de la source, tel que dans `sources.csv` | `sources.csv` |
| `lien` | texte (URL) | oui | Adresse de l'article chez l'éditeur (« lire la suite »). Un item sans lien est ignoré | `link` / `link href` |
| `titre` | texte | oui (peut être vide) | Titre, espaces de début et de fin retirés | `title` |
| `resume` | texte | non (vide possible) | Extrait fourni par l'éditeur, tel quel (peut contenir du HTML) | `description` / `summary` |
| `publie_le` | date UTC | non (`null` possible) | Date de publication, sinon de mise à jour, convertie en UTC | `pubDate` / `published`, sinon `updated` |
| `recupere_le` | date UTC | oui | Moment où **nous** avons lu le flux | calculé |
| `rubrique` | texte | non (`null` possible) | Première catégorie de l'item. Absente du flux « À la une » du Monde | `category` / `category term` |
| `payload` | objet | oui | Les champs du flux **tels que reçus**, pour pouvoir rejouer le nettoyage : `id`, `title`, `link`, `summary`, `published`, `updated`, `author` quand ils existent. **Jamais** `content` (texte intégral) ni `media_*` (images) | flux |

Pièges connus, à traiter au nettoyage (TD 4) :
- `resume` vide sur certains items (observé : Le Figaro le 20/10, Sud Ouest le 22/10) ;
- `publie_le` ancien : La Dépêche du Midi garde un article de 2025 dans son flux ;
- `guid` pas fiable partout : il n'est **pas** utilisé comme clé.

## 2. Table `sources` (PostgreSQL)

Créée par `migrations/001_creer_table_sources.sql`. Une ligne par source ; remplie depuis
`sources.csv` à chaque passe, sans écraser l'état ci-dessous.

| Colonne | Type | Description |
|---|---|---|
| `nom` | texte, clé primaire | Nom de la source |
| `type` | `PQN` ou `PQR` | Presse quotidienne nationale ou régionale |
| `url_flux` | texte | Adresse du flux (colonne `acces` de `sources.csv`) |
| `actif` | booléen | `false` = **en sommeil** : la source n'est plus appelée |
| `derniere_reussite` | date (fuseau) | Dernière passe réussie (y compris « inchangé », HTTP 304) |
| `echecs_consecutifs` | entier ≥ 0 | Remis à 0 à chaque réussite. **À 3, la source passe en sommeil** |
| `etag` | texte | Dernier `ETag` reçu, renvoyé en `If-None-Match` |
| `last_modified` | texte | Dernier `Last-Modified` reçu, renvoyé en `If-Modified-Since` |

Réveiller une source après correction :
`docker compose run --rm app python -m gazette.db reveiller "Nom"`.

## 3. Table `schema_migrations` (PostgreSQL)

| Colonne | Description |
|---|---|
| `version` | Nom du fichier de migration appliqué (`001_creer_table_sources.sql`, `002_creer_tables_propres_et_rejets.sql`, `003_creer_metriques_et_controles.sql`) |
| `appliquee_le` | Date d'application |

## 4. Journal de la collecte (une ligne JSON par événement)

| `evenement` | Champs |
|---|---|
| `source_collectee` | `source`, `statut` (`ok`, `inchange`, `erreur`), `http`, `tentatives`, `recus`, `ecrits`, `ignores`, `duree_s`, `erreur` |
| `source_mise_en_sommeil` | `source`, `echecs_consecutifs`, `derniere_erreur` |
| `passe_terminee` | `sources`, `ok`, `inchangees`, `erreurs`, `en_sommeil`, `recus`, `ecrits`, `ignores`, `duree_s` |
| `passe_nettoyage_terminee` | `entres`, `gardes`, `rejetes`, `illisibles`, `par_regle`, `rapport` |
| `brut_illisible` | `fichier` (ou `id`) : fichier du brut ni JSON valide ni complet, ignoré |
| `controles_termines` | `en_echec` (liste d'identifiants de contrôles), `ok` |
| `alerte_envoyee` | `controles` : contrôles annoncés sur Discord |
| `alerte_non_envoyee` | `erreur` : Discord a refusé ou était injoignable (jamais l'adresse du webhook) |
| `alerte_non_configuree` | `controles` : alerte à envoyer, mais `DISCORD_WEBHOOK_URL` est vide |

Erreurs : **transitoires** (HTTP 429, 5xx, timeout, réseau) réessayées après 2 s, 10 s, 30 s ;
**permanentes** (autres 4xx, flux illisible) sans nouvel essai. Dans les deux cas, un échec
final incrémente `echecs_consecutifs`.

## 5. Table `articles_propres` (PostgreSQL)

Créée par `migrations/002_creer_tables_propres_et_rejets.sql`. Les articles **gardés** après
normalisation et règles d'exclusion. Alimentée à chaque passe par `gazette.nettoyage`.

| Colonne | Type | Description |
|---|---|---|
| `id` | texte, clé primaire | **Identique à l'`id` du brut** : c'est le lien de traçabilité vers `data/articles_bruts/<source>/<id>.json` |
| `source` | texte | Nom de la source |
| `lien` | texte | Adresse de l'article chez l'éditeur. `(source, lien)` est unique |
| `titre` | texte, non vide | Titre normalisé : sans HTML, entités décodées, espaces uniques, encodage réparé |
| `extrait` | texte (≤ 300 caractères) | Extrait normalisé, coupé à la fin d'un mot avec « … » s'il dépasse |
| `publie_le` | date (fuseau), non nulle | Date de publication en UTC |
| `recupere_le` | date (fuseau) | Moment de la collecte |
| `rubrique` | texte, peut être nul | Rubrique normalisée (absente chez plusieurs sources) |
| `traite_le` | date (fuseau) | Moment du nettoyage ; sert à compter « ce qui a été traité ce jour-là » |

**Ce qu'on ne copie pas :** le champ `payload` du brut et le nom de l'auteur (donnée personnelle).

## 6. Table `rejets` (PostgreSQL)

Les articles **écartés**, avec la règle qui les a écartés (identifiants dans `docs/qualite.md`).

| Colonne | Type | Description |
|---|---|---|
| `id` | texte, clé primaire | `id` du brut |
| `source`, `lien`, `titre` | texte | Comme dans `articles_propres` (pas d'extrait) |
| `regle` | texte | Identifiant de la **première** règle qui s'applique (`R06_autopromo`, `R13_trop_ancien`…) |
| `publie_le`, `recupere_le` | date (fuseau), peuvent être nulles | `publie_le` est nulle pour `R03_date_absente` |
| `traite_le` | date (fuseau) | Moment du nettoyage |

Un article du brut traité figure dans **exactement une** des deux tables. Ceux dont l'`id` n'est
dans aucune des deux restent à traiter à la passe suivante : rejouer le nettoyage ne crée donc
aucun doublon. Aucune clé étrangère vers `sources` : le brut d'une source retirée de
`sources.csv` reste valable.

## 7. Rapport de qualité — `rapports/qualite-AAAA-MM-JJ.md` et `.json`

Un rapport **par jour (UTC)**, recalculé après chaque passe à partir des tables
`articles_propres` et `rejets` (donc toujours à jour). Le dossier `rapports/` n'est pas versionné.

Contenu : articles traités, gardés, rejetés ; rejets par règle ; par source ; les cinq couples
(règle, source) les plus fréquents ; règles à surveiller (au moins 30 % d'une source et au moins
3 articles) ; trois exemples de titres rejetés par règle. Le premier jour compte aussi
l'arriéré du brut, traité en une fois.

## 8. Table `metriques` (PostgreSQL)

Créée par `migrations/003_creer_metriques_et_controles.sql`. Une mesure par ligne ; chaque passe
ajoute ses lignes, ce qui garde l'historique. Liste des métriques : `docs/controles.md`.

| Colonne | Type | Description |
|---|---|---|
| `id` | entier auto-incrémenté | Clé primaire |
| `mesure_le` | date (fuseau) | Moment de la mesure |
| `nom` | texte | Nom de la métrique (`collecte_recus`, `jour_taux_rejet_par_source`…) |
| `etiquette` | texte | De quoi on parle : une source, une règle, un contrôle ; vide pour une valeur globale |
| `valeur` | nombre | La mesure |

## 9. Table `controles_etat` (PostgreSQL)

L'état de chaque contrôle de qualité, pour n'alerter qu'à l'apparition d'une panne, en rappel
après 24 h, et au rétablissement.

| Colonne | Type | Description |
|---|---|---|
| `controle` | texte, clé primaire | Identifiant (`C04_taux_rejet_par_source`…) |
| `en_echec` | booléen | `true` tant que le fait est faux |
| `depuis` | date (fuseau) | Début de l'état actuel |
| `derniere_alerte` | date (fuseau), peut être nulle | Dernier message envoyé ; nulle si la panne n'a jamais pu être annoncée |
| `detail` | texte | Ce qui a été constaté lors du dernier contrôle |

