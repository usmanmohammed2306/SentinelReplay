FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

RUN uv sync --frozen --no-dev --no-editable --no-cache \
    && groupadd --system sentinel \
    && useradd --system --gid sentinel --home-dir /nonexistent sentinel \
    && mkdir -p /var/lib/sentinel/evidence \
    && chown -R sentinel:sentinel /var/lib/sentinel

ENV PATH="/app/.venv/bin:${PATH}" \
    SENTINEL_EVIDENCE_ROOT=/var/lib/sentinel/evidence \
    SENTINEL_TRUSTED_PUBLIC_KEY=/run/sentinel/trusted.pub

USER sentinel
EXPOSE 8000
CMD ["uvicorn", "sentinel_replay.api:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
