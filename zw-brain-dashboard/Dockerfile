# zw-brain-dashboard — read-only K12 dashboard image.
#
# The image ships the dashboard static frontend together with the shared
# zw_brain runtime so the Python read-only BFF can serve dashboard.* skills.

FROM python:3.12-slim AS bff

WORKDIR /app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY zw_brain /app/zw_brain
COPY zw-brain-web /app/zw-brain-web
COPY zw-brain-dashboard /app/zw-brain-dashboard

RUN pip install --no-cache-dir "SQLAlchemy>=2.0" "alembic>=1.18"

EXPOSE 8801
ENV ZW_BRAIN_DASHBOARD_BFF_PORT=8801
CMD ["python", "zw-brain-dashboard/bff/main.py"]
