"""Collecteur multi-sources contre un faux éditeur local (pas d'Internet)."""
from conftest import FauxEditeur

from gazette import collecteur
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


def test_source_en_panne_backoff_puis_sommeil(conn, editeur, tmp_path, monkeypatch):
    """Le serveur local renvoie 503 : on réessaie, on compte, on endort au 3e échec."""
    monkeypatch.setattr(collecteur, "PAUSES", (0.01, 0.02))  # backoff accéléré pour le test
    _preparer(conn, editeur, [("En panne", "/panne"), ("Bon", "/flux.xml")])

    for passe in (1, 2):
        collecter_tout(conn, tmp_path)
        assert FauxEditeur.appels.count("/panne") == 3 * passe  # 1 essai + 2 reprises par passe
        assert _actif(conn, "En panne") is True

    compteurs = collecter_tout(conn, tmp_path)
    assert _etat(conn, "En panne") == (False, 3, None)
    assert _actif(conn, "En panne") is False
    assert compteurs["en_sommeil"] == 1

    FauxEditeur.appels.clear()
    collecter_tout(conn, tmp_path)  # une source en sommeil n'est plus appelée
    assert "/panne" not in FauxEditeur.appels
    assert _etat(conn, "Bon")[1] == 0


def test_erreur_permanente_sans_reprise(conn, editeur, tmp_path, monkeypatch):
    monkeypatch.setattr(collecteur, "PAUSES", (0.01, 0.02))
    _preparer(conn, editeur, [("Absente", "/absent")])
    collecter_tout(conn, tmp_path)
    assert FauxEditeur.appels.count("/absent") == 1  # un 404 ne se réessaie pas


def _actif(conn, nom):
    return conn.execute("SELECT actif FROM sources WHERE nom = %s", (nom,)).fetchone()[0]
