# La gazette

Chaque matin, lire la presse quotidienne régionale et nationale et publier un résumé
des thèmes abordés : quels sujets, avec quelles sources, et où lire la suite.
On ne garde que titre, extrait, lien et date, jamais l'article entier.

**État (TD 3) :** toutes les sources actives de `sources.csv` sont collectées toutes les
30 minutes par Airflow. Chaque article est écrit une seule fois dans
`data/articles_bruts/<source>/<id>.json` ; la table `sources` (PostgreSQL) garde l'état de
chaque source (dernière réussite, échecs, ETag). Une source qui échoue 3 fois de suite est
mise en sommeil. Détail des champs : [docs/donnees.md](docs/donnees.md).

## Prérequis

- Git
- Docker Desktop (avec Docker Compose), **lancé**
- Sous Windows : Git Bash (ou WSL) pour les scripts `bin/`

## Lancer (deux commandes)

```bash
git clone <URL-du-dépôt> && cd <nom-du-dépôt>
bin/dev
```

Le script crée `.env` (depuis `.env.example`), construit l'image, démarre PostgreSQL et
lance **une passe de collecte** sur toutes les sources actives. Résultat attendu : une ligne
JSON `source_collectee` par source, puis `passe_terminee`, et des fichiers dans
`data/articles_bruts/`.

> Sous Linux, ne lancez pas ces commandes avec `sudo` : `data/` serait créé par root et la
> collecte (uid 1000) ne pourrait pas y écrire (`PermissionError`). Correctif :
> `sudo chown $USER: data`.

Sans Git Bash, équivalent dans PowerShell :

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data | Out-Null
docker compose up --build --exit-code-from app
```

Lire une seule source (sans mettre à jour la table) :

```bash
docker compose run --rm app python -m gazette.collecte "Libération"
```

État des sources, et réveil d'une source en sommeil :

```bash
docker compose run --rm app python -m gazette.db etat
docker compose run --rm app python -m gazette.db reveiller "La Voix du Nord"
```

Puis arrêter l'environnement : `docker compose down`.

## Orchestration (Airflow)

La collecte planifiée tourne dans Airflow (DAG `dags/collecte_flux.py`, toutes les 30 min,
heure de Paris). Les services sont dans le profil `orchestration` :

```bash
docker compose --profile orchestration up -d --build
```

Interface : http://localhost:8080 (sans mot de passe, accessible seulement depuis la
machine). Activer le DAG `collecte_flux` avec l'interrupteur ; « Déclencher » lance une
passe tout de suite. Si le port 8080 est déjà pris, choisir un autre port dans `.env`
(`AIRFLOW_PORT=8081`).

Pour qu'elle continue de tourner : laisser la machine allumée et Docker lancé ; ne pas faire
`docker compose down`. Arrêter : `docker compose --profile orchestration down`.

## Tester

```bash
bin/test
```

Résultat attendu : `13 passed`. Les tests de base de données démarrent PostgreSQL ; ceux
du collecteur utilisent un faux éditeur HTTP local (pas besoin d'Internet).

## Développer sans Docker (facultatif)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

## Organisation du dépôt

| Chemin | Contenu |
|---|---|
| `src/gazette/` | Le code : `collecte.py` (parseur, articles bruts), `collecteur.py` (passe multi-sources, reprise, sommeil), `db.py` (migrations, table `sources`) |
| `migrations/` | Migrations SQL versionnées (`001_…`, `002_…`), appliquées une seule fois |
| `dags/` | Le DAG Airflow |
| `infra/airflow/` | L'image Airflow avec notre paquet |
| `tests/` | Tests et exemples enregistrés (`tests/fixtures/`) |
| `docs/` | Cadrage, stratégie CI/CD, dictionnaire de données (`donnees.md`) |
| `sources.csv` | Les 8 sources, leur adresse, leurs conditions d'utilisation |
| `Dockerfile`, `docker-compose.yml` | L'environnement, décrit en code |
| `bin/dev`, `bin/test` | Lancer et tester |
| `.github/workflows/ci.yml` | L'intégration continue |

## Contribuer

Lisez [CONTRIBUTING.md](CONTRIBUTING.md) (branches, commits, revue).
La stratégie d'intégration continue est décrite dans [docs/ci-cd.md](docs/ci-cd.md).