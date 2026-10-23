"""Tests pour les modules d'embeddings, de clustering et de persistance MLOps."""

from datetime import datetime, timezone

import numpy as np
from gazette.clustering import (
    executer_hdbscan,
    extraire_hash_entree,
    nommer_clusters_tfidf,
)
from gazette.embeddings import obtenir_vecteurs_articles, preparer_texte_article


class ModeleFictif:
    """Modèle léger simulé pour les tests unitaires sans téléchargement lourd."""

    def encode(self, textes, convert_to_numpy=True, show_progress_bar=False):
        vecteurs = []
        for t in textes:
            valeur = float(len(t) % 10)
            vecteurs.append([valeur, 1.0 - (valeur / 10.0)])
        return np.array(vecteurs)


def test_preparer_texte_article():
    assert preparer_texte_article("Titre", "Extrait court") == "Titre : Extrait court"
    assert preparer_texte_article("Titre", None) == "Titre"
    assert preparer_texte_article(" Titre ", " ") == "Titre"


def test_extraire_hash_entree():
    hash1 = extraire_hash_entree([1, 2, 3])
    hash2 = extraire_hash_entree([3, 2, 1])
    hash3 = extraire_hash_entree([1, 2, 4])
    assert hash1 == hash2
    assert hash1 != hash3


def test_embeddings_cache_dix_articles(db_conn):
    """Vérifie la vectorisation de 10 articles et le mécanisme d'évitement de recalcul."""
    with db_conn.cursor() as cur:
        # Création d'une source fictive
        cur.execute(
            "INSERT INTO sources (code, nom, url) VALUES ('test_src', 'Test', 'https://test.fr') ON CONFLICT DO NOTHING;"
        )
        cur.execute("DELETE FROM articles_propres WHERE source = 'test_src';")

        articles_ids = []
        for i in range(10):
            cur.execute(
                """
                INSERT INTO articles_propres (source, lien, titre, extrait, publie_le, recupere_le, rubrique, traite_le)
                VALUES ('test_src', %s, %s, %s, %s, %s, 'actu', %s)
                RETURNING id;
                """,
                (
                    f"https://test.fr/art_{i}",
                    f"Titre article {i}",
                    f"Extrait de test pour l'article numéro {i}",
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                ),
            )
            articles_ids.append(cur.fetchone()[0])
        db_conn.commit()

    articles = [
        {"id": aid, "titre": f"Titre article {i}", "extrait": f"Extrait {i}"}
        for i, aid in enumerate(articles_ids)
    ]

    nom_modele = "modele-test"
    modele_simule = ModeleFictif()

    # Premier calcul : insertion en base
    ids, vecteurs = obtenir_vecteurs_articles(
        db_conn, articles, nom_modele, modele=modele_simule
    )
    assert len(ids) == 10
    assert len(vecteurs) == 10

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM embeddings WHERE modele = %s;", (nom_modele,))
        assert cur.fetchone()[0] == 10

    # Deuxième appel : récupération du cache sans passer par encode()
    ids2, vecteurs2 = obtenir_vecteurs_articles(
        db_conn, articles, nom_modele, modele=None
    )
    assert ids == ids2
    assert vecteurs == vecteurs2


def test_hdbscan_clustering():
    vecteurs = [
        [1.0, 0.0],
        [1.0, 0.05],
        [0.98, 0.02],
        [0.0, 1.0],
        [0.02, 0.99],
        [0.5, 0.5],  # Point isolé (bruit potentiel)
    ]
    labels, metriques = executer_hdbscan(
        vecteurs,
        min_cluster_size=2,
        min_samples=1,
        cluster_selection_epsilon=0.1,
    )
    assert len(labels) == len(vecteurs)
    assert "silhouette" in metriques
    assert "part_bruit" in metriques
    assert metriques["nombre_themes"] >= 1


def test_nommer_clusters_tfidf():
    groupes = {
        0: [
            "Grève à la SNCF perturbations sur les trains",
            "Trafic SNCF très perturbé ce matin",
            "Les syndicats reconduisent la grève SNCF",
        ],
        1: [
            "Victoire du PSG en Ligue des champions",
            "Le match de football PSG se termine sur une victoire",
        ],
    }
    noms = nommer_clusters_tfidf(groupes, nombre_mots=3)
    assert 0 in noms
    assert 1 in noms
    assert len(noms[0][1]) > 0
    assert any("sncf" in mot.lower() or "grève" in mot.lower() for mot in noms[0][1])