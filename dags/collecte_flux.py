"""DAG Airflow : collecte, nettoyage du brut, puis contrôles de qualité, toutes les 30 min."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
        from datetime import datetime, timezone

        from gazette.collecte import lire_sources
        from gazette.collecteur import collecter_tout
        from gazette.db import connexion, migrer, synchroniser_sources
        from gazette.metriques import enregistrer_metriques, metriques_collecte

        with connexion() as conn:
            migrer(conn, RACINE / "migrations")
            synchroniser_sources(conn, lire_sources(RACINE / "sources.csv"))
            compteurs = collecter_tout(conn, RACINE / "data" / "articles_bruts")
            # Les chiffres de la passe sont gardés avant l'éventuelle erreur ci-dessous.
            enregistrer_metriques(conn, datetime.now(timezone.utc), metriques_collecte(compteurs))
        if compteurs["sources"] and compteurs["erreurs"] == compteurs["sources"]:
            raise RuntimeError(f"Toutes les sources ont échoué : {compteurs}")
        return compteurs  # visible dans l'onglet XCom de la tâche

    @task
    def nettoyer() -> dict:
        """Du brut aux articles propres et aux rejets, puis le rapport de qualité du jour."""
        from datetime import datetime, timezone

        from gazette.db import connexion, migrer
        from gazette.metriques import enregistrer_metriques, metriques_nettoyage
        from gazette.nettoyage import traiter_passe

        with connexion() as conn:
            migrer(conn, RACINE / "migrations")
            compteurs = traiter_passe(conn, RACINE / "data" / "articles_bruts", RACINE / "rapports")
            enregistrer_metriques(conn, datetime.now(timezone.utc), metriques_nettoyage(compteurs))
        return compteurs  # visibles dans l'onglet XCom

    # Tourne même si la collecte ou le nettoyage ont échoué : c'est précisément là qu'il faut alerter.
    @task(trigger_rule="all_done")
    def controler() -> dict:
        """Vérifie des faits sur les vraies données, publie les métriques, alerte sur Discord."""
        from gazette.controles import controler_passe
        from gazette.db import connexion, migrer

        with connexion() as conn:
            migrer(conn, RACINE / "migrations")
            return controler_passe(conn)  # résumé visible dans l'onglet XCom

    collecter() >> nettoyer() >> controler()


collecte_flux()
