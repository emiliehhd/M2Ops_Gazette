-- 002 : articles propres (gardés) et rejets (écartés), alimentés après chaque passe.
--
-- `id` est celui de l'article brut (data/articles_bruts/<source>/<id>.json) : c'est le lien
-- de traçabilité. Un article du brut traité figure dans exactement une des deux tables ;
-- ceux dont l'id n'est dans aucune des deux restent à traiter.
-- Ni `payload` ni l'auteur ne sont copiés : on ne garde que ce qu'on a le droit de republier.
-- Pas de clé étrangère vers `sources` : le brut d'une source retirée de sources.csv reste valable.

CREATE TABLE articles_propres (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    lien          TEXT NOT NULL,
    titre         TEXT NOT NULL,
    extrait       TEXT NOT NULL,
    publie_le     TIMESTAMPTZ NOT NULL,
    recupere_le   TIMESTAMPTZ NOT NULL,
    rubrique      TEXT,
    traite_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, lien)
);
CREATE INDEX articles_propres_publie_le ON articles_propres (publie_le);
CREATE INDEX articles_propres_traite_le ON articles_propres (traite_le);

CREATE TABLE rejets (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    lien          TEXT NOT NULL,
    titre         TEXT NOT NULL,
    regle         TEXT NOT NULL,
    publie_le     TIMESTAMPTZ,
    recupere_le   TIMESTAMPTZ,
    traite_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX rejets_regle ON rejets (regle);
CREATE INDEX rejets_traite_le ON rejets (traite_le);
