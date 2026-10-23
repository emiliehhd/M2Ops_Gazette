import json
from datetime import date

import pytest

from gazette.rapport import (
    MIN_REJETS_A_SURVEILLER,
    NB_EXEMPLES,
    NB_RANGS,
    construire_rapport,
    decisions_depuis_filtrage,
    ecrire_rapport,
    en_markdown,
)

JOUR = date(2026, 10, 23)


def decisions_exemple():
    """10 articles Dépêche (4 rejetés), 5 articles Monde (1 rejeté), 1 article Croix."""
    d = [("La Dépêche du Midi", f"Article {i}", None) for i in range(6)]
    d += [("La Dépêche du Midi", f"Replay {i}", "R11_replay") for i in range(3)]
    d += [("La Dépêche du Midi", "Offre voyage", "R06_autopromo")]
    d += [("Le Monde", f"Papier {i}", None) for i in range(4)]
    d += [("Le Monde", "Titre ancien", "R13_trop_ancien")]
    d += [("La Croix", "Une chronique", None)]
    return d


def test_compteurs_generaux():
    r = construire_rapport(decisions_exemple(), JOUR)
    assert (r["jour"], r["entres"], r["gardes"], r["rejetes"]) == ("2026-10-23", 16, 11, 5)
    assert r["taux_rejet"] == pytest.approx(5 / 16)


def test_rejets_par_regle_tries_du_plus_frequent_au_moins_frequent():
    r = construire_rapport(decisions_exemple(), JOUR)
    assert [(x["regle"], x["rejets"]) for x in r["par_regle"]] == [
        ("R11_replay", 3),
        ("R06_autopromo", 1),
        ("R13_trop_ancien", 1),
    ]
    assert r["par_regle"][0]["part_des_entres"] == pytest.approx(3 / 16)
    assert r["par_regle"][0]["description"] == "Rediffusion d'un direct"


def test_par_source():
    r = construire_rapport(decisions_exemple(), JOUR)
    depeche = next(x for x in r["par_source"] if x["source"] == "La Dépêche du Midi")
    assert (depeche["entres"], depeche["gardes"], depeche["rejetes"]) == (10, 6, 4)
    assert depeche["taux_rejet"] == pytest.approx(0.4)
    croix = next(x for x in r["par_source"] if x["source"] == "La Croix")
    assert croix["taux_rejet"] == 0.0
    # Triées par nombre d'articles traités décroissant.
    assert [x["source"] for x in r["par_source"]] == ["La Dépêche du Midi", "Le Monde", "La Croix"]


def test_les_rejets_les_plus_frequents_sont_des_couples_regle_source():
    r = construire_rapport(decisions_exemple(), JOUR)
    assert r["top_rejets"][0] == {
        "regle": "R11_replay",
        "source": "La Dépêche du Midi",
        "rejets": 3,
        "part_de_la_source": pytest.approx(0.3),
    }
    assert len(r["top_rejets"]) == 3


def test_le_classement_est_limite_a_cinq_et_deterministe():
    decisions = [(f"Source {i}", "titre", f"R{i:02d}_x") for i in range(8)]
    r1 = construire_rapport(decisions, JOUR)
    r2 = construire_rapport(list(reversed(decisions)), JOUR)
    assert len(r1["top_rejets"]) == NB_RANGS
    assert r1["top_rejets"] == r2["top_rejets"]


def test_une_regle_gourmande_est_signalee():
    r = construire_rapport(decisions_exemple(), JOUR)
    # 3 replays sur 10 articles de La Dépêche du Midi : 30 %, et 3 rejets au moins.
    assert [(x["regle"], x["source"]) for x in r["a_surveiller"]] == [
        ("R11_replay", "La Dépêche du Midi")
    ]


def test_un_rejet_isole_n_est_pas_signale_meme_sur_une_petite_source():
    # 1 rejet sur 1 article = 100 % de la source, mais ça ne prouve rien.
    r = construire_rapport([("Petite source", "titre", "R06_autopromo")], JOUR)
    assert MIN_REJETS_A_SURVEILLER > 1
    assert r["a_surveiller"] == []


def test_exemples_limites_et_rangees_par_regle():
    decisions = [("S", f"Replay numéro {i}", "R11_replay") for i in range(10)]
    r = construire_rapport(decisions, JOUR)
    assert len(r["exemples"]["R11_replay"]) == NB_EXEMPLES


def test_rapport_vide():
    r = construire_rapport([], JOUR)
    assert (r["entres"], r["taux_rejet"], r["par_regle"], r["par_source"]) == (0, 0.0, [], [])
    assert "Aucun article traité." in en_markdown(r)


def test_aucun_rejet():
    r = construire_rapport([("Le Monde", "Un titre", None)], JOUR)
    texte = en_markdown(r)
    assert "1 articles traités : 1 gardés, 0 rejetés (0,0 %)" in texte
    assert "Aucun rejet." in texte
    assert "Aucune." in texte


def test_markdown_contient_les_sections_et_les_pourcentages_a_la_francaise():
    texte = en_markdown(construire_rapport(decisions_exemple(), JOUR))
    assert texte.startswith("# Rapport de qualité du 2026-10-23")
    assert "16 articles traités : 11 gardés, 5 rejetés (31,2 %)" in texte
    for titre in (
        "## Rejets par règle",
        "## Par source",
        "## Les 5 rejets les plus fréquents (règle et source)",
        "## Règles à surveiller",
        "## Exemples de rejets",
    ):
        assert titre in texte
    assert "| `R11_replay` | Rediffusion d'un direct | 3 | 18,8 % |" in texte
    assert "- `R11_replay` sur La Dépêche du Midi : 3 rejets, 30,0 % de la source" in texte
    assert "  - Offre voyage" in texte


def test_decisions_depuis_filtrage():
    gardes = [{"source": "Le Monde", "titre": "A"}]
    rejets = [({"source": "Le Monde", "titre": "B"}, "R11_replay")]
    assert decisions_depuis_filtrage(gardes, rejets) == [
        ("Le Monde", "A", None),
        ("Le Monde", "B", "R11_replay"),
    ]


def test_ecrire_rapport_cree_le_markdown_et_le_json(tmp_path):
    rapport = construire_rapport(decisions_exemple(), JOUR)
    chemin_md, chemin_json = ecrire_rapport(rapport, tmp_path / "rapports")
    assert chemin_md.name == "qualite-2026-10-23.md"
    assert chemin_json.name == "qualite-2026-10-23.json"
    assert chemin_md.read_text(encoding="utf-8") == en_markdown(rapport)
    assert json.loads(chemin_json.read_text(encoding="utf-8")) == json.loads(json.dumps(rapport))


def test_ecrire_rapport_remplace_le_rapport_du_meme_jour(tmp_path):
    dossier = tmp_path / "rapports"
    ecrire_rapport(construire_rapport([("S", "a", None)], JOUR), dossier)
    chemin_md, _ = ecrire_rapport(
        construire_rapport([("S", "a", None), ("S", "b", None)], JOUR), dossier
    )
    assert "2 articles traités" in chemin_md.read_text(encoding="utf-8")
    assert len(list(dossier.iterdir())) == 2
