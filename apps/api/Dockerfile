# Build from the repository root:  docker build -f apps/api/Dockerfile .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /srv/apps/api

COPY apps/api/requirements.txt ./
RUN pip install -r requirements.txt

COPY apps/api/alembic.ini apps/api/pyproject.toml ./
COPY apps/api/app ./app
# alembic.ini points at ../../migrations, so keep the same relative layout as the repo.
COPY migrations /srv/migrations

# Never run as root inside the container.
USER app
EXPOSE 8000

# FORWARDED_ALLOW_IPS lists the proxies (the web container) whose X-Forwarded-For is trusted for rate limiting.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
