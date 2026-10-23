"""Traçabilité : d'un article, retrouver la décision, l'item brut et la source.

Chaîne complète : flux de la source -> fichier brut `data/articles_bruts/<source>/<id>.json`
-> ligne de `articles_propres` (gardé) ou de `rejets` (écarté, avec la règle). L'`id` est le même
partout : il est calculé à partir de `(source, lien)`.

Commande : `python -m gazette.tracer "<id, morceau du lien ou du titre>"`.
"""

import json
import sys
from pathlib import Path

import psycopg

from gazette.collecte import DOSSIER_BRUTS
from gazette.db import connexion, migrer
from gazette.regles import DESCRIPTIONS

MAX_RESULTATS = 5


def _motif(texte: str) -> str:
    """Motif LIKE qui cherche `texte` tel quel (les % et _ saisis ne sont pas des jokers)."""
    echappe = texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{echappe}%"


def chercher(conn: psycopg.Connection, requete: str) -> list[dict]:
    """Articles, gardés ou rejetés, dont l'id, le lien ou le titre correspond à la requête."""
    colonnes = ("id", "source", "lien", "titre", "regle", "publie_le", "traite_le", "statut")
    lignes = conn.execute(
        "SELECT id, source, lien, titre, NULL::text, publie_le, traite_le, 'garde' "
        "FROM articles_propres WHERE id = %(q)s OR lien ILIKE %(m)s OR titre ILIKE %(m)s "
        "UNION ALL "
        "SELECT id, source, lien, titre, regle, publie_le, traite_le, 'rejete' "
        "FROM rejets WHERE id = %(q)s OR lien ILIKE %(m)s OR titre ILIKE %(m)s "
        "ORDER BY 6 DESC NULLS LAST LIMIT %(n)s",
        {"q": requete, "m": _motif(requete), "n": MAX_RESULTATS},
    )
    return [dict(zip(colonnes, ligne)) for ligne in lignes]


def tracer(
    conn: psycopg.Connection, requete: str, dossier_bruts: Path = DOSSIER_BRUTS
) -> list[dict]:
    """Pour chaque article trouvé : sa décision, son état de source et son item brut."""
    resultats = []
    for article in chercher(conn, requete):
        ligne = conn.execute(
            "SELECT type, url_flux, actif, echecs_consecutifs, derniere_reussite "
            "FROM sources WHERE nom = %s",
            (article["source"],),
        ).fetchone()
        source = None
        if ligne:
            cles = ("type", "url_flux", "actif", "echecs_consecutifs", "derniere_reussite")
            source = dict(zip(cles, ligne))
        fichiers = sorted(dossier_bruts.glob(f"*/{article['id']}.json"))
        brut = json.loads(fichiers[0].read_text(encoding="utf-8")) if fichiers else None
        resultats.append(
            {
                **article,
                "source_etat": source,
                "brut_fichier": str(fichiers[0]) if fichiers else None,
                "brut": brut,
            }
        )
    return resultats


def formater(trace: dict) -> str:
    """Une trace, lisible par une personne."""
    if trace["statut"] == "garde":
        decision = "GARDÉ (table articles_propres)"
    else:
        sens = DESCRIPTIONS.get(trace["regle"], "")
        decision = f"REJETÉ par {trace['regle']}" + (f" : {sens}" if sens else "")
    lignes = [
        f"Article {trace['id']}",
        f"  Décision     : {decision}",
        f"  Titre        : {trace['titre']}",
        f"  Lien         : {trace['lien']}",
        f"  Publié le    : {trace['publie_le']}   Traité le : {trace['traite_le']}",
    ]
    s = trace["source_etat"]
    if s:
        etat = "active" if s["actif"] else "EN SOMMEIL"
        lignes.append(
            f"  Source       : {trace['source']} ({s['type']}), {etat}, flux {s['url_flux']}"
        )
    else:
        lignes.append(f"  Source       : {trace['source']} (absente de la table sources)")
    brut = trace["brut"]
    if brut is None:
        lignes.append("  Brut         : fichier introuvable (purgé, ou autre machine)")
    else:
        payload = brut.get("payload") or {}
        lignes += [
            f"  Brut         : {trace['brut_fichier']}",
            f"    titre reçu       : {brut.get('titre')}",
            f"    résumé reçu      : {(brut.get('resume') or '')[:120]}",
            f"    récupéré le      : {brut.get('recupere_le')}",
            f"    publié (éditeur) : {payload.get('published') or payload.get('updated')}",
        ]
    return "\n".join(lignes)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Usage : python -m gazette.tracer "<id, morceau du lien ou du titre>"')
    with connexion() as conn:
        migrer(conn)
        traces = tracer(conn, sys.argv[1])
    if not traces:
        sys.exit("Aucun article trouvé.")
    print("\n\n".join(formater(t) for t in traces))


if __name__ == "__main__":
    main()
