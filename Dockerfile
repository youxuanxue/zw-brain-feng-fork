FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . .
RUN uv build --wheel --out-dir /dist

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db

WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN uv pip install --system /tmp/*.whl && uv pip install --system 'redis>=5.0' && rm -f /tmp/*.whl

VOLUME ["/data/zw-brain"]
EXPOSE 8800 8801
CMD ["zw-brain-rest"]
