"""Conformité : retirer du brut les données personnelles qu'on ne collecte plus.

Le brut est écrit une seule fois et ne change jamais, sauf ici : c'est une exception voulue,
au nom de la minimisation des données. Le nom de l'auteur d'un article (donnée personnelle) était
gardé dans `payload.author` avant le 23/10/2026 ; plus rien ne s'en sert, il est retiré.

Commande : `python -m gazette.conformite purger-auteurs` (idempotente : on peut la relancer).
"""

import json
import sys
from pathlib import Path

from gazette.collecte import DOSSIER_BRUTS
from gazette.collecteur import journal


def purger_auteurs(dossier: Path = DOSSIER_BRUTS) -> dict:
    """Retire `payload.author` de chaque fichier du brut. Renvoie les compteurs."""
    fichiers = purges = illisibles = 0
    for chemin in sorted(dossier.glob("*/*.json")):
        fichiers += 1
        try:
            article = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            illisibles += 1
            continue
        payload = article.get("payload") if isinstance(article, dict) else None
        if not isinstance(payload, dict) or "author" not in payload:
            continue
        del payload["author"]
        temporaire = chemin.with_name(chemin.name + ".tmp")
        temporaire.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
        temporaire.replace(chemin)  # remplacement d'un bloc : jamais de fichier à moitié écrit
        purges += 1
    compteurs = {"fichiers": fichiers, "purges": purges, "illisibles": illisibles}
    journal("brut_auteurs_purges", **compteurs)
    return compteurs


def main() -> None:
    commande = sys.argv[1] if len(sys.argv) > 1 else ""
    if commande != "purger-auteurs":
        sys.exit("Commande inconnue : attendu « purger-auteurs »")
    compteurs = purger_auteurs()
    print(f"{compteurs['purges']} fichier(s) nettoyé(s) sur {compteurs['fichiers']}.")


if __name__ == "__main__":
    main()
