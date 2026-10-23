"""Contrôles de qualité des données, métriques et alerte Discord, après chaque passe.

Les tests (CI) vérifient le CODE des règles sur une fixture. Les contrôles d'ici vérifient des
FAITS sur les vraies données (tables `articles_propres`, `rejets`, `sources`) : « aucune date
future », « aucun titre vide », « le taux de rejet d'une source reste raisonnable ». Leur place
est l'exploitation : ils tournent dans une tâche Airflow, après chaque passe.

Alerte : un message Discord à l'apparition d'une panne, en rappel après 24 h si elle dure,
et quand elle est rétablie. Pas un message toutes les 30 minutes pour la même panne.

Commandes : `python -m gazette.controles` (lancer les contrôles maintenant) et
`python -m gazette.controles test-alerte` (vérifier que le canal Discord fonctionne).
"""

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import psycopg
import requests

from gazette.collecteur import journal
from gazette.db import connexion, migrer
from gazette.metriques import (
    enregistrer_metriques,
    metriques_collecte,
    metriques_controles,
    metriques_jour,
    metriques_nettoyage,
)
from gazette.nettoyage import decisions_du_jour
from gazette.normalisation import EXTRAIT_MAX
from gazette.rapport import construire_rapport
from gazette.regles import FRAICHEUR_MAX, TOLERANCE_FUTUR

# Un contrôle échoue si une source voit plus de cette part de ses articles rejetés (le seuil se
# règle par la variable GAZETTE_SEUIL_TAUX_REJET, utile pour provoquer l'alerte à la demande).
SEUIL_TAUX_REJET_DEFAUT = 0.8
# Une source qui n'a que 1 ou 2 articles traités n'a pas de taux de rejet significatif.
MIN_ARTICLES_TAUX = 5
# La collecte est vivante si au moins une source a réussi depuis moins de 2 heures (4 passes).
RETARD_MAX_COLLECTE = timedelta(hours=2)
# Une panne qui dure est rappelée toutes les 24 heures.
RAPPEL = timedelta(hours=24)
LIMITE_MESSAGE = 1900  # Discord refuse plus de 2000 caractères


class ErreurAlerte(Exception):
    """Le message n'a pas pu être envoyé à Discord."""


@dataclass(frozen=True)
class Resultat:
    id: str
    fait: str  # le fait vérifié, en une phrase
    ok: bool
    valeur: float  # ce qu'on a mesuré (0 attendu pour un « aucun… »)
    detail: str = ""


@dataclass(frozen=True)
class Contexte:
    jour: date
    maintenant: datetime
    seuil_taux_rejet: float


@dataclass(frozen=True)
class Evenement:
    type: str  # "alerte", "rappel" ou "retabli"
    resultat: Resultat


def seuil_taux_rejet() -> float:
    return float(os.environ.get("GAZETTE_SEUIL_TAUX_REJET", SEUIL_TAUX_REJET_DEFAUT))


def pct(part: float) -> str:
    return f"{part * 100:.1f}".replace(".", ",") + " %"


# --------------------------------------------------------------------------------------
# Les contrôles : chacun répond par un Resultat.
# --------------------------------------------------------------------------------------


def _compter(conn: psycopg.Connection, requete: str, params: tuple = ()) -> int:
    return conn.execute(requete, params).fetchone()[0]


def _aucun(identifiant: str, fait: str, nombre: int, unite: str) -> Resultat:
    detail = "" if nombre == 0 else f"{nombre} {unite}"
    return Resultat(identifiant, fait, nombre == 0, nombre, detail)


def aucune_date_future(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    n = _compter(
        conn,
        "SELECT count(*) FROM articles_propres WHERE publie_le - recupere_le > %s",
        (TOLERANCE_FUTUR,),
    )
    return _aucun(
        "C01_aucune_date_future", "Aucun article gardé n'a une date future", n, "article(s)"
    )


def aucun_titre_vide(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    n = _compter(conn, "SELECT count(*) FROM articles_propres WHERE btrim(titre) = ''")
    return _aucun("C02_aucun_titre_vide", "Aucun article gardé n'a un titre vide", n, "article(s)")


def aucun_article_trop_ancien(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    n = _compter(
        conn,
        "SELECT count(*) FROM articles_propres WHERE recupere_le - publie_le > %s",
        (FRAICHEUR_MAX,),
    )
    return _aucun(
        "C03_aucun_article_trop_ancien",
        "Aucun article gardé n'avait plus de 24 h à sa collecte",
        n,
        "article(s)",
    )


def taux_rejet_par_source(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    """Le taux de rejet d'une source ne dépasse pas le seuil (sur la journée UTC en cours)."""
    mesurees = [s for s in rapport["par_source"] if s["entres"] >= MIN_ARTICLES_TAUX]
    trop = [s for s in mesurees if s["taux_rejet"] > ctx.seuil_taux_rejet]
    pire = max((s["taux_rejet"] for s in mesurees), default=0.0)
    detail = ", ".join(
        f"{s['source']} {pct(s['taux_rejet'])} ({s['rejetes']} sur {s['entres']})" for s in trop
    )
    return Resultat(
        "C04_taux_rejet_par_source",
        f"Le taux de rejet d'une source ne dépasse pas {pct(ctx.seuil_taux_rejet)}",
        not trop,
        pire,
        detail,
    )


def extrait_borne(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    n = _compter(
        conn, "SELECT count(*) FROM articles_propres WHERE length(extrait) > %s", (EXTRAIT_MAX,)
    )
    return _aucun(
        "C05_extrait_borne",
        f"Aucun extrait ne dépasse {EXTRAIT_MAX} caractères",
        n,
        "article(s)",
    )


def aucun_html(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    n = _compter(
        conn,
        "SELECT count(*) FROM articles_propres WHERE titre ~ '<[a-zA-Z/]' OR extrait ~ '<[a-zA-Z/]'",
    )
    return _aucun(
        "C06_aucun_html", "Aucun titre ni extrait ne contient de balise HTML", n, "article(s)"
    )


def aucune_source_en_sommeil(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    noms = [n for (n,) in conn.execute("SELECT nom FROM sources WHERE NOT actif ORDER BY nom")]
    return Resultat(
        "C07_aucune_source_en_sommeil",
        "Aucune source n'est en sommeil",
        not noms,
        len(noms),
        ", ".join(noms),
    )


def collecte_recente(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> Resultat:
    """Au moins une source a été lue avec succès récemment : la collecte n'est pas à l'arrêt."""
    derniere = conn.execute("SELECT max(derniere_reussite) FROM sources").fetchone()[0]
    fait = "Une source au moins a été lue avec succès depuis moins de 2 h"
    if derniere is None:
        return Resultat("C08_collecte_recente", fait, False, -1, "aucune collecte réussie")
    retard = ctx.maintenant - derniere
    minutes = int(retard.total_seconds() // 60)
    detail = "" if retard <= RETARD_MAX_COLLECTE else f"dernière réussite il y a {minutes} min"
    return Resultat("C08_collecte_recente", fait, retard <= RETARD_MAX_COLLECTE, minutes, detail)


CONTROLES = (
    aucune_date_future,
    aucun_titre_vide,
    aucun_article_trop_ancien,
    taux_rejet_par_source,
    extrait_borne,
    aucun_html,
    aucune_source_en_sommeil,
    collecte_recente,
)


def executer_controles(conn: psycopg.Connection, ctx: Contexte, rapport: dict) -> list[Resultat]:
    return [controle(conn, ctx, rapport) for controle in CONTROLES]


# --------------------------------------------------------------------------------------
# Alerte : quand parler, et quoi dire.
# --------------------------------------------------------------------------------------


def lire_etats(conn: psycopg.Connection) -> dict[str, dict]:
    lignes = conn.execute("SELECT controle, en_echec, depuis, derniere_alerte FROM controles_etat")
    return {c: {"en_echec": e, "depuis": d, "derniere_alerte": a} for c, e, d, a in lignes}


def evenements(
    resultats: list[Resultat], etats: dict[str, dict], maintenant: datetime
) -> list[Evenement]:
    """Ce qu'il faut annoncer : une panne qui apparaît, qui dure (rappel), ou qui se rétablit."""
    annonces = []
    for r in resultats:
        ancien = etats.get(r.id)
        etait_en_echec = bool(ancien and ancien["en_echec"])
        derniere = ancien["derniere_alerte"] if ancien else None
        if not r.ok:
            if not etait_en_echec or derniere is None:
                annonces.append(Evenement("alerte", r))
            elif maintenant - derniere >= RAPPEL:
                annonces.append(Evenement("rappel", r))
        elif etait_en_echec and derniere is not None:  # on n'annonce pas ce qu'on n'a jamais dit
            annonces.append(Evenement("retabli", r))
    return annonces


def message_alerte(annonces: list[Evenement], maintenant: datetime) -> str:
    marques = {"alerte": "ALERTE", "rappel": "RAPPEL (toujours en échec)", "retabli": "RÉTABLI"}
    lignes = [f"**La gazette : contrôles de qualité** ({maintenant:%Y-%m-%d %H:%M} UTC)"]
    for a in annonces:
        r = a.resultat
        constat = f" (constaté : {r.detail})" if r.detail and a.type != "retabli" else ""
        lignes.append(f"- **{marques[a.type]}** `{r.id}` : {r.fait}{constat}")
    texte = "\n".join(lignes)
    return texte if len(texte) <= LIMITE_MESSAGE else texte[: LIMITE_MESSAGE - 1] + "…"


def envoyer_discord(url: str, texte: str) -> None:
    """Poste un message sur le canal Discord du webhook.

    L'adresse du webhook est un secret : quiconque la connaît peut écrire dans le canal. Elle
    ne figure donc jamais dans un message d'erreur ni dans le journal (les erreurs de
    `requests` la contiennent), et les mentions (@everyone) sont désactivées.
    """
    corps = {
        "username": "La gazette",
        "content": texte[:LIMITE_MESSAGE],
        "allowed_mentions": {"parse": []},
    }
    try:
        reponse = requests.post(url, json=corps, timeout=(5, 15))
    except requests.RequestException as erreur:
        raise ErreurAlerte(f"envoi à Discord impossible ({type(erreur).__name__})") from None
    if reponse.status_code not in (200, 204):
        raise ErreurAlerte(f"Discord a répondu HTTP {reponse.status_code}")


def sauver_etats(
    conn: psycopg.Connection,
    resultats: list[Resultat],
    anciens: dict[str, dict],
    annonces: list[Evenement],
    annonces_envoyees: bool,
    maintenant: datetime,
) -> None:
    annonce_par_id = {a.resultat.id: a for a in annonces}
    with conn.transaction():
        for r in resultats:
            ancien = anciens.get(r.id)
            etait_en_echec = bool(ancien and ancien["en_echec"])
            annonce = annonce_par_id.get(r.id)
            if r.ok:
                if annonce and not annonces_envoyees:
                    continue  # le rétablissement n'a pas été annoncé : on le retentera
                depuis = ancien["depuis"] if ancien and not etait_en_echec else maintenant
                derniere = None
            else:
                depuis = ancien["depuis"] if etait_en_echec else maintenant
                derniere = ancien["derniere_alerte"] if etait_en_echec else None
                if annonce and annonces_envoyees:
                    derniere = maintenant
            conn.execute(
                "INSERT INTO controles_etat (controle, en_echec, depuis, derniere_alerte, detail) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (controle) DO UPDATE SET en_echec = EXCLUDED.en_echec, "
                "depuis = EXCLUDED.depuis, derniere_alerte = EXCLUDED.derniere_alerte, "
                "detail = EXCLUDED.detail",
                (r.id, not r.ok, depuis, derniere, r.detail),
            )


# --------------------------------------------------------------------------------------
# Une passe de contrôle.
# --------------------------------------------------------------------------------------


def controler_passe(
    conn: psycopg.Connection,
    compteurs_collecte: dict | None = None,
    compteurs_nettoyage: dict | None = None,
    maintenant: datetime | None = None,
    webhook: str | None = None,
) -> dict:
    """Vérifie les faits, alerte si besoin, enregistre les métriques. Renvoie un résumé.

    `webhook` : adresse Discord ; par défaut la variable DISCORD_WEBHOOK_URL. Sans adresse,
    les contrôles et les métriques fonctionnent, seule l'alerte manque (signalée au journal).
    Si Discord refuse le message, les métriques sont tout de même enregistrées, puis l'erreur
    est levée : la tâche devient rouge et l'alerte sera retentée à la passe suivante.
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    if webhook is None:
        webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    ctx = Contexte(maintenant.date(), maintenant, seuil_taux_rejet())

    rapport = construire_rapport(decisions_du_jour(conn, ctx.jour), ctx.jour)
    resultats = executer_controles(conn, ctx, rapport)
    anciens = lire_etats(conn)
    annonces = evenements(resultats, anciens, maintenant)

    envoyees, erreur = False, None
    if annonces and webhook:
        try:
            envoyer_discord(webhook, message_alerte(annonces, maintenant))
            envoyees = True
            journal("alerte_envoyee", controles=[a.resultat.id for a in annonces])
        except ErreurAlerte as e:
            erreur = e
            journal("alerte_non_envoyee", erreur=str(e))
    elif annonces:
        journal("alerte_non_configuree", controles=[a.resultat.id for a in annonces])
    sauver_etats(conn, resultats, anciens, annonces, envoyees, maintenant)

    metriques = metriques_jour(rapport) + metriques_controles(resultats)
    if compteurs_collecte:
        metriques += metriques_collecte(compteurs_collecte)
    if compteurs_nettoyage:
        metriques += metriques_nettoyage(compteurs_nettoyage)
    enregistrer_metriques(conn, maintenant, metriques)
    conn.commit()

    en_echec = [r.id for r in resultats if not r.ok]
    resume = {
        "controles": [
            {"id": r.id, "ok": r.ok, "valeur": r.valeur, "detail": r.detail} for r in resultats
        ],
        "en_echec": en_echec,
        "annonces_envoyees": len(annonces) if envoyees else 0,
        "metriques": len(metriques),
    }
    journal("controles_termines", en_echec=en_echec, ok=len(resultats) - len(en_echec))
    if erreur:
        raise erreur
    return resume


def main() -> None:
    commande = sys.argv[1] if len(sys.argv) > 1 else "controler"
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if commande == "test-alerte":
        if not webhook:
            sys.exit("DISCORD_WEBHOOK_URL n'est pas défini : voir .env.example")
        envoyer_discord(
            webhook, "Test d'alerte de La gazette : si vous lisez ceci, le canal marche."
        )
        print("Message de test envoyé.")
    elif commande == "controler":
        with connexion() as conn:
            migrer(conn)
            resume = controler_passe(conn)
        for c in resume["controles"]:
            etat = "ok   " if c["ok"] else "ECHEC"
            print(f"{etat} {c['id']:32} {c['detail']}")
    else:
        sys.exit(f"Commande inconnue : {commande} (attendu : controler, test-alerte)")


if __name__ == "__main__":
    main()
