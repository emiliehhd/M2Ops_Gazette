"""Module de calcul et de cache des embeddings pour les articles."""

import json
from typing import Any

from sentence_transformers import SentenceTransformer


def charger_modele_embedding(nom_modele: str) -> SentenceTransformer:
    """Charge le modèle SentenceTransformer sur CPU."""
    return SentenceTransformer(nom_modele, device="cpu")


def preparer_texte_article(titre: str, extrait: str | None) -> str:
    """Combine titre et extrait pour la vectorisation."""
    if not extrait:
        return titre.strip()
    return f"{titre.strip()} : {extrait.strip()}"


def recuperer_embeddings_en_cache(
    conn: Any, article_ids: list[int], nom_modele: str
) -> dict[int, list[float]]:
    """Récupère les vecteurs déjà calculés en base pour éviter les recalculs."""
    if not article_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT article_id, vecteur
            FROM embeddings
            WHERE modele = %s AND article_id = ANY(%s);
            """,
            (nom_modele, article_ids),
        )
        lignes = cur.fetchall()
    return {ligne[0]: ligne[1] if isinstance(ligne[1], list) else json.loads(ligne[1]) for ligne in lignes}


def sauvegarder_embeddings(
    conn: Any, donnees: list[tuple[int, str, list[float]]]
) -> None:
    """Insère les nouveaux embeddings dans la table de cache."""
    if not donnees:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO embeddings (article_id, modele, vecteur)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (article_id, modele) DO NOTHING;
            """,
            [(art_id, mod, json.dumps(vect)) for art_id, mod, vect in donnees],
        )
    conn.commit()


def obtenir_vecteurs_articles(
    conn: Any,
    articles: list[dict[str, Any]],
    nom_modele: str,
    modele: SentenceTransformer | None = None,
) -> tuple[list[int], list[list[float]]]:
    """Retourne la liste ordonnée des IDs et de leurs vecteurs en utilisant le cache SQL."""
    if not articles:
        return [], []

    ids = [a["id"] for a in articles]
    cache = recuperer_embeddings_en_cache(conn, ids, nom_modele)

    articles_a_calculer = [a for a in articles if a["id"] not in cache]

    if articles_a_calculer:
        instance_modele = modele or charger_modele_embedding(nom_modele)
        textes = [
            preparer_texte_article(a["titre"], a.get("extrait"))
            for a in articles_a_calculer
        ]
        vecteurs_calcules = instance_modele.encode(
            textes, convert_to_numpy=True, show_progress_bar=False
        )

        nouveaux = []
        for a, vec in zip(articles_a_calculer, vecteurs_calcules, strict=True):
            vec_list = vec.tolist()
            cache[a["id"]] = vec_list
            nouveaux.append((a["id"], nom_modele, vec_list))

        sauvegarder_embeddings(conn, nouveaux)

    return ids, [cache[art_id] for art_id in ids]