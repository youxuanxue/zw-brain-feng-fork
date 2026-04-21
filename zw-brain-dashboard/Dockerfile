# zw-brain-dashboard — Phase-0 placeholder Dockerfile.
#
# Real multi-stage build (Node bundler → nginx + Python BFF) lands once
# the Phase-0 PoC picks the frontend framework + BFF runtime (D19).
# This stub exists so deploy CI has a target image name + tag scheme.

FROM python:3.12-slim AS bff

WORKDIR /app
COPY bff /app/bff
COPY src /app/static
COPY index.html /app/static/index.html

EXPOSE 8801
CMD ["python", "-m", "bff.main"]
