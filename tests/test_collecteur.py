"""Collecteur multi-sources contre un faux éditeur local (pas d'Internet)."""
from gazette.collecteur import collecter_tout
from gazette.db import migrer, synchroniser_sources


def _preparer(conn, editeur, chemins):
    migrer(conn)
    synchroniser_sources(
        conn, [{"nom": nom, "type": "PQN", "url": editeur + chemin} for nom, chemin in chemins]
    )


def _etat(conn, nom):
    return conn.execute(
        "SELECT derniere_reussite IS NOT NULL, echecs_consecutifs, etag FROM sources WHERE nom = %s",
        (nom,),
    ).fetchone()


def test_collecte_ecrit_et_note_la_reussite(conn, editeur, tmp_path):
    _preparer(conn, editeur, [("Bon", "/flux.xml")])
    compteurs = collecter_tout(conn, tmp_path)
    assert compteurs["ok"] == 1 and compteurs["ecrits"] > 0
    assert len(list(tmp_path.rglob("*.json"))) == compteurs["ecrits"]
    assert _etat(conn, "Bon") == (True, 0, '"v1"')


def test_deuxieme_passe_conditionnelle_304(conn, editeur, tmp_path):
    _preparer(conn, editeur, [("Bon", "/flux.xml")])
    collecter_tout(conn, tmp_path)
    compteurs = collecter_tout(conn, tmp_path)  # le serveur reçoit If-None-Match
    assert compteurs["inchangees"] == 1 and compteurs["recus"] == 0


def test_une_source_en_erreur_n_arrete_pas_les_autres(conn, editeur, tmp_path):
    _preparer(conn, editeur, [("Absente", "/absent"), ("Bon", "/flux.xml")])
    compteurs = collecter_tout(conn, tmp_path)
    assert (compteurs["ok"], compteurs["erreurs"]) == (1, 1)
    assert _etat(conn, "Absente") == (False, 1, None)
    assert _etat(conn, "Bon")[1] == 0
