"""Tests de la base : ils ont besoin d'un PostgreSQL (fourni par Docker Compose et la CI)."""
from gazette.db import migrer, synchroniser_sources

SOURCES = [
    {"nom": "Le Monde", "type": "PQN", "url": "https://www.lemonde.fr/rss/une.xml"},
    {"nom": "Sud Ouest", "type": "PQR", "url": "https://www.sudouest.fr/rss.xml"},
]


def test_migrer_deux_fois_n_applique_qu_une_fois(conn):
    assert migrer(conn) == ["001_creer_table_sources.sql"]
    assert migrer(conn) == []
    colonnes = {
        nom
        for (nom,) in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'test' AND table_name = 'sources'"
        )
    }
    assert colonnes == {
        "nom", "type", "url_flux", "actif", "derniere_reussite",
        "echecs_consecutifs", "etag", "last_modified",
    }


def test_synchroniser_garde_l_etat_des_sources(conn):
    migrer(conn)
    synchroniser_sources(conn, SOURCES)
    conn.execute("UPDATE sources SET echecs_consecutifs = 2 WHERE nom = 'Le Monde'")
    conn.commit()
    nouvelle_url = [{**SOURCES[0], "url": "https://www.lemonde.fr/rss/en_continu.xml"}, SOURCES[1]]
    synchroniser_sources(conn, nouvelle_url)
    lignes = conn.execute(
        "SELECT nom, url_flux, actif, echecs_consecutifs FROM sources ORDER BY nom"
    ).fetchall()
    assert lignes == [
        ("Le Monde", "https://www.lemonde.fr/rss/en_continu.xml", True, 2),
        ("Sud Ouest", "https://www.sudouest.fr/rss.xml", True, 0),
    ]
