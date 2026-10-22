from datetime import datetime, timezone
from pathlib import Path

import pytest

from gazette.collecte import lire_sources, parse

RACINE = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "lemonde_une.xml"
FETCHED_AT = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_parse_flux_le_monde():
    items = parse(FIXTURE.read_bytes(), "Le Monde", fetched_at=FETCHED_AT)
    #assert len(items) >= 1
    assert len(items) >= 999
    for item in items:
        assert item["source"] == "Le Monde"
        assert item["title"]
        assert item["link"].startswith("https://")
        assert item["published_at"].endswith("+00:00")
        assert item["fetched_at"] == FETCHED_AT.isoformat()


def test_parse_item_sans_extrait():
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Sans extrait</title><link>https://exemple.fr/a</link>
    <guid>a</guid><pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = parse(xml, "Test", fetched_at=FETCHED_AT)
    assert items[0]["summary"] == ""
    assert items[0]["published_at"] == "2026-10-20T10:00:00+00:00"


def test_lire_sources_extrait_l_adresse(tmp_path):
    fichier = tmp_path / "sources.csv"
    fichier.write_text(
        "nom,type,region,acces,conditions,notes\n"
        'Le Monde,PQN,France,RSS 2.0 https://www.lemonde.fr/rss/une.xml,ok,"note, avec virgule"\n',
        encoding="utf-8",
    )
    assert lire_sources(fichier) == [
        {"nom": "Le Monde", "type": "PQN", "url": "https://www.lemonde.fr/rss/une.xml"}
    ]


def test_lire_sources_sans_adresse(tmp_path):
    fichier = tmp_path / "sources.csv"
    fichier.write_text("nom,type,region,acces,conditions,notes\nX,PQN,France,RSS,,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lire_sources(fichier)


def test_sources_csv_du_projet_est_valide():
    sources = lire_sources(RACINE / "sources.csv")
    assert all(s["url"].startswith("https://") for s in sources)
    assert sum(s["type"] == "PQN" for s in sources) >= 4
    assert sum(s["type"] == "PQR" for s in sources) >= 4