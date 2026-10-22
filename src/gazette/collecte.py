"""Première source : lire son adresse dans sources.csv, parser le flux, écrire du JSON."""
import csv
import json
import re
import sys
import unicodedata
from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

SOURCES_CSV = Path("sources.csv")
SOURCE_PAR_DEFAUT = "Le Monde"
USER_AGENT = "la-gazette/0.1 (projet pedagogique EFREI)"
URL_RE = re.compile(r"https?://\S+")


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


def parse(xml: bytes, source: str, fetched_at: datetime | None = None) -> list[dict]:
    """Transforme le XML en liste d'items : seulement les champs autorisés."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    flux = feedparser.parse(xml)
    return [
        {
            "source": source,
            "guid": e.get("id") or e.get("link"),
            "title": e.get("title", "").strip(),
            "summary": e.get("summary", "").strip(),
            "link": e.get("link"),
            "published_at": _date_utc(e),
            "fetched_at": fetched_at.isoformat(),
        }
        for e in flux.entries
    ]


def _slug(nom: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sans_accents.lower()).strip("_")


def chemin_sortie(nom: str) -> Path:
    return Path("data") / f"{_slug(nom)}.json"


def ecrire_json(items: list[dict], chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    nom = sys.argv[1] if len(sys.argv) > 1 else SOURCE_PAR_DEFAUT
    source = trouver_source(nom)
    items = parse(fetch(source["url"]), source["nom"])
    sortie = chemin_sortie(source["nom"])
    ecrire_json(items, sortie)
    print(f"{len(items)} items de {source['nom']} écrits dans {sortie}")


if __name__ == "__main__":
    main()