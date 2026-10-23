"""Normalisation des champs d'un article brut.

Une fonction pure par transformation (pas de réseau, pas de fichier, pas de base) :
chacune est testée seule dans tests/test_normalisation.py. Les deux fonctions du bas
(nettoyer_texte, normaliser_article) ne font que les assembler.

Conformité : normaliser_article ne recopie ni `payload` ni l'auteur. On ne garde que
ce qu'on a le droit de republier : titre, extrait court, lien, date, source.
"""
import html
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Longueur maximale de l'extrait conservé (en caractères, « … » compris).
EXTRAIT_MAX = 300

_SCRIPTS = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENTAIRES = re.compile(r"<!--.*?-->", re.DOTALL)
# Balises « de bloc » : elles séparent des mots, on les remplace par une espace.
_BLOCS = re.compile(r"</?(?:br|p|div|li|ul|ol|h[1-6]|tr|td|table|blockquote)\b[^>]*>", re.IGNORECASE)
# Les autres balises (b, i, a, span…) disparaissent sans laisser d'espace.
# Il faut une lettre juste après « < » : « 5 < 6 » n'est donc pas pris pour une balise.
_BALISES = re.compile(r"</?[a-zA-Z][^>]*>")

_MARQUEURS_MOJIBAKE = ("Ã", "Â", "â€")
_INVISIBLES = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def retirer_html(texte: str) -> str:
    """Retire les balises HTML (et le contenu des <script> et <style>)."""
    texte = _SCRIPTS.sub(" ", texte)
    texte = _COMMENTAIRES.sub("", texte)
    texte = _BLOCS.sub(" ", texte)
    return _BALISES.sub("", texte)


def decoder_entites(texte: str) -> str:
    """Remplace les entités (&amp;, &#39;, &nbsp;…) par les caractères qu'elles désignent."""
    return html.unescape(texte)


def reparer_encodage(texte: str) -> str:
    """Répare un texte UTF-8 qui a été lu comme du Windows-1252 (« Ã© » pour « é »).

    On ne tente la réparation que si un marqueur typique est présent ; si elle échoue,
    le texte est rendu tel quel. Limite : un texte qui mélange des caractères abîmés et des
    caractères corrects n'est pas réparé (la bibliothèque ftfy saurait le faire, à envisager
    si les contrôles de qualité en trouvent dans les vraies données).
    """
    if not any(marqueur in texte for marqueur in _MARQUEURS_MOJIBAKE):
        return texte
    for codec in ("cp1252", "latin-1"):
        try:
            return texte.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texte


def normaliser_unicode(texte: str) -> str:
    """Forme Unicode canonique (NFC) et suppression des caractères invisibles."""
    return unicodedata.normalize("NFC", texte).translate(_INVISIBLES)


def normaliser_espaces(texte: str) -> str:
    """Remplace toute suite d'espaces (insécables, fines, tabulations, retours) par une seule."""
    return re.sub(r"\s+", " ", texte).strip()


def borner_extrait(texte: str, longueur_max: int = EXTRAIT_MAX) -> str:
    """Coupe l'extrait à `longueur_max` caractères au plus, à la fin d'un mot, avec « … »."""
    if len(texte) <= longueur_max:
        return texte
    coupe = texte[: longueur_max - 1]
    if not texte[longueur_max - 1].isspace() and " " in coupe:
        coupe = coupe.rsplit(" ", 1)[0]
    return coupe.rstrip(" ,;:.!?-–—") + "…"


def date_en_utc(valeur, tz_defaut=timezone.utc) -> datetime | None:
    """Convertit une date (texte ISO 8601, texte RFC 822 ou datetime) en datetime UTC.

    Une date sans fuseau est supposée dans `tz_defaut`. Renvoie None si illisible.
    """
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        dt = valeur
    else:
        texte = str(valeur).strip()
        if not texte:
            return None
        try:
            dt = datetime.fromisoformat(texte[:-1] + "+00:00" if texte.endswith("Z") else texte)
        except ValueError:
            try:
                dt = parsedate_to_datetime(texte)
            except (TypeError, ValueError, IndexError):
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz_defaut)
    return dt.astimezone(timezone.utc)


def nettoyer_texte(texte: str | None) -> str:
    """Enchaîne les transformations de texte (titre, extrait, rubrique)."""
    if not texte:
        return ""
    texte = reparer_encodage(texte)
    texte = retirer_html(texte)
    texte = decoder_entites(texte)
    texte = normaliser_unicode(texte)
    return normaliser_espaces(texte)


def normaliser_article(brut: dict) -> dict:
    """Transforme un article brut en article normalisé (avant les règles d'exclusion).

    `id` est celui du brut : c'est le lien de traçabilité. `payload` et l'auteur
    ne sont volontairement pas recopiés.
    """
    return {
        "id": brut["id"],
        "source": brut["source"],
        "lien": (brut.get("lien") or "").strip(),
        "titre": nettoyer_texte(brut.get("titre")),
        "extrait": borner_extrait(nettoyer_texte(brut.get("resume"))),
        "publie_le": date_en_utc(brut.get("publie_le")),
        "recupere_le": date_en_utc(brut.get("recupere_le")),
        "rubrique": nettoyer_texte(brut.get("rubrique")) or None,
    }
