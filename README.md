# La gazette

Chaque matin, lire la presse quotidienne régionale et nationale et publier un résumé
des thèmes abordés : quels sujets, avec quelles sources, et où lire la suite.
On ne garde que titre, extrait, lien et date, jamais l'article entier.

**État (TD 2) :** une première source (Le Monde) est lue depuis son flux RSS et écrite
en JSON (`data/le_monde.json`). Le format de sortie est temporaire : au TD 3, le brut
passera en Parquet dans un stockage compatible S3.

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
lance la collecte. Résultat attendu : le fichier `data/le_monde.json`.

Sans Git Bash, équivalent dans PowerShell :

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data | Out-Null
docker compose up --build --exit-code-from app
```

Pour lire une autre source de `sources.csv` :

```bash
docker compose run --rm app python -m gazette.collecte "Libération"
```

Puis arrêter l'environnement : `docker compose down`.

## Tester

```bash
bin/test
```

Résultat attendu : `5 passed`.

## Développer sans Docker (facultatif)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

## Organisation du dépôt

| Chemin | Contenu |
|---|---|
| `src/gazette/` | Le code (lecture de `sources.csv`, parseur, écriture JSON) |
| `tests/` | Tests et exemples enregistrés (`tests/fixtures/`) |
| `docs/` | Cadrage, stratégie CI/CD |
| `sources.csv` | Les 8 sources, leur adresse, leurs conditions d'utilisation |
| `Dockerfile`, `docker-compose.yml` | L'environnement, décrit en code |
| `bin/dev`, `bin/test` | Lancer et tester |
| `.github/workflows/ci.yml` | L'intégration continue |

## Contribuer

Lisez [CONTRIBUTING.md](CONTRIBUTING.md) (branches, commits, revue).
La stratégie d'intégration continue est décrite dans [docs/ci-cd.md](docs/ci-cd.md).