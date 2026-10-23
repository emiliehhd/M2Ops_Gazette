"""Module orchestrant le pipeline de clustering et d'enregistrement en base."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from gazette.clustering import (
    executer_hdbscan,
    extraire_hash_entree,
    nommer_clusters_tfidf,
)
from gazette.embeddings import (
    charger_modele_embedding,
    obtenir_vecteurs_articles,
    preparer_texte_article,
)


def charger_config_clustering(chemin_config: str = "config/clustering.yaml") -> dict[str, Any]:
    """Charge le fichier YAML de configuration."""
    with Path(chemin_config).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def lire_articles_recents(conn: Any, fenetre_heures: int = 24) -> list[dict[str, Any]]:
    """Récupère les articles de la table articles_propres sur la fenêtre définie."""
    limite = datetime.now(timezone.utc) - timedelta(hours=fenetre_heures)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source, titre, extrait, publie_le
            FROM articles_propres
            WHERE publie_le >= %s
            ORDER BY id ASC;
            """,
            (limite,),
        )
        lignes = cur.fetchall()

    return [
        {
            "id": l[0],
            "source": l[1],
            "titre": l[2],
            "extrait": l[3],
            "publie_le": l[4],
        }
        for l in lignes
    ]


def enregistrer_run_et_themes(
    conn: Any,
    run_id: str,
    fenetre_debut: datetime,
    fenetre_fin: datetime,
    hash_entree: str,
    articles: list[dict[str, Any]],
    labels: list[int],
    noms_themes: dict[int, tuple[str, list[str]]],
    modele_nom: str,
    parametres: dict[str, Any],
    metriques: dict[str, Any],
) -> None:
    """Enregistre le run, les thèmes découverts et l'association des articles."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (
                id, date_debut, date_fin, hash_entree, nombre_articles,
                modele_embedding, parametres, metriques
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb);
            """,
            (
                run_id,
                fenetre_debut,
                fenetre_fin,
                hash_entree,
                len(articles),
                modele_nom,
                yaml.dump(parametres),
                yaml.dump(metriques),
            ),
        )

        for cluster_id, (nom, mots_cles) in noms_themes.items():
            articles_du_theme = [
                art["id"]
                for art, lbl in zip(articles, labels, strict=True)
                if lbl == cluster_id
            ]
            taille = len(articles_du_theme)

            cur.execute(
                """
                INSERT INTO themes (run_id, nom, mots_cles, taille)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (run_id, nom, mots_cles, taille),
            )
            theme_bdd_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO articles_themes (theme_id, article_id)
                VALUES (%s, %s);
                """,
                [(theme_bdd_id, aid) for aid in articles_du_theme],
            )

    conn.commit()


def executer_pipeline_themes(conn: Any, chemin_config: str = "config/clustering.yaml") -> str:
    """Fonction principale appelée par la tâche Airflow."""
    config = charger_config_clustering(chemin_config)
    fenetre_heures = config.get("fenetre_heures", 24)
    maintenant = datetime.now(timezone.utc)
    date_debut = maintenant - timedelta(hours=fenetre_heures)

    articles = lire_articles_recents(conn, fenetre_heures=fenetre_heures)
    if not articles:
        return "Aucun article sur la fenêtre."

    hash_entree = extraire_hash_entree([a["id"] for a in articles])
    run_id = f"run_{maintenant.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    nom_modele = config["embeddings"]["modele"]
    modele = charger_modele_embedding(nom_modele)
    ids, vecteurs = obtenir_vecteurs_articles(conn, articles, nom_modele, modele=modele)

    params_cluster = config["clustering"]
    labels, metriques = executer_hdbscan(
        vecteurs,
        min_cluster_size=params_cluster.get("min_cluster_size", 2),
        min_samples=params_cluster.get("min_samples", 1),
        metric=params_cluster.get("metric", "cosine"),
        cluster_selection_epsilon=params_cluster.get("cluster_selection_epsilon", 0.15),
    )

    textes_par_cluster: dict[int, list[str]] = {}
    for art, label in zip(articles, labels, strict=True):
        if label != -1:
            texte = preparer_texte_article(art["titre"], art.get("extrait"))
            textes_par_cluster.setdefault(label, []).append(texte)

    cfg_mots = config.get("mots_cles", {})
    noms_themes = nommer_clusters_tfidf(
        textes_par_cluster,
        nombre_mots=cfg_mots.get("nombre_max", 5),
        stop_words=cfg_mots.get("stop_words", "french"),
    )

    enregistrer_run_et_themes(
        conn=conn,
        run_id=run_id,
        fenetre_debut=date_debut,
        fenetre_fin=maintenant,
        hash_entree=hash_entree,
        articles=articles,
        labels=labels.tolist(),
        noms_themes=noms_themes,
        modele_nom=nom_modele,
        parametres=config,
        metriques=metriques,
    )

    return run_id