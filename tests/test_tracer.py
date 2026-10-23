"""Tests de la traçabilité : ils ont besoin d'un PostgreSQL (Docker Compose, CI)."""

import json
from datetime import datetime, timezone

from gazette.db import migrer, synchroniser_sources
from gazette.tracer import chercher, formater, tracer

MAINTENANT = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
SOURCE = {"nom": "La Dépêche du Midi", "type": "PQR", "url": "https://www.ladepeche.fr/rss.xml"}


def brut_ecrit(dossier, id, titre="Un titre"):
    chemin = dossier / "la_depeche_du_midi" / f"{id}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(
            {
                "id": id, "source": SOURCE["nom"], "titre": titre + "\u00a0!",
                "resume": "Le résumé tel que reçu.", "recupere_le": MAINTENANT.isoformat(),
                "payload": {"published": "Fri, 23 Oct 2026 07:00:00 GMT"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return chemin


def inserer(conn):
    migrer(conn)
    synchroniser_sources(conn, [SOURCE])
    conn.execute(
        "INSERT INTO articles_propres (id, source, lien, titre, extrait, publie_le, recupere_le, "
        "rubrique, traite_le) VALUES ('garde1', %s, 'https://exemple.fr/le-garde_1', "
        "'Un titre !', 'Extrait.', %s, %s, NULL, %s)",
        (SOURCE["nom"], MAINTENANT, MAINTENANT, MAINTENANT),
    )
    conn.execute(
        "INSERT INTO rejets (id, source, lien, titre, regle, publie_le, recupere_le, traite_le) "
        "VALUES ('rejet1', %s, 'https://exemple.fr/le-rejet', 'REPLAY. Hier soir', "
        "'R11_replay', %s, %s, %s)",
        (SOURCE["nom"], MAINTENANT, MAINTENANT, MAINTENANT),
    )
    conn.commit()


def test_on_retrouve_un_article_par_id_lien_ou_titre(conn):
    inserer(conn)
    assert [a["id"] for a in chercher(conn, "garde1")] == ["garde1"]
    assert [a["id"] for a in chercher(conn, "le-rejet")] == ["rejet1"]
    assert [a["id"] for a in chercher(conn, "replay")] == [
        "rejet1"
    ]  # sans tenir compte de la casse
    assert chercher(conn, "introuvable") == []


def test_les_jokers_saisis_ne_sont_pas_interpretes(conn):
    inserer(conn)
    assert chercher(conn, "%") == []  # un « % » cherché tel quel n'est dans aucun titre
    assert [a["id"] for a in chercher(conn, "le-garde_1")] == ["garde1"]
    assert chercher(conn, "le-garde_x") == []  # « _ » n'est pas un joker


def test_trace_d_un_article_garde_jusqu_au_brut_et_a_la_source(conn, tmp_path):
    inserer(conn)
    chemin = brut_ecrit(tmp_path, "garde1")
    (trace,) = tracer(conn, "garde1", tmp_path)
    assert trace["statut"] == "garde" and trace["regle"] is None
    assert trace["brut_fichier"] == str(chemin)
    assert trace["brut"]["resume"] == "Le résumé tel que reçu."
    assert trace["source_etat"]["url_flux"] == SOURCE["url"]
    assert trace["source_etat"]["actif"] is True


def test_trace_d_un_rejet_donne_la_regle(conn, tmp_path):
    inserer(conn)
    (trace,) = tracer(conn, "rejet1", tmp_path)
    texte = formater(trace)
    assert trace["statut"] == "rejete" and trace["regle"] == "R11_replay"
    assert "REJETÉ par R11_replay : Rediffusion d'un direct" in texte


def test_brut_absent_est_signale_sans_planter(conn, tmp_path):
    inserer(conn)
    (trace,) = tracer(conn, "garde1", tmp_path)  # aucun fichier dans tmp_path
    assert trace["brut"] is None and trace["brut_fichier"] is None
    assert "fichier introuvable" in formater(trace)


def test_le_texte_montre_la_chaine_complete(conn, tmp_path):
    inserer(conn)
    brut_ecrit(tmp_path, "garde1")
    texte = formater(tracer(conn, "garde1", tmp_path)[0])
    for attendu in (
        "GARDÉ (table articles_propres)",
        "La Dépêche du Midi (PQR), active, flux https://www.ladepeche.fr/rss.xml",
        "garde1.json",
        "résumé reçu      : Le résumé tel que reçu.",
        "publié (éditeur) : Fri, 23 Oct 2026 07:00:00 GMT",
    ):
        assert attendu in texte


def test_une_source_en_sommeil_est_signalee(conn, tmp_path):
    inserer(conn)
    conn.execute("UPDATE sources SET actif = FALSE")
    conn.commit()
    assert "EN SOMMEIL" in formater(tracer(conn, "garde1", tmp_path)[0])


def test_une_source_absente_de_la_table_est_signalee(conn, tmp_path):
    inserer(conn)
    conn.execute("DELETE FROM sources")
    conn.commit()
    (trace,) = tracer(conn, "garde1", tmp_path)
    assert trace["source_etat"] is None
    assert "absente de la table sources" in formater(trace)
