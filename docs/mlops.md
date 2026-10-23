# Documentation MLOps — Regroupement par thèmes (TD 5)

## 1. Architecture et chaîne de traitement

Le regroupement par thèmes s'exécute automatiquement après le nettoyage dans le DAG Airflow `collecte_flux` toutes les 30 minutes :
1. **Sélection :** Récupération des articles de `articles_propres` publiés au cours des dernières 24 heures.
2. **Vectorisation :** Concaténation `titre + extrait` vectorisée par le modèle d'embedding avec cache en base PostgreSQL (`embeddings`).
3. **Clustering :** Regroupement non supervisé par densité (HDBSCAN).
4. **Nommage :** Extraction des n-grams discriminants par cluster via c-TF-IDF (Scikit-Learn).
5. **Traçabilité :** Stockage du run dans `runs`, des groupes dans `themes` et des liens dans `articles_themes`.

---

## 2. Choix d'algorithmes et justifications

| Composant | Solution retenue | Justification | Alternatives écartées |
|---|---|---|---|
| **Embeddings** | `paraphrase-multilingual-MiniLM-L12-v2` | Léger (120 Mo, 384 dimensions), rapide sur CPU, multilingue avec d'excellentes performances en français. | Modèles OpenAI (payants, réseau requis), RoBERTa-large (trop lourd pour exécution locale CPU). |
| **Clustering** | **HDBSCAN** | Détermine automatiquement le nombre de thèmes, gère explicitement le bruit (articles isolés sans label forcé). | **K-Means :** Impose un $k$ fixe inadapté à l'actualité fluctuante.<br>**BERTopic :** Trop complexe, dépendance externe lourde. |
| **Nommage** | **c-TF-IDF** (Scikit-Learn) | Déterministe, instantané sur CPU, isole les termes distinctifs du cluster par rapport à l'ensemble du corpus. | LLM / API générative (coûteux, non reproductible, latence réseau). |
| **Suivi (Tracking)** | **Table SQL `runs`** | Déjà intégré dans PostgreSQL 16, zéro service tiers à monitorer, intégrité référentielle native. | MLflow (infrastructure et maintenance additionnelles injustifiées pour le scope). |

---

## 3. Paramètres (`config/clustering.yaml`)

- `fenetre_heures` : `24`
- `embeddings.modele` : `paraphrase-multilingual-MiniLM-L12-v2`
- `clustering.min_cluster_size` : `2` (rapproche au minimum 2 journaux sur le même sujet)
- `clustering.min_samples` : `1`
- `clustering.metric` : `cosine`
- `clustering.cluster_selection_epsilon` : `0.15`
- `mots_cles.nombre_max` : `5`

---

## 4. Consultation des runs et des thèmes

Les runs et métriques se consultent directement en SQL :

```sql
-- Consulter les derniers runs
SELECT id, cree_le, nombre_articles, metriques->>'nombre_themes' AS themes, metriques->>'silhouette' AS silhouette
FROM runs
ORDER BY cree_le DESC
LIMIT 5;

-- Consulter les thèmes et articles associés au dernier run
SELECT t.nom, t.mots_cles, t.taille, a.source, a.titre
FROM themes t
JOIN articles_themes at ON at.theme_id = t.id
JOIN articles_propres a ON a.id = at.article_id
WHERE t.run_id = (SELECT id FROM runs ORDER BY cree_le DESC LIMIT 1)
ORDER BY t.taille DESC;