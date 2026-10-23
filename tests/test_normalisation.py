from datetime import datetime, timedelta, timezone

import pytest

from gazette.normalisation import (
    EXTRAIT_MAX,
    borner_extrait,
    date_en_utc,
    decoder_entites,
    nettoyer_texte,
    normaliser_article,
    normaliser_espaces,
    normaliser_unicode,
    reparer_encodage,
    retirer_html,
)

# --- retirer_html -----------------------------------------------------------------


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("<p>Bonjour <b>le monde</b></p>", " Bonjour le monde "),
        ("ligne un<br/>ligne deux", "ligne un ligne deux"),
        ('<a href="https://exemple.fr">le lien</a>', "le lien"),
        ("avant<script>alert('x')</script>après", "avant après"),
        ("avant<!-- un commentaire -->après", "avantaprès"),
        ("5 < 6 et 7 > 3", "5 < 6 et 7 > 3"),
        ("sans balise", "sans balise"),
    ],
)
def test_retirer_html(brut, attendu):
    assert retirer_html(brut) == attendu


# --- decoder_entites --------------------------------------------------------------


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("Tom &amp; Jerry", "Tom & Jerry"),
        ("l&#39;été", "l'été"),
        ("5 &lt; 6", "5 < 6"),
        ("deux&nbsp;mots", "deux\u00a0mots"),
        ("rien à décoder", "rien à décoder"),
    ],
)
def test_decoder_entites(brut, attendu):
    assert decoder_entites(brut) == attendu


# --- reparer_encodage -------------------------------------------------------------


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("Ã©tÃ©", "été"),
        ("dÃ©jÃ\u00a0", "déjà"),
        ("lâ€™Ã©tÃ©", "l’été"),
        ("été déjà là", "été déjà là"),
        ("sans accent", "sans accent"),
    ],
)
def test_reparer_encodage(brut, attendu):
    assert reparer_encodage(brut) == attendu


def test_reparer_encodage_laisse_un_texte_irreparable():
    # « Ã » suivi d'un caractère qui ne forme pas de l'UTF-8 valide : on ne touche à rien.
    assert reparer_encodage("Ã seul") == "Ã seul"


def test_reparer_encodage_laisse_un_texte_a_moitie_abime():
    # Limite connue : un texte qui mélange des caractères abîmés et des caractères
    # corrects n'est pas réparé (on ne tente que de refaire un décodage complet).
    assert reparer_encodage("Ã©té et dégrade") == "Ã©té et dégrade"


# --- normaliser_unicode -----------------------------------------------------------


def test_normaliser_unicode_compose_les_accents():
    decompose = "e\u0301te\u0301"  # « été » écrit avec des accents séparés
    assert normaliser_unicode(decompose) == "été"


def test_normaliser_unicode_retire_les_caracteres_invisibles():
    assert normaliser_unicode("mot\u200bsuivant\ufeff") == "motsuivant"


# --- normaliser_espaces -----------------------------------------------------------


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("jeux\u00a0: à vos neurones, jouez\u00a0!", "jeux : à vos neurones, jouez !"),
        ("  trop   d'espaces \n et\tdes\r\nretours  ", "trop d'espaces et des retours"),
        ("fine\u202fespace", "fine espace"),
        ("", ""),
    ],
)
def test_normaliser_espaces(brut, attendu):
    assert normaliser_espaces(brut) == attendu


# --- borner_extrait ---------------------------------------------------------------


def test_borner_extrait_ne_touche_pas_un_texte_court():
    assert borner_extrait("Un extrait court.", 50) == "Un extrait court."


def test_borner_extrait_ne_touche_pas_un_texte_deja_tronque_et_court():
    assert borner_extrait("Un début d'extrait…", 50) == "Un début d'extrait…"


def test_borner_extrait_coupe_a_la_fin_d_un_mot():
    assert borner_extrait("abcdefghij klmnopqrst", 15) == "abcdefghij…"


def test_borner_extrait_garde_le_dernier_mot_quand_la_coupe_tombe_sur_une_espace():
    assert borner_extrait("un deux trois quatre", 14) == "un deux trois…"


def test_borner_extrait_coupe_un_mot_unique_trop_long():
    assert borner_extrait("a" * 50, 10) == "aaaaaaaaa…"


def test_borner_extrait_respecte_toujours_la_limite():
    texte = "mot " * 200
    assert len(borner_extrait(texte)) <= EXTRAIT_MAX


# --- date_en_utc ------------------------------------------------------------------

REFERENCE = datetime(2026, 10, 22, 11, 53, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "valeur",
    [
        "2026-10-22T11:53:15+00:00",  # ISO, déjà UTC
        "2026-10-22T13:53:15+02:00",  # ISO, heure de Paris en été
        "2026-10-22T11:53:15Z",  # ISO avec Z
        "Thu, 22 Oct 2026 11:53:15 GMT",  # RFC 822 (pubDate)
        "Thu, 22 Oct 2026 13:53:15 +0200",  # RFC 822 avec décalage
        datetime(2026, 10, 22, 13, 53, 15, tzinfo=timezone(timedelta(hours=2))),
        datetime(2026, 10, 22, 11, 53, 15),  # sans fuseau : supposée UTC
    ],
)
def test_date_en_utc_formats_acceptes(valeur):
    resultat = date_en_utc(valeur)
    assert resultat == REFERENCE
    assert resultat.utcoffset() == timedelta(0)


@pytest.mark.parametrize("valeur", [None, "", "   ", "pas une date", "32/13/2026"])
def test_date_en_utc_illisible(valeur):
    assert date_en_utc(valeur) is None


# --- nettoyer_texte ---------------------------------------------------------------


def test_nettoyer_texte_enchaine_les_transformations():
    brut = "<p>Dette&nbsp;: pourquoi Moodyâ€™s <b>dÃ©grade</b>   la note &amp; l'avenir</p>"
    assert nettoyer_texte(brut) == "Dette : pourquoi Moody’s dégrade la note & l'avenir"


@pytest.mark.parametrize("vide", [None, "", "   ", "<p></p>"])
def test_nettoyer_texte_vide(vide):
    assert nettoyer_texte(vide) == ""


# --- normaliser_article -----------------------------------------------------------


def brut_exemple():
    return {
        "id": "55ff60d175b38f57e201",
        "source": "La Dépêche du Midi",
        "lien": " https://www.ladepeche.fr/2026/10/22/exemple.php ",
        "titre": "Fenix Handball\u00a0: la parole est à la défense\u00a0!",
        "resume": "<p>Troisième meilleure arrière-garde du championnat&nbsp;…</p>",
        "publie_le": "2026-10-22T16:40:10+00:00",
        "recupere_le": "2026-10-23T07:59:54.388842+00:00",
        "rubrique": "Fenix Toulouse Handball",
        "payload": {"author": "Prénom Nom", "summary": "…"},
    }


def test_normaliser_article_nettoie_les_champs():
    propre = normaliser_article(brut_exemple())
    assert propre["id"] == "55ff60d175b38f57e201"
    assert propre["source"] == "La Dépêche du Midi"
    assert propre["lien"] == "https://www.ladepeche.fr/2026/10/22/exemple.php"
    assert propre["titre"] == "Fenix Handball : la parole est à la défense !"
    assert propre["extrait"] == "Troisième meilleure arrière-garde du championnat …"
    assert propre["publie_le"] == datetime(2026, 10, 22, 16, 40, 10, tzinfo=timezone.utc)
    assert propre["recupere_le"].tzinfo == timezone.utc
    assert propre["rubrique"] == "Fenix Toulouse Handball"


def test_normaliser_article_ne_garde_ni_payload_ni_auteur():
    propre = normaliser_article(brut_exemple())
    assert "payload" not in propre
    assert "auteur" not in propre
    assert "Prénom Nom" not in str(propre)


def test_normaliser_article_tolere_les_champs_manquants():
    propre = normaliser_article({"id": "x", "source": "S", "titre": None, "resume": None})
    assert propre["titre"] == ""
    assert propre["extrait"] == ""
    assert propre["lien"] == ""
    assert propre["publie_le"] is None
    assert propre["rubrique"] is None


def test_normaliser_article_borne_l_extrait():
    brut = brut_exemple() | {"resume": "mot " * 200}
    assert len(normaliser_article(brut)["extrait"]) <= EXTRAIT_MAX
