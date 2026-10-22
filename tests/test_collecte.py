from datetime import datetime, timezone
from pathlib import Path

import pytest

from gazette.collecte import ecrire_bruts, identifiant, lire_sources, parse

RACINE = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "lemonde_une.xml"
RECUPERE_LE = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_parse_flux_le_monde():
    items = parse(FIXTURE.read_bytes(), "Le Monde", recupere_le=RECUPERE_LE)
    assert len(items) >= 1
    for item in items:
        assert set(item) == {
            "id", "source", "lien", "titre", "resume",
            "publie_le", "recupere_le", "rubrique", "payload",
        }
        assert item["source"] == "Le Monde"
        assert item["titre"]
        assert item["lien"].startswith("https://")
        assert item["publie_le"].endswith("+00:00")
        assert item["recupere_le"] == RECUPERE_LE.isoformat()
        assert item["id"] == identifiant("Le Monde", item["lien"])
        # On borne : ni texte intégral ni images dans le payload
        assert "content" not in item["payload"]
        assert not any(k.startswith("media") for k in item["payload"])


def test_parse_item_sans_extrait():
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Sans extrait</title><link>https://exemple.fr/a</link>
    <guid>a</guid><pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = parse(xml, "Test", recupere_le=RECUPERE_LE)
    assert items[0]["resume"] == ""
    assert items[0]["publie_le"] == "2026-10-20T10:00:00+00:00"


def test_deux_passages_zero_doublon(tmp_path):
    xml = FIXTURE.read_bytes()
    premier = parse(xml, "Le Monde", recupere_le=RECUPERE_LE)
    second = parse(xml, "Le Monde")  # même flux, relu plus tard
    assert ecrire_bruts(premier, tmp_path) == (len(premier), 0)
    assert ecrire_bruts(second, tmp_path) == (0, len(second))
    fichiers = list(tmp_path.rglob("*.json"))
    assert len(fichiers) == len(premier)


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