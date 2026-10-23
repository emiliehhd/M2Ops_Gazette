"""Tests des contrôles de qualité, des métriques et de l'alerte Discord.

Ils ont besoin d'un PostgreSQL (Docker Compose, CI) et d'un faux serveur Discord local : rien
n'est jamais envoyé à un vrai canal.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from gazette.controles import (
    CONTROLES,
    LIMITE_MESSAGE,
    Contexte,
    ErreurAlerte,
    Evenement,
    Resultat,
    controler_passe,
    envoyer_discord,
    evenements,
    executer_controles,
    message_alerte,
    seuil_taux_rejet,
)
from gazette.db import migrer
from gazette.nettoyage import decisions_du_jour
from gazette.rapport import construire_rapport

MAINTENANT = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
SECRET = "SECRET-TOKEN-DU-WEBHOOK"


# --- faux Discord -----------------------------------------------------------------


class FauxDiscord(BaseHTTPRequestHandler):
    messages: ClassVar[list[dict]] = []
    statut: ClassVar[int] = 204

    def do_POST(self):  # nom imposé par http.server
        taille = int(self.headers["Content-Length"])
        FauxDiscord.messages.append(json.loads(self.rfile.read(taille)))
        self.send_response(FauxDiscord.statut)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def discord():
    """L'adresse d'un faux webhook Discord (avec un faux secret) ; les messages reçus sont dans
    FauxDiscord.messages."""
    FauxDiscord.messages, FauxDiscord.statut = [], 204
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), FauxDiscord)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_port}/api/webhooks/123/{SECRET}"
    serveur.shutdown()


# --- outils de base de données ----------------------------------------------------


def propre(conn, id="a1", source="Le Monde", titre="Un titre", extrait="Un extrait.", publie=None):
    publie = publie if publie is not None else MAINTENANT - timedelta(hours=2)
    conn.execute(
        "INSERT INTO articles_propres "
        "(id, source, lien, titre, extrait, publie_le, recupere_le, rubrique, traite_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s)",
        (id, source, f"https://exemple.fr/{id}", titre, extrait, publie, MAINTENANT, MAINTENANT),
    )
    conn.commit()


def rejet(conn, id, source="Le Monde", regle="R11_replay"):
    conn.execute(
        "INSERT INTO rejets (id, source, lien, titre, regle, publie_le, recupere_le, traite_le) "
        "VALUES (%s, %s, %s, 'Un titre rejeté', %s, %s, %s, %s)",
        (id, source, f"https://exemple.fr/{id}", regle, MAINTENANT, MAINTENANT, MAINTENANT),
    )
    conn.commit()


def source(conn, nom="Le Monde", actif=True, reussite=MAINTENANT - timedelta(minutes=10)):
    conn.execute(
        "INSERT INTO sources (nom, type, url_flux, actif, derniere_reussite) "
        "VALUES (%s, 'PQN', 'https://exemple.fr/flux', %s, %s) "
        "ON CONFLICT (nom) DO UPDATE SET actif = EXCLUDED.actif, "
        "derniere_reussite = EXCLUDED.derniere_reussite",
        (nom, actif, reussite),
    )
    conn.commit()


@pytest.fixture
def base(conn):
    """Tables créées, une source active lue il y a 10 minutes."""
    migrer(conn)
    source(conn)
    return conn


def verifier(conn, seuil=0.8):
    ctx = Contexte(MAINTENANT.date(), MAINTENANT, seuil)
    rapport = construire_rapport(decisions_du_jour(conn, ctx.jour), ctx.jour)
    return {r.id: r for r in executer_controles(conn, ctx, rapport)}


def messages_discord():
    return [m["content"] for m in FauxDiscord.messages]


# --- les contrôles ----------------------------------------------------------------


def test_des_donnees_saines_passent_tous_les_controles(base):
    propre(base)
    resultats = verifier(base)
    assert len(resultats) == len(CONTROLES) == 8
    assert all(r.ok for r in resultats.values()), [r for r in resultats.values() if not r.ok]


def test_une_base_vide_ne_fait_echouer_que_le_controle_de_collecte(conn):
    migrer(conn)  # aucune source, aucun article
    echecs = [r.id for r in verifier(conn).values() if not r.ok]
    assert echecs == ["C08_collecte_recente"]


@pytest.mark.parametrize(
    "controle, preparer",
    [
        ("C01_aucune_date_future", lambda c: propre(c, publie=MAINTENANT + timedelta(hours=1))),
        ("C02_aucun_titre_vide", lambda c: propre(c, titre="   ")),
        (
            "C03_aucun_article_trop_ancien",
            lambda c: propre(c, publie=MAINTENANT - timedelta(hours=30)),
        ),
        ("C05_extrait_borne", lambda c: propre(c, extrait="x" * 301)),
        ("C06_aucun_html", lambda c: propre(c, titre="Un <b>titre</b> mal nettoyé")),
        ("C06_aucun_html", lambda c: propre(c, extrait="Un extrait avec </p> restant")),
        ("C07_aucune_source_en_sommeil", lambda c: source(c, "Sud Ouest", actif=False)),
        (
            "C08_collecte_recente",
            lambda c: source(c, reussite=MAINTENANT - timedelta(hours=3)),
        ),
    ],
)
def test_un_fait_faux_est_detecte(base, controle, preparer):
    preparer(base)
    resultat = verifier(base)[controle]
    assert not resultat.ok
    assert resultat.detail


def test_les_limites_sont_tolerees(base):
    propre(base, id="a1", publie=MAINTENANT + timedelta(minutes=10))  # tolérance d'horloge
    propre(base, id="a2", publie=MAINTENANT - timedelta(hours=24))  # pile 24 h
    propre(base, id="a3", extrait="x" * 300)  # pile la longueur maximale
    resultats = verifier(base)
    assert all(r.ok for r in resultats.values())


def test_la_source_en_sommeil_est_nommee(base):
    source(base, "Sud Ouest", actif=False)
    source(base, "La Voix du Nord", actif=False)
    assert verifier(base)["C07_aucune_source_en_sommeil"].detail == "La Voix du Nord, Sud Ouest"


def test_aucune_collecte_reussie_du_tout(conn):
    migrer(conn)
    source(conn, reussite=None)
    r = verifier(conn)["C08_collecte_recente"]
    assert not r.ok and r.detail == "aucune collecte réussie"


def test_taux_de_rejet_trop_eleve_pour_une_source(base):
    propre(base, id="ok1", source="La Dépêche du Midi")
    for i in range(9):
        rejet(base, f"r{i}", source="La Dépêche du Midi")
    r = verifier(base)["C04_taux_rejet_par_source"]
    assert not r.ok
    assert r.valeur == pytest.approx(0.9)
    assert r.detail == "La Dépêche du Midi 90,0 % (9 sur 10)"


def test_taux_de_rejet_pile_au_seuil_est_accepte(base):
    for i in range(2):
        propre(base, id=f"p{i}", source="Sud Ouest")
    for i in range(8):
        rejet(base, f"r{i}", source="Sud Ouest")
    assert verifier(base)["C04_taux_rejet_par_source"].ok  # 80 % : « ne dépasse pas »


def test_taux_de_rejet_d_une_toute_petite_source_n_est_pas_juge(base):
    for i in range(4):
        rejet(base, f"r{i}", source="Petite source")  # 100 %, mais 4 articles seulement
    assert verifier(base)["C04_taux_rejet_par_source"].ok


def test_le_seuil_de_taux_de_rejet_se_regle(base, monkeypatch):
    for i in range(8):
        propre(base, id=f"p{i}", source="La Dépêche du Midi")
    rejet(base, "r1", source="La Dépêche du Midi")  # 1 sur 9 = 11 %
    assert verifier(base, seuil=0.8)["C04_taux_rejet_par_source"].ok
    assert not verifier(base, seuil=0.05)["C04_taux_rejet_par_source"].ok
    monkeypatch.setenv("GAZETTE_SEUIL_TAUX_REJET", "0.05")
    assert seuil_taux_rejet() == 0.05
    monkeypatch.delenv("GAZETTE_SEUIL_TAUX_REJET")
    assert seuil_taux_rejet() == 0.8


# --- quand alerter (fonction pure) ------------------------------------------------


def res(ok, id="C01_x"):
    return Resultat(id, "Un fait", ok, 0 if ok else 3, "" if ok else "3 article(s)")


def etat(en_echec, derniere_alerte):
    return {"en_echec": en_echec, "depuis": MAINTENANT, "derniere_alerte": derniere_alerte}


def types(annonces):
    return [a.type for a in annonces]


def test_premiere_panne_alerte():
    assert types(evenements([res(False)], {}, MAINTENANT)) == ["alerte"]


def test_une_panne_qui_dure_ne_realerte_pas_avant_24_h():
    etats = {"C01_x": etat(True, MAINTENANT - timedelta(hours=23, minutes=59))}
    assert evenements([res(False)], etats, MAINTENANT) == []


def test_une_panne_qui_dure_est_rappelee_apres_24_h():
    etats = {"C01_x": etat(True, MAINTENANT - timedelta(hours=24))}
    assert types(evenements([res(False)], etats, MAINTENANT)) == ["rappel"]


def test_une_panne_jamais_annoncee_est_annoncee():
    etats = {"C01_x": etat(True, None)}  # Discord n'était pas joignable
    assert types(evenements([res(False)], etats, MAINTENANT)) == ["alerte"]


def test_le_retablissement_est_annonce():
    etats = {"C01_x": etat(True, MAINTENANT - timedelta(hours=2))}
    assert types(evenements([res(True)], etats, MAINTENANT)) == ["retabli"]


def test_rien_a_dire_quand_tout_va_bien():
    assert evenements([res(True)], {}, MAINTENANT) == []
    assert evenements([res(True)], {"C01_x": etat(False, None)}, MAINTENANT) == []


def test_pas_de_retablissement_pour_une_panne_jamais_annoncee():
    etats = {"C01_x": etat(True, None)}
    assert evenements([res(True)], etats, MAINTENANT) == []


# --- le message et l'envoi --------------------------------------------------------


def test_le_message_dit_quoi_et_quand():
    texte = message_alerte([Evenement("alerte", res(False, "C04_taux"))], MAINTENANT)
    assert "2026-10-23 08:00 UTC" in texte
    assert "**ALERTE** `C04_taux` : Un fait (constaté : 3 article(s))" in texte
    texte_retabli = message_alerte([Evenement("retabli", res(True, "C04_taux"))], MAINTENANT)
    assert "**RÉTABLI** `C04_taux` : Un fait" in texte_retabli and "constaté" not in texte_retabli


def test_le_message_ne_depasse_jamais_la_limite_de_discord():
    annonces = [Evenement("alerte", res(False, f"C{i:02d}_x")) for i in range(200)]
    assert len(message_alerte(annonces, MAINTENANT)) <= LIMITE_MESSAGE


def test_envoyer_discord_poste_le_message_sans_mention(discord):
    envoyer_discord(discord, "Bonjour @everyone")
    (corps,) = FauxDiscord.messages
    assert corps["content"] == "Bonjour @everyone"
    assert corps["allowed_mentions"] == {"parse": []}


def test_envoyer_discord_refus_et_secret_non_divulgue(discord):
    FauxDiscord.statut = 500
    with pytest.raises(ErreurAlerte) as erreur:
        envoyer_discord(discord, "x")
    assert "500" in str(erreur.value) and SECRET not in str(erreur.value)


def test_envoyer_discord_serveur_injoignable_et_secret_non_divulgue():
    adresse = f"http://127.0.0.1:1/api/webhooks/123/{SECRET}"  # personne n'écoute sur le port 1
    with pytest.raises(ErreurAlerte) as erreur:
        envoyer_discord(adresse, "x")
    assert SECRET not in str(erreur.value)
    assert SECRET not in repr(erreur.value.__cause__)  # pas de cause enchaînée qui l'afficherait


# --- une passe complète : alerte, silence, rappel, rétablissement -----------------


def lancer(conn, maintenant=MAINTENANT, webhook="", **compteurs):
    return controler_passe(conn, maintenant=maintenant, webhook=webhook, **compteurs)


def test_la_panne_alerte_une_seule_fois_puis_se_rappelle_puis_se_retablit(base, discord):
    propre(base, publie=MAINTENANT + timedelta(hours=1))  # date future : C01 échoue
    premiere = lancer(base, webhook=discord)
    assert premiere["en_echec"] == ["C01_aucune_date_future"]
    assert premiere["annonces_envoyees"] == 1
    assert len(FauxDiscord.messages) == 1
    assert "ALERTE" in messages_discord()[0] and "C01_aucune_date_future" in messages_discord()[0]

    lancer(base, MAINTENANT + timedelta(minutes=30), discord)  # même panne, 30 min plus tard
    assert len(FauxDiscord.messages) == 1  # silence

    lancer(base, MAINTENANT + timedelta(hours=25), discord)  # la panne dure
    assert len(FauxDiscord.messages) == 2 and "RAPPEL" in messages_discord()[1]

    base.execute("DELETE FROM articles_propres")
    base.commit()
    lancer(base, MAINTENANT + timedelta(hours=26), discord)
    assert len(FauxDiscord.messages) == 3 and "RÉTABLI" in messages_discord()[2]

    lancer(base, MAINTENANT + timedelta(hours=27), discord)
    assert len(FauxDiscord.messages) == 3  # tout va bien : plus rien à dire


def test_sans_webhook_les_controles_tournent_et_l_alerte_attend(base, discord):
    propre(base, publie=MAINTENANT + timedelta(hours=1))
    resume = lancer(base, webhook="")
    assert resume["en_echec"] == ["C01_aucune_date_future"]
    assert resume["annonces_envoyees"] == 0
    assert FauxDiscord.messages == []
    # Le webhook est configuré plus tard : la panne, jamais annoncée, l'est maintenant.
    lancer(base, MAINTENANT + timedelta(minutes=30), discord)
    assert len(FauxDiscord.messages) == 1


def test_discord_refuse_les_metriques_sont_gardees_et_l_alerte_sera_retentee(base, discord):
    propre(base, publie=MAINTENANT + timedelta(hours=1))
    FauxDiscord.statut = 500
    with pytest.raises(ErreurAlerte):
        lancer(base, webhook=discord)
    assert base.execute("SELECT count(*) FROM metriques").fetchone()[0] > 0
    assert (
        base.execute("SELECT derniere_alerte FROM controles_etat WHERE en_echec").fetchall()
        == [(None,)] * 1
    )
    FauxDiscord.statut = 204  # Discord revient : la passe suivante réalerte
    lancer(base, MAINTENANT + timedelta(minutes=30), discord)
    assert any("ALERTE" in m for m in messages_discord())


def test_plusieurs_pannes_donnent_un_seul_message(base, discord):
    propre(base, titre="  ", publie=MAINTENANT + timedelta(hours=1))  # C01 et C02
    lancer(base, webhook=discord)
    assert len(FauxDiscord.messages) == 1
    texte = messages_discord()[0]
    assert "C01_aucune_date_future" in texte and "C02_aucun_titre_vide" in texte


# --- les métriques ----------------------------------------------------------------


def valeurs(conn, nom):
    lignes = conn.execute("SELECT etiquette, valeur FROM metriques WHERE nom = %s", (nom,))
    return dict(lignes.fetchall())


def test_les_metriques_comptent_les_articles_recus_gardes_et_rejetes(base):
    propre(base, id="p1", source="Le Monde")
    propre(base, id="p2", source="Le Monde")
    rejet(base, "r1", source="Le Monde", regle="R11_replay")
    rejet(base, "r2", source="La Croix", regle="R13_trop_ancien")
    collecte = {
        "sources": 8,
        "ok": 6,
        "inchangees": 1,
        "erreurs": 1,
        "en_sommeil": 1,
        "recus": 120,
        "ecrits": 40,
        "ignores": 80,
        "duree_s": 12.5,
    }
    nettoyage = {
        "entres": 40,
        "gardes": 38,
        "rejetes": 2,
        "illisibles": 0,
        "par_regle": {"R11_replay": 1, "R13_trop_ancien": 1},
    }
    lancer(base, compteurs_collecte=collecte, compteurs_nettoyage=nettoyage)

    assert valeurs(base, "collecte_recus") == {"": 120}
    assert valeurs(base, "collecte_ecrits") == {"": 40}
    assert valeurs(base, "collecte_sources_en_sommeil") == {"": 1}
    assert valeurs(base, "nettoyage_entres") == {"": 40}
    assert valeurs(base, "nettoyage_rejets_par_regle") == {"R11_replay": 1, "R13_trop_ancien": 1}
    assert valeurs(base, "jour_traites") == {"": 4}
    assert valeurs(base, "jour_rejetes") == {"": 2}
    assert valeurs(base, "jour_taux_rejet") == {"": 0.5}
    assert valeurs(base, "jour_rejetes_par_source") == {"Le Monde": 1, "La Croix": 1}
    assert valeurs(base, "jour_taux_rejet_par_source")["Le Monde"] == pytest.approx(1 / 3)
    assert valeurs(base, "controles_en_echec") == {"": 0}
    assert len(valeurs(base, "controle_ok")) == len(CONTROLES) == 8
    assert set(valeurs(base, "controle_ok").values()) == {1}  # tous vérifiés


def test_chaque_passe_ajoute_ses_metriques_a_l_historique(base):
    propre(base)
    lancer(base, MAINTENANT)
    lancer(base, MAINTENANT + timedelta(minutes=30))
    n = base.execute("SELECT count(DISTINCT mesure_le) FROM metriques").fetchone()[0]
    assert n == 2


def test_les_metriques_sont_enregistrees_meme_sans_compteurs(base):
    propre(base)
    resume = lancer(base)
    assert resume["metriques"] > 0
    assert valeurs(base, "collecte_recus") == {}  # pas de compteurs de collecte fournis
