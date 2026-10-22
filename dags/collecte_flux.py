"""DAG Airflow : une passe de collecte sur toutes les sources actives, toutes les 30 minutes."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import dag, task

RACINE = Path("/opt/gazette")  # sources.csv, migrations/ et data/ sont montés ici (docker-compose.yml)


@dag(
    dag_id="collecte_flux",
    schedule="*/30 * * * *",  # à :00 et :30, heure de Paris
    start_date=datetime(2026, 10, 22, tzinfo=ZoneInfo("Europe/Paris")),
    catchup=False,  # au redémarrage, on ne rattrape pas les passes manquées
    max_active_runs=1,  # jamais deux passes en même temps sur les mêmes éditeurs
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["gazette", "td3"],
)
def collecte_flux():
    @task
    def collecter() -> dict:
        from gazette.collecte import lire_sources
        from gazette.collecteur import collecter_tout
        from gazette.db import connexion, migrer, synchroniser_sources

        with connexion() as conn:
            migrer(conn, RACINE / "migrations")
            synchroniser_sources(conn, lire_sources(RACINE / "sources.csv"))
            compteurs = collecter_tout(conn, RACINE / "data" / "articles_bruts")
        if compteurs["sources"] and compteurs["erreurs"] == compteurs["sources"]:
            raise RuntimeError(f"Toutes les sources ont échoué : {compteurs}")
        return compteurs  # visible dans l'onglet XCom de la tâche

    collecter()


collecte_flux()
