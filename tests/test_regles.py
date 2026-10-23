from datetime import datetime, timedelta, timezone

import pytest

from gazette.regles import (
    DESCRIPTIONS,
    FRAICHEUR_MAX,
    REGLES,
    TOLERANCE_FUTUR,
    appliquer_regles,
    filtrer,
    jaccard,
    mots_du_titre,
    simplifier,
)

COLLECTE = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)


def article(**champs):
    """Un article normalisé ordinaire, gardé par toutes les règles ; `champs` le modifie."""
    base = {
        "id": "a1",
        "source": "Le Monde",
        "lien": "https://exemple.fr/a1",
        "titre": "La tempête Austen balaie le nord-ouest du pays",
        "extrait": "Des vents violents sont attendus ce jeudi.",
        "publie_le": COLLECTE - timedelta(hours=2),
        "recupere_le": COLLECTE,
        "rubrique": None,
    }
    return base | champs


# --- un article ordinaire est gardé -----------------------------------------------


def test_article_ordinaire_est_garde():
    assert appliquer_regles(article()) is None


def test_chaque_regle_a_un_identifiant_unique_et_une_description():
    identifiants = [r.id for r in REGLES]
    assert len(identifiants) == len(set(identifiants))
    assert all(r.ecarte for r in REGLES)
    assert set(identifiants) <= set(DESCRIPTIONS)


# --- les règles, une par une (cas écartés) ----------------------------------------


@pytest.mark.parametrize(
    "champs, regle",
    [
        # R01 : titre vide
        ({"titre": ""}, "R01_titre_vide"),
        ({"titre": "   "}, "R01_titre_vide"),
        # R02 : encodage encore cassé
        ({"titre": "L'Ã©conomie en crise"}, "R02_encodage_casse"),
        ({"extrait": "Moodyâ€™s dégrade la note"}, "R02_encodage_casse"),
        ({"titre": "Titre avec caractère de remplacement \ufffd"}, "R02_encodage_casse"),
        # R03 : date absente
        ({"publie_le": None}, "R03_date_absente"),
        # R04 : date future (au-delà de la tolérance)
        ({"publie_le": COLLECTE + timedelta(hours=1)}, "R04_date_future"),
        # R05 : contenu partenaire
        ({"titre": "Contenu partenaire : trois astuces pour votre jardin"}, "R05_publi"),
        ({"titre": "Un publi-reportage sur les vacances"}, "R05_publi"),
        ({"rubrique": "Contenu partenaire"}, "R05_publi"),
        # R06 : auto-promotion (vrais titres de La Dépêche du Midi)
        (
            {
                "source": "La Dépêche du Midi",
                "titre": "La Dépêche du Midi lance son espace jeux : à vos neurones, prêts, jouez !",
            },
            "R06_autopromo",
        ),
        (
            {
                "source": "La Dépêche du Midi",
                "titre": "Un voyage exceptionnel de Pékin à la Grande Muraille : "
                "découvrez la Chine avec La Dépêche du Midi",
            },
            "R06_autopromo",
        ),
        (
            {"source": "Le Monde", "titre": "Abonnez-vous à Le Monde : 1 € le premier mois"},
            "R06_autopromo",
        ),
        (
            {
                "source": "Ouest-France",
                "titre": "Rejoignez Ouest-France pour suivre l'actualité de votre région",
            },
            "R06_autopromo",
        ),
        # R07 : horoscope
        (
            {"titre": "Horoscope du jeudi 23 octobre : votre signe sous les étoiles"},
            "R07_horoscope",
        ),
        ({"rubrique": "Horoscope"}, "R07_horoscope"),
        # R08 : programme télé
        (
            {"titre": "Programme TV de ce soir : que regarder à la télé ce jeudi"},
            "R08_programme_tv",
        ),
        ({"rubrique": "Programme TV"}, "R08_programme_tv"),
        # R09 : jeux
        ({"titre": "Quiz : testez vos connaissances sur la tempête"}, "R09_jeux"),
        ({"titre": "Mots croisés du jour : la grille du jeudi"}, "R09_jeux"),
        ({"titre": "Jeu concours : gagnez deux places pour le match"}, "R09_jeux"),
        ({"rubrique": "Jeux"}, "R09_jeux"),
        # R10 : rubrique « magazine » (vrais articles du Progrès)
        (
            {
                "source": "Le Progrès",
                "rubrique": "Magazine Lifestyle",
                "titre": "Témoignage. « J’ai peur de reprendre du poids » : Émilie raconte",
            },
            "R10_rubrique_exclue",
        ),
        (
            {
                "source": "Le Progrès",
                "rubrique": "Magazine Automobile",
                "titre": "Automobile. Rouler au fioul à la place du gasoil : bonne ou mauvaise idée ?",
            },
            "R10_rubrique_exclue",
        ),
        # R11 : replay (vrai titre de La Dépêche du Midi)
        (
            {
                "source": "La Dépêche du Midi",
                "titre": "REPLAY. Manifestations du 24 octobre : Emmanuel Macron recevra "
                "les organisations lycéennes vendredi",
            },
            "R11_replay",
        ),
        # R12 : avis de décès
        ({"titre": "Avis de décès : M. Dupont nous a quittés à l'âge de 91 ans"}, "R12_avis_deces"),
        ({"titre": "Remerciements de la famille suite au décès de Mme Martin"}, "R12_avis_deces"),
        # R13 : trop ancien (mesuré depuis la collecte)
        ({"publie_le": COLLECTE - FRAICHEUR_MAX - timedelta(minutes=1)}, "R13_trop_ancien"),
        ({"publie_le": COLLECTE - timedelta(days=372)}, "R13_trop_ancien"),
    ],
)
def test_article_ecarte_par_la_bonne_regle(champs, regle):
    assert appliquer_regles(article(**champs)) == regle


# --- les limites : ce qui doit rester gardé ---------------------------------------


@pytest.mark.parametrize(
    "champs",
    [
        # Pile à la limite de fraîcheur, et petite avance de l'horloge : tolérés.
        {"publie_le": COLLECTE - FRAICHEUR_MAX},
        {"publie_le": COLLECTE + TOLERANCE_FUTUR},
        # « Carnet noir » : ici la mort d'une personnalité publique, donc de l'actualité.
        {
            "source": "La Dépêche du Midi",
            "rubrique": "Carnet noir",
            "titre": "Mort de Jean-Paul Huchon : l'ancien président socialiste de la région "
            "Île-de-France est décédé à l'âge de 80 ans",
        },
        # « Concours. » désigne ici un concours de beauté, pas un jeu.
        {
            "source": "Le Progrès",
            "rubrique": "People",
            "titre": "Concours. Miss Univers : Garance Authié représentera la France "
            "sans passer par Miss France",
        },
        # « jeu » au sens sportif.
        {
            "source": "La Dépêche du Midi",
            "titre": "Fenix Handball : à Toulouse, la parole est à la défense ! Radioscopie "
            "d'un secteur de jeu où les hommes de Danijel Andjelkovic excellent",
        },
        # Un direct d'actualité n'est pas un replay.
        {
            "source": "La Dépêche du Midi",
            "titre": "DIRECT. Manifestations du 24 octobre : Emmanuel Macron va recevoir les lycéens",
        },
        {
            "source": "Le Figaro",
            "titre": "EN DIRECT - Tempête Austen : 23 départements en alerte orange",
        },
        # Un journal cité dans un entretien n'est pas de l'auto-promotion.
        {"titre": "Dans un entretien accordé au Monde, le ministre annonce une réforme"},
        {
            "source": "Le Figaro",
            "titre": "Découvrez les résultats du sondage Ifop pour Le Figaro Magazine",
        },
        # Un jeu télévisé présenté dans la rubrique médias : un sujet de rédaction.
        {
            "source": "La Dépêche du Midi",
            "rubrique": "Télé - médias",
            "titre": "Wanted : on vous présente le nouveau jeu de course-poursuite lancé sur M6",
        },
    ],
)
def test_articles_a_ne_pas_ecarter(champs):
    assert appliquer_regles(article(**champs)) is None


def test_la_premiere_regle_de_la_liste_l_emporte():
    # Titre vide ET trop ancien : c'est R01 qui est comptée.
    ancien_et_vide = article(titre="", publie_le=COLLECTE - timedelta(days=30))
    assert appliquer_regles(ancien_et_vide) == "R01_titre_vide"


def test_un_article_ancien_et_publicitaire_est_compte_comme_publicitaire():
    # Les règles de contenu passent avant la fraîcheur, pour rester visibles dans le rapport.
    vieux_publi = article(
        titre="Contenu partenaire : le meilleur de l'été",
        publie_le=COLLECTE - timedelta(days=30),
    )
    assert appliquer_regles(vieux_publi) == "R05_publi"


def test_les_regles_ne_dependent_pas_de_l_heure_de_la_machine():
    # La fraîcheur est mesurée par rapport à recupere_le : même résultat dans dix ans.
    assert appliquer_regles(article()) is None
    ancien = article(publie_le=COLLECTE - timedelta(hours=30))
    assert appliquer_regles(ancien) == "R13_trop_ancien"


def test_sans_date_de_collecte_on_ne_juge_pas_la_fraicheur():
    assert (
        appliquer_regles(
            article(recupere_le=None, publie_le=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
        is None
    )


# --- outils -----------------------------------------------------------------------


def test_simplifier_retire_accents_majuscules_et_apostrophes_typographiques():
    assert simplifier("L’Île-de-France à l’honneur") == "l'ile-de-france a l'honneur"
    assert simplifier(None) == ""


def test_mots_du_titre_garde_les_nombres_et_ignore_les_petits_mots():
    assert mots_du_titre("Tempête Austen : 23 départements en vigilance") == frozenset(
        {"tempete", "austen", "23", "departements", "vigilance"}
    )


def test_jaccard():
    a, b = frozenset({"a", "b", "c", "d"}), frozenset({"c", "d", "e", "f"})
    assert jaccard(a, b) == pytest.approx(2 / 6)
    assert jaccard(a, a) == 1.0
    assert jaccard(a, frozenset()) == 0.0


# --- doublons ---------------------------------------------------------------------

TITRE_TEMPETE = "Tempête Austen : 23 départements en vigilance orange vent"


def test_doublon_exact_meme_source_meme_titre_a_la_casse_et_aux_accents_pres():
    premier = article(id="a1", titre=TITRE_TEMPETE, publie_le=COLLECTE - timedelta(hours=3))
    second = article(
        id="a2",
        lien="https://exemple.fr/a2",
        titre="TEMPETE AUSTEN :  23 departements en vigilance orange vent",
        publie_le=COLLECTE - timedelta(hours=1),
    )
    gardes, rejets = filtrer([second, premier])
    assert [a["id"] for a in gardes] == ["a1"]
    assert [(a["id"], r) for a, r in rejets] == [("a2", "R14_doublon_exact")]


def test_doublon_approximatif_a_un_mot_pres():
    premier = article(id="a1", titre=TITRE_TEMPETE, publie_le=COLLECTE - timedelta(hours=3))
    second = article(
        id="a2", titre=TITRE_TEMPETE + " jeudi", publie_le=COLLECTE - timedelta(hours=1)
    )
    gardes, rejets = filtrer([premier, second])
    assert [a["id"] for a in gardes] == ["a1"]
    assert [(a["id"], r) for a, r in rejets] == [("a2", "R15_doublon_approx")]


def test_on_garde_le_premier_publie_quel_que_soit_l_ordre_d_entree():
    ancien = article(id="ancien", titre=TITRE_TEMPETE, publie_le=COLLECTE - timedelta(hours=5))
    recent = article(
        id="recent", titre=TITRE_TEMPETE + " jeudi", publie_le=COLLECTE - timedelta(hours=1)
    )
    for entree in ([ancien, recent], [recent, ancien]):
        gardes, rejets = filtrer(entree)
        assert [a["id"] for a in gardes] == ["ancien"]
        assert [a["id"] for a, _ in rejets] == ["recent"]


def test_pas_de_doublon_entre_deux_sources():
    # Deux journaux sur le même sujet : c'est ce que la gazette doit montrer.
    libe = article(
        id="libe",
        source="Libération",
        titre="Mort de Jean-Paul Huchon, ancien président de la région Ile-de-France",
    )
    croix = article(
        id="croix",
        source="La Croix",
        titre="Mort de Jean-Paul Huchon, ancien président PS de la région Île-de-France",
    )
    gardes, rejets = filtrer([libe, croix])
    assert len(gardes) == 2 and rejets == []


def test_deux_articles_distincts_proches_ne_sont_pas_des_doublons():
    # Vrais titres de La Dépêche du Midi : deux étapes de la même affaire (Jaccard 0,69 < 0,8).
    parcours = article(
        id="p1",
        source="La Dépêche du Midi",
        titre="Manifestation du 24 octobre à Toulouse : un parcours plus éloigné du centre-ville",
        publie_le=COLLECTE - timedelta(hours=16),
    )
    accord = article(
        id="p2",
        source="La Dépêche du Midi",
        titre="Manifestation du 24 octobre à Toulouse : accord préfecture-syndicats pour un parcours plus éloigné du centre-ville",
        publie_le=COLLECTE - timedelta(hours=15),
    )
    gardes, rejets = filtrer([parcours, accord])
    assert len(gardes) == 2 and rejets == []


def test_les_titres_trop_courts_ne_sont_pas_compares():
    # « Billet » ou « Édito » reviennent chaque jour : jamais des doublons.
    lundi = article(id="l", titre="Édito", publie_le=COLLECTE - timedelta(hours=20))
    mardi = article(id="m", titre="Édito", publie_le=COLLECTE - timedelta(hours=2))
    gardes, rejets = filtrer([lundi, mardi])
    assert len(gardes) == 2 and rejets == []


def test_doublon_avec_un_article_deja_garde_lors_d_un_passage_precedent():
    deja = article(id="deja", titre=TITRE_TEMPETE, publie_le=COLLECTE - timedelta(hours=10))
    nouveau = article(id="nouveau", titre=TITRE_TEMPETE, publie_le=COLLECTE - timedelta(hours=1))
    gardes, rejets = filtrer([nouveau], deja_gardes=[deja])
    assert gardes == []
    assert [(a["id"], r) for a, r in rejets] == [("nouveau", "R14_doublon_exact")]


def test_filtrer_separe_gardes_et_rejetes_avec_la_regle():
    ok = article(id="ok")
    vide = article(id="vide", titre="")
    replay = article(id="replay", titre="REPLAY. Le direct d'hier soir sur la tempête")
    gardes, rejets = filtrer([ok, vide, replay])
    assert [a["id"] for a in gardes] == ["ok"]
    assert sorted((a["id"], r) for a, r in rejets) == [
        ("replay", "R11_replay"),
        ("vide", "R01_titre_vide"),
    ]
