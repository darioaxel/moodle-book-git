# Servicio courseascode (engine) — imagen de producción (ENG-105).

FROM python:3.12-slim

# git: LocalGitProvider usa el CLI (`git worktree add`, ENG-021); GitPython
# también necesita el binario.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Defaults de desarrollo; sobrescribir en despliegue real.
    HOST=0.0.0.0 \
    PORT=8000 \
    COURSEASCODE_DB=/data/courseascode.db \
    COURSEASCODE_LOG_FORMAT=json

WORKDIR /srv/courseascode

# Dependencias primero para aprovechar la caché de capas.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# BD SQLite persistente y usuario no-root.
RUN useradd --create-home courseascode \
    && mkdir -p /data \
    && chown -R courseascode:courseascode /data /srv/courseascode
USER courseascode

# El repo de contenidos se monta en /content con otro propietario (host):
# sin esta excepción git rechaza operar sobre él ("dubious ownership").
RUN git config --global --add safe.directory /content
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/')" || exit 1

# El repo de contenidos se monta en /content (ver docker-compose.yml).
CMD ["python", "-m", "courseascode.serve"]
