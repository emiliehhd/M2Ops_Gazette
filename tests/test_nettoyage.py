"""Tests du nettoyage : ils ont besoin d'un PostgreSQL (fourni par Docker Compose et la CI)."""

import json
from datetime import datetime, timedelta, timezone

from gazette.collecte import ecrire_bruts, identifiant
from gazette.db import migrer
from gazette.nettoyage import ids_traites, lire_bruts_non_traites, traiter_passe

COLLECTE = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
TITRE = "La tempête Austen balaie le nord-ouest du pays"


def brut(titre, *, source="Le Monde", lien=None, publie=None, resume="Un extrait.", auteur=None):
    """Un article brut tel que le collecteur l'écrit."""
    lien = lien or f"https://exemple.fr/{identifiant(source, titre)}"
    publie = publie or COLLECTE - timedelta(hours=2)
    return {
        "id": identifiant(source, lien),
        "source": source,
        "lien": lien,
        "titre": titre,
        "resume": resume,
        "publie_le": publie.isoformat(),
        "recupere_le": COLLECTE.isoformat(),
        "rubrique": None,
        "payload": {"title": titre, "author": auteur},
    }


def deposer(dossier, *items):
    ecrire_bruts(list(items), dossier)


def passe(conn, tmp_path, maintenant=COLLECTE):
    migrer(conn)
    return traiter_passe(conn, tmp_path / "bruts", tmp_path / "rapports", maintenant)


def test_une_passe_garde_et_rejette_avec_la_regle(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(
        bruts,
        brut(TITRE, publie=COLLECTE - timedelta(hours=3)),
        brut(TITRE, lien="https://exemple.fr/autre", publie=COLLECTE - timedelta(hours=1)),
        brut("REPLAY. Le direct d'hier soir sur la tempête"),
        brut("Un article de la semaine dernière", publie=COLLECTE - timedelta(days=7)),
    )
    compteurs = passe(conn, tmp_path)
    assert (compteurs["entres"], compteurs["gardes"], compteurs["rejetes"]) == (4, 1, 3)
    assert compteurs["par_regle"] == {
        "R11_replay": 1,
        "R13_trop_ancien": 1,
        "R14_doublon_exact": 1,
    }
    assert compteurs["illisibles"] == 0
    gardes = conn.execute("SELECT titre, publie_le, traite_le FROM articles_propres").fetchall()
    assert [g[0] for g in gardes] == [TITRE]
    assert gardes[0][1] == COLLECTE - timedelta(hours=3)  # le premier publié est gardé
    assert gardes[0][2] == COLLECTE
    rejets = conn.execute("SELECT regle FROM rejets ORDER BY regle").fetchall()
    assert [r[0] for r in rejets] == ["R11_replay", "R13_trop_ancien", "R14_doublon_exact"]


def test_deux_passages_zero_doublon(conn, tmp_path):
    deposer(tmp_path / "bruts", brut(TITRE), brut("REPLAY. Hier soir"))
    premiere = passe(conn, tmp_path)
    seconde = passe(conn, tmp_path, COLLECTE + timedelta(minutes=30))
    assert premiere["entres"] == 2
    assert (seconde["entres"], seconde["gardes"], seconde["rejetes"]) == (0, 0, 0)
    assert conn.execute("SELECT count(*) FROM articles_propres").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM rejets").fetchone()[0] == 1


def test_un_article_n_est_jamais_dans_les_deux_tables(conn, tmp_path):
    deposer(tmp_path / "bruts", brut(TITRE), brut("REPLAY. Hier soir"))
    passe(conn, tmp_path)
    communs = conn.execute(
        "SELECT count(*) FROM articles_propres p JOIN rejets r ON r.id = p.id"
    ).fetchone()[0]
    assert communs == 0


def test_seuls_les_nouveaux_articles_sont_traites_a_la_passe_suivante(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(bruts, brut(TITRE))
    passe(conn, tmp_path)
    deposer(bruts, brut("Un autre sujet, publié depuis"))
    seconde = passe(conn, tmp_path, COLLECTE + timedelta(minutes=30))
    assert (seconde["entres"], seconde["gardes"]) == (1, 1)
    assert conn.execute("SELECT count(*) FROM articles_propres").fetchone()[0] == 2


def test_un_doublon_d_un_article_garde_lors_d_une_passe_precedente_est_rejete(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(bruts, brut(TITRE, publie=COLLECTE - timedelta(hours=5)))
    passe(conn, tmp_path)
    deposer(bruts, brut(TITRE, lien="https://exemple.fr/republie", publie=COLLECTE))
    seconde = passe(conn, tmp_path, COLLECTE + timedelta(minutes=30))
    assert seconde["par_regle"] == {"R14_doublon_exact": 1}
    assert conn.execute("SELECT count(*) FROM articles_propres").fetchone()[0] == 1


def test_tracabilite_d_un_article_propre_au_brut_et_a_la_source(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(bruts, brut(TITRE, source="Ouest-France"))
    passe(conn, tmp_path)
    ((id_propre, source),) = conn.execute("SELECT id, source FROM articles_propres").fetchall()
    fichiers = list(bruts.glob(f"*/{id_propre}.json"))
    assert len(fichiers) == 1
    contenu = json.loads(fichiers[0].read_text(encoding="utf-8"))
    assert (contenu["id"], contenu["source"]) == (id_propre, source) == (id_propre, "Ouest-France")


def test_ni_auteur_ni_payload_dans_les_tables(conn, tmp_path):
    deposer(tmp_path / "bruts", brut(TITRE, auteur="Prénom Journaliste"), brut("REPLAY. X y z"))
    passe(conn, tmp_path)
    for table in ("articles_propres", "rejets"):
        lignes = conn.execute(f"SELECT * FROM {table}").fetchall()
        assert lignes
        assert "Prénom Journaliste" not in str(lignes)


def test_le_titre_et_l_extrait_sont_normalises(conn, tmp_path):
    deposer(
        tmp_path / "bruts",
        brut(
            "Dette\u00a0: pourquoi Moody’s dégrade",
            resume="<p>Un extrait&nbsp;avec <b>HTML</b></p>",
        ),
    )
    passe(conn, tmp_path)
    ((titre, extrait),) = conn.execute("SELECT titre, extrait FROM articles_propres").fetchall()
    assert titre == "Dette : pourquoi Moody’s dégrade"
    assert extrait == "Un extrait avec HTML"


def test_un_fichier_illisible_n_arrete_pas_la_passe(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(bruts, brut(TITRE))
    (bruts / "le_monde" / "casse.json").write_text("{pas du json", encoding="utf-8")
    (bruts / "le_monde" / "incomplet.json").write_text('{"titre": "sans id"}', encoding="utf-8")
    compteurs = passe(conn, tmp_path)
    assert compteurs["illisibles"] == 2
    assert compteurs["gardes"] == 1


def test_le_rapport_du_jour_est_ecrit_et_cumule_les_passes(conn, tmp_path):
    bruts = tmp_path / "bruts"
    deposer(bruts, brut(TITRE), brut("REPLAY. Hier soir"))
    premiere = passe(conn, tmp_path)
    chemin = tmp_path / "rapports" / "qualite-2026-10-23.md"
    assert premiere["rapport"] == str(chemin)
    assert "2 articles traités : 1 gardés, 1 rejetés (50,0 %)" in chemin.read_text(encoding="utf-8")

    deposer(bruts, brut("Un autre sujet, publié depuis"))
    passe(conn, tmp_path, COLLECTE + timedelta(minutes=30))
    assert "3 articles traités : 2 gardés, 1 rejetés" in chemin.read_text(encoding="utf-8")
    rapport = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
    assert (rapport["entres"], rapport["gardes"], rapport["rejetes"]) == (3, 2, 1)
    assert rapport["par_regle"][0]["regle"] == "R11_replay"


def test_pas_de_brut_pas_d_erreur(conn, tmp_path):
    compteurs = passe(conn, tmp_path)
    assert (compteurs["entres"], compteurs["gardes"], compteurs["rejetes"]) == (0, 0, 0)
    assert "Aucun article traité." in (tmp_path / "rapports" / "qualite-2026-10-23.md").read_text(
        encoding="utf-8"
    )


def test_lire_bruts_non_traites_et_ids_traites(conn, tmp_path):
    bruts = tmp_path / "bruts"
    a, b = brut(TITRE), brut("Un autre sujet")
    deposer(bruts, a)
    passe(conn, tmp_path)
    deposer(bruts, b)
    assert ids_traites(conn) == {a["id"]}
    nouveaux, illisibles = lire_bruts_non_traites(conn, bruts)
    assert [n["id"] for n in nouveaux] == [b["id"]]
    assert illisibles == 0
