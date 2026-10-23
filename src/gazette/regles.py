"""Règles d'exclusion et dédoublonnage des articles normalisés.

Toutes les règles travaillent sur un article déjà normalisé (voir normalisation.py) et
sont lisibles ici : réglages en haut du fichier, une fonction par règle, la liste ordonnée
REGLES en bas. Chaque règle a un identifiant stable (R01_titre_vide, R06_publi…) : le
rapport de qualité compte les rejets par identifiant. Quand plusieurs règles s'appliquent
à un article, seule la première (dans l'ordre de REGLES) est retenue.

Les règles sont déterministes : elles ne regardent jamais l'heure de la machine. La
fraîcheur se mesure par rapport à `recupere_le` (le moment de la collecte), pour qu'un
rejeu du même brut donne exactement le même résultat.
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

# --------------------------------------------------------------------------------------
# Réglages : c'est ici, et seulement ici, qu'on les ajuste.
# --------------------------------------------------------------------------------------

# Un article publié plus de 24 h avant sa collecte est écarté.
FRAICHEUR_MAX = timedelta(hours=24)
# Une date postérieure à la collecte de plus de 10 minutes est jugée fausse.
TOLERANCE_FUTUR = timedelta(minutes=10)
# Deux titres d'une même source sont des doublons approximatifs à partir de ce seuil de
# Jaccard (part de mots communs). À 0,6, deux articles distincts sur la manifestation du
# 24 octobre à Toulouse étaient rapprochés à tort ; à 0,8 ils restent séparés.
SEUIL_DOUBLON_APPROX = 0.8
# En dessous de ce nombre de mots, un titre est trop court pour juger d'un doublon
# (« Billet », « Édito » reviennent légitimement chaque jour).
MIN_MOTS_DOUBLON = 4

# Rubriques de contenu « magazine » (conseils, témoignages) qui ne sont pas de l'actualité.
# Les comparaisons se font sans accents ni majuscules.
RUBRIQUES_EXCLUES = frozenset({"magazine lifestyle", "magazine automobile"})
RUBRIQUES_JEUX = frozenset({"jeux", "jeux et concours", "mots croises", "loto"})

# Motifs cherchés dans le titre (et la rubrique), sans accents ni majuscules.
MOTIF_PUBLI = re.compile(
    r"contenu partenaire|contenu sponsorise|publi-?reportage|brand content|partenariat commercial"
)
MOTIF_HOROSCOPE = re.compile(r"\bhoroscope|\bastrologi")
MOTIF_PROGRAMME_TV = re.compile(
    r"\bprogrammes? tv\b|\bprogramme tele\b|ce soir a la tele|a la tele ce soir"
    r"|que regarder (?:a la tele|ce soir)|\bprogramme de la soiree\b"
)
MOTIF_JEUX = re.compile(
    r"\bjeu[- ]concours\b|\bquiz\b|\bmots? (?:croises|fleches)\b|\bsudoku\b"
    r"|\bgagnez\b|\btentez de gagner\b|\bespace jeux\b"
)
MOTIF_REPLAY = re.compile(r"^\s*replay\b")
MOTIF_AVIS_DECES = re.compile(
    r"\bavis de deces\b|\bavis d'obseques\b|\bfaire-part\b|\bremerciements? (?:de la famille|suite)"
)
# Texte encore cassé après normalisation : « Ã » (jamais utilisé en français), « â€ »,
# ou le caractère de remplacement.
MARQUEURS_ENCODAGE_CASSE = ("Ã", "â€", "\ufffd")


# --------------------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------------------


def simplifier(texte: str | None) -> str:
    """Minuscules, sans accents, apostrophes droites, espaces uniques : pour comparer et chercher."""
    texte = (texte or "").replace("’", "'")
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().split())


def mots_du_titre(titre: str | None) -> frozenset[str]:
    """Mots significatifs d'un titre : plus de 2 lettres, ou nombres (le « 24 » compte)."""
    mots = re.findall(r"[a-z0-9]+", simplifier(titre))
    return frozenset(m for m in mots if len(m) > 2 or m.isdigit())


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Part de mots communs : taille de l'intersection divisée par celle de l'union."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------------------
# Les règles : chaque fonction répond True quand l'article doit être écarté.
# --------------------------------------------------------------------------------------


def titre_vide(a: dict) -> bool:
    return not (a.get("titre") or "").strip()


def encodage_casse(a: dict) -> bool:
    texte = f"{a.get('titre') or ''} {a.get('extrait') or ''}"
    return any(marqueur in texte for marqueur in MARQUEURS_ENCODAGE_CASSE)


def date_absente(a: dict) -> bool:
    return a.get("publie_le") is None


def date_future(a: dict) -> bool:
    publie, recupere = a.get("publie_le"), a.get("recupere_le")
    return publie is not None and recupere is not None and publie - recupere > TOLERANCE_FUTUR


def trop_ancien(a: dict) -> bool:
    publie, recupere = a.get("publie_le"), a.get("recupere_le")
    return publie is not None and recupere is not None and recupere - publie > FRAICHEUR_MAX


def _titre_ou_rubrique(motif: re.Pattern) -> Callable[[dict], bool]:
    def test(a: dict) -> bool:
        return bool(
            motif.search(simplifier(a.get("titre"))) or motif.search(simplifier(a.get("rubrique")))
        )

    return test


def autopromo(a: dict) -> bool:
    """Le journal se vend lui-même.

    Trois formes seulement, pour ne pas écarter un article qui cite simplement le journal :
    « <Journal> lance/propose… » en début de titre, « Découvrez … avec <Journal> »,
    « Rejoignez / Abonnez-vous à <Journal> ».
    """
    nom = re.escape(simplifier(a.get("source")))
    if not nom:
        return False
    motif = (
        rf"^{nom}\s+(?:lance|propose|vous propose|recrute|organise)\b"
        rf"|\b(?:decouvrez|partez|voyagez)\b.*\bavec {nom}\b"
        rf"|\b(?:rejoignez|abonnez-vous (?:a|au))\s+(?:le journal\s+)?{nom}\b"
    )
    return bool(re.search(motif, simplifier(a.get("titre"))))


def jeux(a: dict) -> bool:
    return bool(MOTIF_JEUX.search(simplifier(a.get("titre")))) or (
        simplifier(a.get("rubrique")) in RUBRIQUES_JEUX
    )


def rubrique_exclue(a: dict) -> bool:
    return simplifier(a.get("rubrique")) in RUBRIQUES_EXCLUES


def replay(a: dict) -> bool:
    return bool(MOTIF_REPLAY.search(simplifier(a.get("titre"))))


def avis_deces(a: dict) -> bool:
    return bool(MOTIF_AVIS_DECES.search(simplifier(a.get("titre"))))


@dataclass(frozen=True)
class Regle:
    id: str
    ecarte: str  # une phrase : ce que la règle écarte (reprise dans le rapport)
    test: Callable[[dict], bool]


REGLES = (
    Regle("R01_titre_vide", "Titre vide", titre_vide),
    Regle("R02_encodage_casse", "Texte encore cassé après normalisation (Ã©)", encodage_casse),
    Regle("R03_date_absente", "Date de publication absente ou illisible", date_absente),
    Regle("R04_date_future", "Date de publication postérieure à la collecte", date_future),
    Regle("R05_publi", "Contenu partenaire, publi-reportage", _titre_ou_rubrique(MOTIF_PUBLI)),
    Regle("R06_autopromo", "Le journal fait sa propre promotion", autopromo),
    Regle("R07_horoscope", "Horoscope, astrologie", _titre_ou_rubrique(MOTIF_HOROSCOPE)),
    Regle("R08_programme_tv", "Programme télévisé", _titre_ou_rubrique(MOTIF_PROGRAMME_TV)),
    Regle("R09_jeux", "Jeux, quiz, mots croisés, concours", jeux),
    Regle("R10_rubrique_exclue", "Rubrique « magazine » (lifestyle, automobile)", rubrique_exclue),
    Regle("R11_replay", "Rediffusion d'un direct", replay),
    Regle("R12_avis_deces", "Avis de décès, faire-part", avis_deces),
    # Évaluée en dernier : c'est une règle mécanique. Placée après les règles de contenu,
    # elle ne masque pas leurs rejets dans le rapport (un article ancien ET publicitaire
    # est compté comme publicitaire).
    Regle("R13_trop_ancien", "Article publié plus de 24 h avant sa collecte", trop_ancien),
)

R14_DOUBLON_EXACT = "R14_doublon_exact"
R15_DOUBLON_APPROX = "R15_doublon_approx"

# Pour le rapport : identifiant -> ce que la règle écarte.
DESCRIPTIONS = {r.id: r.ecarte for r in REGLES} | {
    R14_DOUBLON_EXACT: "Même titre qu'un article déjà gardé de la même source",
    R15_DOUBLON_APPROX: "Titre presque identique à un article déjà gardé de la même source",
}


def appliquer_regles(article: dict) -> str | None:
    """Identifiant de la première règle qui écarte l'article, ou None s'il est gardé."""
    for regle in REGLES:
        if regle.test(article):
            return regle.id
    return None


# --------------------------------------------------------------------------------------
# Doublons : on ne compare qu'au sein d'une même source. Deux journaux qui parlent du même
# sujet, c'est précisément ce que la gazette veut montrer (regroupement au TD 5).
# --------------------------------------------------------------------------------------


def _doublon_de(article: dict, references: list[tuple[str, str, frozenset[str]]]) -> str | None:
    source = article["source"]
    titre = simplifier(article["titre"])
    mots = mots_du_titre(article["titre"])
    if len(mots) < MIN_MOTS_DOUBLON:
        return None
    memes_sources = [(t, m) for s, t, m in references if s == source]
    if any(t == titre for t, _ in memes_sources):
        return R14_DOUBLON_EXACT
    if any(
        len(m) >= MIN_MOTS_DOUBLON and jaccard(mots, m) >= SEUIL_DOUBLON_APPROX
        for _, m in memes_sources
    ):
        return R15_DOUBLON_APPROX
    return None


def filtrer(
    articles: list[dict], deja_gardes: Sequence[dict] = ()
) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Sépare les articles en (gardés, rejetés).

    `deja_gardes` : articles déjà gardés lors de passages précédents, auxquels on compare
    pour repérer les doublons (ils ne sont ni rendus ni modifiés).
    Les gardés sont rendus du plus ancien au plus récent ; à doublon, on garde le premier
    publié. Les rejetés sont des couples (article, identifiant de règle).
    """
    rejets: list[tuple[dict, str]] = []
    candidats = []
    for article in articles:
        regle = appliquer_regles(article)
        if regle:
            rejets.append((article, regle))
        else:
            candidats.append(article)

    candidats.sort(key=lambda a: (a["publie_le"], a["id"]))
    references = [
        (a["source"], simplifier(a["titre"]), mots_du_titre(a["titre"])) for a in deja_gardes
    ]
    gardes = []
    for article in candidats:
        regle = _doublon_de(article, references)
        if regle:
            rejets.append((article, regle))
            continue
        gardes.append(article)
        references.append(
            (article["source"], simplifier(article["titre"]), mots_du_titre(article["titre"]))
        )
    return gardes, rejets
