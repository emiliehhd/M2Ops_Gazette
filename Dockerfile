# --- Étape 1 : construire le paquet ---
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .

# --- Étape 2 : image de test (dépendances de dev, tests, sources.csv) ---
FROM builder AS test
RUN pip install --no-cache-dir ".[dev]"
COPY tests/ tests/
COPY sources.csv ./
CMD ["pytest"]

# --- Étape finale : image d'exécution, petite et non root ---
FROM python:3.12-slim AS final
RUN useradd --create-home --uid 1000 gazette \
 && mkdir /home/gazette/data \
 && chown gazette:gazette /home/gazette/data
COPY --from=builder /install /usr/local
USER gazette
WORKDIR /home/gazette
COPY sources.csv ./
CMD ["python", "-m", "gazette.collecte"]