"""Métriques : les chiffres de chaque passe (articles reçus, gardés, rejetés…).

Une métrique est un triplet (nom, étiquette, valeur) : l'étiquette précise de quoi on parle
(une source, une règle, un contrôle) et reste vide pour une valeur globale. Les fonctions
`metriques_*` sont pures ; `enregistrer_metriques` les écrit dans la table `metriques`, qui
garde l'historique : on peut y voir une dérive d'un jour à l'autre.
"""

from datetime import datetime

import psycopg

Metrique = tuple[str, str, float]


def metriques_collecte(compteurs: dict) -> list[Metrique]:
    """Chiffres d'une passe de collecte (résultat de `collecter_tout`)."""
    return [
        ("collecte_recus", "", compteurs["recus"]),
        ("collecte_ecrits", "", compteurs["ecrits"]),
        ("collecte_ignores", "", compteurs["ignores"]),
        ("collecte_sources_inchangees", "", compteurs["inchangees"]),
        ("collecte_sources_en_erreur", "", compteurs["erreurs"]),
        ("collecte_sources_en_sommeil", "", compteurs["en_sommeil"]),
        ("collecte_duree_secondes", "", compteurs["duree_s"]),
    ]


def metriques_nettoyage(compteurs: dict) -> list[Metrique]:
    """Chiffres d'une passe de nettoyage (résultat de `traiter_passe`)."""
    metriques = [
        ("nettoyage_entres", "", compteurs["entres"]),
        ("nettoyage_gardes", "", compteurs["gardes"]),
        ("nettoyage_rejetes", "", compteurs["rejetes"]),
        ("nettoyage_illisibles", "", compteurs["illisibles"]),
    ]
    return metriques + [
        ("nettoyage_rejets_par_regle", regle, n) for regle, n in compteurs["par_regle"].items()
    ]


def metriques_jour(rapport: dict) -> list[Metrique]:
    """Chiffres cumulés de la journée (UTC), tirés du rapport de qualité."""
    metriques = [
        ("jour_traites", "", rapport["entres"]),
        ("jour_gardes", "", rapport["gardes"]),
        ("jour_rejetes", "", rapport["rejetes"]),
        ("jour_taux_rejet", "", rapport["taux_rejet"]),
    ]
    for s in rapport["par_source"]:
        metriques += [
            ("jour_traites_par_source", s["source"], s["entres"]),
            ("jour_rejetes_par_source", s["source"], s["rejetes"]),
            ("jour_taux_rejet_par_source", s["source"], s["taux_rejet"]),
        ]
    return metriques + [
        ("jour_rejets_par_regle", r["regle"], r["rejets"]) for r in rapport["par_regle"]
    ]


def metriques_controles(resultats: list) -> list[Metrique]:
    """Résultat de chaque contrôle (1 = vérifié, 0 = en échec) et sa valeur mesurée."""
    metriques = [("controles_en_echec", "", sum(1 for r in resultats if not r.ok))]
    for r in resultats:
        metriques += [("controle_ok", r.id, 1 if r.ok else 0), ("controle_valeur", r.id, r.valeur)]
    return metriques


def enregistrer_metriques(
    conn: psycopg.Connection, mesure_le: datetime, metriques: list[Metrique]
) -> None:
    with conn.transaction(), conn.cursor() as curseur:
        curseur.executemany(
            "INSERT INTO metriques (mesure_le, nom, etiquette, valeur) VALUES (%s, %s, %s, %s)",
            [(mesure_le, nom, etiquette, float(valeur)) for nom, etiquette, valeur in metriques],
        )
    conn.commit()
