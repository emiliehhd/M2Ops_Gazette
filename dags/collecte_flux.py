"""DAG Airflow : une passe de collecte, puis le nettoyage du brut, toutes les 30 minutes."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from gazette.collecte import collecter_tout
from gazette.db import ouvrir_connexion
from gazette.nettoyage import traiter_passe
from gazette.themes import executer_pipeline_themes

from airflow.sdk import dag, task

RACINE = Path("/opt/gazette")  # sources.csv, migrations/, data/ et rapports/ sont montés ici


@dag(
    dag_id="collecte_flux",
    schedule="*/30 * * * *",  # à :00 et :30, heure de Paris
    start_date=datetime(2026, 10, 22, tzinfo=ZoneInfo("Europe/Paris")),
    catchup=False,  # au redémarrage, on ne rattrape pas les passes manquées
    max_active_runs=1,  # jamais deux passes en même temps sur les mêmes éditeurs
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["gazette", "td3", "td4"],
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

    @task
    def nettoyer() -> dict:
        """Du brut aux articles propres et aux rejets, puis le rapport de qualité du jour."""
        from gazette.db import connexion, migrer
        from gazette.nettoyage import traiter_passe

        with connexion() as conn:
            migrer(conn, RACINE / "migrations")
            return traiter_passe(
                conn, RACINE / "data" / "articles_bruts", RACINE / "rapports"
            )  # compteurs visibles dans l'onglet XCom

    collecter() >> nettoyer()
    
    """DAG Airflow pour la collecte, le nettoyage et le regroupement par thèmes."""



DEFAULT_ARGS = {
    "owner": "gazette",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


@dag(
    dag_id="collecte_flux",
    default_args=DEFAULT_ARGS,
    schedule="*/30 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["presse", "mlops"],
)
def pipeline_presse():
    @task
    def collecter():
        collecter_tout()

    @task
    def nettoyer():
        with ouvrir_connexion() as conn:
            traiter_passe(conn, "data/articles_bruts", "rapports")

    @task
    def regrouper():
        with ouvrir_connexion() as conn:
            run_id = executer_pipeline_themes(conn, "config/clustering.yaml")
            print(f"Run thèmes achevé avec succès : {run_id}")

    collecter() >> nettoyer() >> regrouper()


pipeline_presse()


collecte_flux()
