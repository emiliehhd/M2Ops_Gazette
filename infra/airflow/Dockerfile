# Image Airflow + notre paquet gazette (même version de Python que le reste du projet).
FROM apache/airflow:3.2.2-python3.12
COPY --chown=airflow:root pyproject.toml /opt/gazette-src/pyproject.toml
COPY --chown=airflow:root src/ /opt/gazette-src/src/
# On réinstalle la même version d'Airflow dans la commande : pip ne peut pas la changer en douce.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" /opt/gazette-src
