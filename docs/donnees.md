# Données — dictionnaire

Ce que la collecte produit et ce qu'elle retient. Début du dictionnaire de données (TD 3) ;
complété au fil des TD (articles propres au TD 4, thèmes au TD 5).

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
| `version` | Nom du fichier de migration appliqué (`001_creer_table_sources.sql`) |
| `appliquee_le` | Date d'application |

## 4. Journal de la collecte (une ligne JSON par événement)

| `evenement` | Champs |
|---|---|
| `source_collectee` | `source`, `statut` (`ok`, `inchange`, `erreur`), `http`, `tentatives`, `recus`, `ecrits`, `ignores`, `duree_s`, `erreur` |
| `source_mise_en_sommeil` | `source`, `echecs_consecutifs`, `derniere_erreur` |
| `passe_terminee` | `sources`, `ok`, `inchangees`, `erreurs`, `en_sommeil`, `recus`, `ecrits`, `ignores`, `duree_s` |

Erreurs : **transitoires** (HTTP 429, 5xx, timeout, réseau) réessayées après 2 s, 10 s, 30 s ;
**permanentes** (autres 4xx, flux illisible) sans nouvel essai. Dans les deux cas, un échec
final incrémente `echecs_consecutifs`.
