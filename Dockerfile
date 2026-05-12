FROM python:3.12-slim AS builder

WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m pip install --no-cache-dir --upgrade pip build
COPY . .
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZW_BRAIN_DB_PATH=/data/zw-brain/zw_brain.db

WORKDIR /app
RUN python -m pip install --no-cache-dir --upgrade pip
COPY --from=builder /dist/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

VOLUME ["/data/zw-brain"]
EXPOSE 8800 8801
CMD ["zw-brain-rest"]
