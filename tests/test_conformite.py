import json

from gazette.collecte import CHAMPS_PAYLOAD, parse
from gazette.conformite import purger_auteurs

FLUX = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>t</title>
<item><title>Un titre</title><link>https://exemple.fr/a</link><guid>a</guid>
<description>Un extrait.</description><pubDate>Tue, 20 Oct 2026 10:00:00 GMT</pubDate>
<dc:creator>Prenom Journaliste</dc:creator></item>
<item><title>Un autre</title><link>https://exemple.fr/b</link><guid>b</guid>
<author>autre@exemple.fr (Autre Journaliste)</author></item>
</channel></rss>"""


def test_le_nom_de_l_auteur_n_est_plus_collecte():
    items = parse(FLUX, "Le Monde")
    assert len(items) == 2
    for item in items:
        assert "author" not in item["payload"]
        assert set(item["payload"]) <= set(CHAMPS_PAYLOAD)
        assert "Journaliste" not in json.dumps(item)
    # Le reste du payload est conservé.
    assert items[0]["payload"]["title"] == "Un titre"
    assert items[0]["payload"]["link"] == "https://exemple.fr/a"


def ecrire(dossier, nom, contenu):
    chemin = dossier / "le_monde" / f"{nom}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def test_purger_auteurs_retire_le_champ_et_garde_le_reste(tmp_path):
    ancien = {
        "id": "a1", "source": "Le Monde", "lien": "https://exemple.fr/a", "titre": "Un titre",
        "payload": {"title": "Un titre", "author": "Prénom Journaliste", "summary": "Résumé"},
    }  # fmt: skip
    chemin = ecrire(tmp_path, "a1", json.dumps(ancien, ensure_ascii=False, indent=2))
    compteurs = purger_auteurs(tmp_path)
    assert compteurs == {"fichiers": 1, "purges": 1, "illisibles": 0}
    apres = json.loads(chemin.read_text(encoding="utf-8"))
    assert "author" not in apres["payload"]
    assert "Journaliste" not in chemin.read_text(encoding="utf-8")
    assert apres["payload"] == {"title": "Un titre", "summary": "Résumé"}
    assert {k: v for k, v in apres.items() if k != "payload"} == {
        k: v for k, v in ancien.items() if k != "payload"
    }


def test_purger_auteurs_est_idempotent_et_ne_laisse_aucun_fichier_temporaire(tmp_path):
    ecrire(tmp_path, "a1", json.dumps({"id": "a1", "payload": {"author": "X Y"}}))
    ecrire(tmp_path, "a2", json.dumps({"id": "a2", "payload": {"title": "Sans auteur"}}))
    assert purger_auteurs(tmp_path)["purges"] == 1
    assert purger_auteurs(tmp_path)["purges"] == 0  # déjà fait
    assert sorted(p.name for p in (tmp_path / "le_monde").iterdir()) == ["a1.json", "a2.json"]


def test_purger_auteurs_ignore_les_fichiers_illisibles_ou_atypiques(tmp_path):
    ecrire(tmp_path, "casse", "{pas du json")
    ecrire(tmp_path, "liste", "[1, 2, 3]")
    ecrire(tmp_path, "sans_payload", json.dumps({"id": "x"}))
    ecrire(tmp_path, "bon", json.dumps({"id": "b", "payload": {"author": "X"}}))
    assert purger_auteurs(tmp_path) == {"fichiers": 4, "purges": 1, "illisibles": 1}
