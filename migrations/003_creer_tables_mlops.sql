-- Migration 003 : Tables MLOps pour le clustering des thèmes et le traçage des runs

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles_propres(id) ON DELETE CASCADE,
    modele VARCHAR(100) NOT NULL,
    vecteur JSONB NOT NULL,
    cree_le TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_article_modele UNIQUE (article_id, modele)
);

CREATE TABLE IF NOT EXISTS runs (
    id VARCHAR(64) PRIMARY KEY,
    date_debut TIMESTAMP WITH TIME ZONE NOT NULL,
    date_fin TIMESTAMP WITH TIME ZONE NOT NULL,
    hash_entree VARCHAR(64) NOT NULL,
    nombre_articles INTEGER NOT NULL,
    modele_embedding VARCHAR(100) NOT NULL,
    parametres JSONB NOT NULL,
    metriques JSONB NOT NULL,
    cree_le TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS themes (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    nom VARCHAR(255) NOT NULL,
    mots_cles TEXT[] NOT NULL,
    taille INTEGER NOT NULL,
    cree_le TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles_themes (
    theme_id INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles_propres(id) ON DELETE CASCADE,
    PRIMARY KEY (theme_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_article ON embeddings(article_id);
CREATE INDEX IF NOT EXISTS idx_themes_run ON themes(run_id);