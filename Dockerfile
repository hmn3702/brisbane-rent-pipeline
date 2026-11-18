# Python + dbt runtime for the pipeline. The repo is bind-mounted at /app by
# docker-compose.yml, so code changes and outputs (powerbi/data) stay on the host.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Baked-in copy so the image also runs without the bind mount (e.g. `docker run`).
COPY . .

CMD ["bash", "scripts/pipeline.sh", "demo"]
