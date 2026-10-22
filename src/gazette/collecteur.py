"""Collecteur multi-sources : lit toutes les sources actives, poliment, et note leur état."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests

from gazette.collecte import DOSSIER_BRUTS, USER_AGENT, ecrire_bruts, lire_sources, parse
from gazette.db import connexion, migrer, synchroniser_sources

TIMEOUT = (5, 20)  # secondes : (connexion, lecture)


def journal(evenement: str, **champs) -> None:
    """Journal structuré : une ligne JSON par événement, sur la sortie standard."""
    ligne = {"horodatage": datetime.now(timezone.utc).isoformat(), "evenement": evenement, **champs}
    print(json.dumps(ligne, ensure_ascii=False), flush=True)


def telecharger(url: str, etag: str | None, last_modified: str | None) -> requests.Response:
    """GET conditionnel : si le flux n'a pas changé, le serveur répond 304 sans contenu."""
    entetes = {"User-Agent": USER_AGENT}
    if etag:
        entetes["If-None-Match"] = etag
    if last_modified:
        entetes["If-Modified-Since"] = last_modified
    reponse = requests.get(url, headers=entetes, timeout=TIMEOUT)
    if reponse.status_code != 304:
        reponse.raise_for_status()
    return reponse


def collecter_source(conn: psycopg.Connection, source: dict, dossier: Path) -> dict:
    """Collecte une source et met à jour sa ligne dans la table `sources`."""
    debut = time.monotonic()
    stats = {"source": source["nom"], "recus": 0, "ecrits": 0, "ignores": 0}
    try:
        reponse = telecharger(source["url_flux"], source["etag"], source["last_modified"])
        if reponse.status_code == 304:
            stats["statut"] = "inchange"
        else:
            items = parse(reponse.content, source["nom"])
            ecrits, ignores = ecrire_bruts(items, dossier)
            stats.update(statut="ok", recus=len(items), ecrits=ecrits, ignores=ignores)
        stats["http"] = reponse.status_code
        conn.execute(
            "UPDATE sources SET derniere_reussite = now(), echecs_consecutifs = 0, "
            "etag = COALESCE(%s, etag), last_modified = COALESCE(%s, last_modified) "
            "WHERE nom = %s",
            (reponse.headers.get("ETag"), reponse.headers.get("Last-Modified"), source["nom"]),
        )
    # Volontairement large : une source en erreur, quelle qu'elle soit, ne doit pas arrêter les autres.
    except Exception as erreur:  # noqa: BLE001
        stats.update(statut="erreur", erreur=f"{type(erreur).__name__}: {erreur}")
        conn.execute(
            "UPDATE sources SET echecs_consecutifs = echecs_consecutifs + 1 WHERE nom = %s",
            (source["nom"],),
        )
    conn.commit()
    stats["duree_s"] = round(time.monotonic() - debut, 2)
    journal("source_collectee", **stats)
    return stats


def sources_actives(conn: psycopg.Connection) -> list[dict]:
    curseur = conn.execute(
        "SELECT nom, url_flux, etag, last_modified FROM sources WHERE actif ORDER BY nom"
    )
    colonnes = [c.name for c in curseur.description]
    return [dict(zip(colonnes, ligne)) for ligne in curseur]


def collecter_tout(conn: psycopg.Connection, dossier: Path = DOSSIER_BRUTS) -> dict:
    """Une passe : chaque source active, l'une après l'autre (pas de parallélisme sur un éditeur)."""
    debut = time.monotonic()
    resultats = [collecter_source(conn, s, dossier) for s in sources_actives(conn)]
    compteurs = {
        "sources": len(resultats),
        "ok": sum(r["statut"] == "ok" for r in resultats),
        "inchangees": sum(r["statut"] == "inchange" for r in resultats),
        "erreurs": sum(r["statut"] == "erreur" for r in resultats),
        "recus": sum(r["recus"] for r in resultats),
        "ecrits": sum(r["ecrits"] for r in resultats),
        "ignores": sum(r["ignores"] for r in resultats),
        "duree_s": round(time.monotonic() - debut, 2),
    }
    journal("passe_terminee", **compteurs)
    return compteurs


def main() -> None:
    with connexion() as conn:
        migrer(conn)
        synchroniser_sources(conn, lire_sources())
        compteurs = collecter_tout(conn)
    # Code de sortie non nul si toutes les sources ont échoué : l'orchestrateur le verra.
    sys.exit(1 if compteurs["sources"] and compteurs["erreurs"] == compteurs["sources"] else 0)


if __name__ == "__main__":
    main()
