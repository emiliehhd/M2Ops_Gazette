-- 001 : état de chaque source suivie par la collecte.
CREATE TABLE sources (
    nom                 TEXT PRIMARY KEY,
    type                TEXT NOT NULL CHECK (type IN ('PQN', 'PQR')),
    url_flux            TEXT NOT NULL,
    actif               BOOLEAN NOT NULL DEFAULT TRUE,
    derniere_reussite   TIMESTAMPTZ,
    echecs_consecutifs  INTEGER NOT NULL DEFAULT 0 CHECK (echecs_consecutifs >= 0),
    etag                TEXT,
    last_modified       TEXT
);
