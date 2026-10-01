# ADI Anvil API and worker image (same image, different command). Built from the repository root.
# Contains source, migrations and committed synthetic fixtures only; never .env, .local or .secrets.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12-slim-bookworm
ENV ANVIL_ROOT=/app \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/app/services/backend/.venv/bin:$PATH
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY .python-version ./
COPY services/backend/pyproject.toml services/backend/uv.lock services/backend/
RUN uv sync --frozen --no-dev --no-install-project --project services/backend
COPY services/backend/alembic.ini services/backend/
COPY services/backend/alembic services/backend/alembic
COPY services/backend/migrations services/backend/migrations
COPY services/backend/src services/backend/src
COPY fixtures fixtures
COPY task-packs task-packs
COPY assets/brand assets/brand
RUN uv sync --frozen --no-dev --project services/backend \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin anvil \
    && mkdir -p /app/.data/artifacts && chown -R anvil /app/.data && chmod 700 /app/.data
USER anvil
EXPOSE 8200
CMD ["python", "-m", "uvicorn", "anvil.api:app", "--host", "0.0.0.0", "--port", "8200", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
