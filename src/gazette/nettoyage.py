"""Nettoyage : du brut aux articles propres, aux rejets et au rapport de qualité.

À chaque passe : on repère les articles du brut pas encore traités (leur id n'est ni dans
`articles_propres` ni dans `rejets`), on les normalise, on applique les règles d'exclusion,
on enregistre le résultat, puis on régénère le rapport de qualité du jour.

Rejouer le nettoyage ne crée aucun doublon : un article déjà traité n'est jamais retraité.
"""

import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg

from gazette.collecte import DOSSIER_BRUTS
from gazette.collecteur import journal
from gazette.db import connexion, migrer
from gazette.normalisation import normaliser_article
from gazette.rapport import construire_rapport, ecrire_rapport
from gazette.regles import filtrer

DOSSIER_RAPPORTS = Path(os.environ.get("GAZETTE_RAPPORTS", "rapports"))
# Pour repérer les doublons, un nouvel article est comparé aux articles gardés depuis moins de
# 3 jours : un article doit avoir moins de 24 h, donc un doublon plus ancien n'a pas de sens.
FENETRE_DOUBLONS = timedelta(days=3)


def ids_traites(conn: psycopg.Connection) -> set[str]:
    """Identifiants des articles du brut déjà traités (gardés ou rejetés)."""
    lignes = conn.execute("SELECT id FROM articles_propres UNION SELECT id FROM rejets")
    return {i for (i,) in lignes}


def lire_bruts_non_traites(conn: psycopg.Connection, dossier: Path) -> tuple[list[dict], int]:
    """Articles du brut pas encore traités. Renvoie (articles, nombre de fichiers illisibles).

    Un fichier illisible n'arrête pas la passe : il est signalé dans le journal et compté.
    """
    deja = ids_traites(conn)
    articles, illisibles = [], 0
    for chemin in sorted(dossier.glob("*/*.json")):
        if chemin.stem in deja:
            continue
        try:
            articles.append(json.loads(chemin.read_text(encoding="utf-8")))
        except (OSError, ValueError):  # ValueError couvre JSON invalide et texte illisible
            illisibles += 1
            journal("brut_illisible", fichier=str(chemin))
    return articles, illisibles


def references_doublons(conn: psycopg.Connection, maintenant: datetime) -> list[dict]:
    """Articles gardés récemment, auxquels comparer les nouveaux pour trouver les doublons."""
    lignes = conn.execute(
        "SELECT source, titre FROM articles_propres WHERE traite_le >= %s",
        (maintenant - FENETRE_DOUBLONS,),
    )
    return [{"source": source, "titre": titre} for source, titre in lignes]


def enregistrer(
    conn: psycopg.Connection,
    gardes: list[dict],
    rejets: list[tuple[dict, str]],
    traite_le: datetime,
) -> None:
    """Écrit les décisions dans une seule transaction : tout, ou rien."""
    with conn.transaction():
        for article in gardes:
            conn.execute(
                "INSERT INTO articles_propres "
                "(id, source, lien, titre, extrait, publie_le, recupere_le, rubrique, traite_le) "
                "VALUES (%(id)s, %(source)s, %(lien)s, %(titre)s, %(extrait)s, "
                "%(publie_le)s, %(recupere_le)s, %(rubrique)s, %(traite_le)s) "
                "ON CONFLICT DO NOTHING",
                {**article, "traite_le": traite_le},
            )
        for article, regle in rejets:
            conn.execute(
                "INSERT INTO rejets "
                "(id, source, lien, titre, regle, publie_le, recupere_le, traite_le) "
                "VALUES (%(id)s, %(source)s, %(lien)s, %(titre)s, %(regle)s, "
                "%(publie_le)s, %(recupere_le)s, %(traite_le)s) ON CONFLICT DO NOTHING",
                {**article, "regle": regle, "traite_le": traite_le},
            )


def decisions_du_jour(conn: psycopg.Connection, jour: date) -> list[tuple[str, str, str | None]]:
    """Toutes les décisions prises ce jour-là (jour UTC), pour le rapport de qualité."""
    return conn.execute(
        "SELECT source, titre, NULL::text FROM articles_propres "
        "WHERE (traite_le AT TIME ZONE 'UTC')::date = %(jour)s "
        "UNION ALL "
        "SELECT source, titre, regle FROM rejets "
        "WHERE (traite_le AT TIME ZONE 'UTC')::date = %(jour)s",
        {"jour": jour},
    ).fetchall()


def traiter_passe(
    conn: psycopg.Connection,
    dossier_bruts: Path = DOSSIER_BRUTS,
    dossier_rapports: Path = DOSSIER_RAPPORTS,
    maintenant: datetime | None = None,
) -> dict:
    """Une passe de nettoyage ; renvoie les compteurs (aussi écrits dans le journal)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    bruts, illisibles = lire_bruts_non_traites(conn, dossier_bruts)

    articles = []
    for brut in bruts:
        try:
            articles.append(normaliser_article(brut))
        except (KeyError, TypeError, AttributeError):  # brut incomplet : id ou source absent
            illisibles += 1
            journal("brut_illisible", id=brut.get("id") if isinstance(brut, dict) else None)

    gardes, rejets = filtrer(articles, deja_gardes=references_doublons(conn, maintenant))
    enregistrer(conn, gardes, rejets, maintenant)
    conn.commit()

    jour = maintenant.date()
    rapport = construire_rapport(decisions_du_jour(conn, jour), jour)
    chemin_rapport, _ = ecrire_rapport(rapport, dossier_rapports)

    compteurs = {
        "entres": len(articles),
        "gardes": len(gardes),
        "rejetes": len(rejets),
        "illisibles": illisibles,
        "par_regle": dict(sorted(Counter(regle for _, regle in rejets).items())),
        "rapport": str(chemin_rapport),
    }
    journal("passe_nettoyage_terminee", **compteurs)
    return compteurs


def main() -> None:
    with connexion() as conn:
        migrer(conn)
        traiter_passe(conn)


if __name__ == "__main__":
    main()
