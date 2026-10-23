-- 003 : métriques de chaque passe et état des contrôles de qualité.
--
-- `metriques` : une mesure par ligne (nom, étiquette éventuelle comme une source ou une règle,
-- valeur), horodatée. Elle garde l'historique que XCom et les journaux ne donnent pas.
-- `controles_etat` : où en est chaque contrôle (en échec depuis quand, dernière alerte envoyée),
-- pour n'alerter qu'à l'apparition d'une panne, en rappel après 24 h, et au rétablissement.

CREATE TABLE metriques (
    id          BIGSERIAL PRIMARY KEY,
    mesure_le   TIMESTAMPTZ NOT NULL,
    nom         TEXT NOT NULL,
    etiquette   TEXT NOT NULL DEFAULT '',
    valeur      DOUBLE PRECISION NOT NULL
);
CREATE INDEX metriques_nom_date ON metriques (nom, mesure_le);

CREATE TABLE controles_etat (
    controle         TEXT PRIMARY KEY,
    en_echec         BOOLEAN NOT NULL,
    depuis           TIMESTAMPTZ NOT NULL,
    derniere_alerte  TIMESTAMPTZ,
    detail           TEXT NOT NULL DEFAULT ''
);
