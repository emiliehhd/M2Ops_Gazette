"""Collecte : lire les flux de sources.csv et écrire les items bruts, sans doublon."""
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

SOURCES_CSV = Path("sources.csv")
DOSSIER_BRUTS = Path(os.environ.get("GAZETTE_BRUTS", "data/articles_bruts"))
SOURCE_PAR_DEFAUT = "Le Monde"
USER_AGENT = "la-gazette/0.1 (projet pedagogique EFREI)"
URL_RE = re.compile(r"https?://\S+")

# Champs du flux qu'on garde tels que reçus dans `payload`.
# Volontairement PAS : content (texte intégral), media_* (images), commentaires.
# (le nom d'un journaliste est une donnée personnelle dont rien ne se sert : on ne la collecte pas).
CHAMPS_PAYLOAD = ("id", "title", "link", "summary", "published", "updated")

def lire_sources(chemin: Path = SOURCES_CSV) -> list[dict]:
    """Lit sources.csv et renvoie [{nom, type, url}, ...]."""
    sources = []
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        for ligne in csv.DictReader(f):
            trouve = URL_RE.search(ligne["acces"])
            if trouve is None:
                raise ValueError(f"Aucune adresse dans la colonne acces pour {ligne['nom']!r}")
            sources.append({"nom": ligne["nom"], "type": ligne["type"], "url": trouve.group(0)})
    return sources


def trouver_source(nom: str, chemin: Path = SOURCES_CSV) -> dict:
    for source in lire_sources(chemin):
        if source["nom"] == nom:
            return source
    raise KeyError(f"Source inconnue dans {chemin} : {nom!r}")


def fetch(url: str) -> bytes:
    """Télécharge le flux (réseau)."""
    reponse = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    reponse.raise_for_status()
    return reponse.content


def _date_utc(entree) -> str | None:
    t = entree.get("published_parsed") or entree.get("updated_parsed")
    if t is None:
        return None
    return datetime.fromtimestamp(timegm(t), tz=timezone.utc).isoformat()


def _rubrique(entree) -> str | None:
    tags = entree.get("tags") or []
    return tags[0].get("term") if tags else None


def identifiant(source: str, lien: str) -> str:
    """Identifiant stable, calculé à partir de la clé naturelle (source, lien)."""
    return hashlib.sha256(f"{source}\n{lien}".encode()).hexdigest()[:20]


def parse(xml: bytes, source: str, recupere_le: datetime | None = None) -> list[dict]:
    """Transforme le XML en items bruts : seulement les champs autorisés."""
    recupere_le = recupere_le or datetime.now(timezone.utc)
    flux = feedparser.parse(xml)
    items = []
    for e in flux.entries:
        lien = e.get("link")
        if not lien:
            continue  # sans lien, pas de clé (source, lien) : on ne peut pas dédoublonner
        items.append(
            {
                "id": identifiant(source, lien),
                "source": source,
                "lien": lien,
                "titre": e.get("title", "").strip(),
                "resume": e.get("summary", "").strip(),
                "publie_le": _date_utc(e),
                "recupere_le": recupere_le.isoformat(),
                "rubrique": _rubrique(e),
                "payload": {k: e[k] for k in CHAMPS_PAYLOAD if k in e},
            }
        )
    return items


def _slug(nom: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sans_accents.lower()).strip("_")


def ecrire_bruts(items: list[dict], dossier: Path = DOSSIER_BRUTS) -> tuple[int, int]:
    """Écrit un fichier JSON par item. Un item déjà écrit n'est jamais réécrit.

    Renvoie (ecrits, ignores).
    """
    ecrits = ignores = 0
    for item in items:
        chemin = dossier / _slug(item["source"]) / f"{item['id']}.json"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            # "x" = création exclusive : échoue si le fichier existe déjà.
            with chemin.open("x", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            ecrits += 1
        except FileExistsError:
            ignores += 1
    return ecrits, ignores


def main() -> None:
    nom = sys.argv[1] if len(sys.argv) > 1 else SOURCE_PAR_DEFAUT
    source = trouver_source(nom)
    items = parse(fetch(source["url"]), source["nom"])
    ecrits, ignores = ecrire_bruts(items)
    print(f"{source['nom']} : {len(items)} reçus, {ecrits} écrits, {ignores} déjà présents")


if __name__ == "__main__":
    main()
