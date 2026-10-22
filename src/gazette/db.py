"""Base PostgreSQL : migrations versionnées et table `sources`."""
import os
import sys
from pathlib import Path

import psycopg

from gazette.collecte import lire_sources

DOSSIER_MIGRATIONS = Path(os.environ.get("GAZETTE_MIGRATIONS", "migrations"))


def dsn() -> str:
    """Adresse de la base, construite depuis les variables de .env."""
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'db')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def connexion(adresse: str | None = None) -> psycopg.Connection:
    return psycopg.connect(adresse or dsn())


def migrer(conn: psycopg.Connection, dossier: Path = DOSSIER_MIGRATIONS) -> list[str]:
    """Applique, dans l'ordre, les fichiers .sql pas encore appliqués. Renvoie leurs noms."""
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY,"
            " appliquee_le TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    deja = {v for (v,) in conn.execute("SELECT version FROM schema_migrations")}
    appliquees = []
    for fichier in sorted(dossier.glob("*.sql")):
        if fichier.name in deja:
            continue
        with conn.transaction():  # tout le fichier, ou rien
            conn.execute(fichier.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (fichier.name,))
        appliquees.append(fichier.name)
    return appliquees


def synchroniser_sources(conn: psycopg.Connection, sources: list[dict]) -> int:
    """Ajoute ou met à jour les sources de sources.csv, sans toucher à leur état."""
    with conn.transaction():
        for s in sources:
            conn.execute(
                "INSERT INTO sources (nom, type, url_flux) VALUES (%s, %s, %s) "
                "ON CONFLICT (nom) DO UPDATE SET type = EXCLUDED.type, url_flux = EXCLUDED.url_flux",
                (s["nom"], s["type"], s["url"]),
            )
    return len(sources)


def main() -> None:
    commande = sys.argv[1] if len(sys.argv) > 1 else "migrer"
    with connexion() as conn:
        if commande == "migrer":
            appliquees = migrer(conn)
            print(f"Migrations appliquées : {appliquees or 'aucune (base à jour)'}")
            n = synchroniser_sources(conn, lire_sources())
            print(f"{n} sources synchronisées depuis sources.csv")
        elif commande == "etat":
            lignes = conn.execute(
                "SELECT nom, type, actif, echecs_consecutifs, derniere_reussite "
                "FROM sources ORDER BY type, nom"
            ).fetchall()
            for nom, type_, actif, echecs, reussite in lignes:
                etat = "actif" if actif else "EN SOMMEIL"
                print(f"{nom:20} {type_}  {etat:10}  échecs={echecs}  dernière réussite={reussite}")
        elif commande == "reveiller" and len(sys.argv) > 2:
            nom = sys.argv[2]
            ligne = conn.execute(
                "UPDATE sources SET actif = TRUE, echecs_consecutifs = 0 WHERE nom = %s RETURNING nom",
                (nom,),
            ).fetchone()
            print(f"{nom} réveillée" if ligne else f"Source inconnue : {nom}")
        else:
            sys.exit(f"Commande inconnue : {commande} (attendu : migrer, etat, reveiller \"Nom\")")


if __name__ == "__main__":
    main()
