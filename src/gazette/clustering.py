"""Module de regroupement (HDBSCAN) et d'extraction de labels discriminants."""

import hashlib
import json
from typing import Any

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score


def extraire_hash_entree(articles_ids: list[int]) -> str:
    """Calcule le hash SHA-256 de la liste ordonnée des identifiants d'articles."""
    payload = ",".join(str(i) for i in sorted(articles_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def executer_hdbscan(
    vecteurs: list[list[float]],
    min_cluster_size: int = 2,
    min_samples: int = 1,
    metric: str = "cosine",
    cluster_selection_epsilon: float = 0.15,
) -> tuple[np.ndarray, dict[str, float]]:
    """Applique HDBSCAN et calcule les métriques (silhouette, bruit)."""
    if len(vecteurs) < 2:
        return np.array([-1] * len(vecteurs)), {
            "silhouette": 0.0,
            "part_bruit": 1.0,
            "nombre_themes": 0,
            "taille_mediane": 0.0,
        }

    matrice = np.array(vecteurs)
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
        cluster_selection_epsilon=cluster_selection_epsilon,
        copy=True,
    )
    labels = clusterer.fit_predict(matrice)

    clusters_valides = [lbl for lbl in labels if lbl != -1]
    nb_clusters = len(set(clusters_valides))
    part_bruit = float(np.mean(labels == -1))

    score_silhouette = 0.0
    if nb_clusters > 1 and len(clusters_valides) >= nb_clusters + 1:
        masque = labels != -1
        try:
            score_silhouette = float(
                silhouette_score(matrice[masque], labels[masque], metric=metric)
            )
        except Exception:
            score_silhouette = 0.0

    tailles = [int(np.sum(labels == c)) for c in set(clusters_valides)]
    taille_mediane = float(np.median(tailles)) if tailles else 0.0

    metriques = {
        "silhouette": round(score_silhouette, 4),
        "part_bruit": round(part_bruit, 4),
        "nombre_themes": nb_clusters,
        "taille_mediane": taille_mediane,
    }
    return labels, metriques


def nommer_clusters_tfidf(
    textes_par_cluster: dict[int, list[str]],
    nombre_mots: int = 5,
    stop_words: str = "french",
) -> dict[int, tuple[str, list[str]]]:
    """Extrait les mots-clés discriminants de chaque groupe via c-TF-IDF simplifié."""
    noms_themes: dict[int, tuple[str, list[str]]] = {}
    if not textes_par_cluster:
        return noms_themes

    ids_clusters = list(textes_par_cluster.keys())
    documents = [" ".join(textes_par_cluster[cid]) for cid in ids_clusters]

    vectoriseur = TfidfVectorizer(
        stop_words=stop_words,
        max_df=0.85,
        min_df=1,
        ngram_range=(1, 2),
    )

    try:
        matrice_tfidf = vectoriseur.fit_transform(documents)
        vocabulaire = np.array(vectoriseur.get_feature_names_out())

        for idx, cid in enumerate(ids_clusters):
            scores = matrice_tfidf[idx].toarray().ravel()
            indices_top = scores.argsort()[::-1][:nombre_mots]
            mots_cles = vocabulaire[indices_top].tolist()
            titre_theme = " / ".join(mots_cles[:2]).capitalize() if mots_cles else f"Thème {cid}"
            noms_themes[cid] = (titre_theme, mots_cles)
    except ValueError:
        for cid in ids_clusters:
            noms_themes[cid] = (f"Thème {cid}", ["actualité"])

    return noms_themes