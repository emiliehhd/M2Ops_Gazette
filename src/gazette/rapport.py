"""Rapport de qualité : ce qu'un passage a gardé et rejeté, par règle et par source.

Les fonctions de construction sont pures : elles prennent des « décisions » (une par article
traité) et rendent un dictionnaire, puis du Markdown. Seule `ecrire_rapport` touche au disque.

Une décision est un triplet (source, titre, regle) : `regle` vaut None pour un article gardé,
l'identifiant de la règle (R06_autopromo…) pour un article rejeté.

Un rapport qui ne permet pas de repérer une règle trop gourmande ne sert à rien : d'où la part
de chaque source écartée par chaque règle, les cinq couples (règle, source) les plus fréquents
et la liste « à surveiller ».
"""

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from gazette.regles import DESCRIPTIONS

# Une règle qui écarte au moins cette part des articles d'une source est « à surveiller »...
SEUIL_REGLE_A_SURVEILLER = 0.30
# ... à condition d'avoir écarté au moins ce nombre d'articles (un seul rejet sur trois
# articles ne prouve rien).
MIN_REJETS_A_SURVEILLER = 3
NB_RANGS = 5
NB_EXEMPLES = 3


def decisions_depuis_filtrage(gardes: list[dict], rejets: list[tuple[dict, str]]):
    """Convertit le résultat de `regles.filtrer` en décisions pour le rapport."""
    return [(a["source"], a["titre"], None) for a in gardes] + [
        (a["source"], a["titre"], regle) for a, regle in rejets
    ]


def construire_rapport(decisions: Iterable[tuple[str, str, str | None]], jour: date) -> dict:
    """Résume les décisions en un dictionnaire (sérialisable en JSON)."""
    decisions = list(decisions)
    entres = len(decisions)
    rejetes = sum(1 for _, _, regle in decisions if regle)

    entres_par_source = Counter(source for source, _, _ in decisions)
    rejets_par_source = Counter(source for source, _, regle in decisions if regle)
    rejets_par_regle = Counter(regle for _, _, regle in decisions if regle)
    rejets_par_couple = Counter((regle, source) for source, _, regle in decisions if regle)

    par_regle = [
        {
            "regle": regle,
            "description": DESCRIPTIONS.get(regle, ""),
            "rejets": n,
            "part_des_entres": n / entres,
        }
        for regle, n in sorted(rejets_par_regle.items(), key=lambda x: (-x[1], x[0]))
    ]
    par_source = [
        {
            "source": source,
            "entres": n,
            "gardes": n - rejets_par_source[source],
            "rejetes": rejets_par_source[source],
            "taux_rejet": rejets_par_source[source] / n,
        }
        for source, n in sorted(entres_par_source.items(), key=lambda x: (-x[1], x[0]))
    ]
    couples = [
        {
            "regle": regle,
            "source": source,
            "rejets": n,
            "part_de_la_source": n / entres_par_source[source],
        }
        for (regle, source), n in rejets_par_couple.items()
    ]
    couples.sort(key=lambda c: (-c["rejets"], -c["part_de_la_source"], c["regle"], c["source"]))

    exemples: dict[str, list[str]] = defaultdict(list)
    for _, titre, regle in sorted(decisions, key=lambda d: (d[2] or "", d[0], d[1])):
        if regle and len(exemples[regle]) < NB_EXEMPLES:
            exemples[regle].append(titre)

    return {
        "jour": jour.isoformat(),
        "entres": entres,
        "gardes": entres - rejetes,
        "rejetes": rejetes,
        "taux_rejet": rejetes / entres if entres else 0.0,
        "par_regle": par_regle,
        "par_source": par_source,
        "top_rejets": couples[:NB_RANGS],
        "a_surveiller": [
            c
            for c in couples
            if c["part_de_la_source"] >= SEUIL_REGLE_A_SURVEILLER
            and c["rejets"] >= MIN_REJETS_A_SURVEILLER
        ],
        "exemples": dict(sorted(exemples.items())),
    }


def _pct(part: float) -> str:
    return f"{part * 100:.1f}".replace(".", ",") + " %"


def en_markdown(rapport: dict) -> str:
    """Met le rapport en forme pour être lu par une personne."""
    r = rapport
    lignes = [f"# Rapport de qualité du {r['jour']}", ""]
    if not r["entres"]:
        return "\n".join(lignes + ["Aucun article traité."]) + "\n"

    lignes += [
        (
            f"**{r['entres']} articles traités : {r['gardes']} gardés, {r['rejetes']} rejetés "
            f"({_pct(r['taux_rejet'])}).**"
        ),
        "",
        "## Rejets par règle",
        "",
    ]
    if r["par_regle"]:
        lignes += [
            "| Règle | Ce qu'elle écarte | Rejets | Part des articles traités |",
            "|---|---|---|---|",
        ]
        lignes += [
            f"| `{x['regle']}` | {x['description']} | {x['rejets']} | {_pct(x['part_des_entres'])} |"
            for x in r["par_regle"]
        ]
    else:
        lignes.append("Aucun rejet.")

    lignes += [
        "",
        "## Par source",
        "",
        "| Source | Traités | Gardés | Rejetés | Taux de rejet |",
        "|---|---|---|---|---|",
    ]
    lignes += [
        f"| {x['source']} | {x['entres']} | {x['gardes']} | {x['rejetes']} | {_pct(x['taux_rejet'])} |"
        for x in r["par_source"]
    ]

    lignes += ["", f"## Les {NB_RANGS} rejets les plus fréquents (règle et source)", ""]
    if r["top_rejets"]:
        lignes += ["| Règle | Source | Rejets | Part de la source |", "|---|---|---|---|"]
        lignes += [
            f"| `{x['regle']}` | {x['source']} | {x['rejets']} | {_pct(x['part_de_la_source'])} |"
            for x in r["top_rejets"]
        ]
    else:
        lignes.append("Aucun rejet.")

    lignes += [
        "",
        "## Règles à surveiller",
        "",
        (
            f"Une règle est signalée quand elle écarte au moins "
            f"{_pct(SEUIL_REGLE_A_SURVEILLER)} des articles d'une source "
            f"(et au moins {MIN_REJETS_A_SURVEILLER} articles) : elle est peut-être trop gourmande."
        ),
        "",
    ]
    if r["a_surveiller"]:
        lignes += [
            f"- `{x['regle']}` sur {x['source']} : {x['rejets']} rejets, "
            f"{_pct(x['part_de_la_source'])} de la source"
            for x in r["a_surveiller"]
        ]
    else:
        lignes.append("Aucune.")

    if r["exemples"]:
        lignes += ["", "## Exemples de rejets", ""]
        for regle, titres in r["exemples"].items():
            lignes.append(f"- `{regle}`")
            lignes += [f"  - {titre}" for titre in titres]
    return "\n".join(lignes) + "\n"


def ecrire_rapport(rapport: dict, dossier: Path = Path("rapports")) -> tuple[Path, Path]:
    """Écrit rapports/qualite-AAAA-MM-JJ.md et .json ; un nouvel appel remplace les fichiers."""
    dossier.mkdir(parents=True, exist_ok=True)
    base = dossier / f"qualite-{rapport['jour']}"
    chemin_md, chemin_json = base.with_suffix(".md"), base.with_suffix(".json")
    chemin_md.write_text(en_markdown(rapport), encoding="utf-8")
    chemin_json.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin_md, chemin_json
