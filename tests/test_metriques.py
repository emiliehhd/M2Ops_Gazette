from gazette.controles import Resultat
from gazette.metriques import (
    metriques_collecte,
    metriques_controles,
    metriques_jour,
    metriques_nettoyage,
)

COLLECTE = {
    "sources": 8, "ok": 6, "inchangees": 1, "erreurs": 1, "en_sommeil": 1,
    "recus": 120, "ecrits": 40, "ignores": 80, "duree_s": 12.5,
}  # fmt: skip


def test_metriques_de_collecte():
    m = {nom: valeur for nom, _, valeur in metriques_collecte(COLLECTE)}
    assert m["collecte_recus"] == 120
    assert m["collecte_ecrits"] == 40
    assert m["collecte_ignores"] == 80
    assert m["collecte_sources_en_erreur"] == 1
    assert m["collecte_sources_en_sommeil"] == 1
    assert m["collecte_duree_secondes"] == 12.5


def test_metriques_de_nettoyage_une_par_regle():
    compteurs = {
        "entres": 40, "gardes": 38, "rejetes": 2, "illisibles": 0,
        "par_regle": {"R11_replay": 1, "R13_trop_ancien": 1},
    }  # fmt: skip
    m = metriques_nettoyage(compteurs)
    assert ("nettoyage_entres", "", 40) in m
    assert ("nettoyage_rejetes", "", 2) in m
    assert ("nettoyage_rejets_par_regle", "R11_replay", 1) in m
    assert ("nettoyage_rejets_par_regle", "R13_trop_ancien", 1) in m


def test_metriques_du_jour_par_source_et_par_regle():
    rapport = {
        "entres": 10, "gardes": 8, "rejetes": 2, "taux_rejet": 0.2,
        "par_source": [{"source": "Le Monde", "entres": 10, "gardes": 8, "rejetes": 2, "taux_rejet": 0.2}],
        "par_regle": [{"regle": "R11_replay", "rejets": 2}],
    }  # fmt: skip
    m = metriques_jour(rapport)
    assert ("jour_traites", "", 10) in m
    assert ("jour_taux_rejet", "", 0.2) in m
    assert ("jour_rejetes_par_source", "Le Monde", 2) in m
    assert ("jour_taux_rejet_par_source", "Le Monde", 0.2) in m
    assert ("jour_rejets_par_regle", "R11_replay", 2) in m


def test_metriques_des_controles():
    resultats = [Resultat("C01_x", "fait", True, 0), Resultat("C02_y", "fait", False, 3, "3")]
    m = metriques_controles(resultats)
    assert ("controles_en_echec", "", 1) in m
    assert ("controle_ok", "C01_x", 1) in m
    assert ("controle_ok", "C02_y", 0) in m
    assert ("controle_valeur", "C02_y", 3) in m
