FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

WORKDIR /opt/education-os

COPY backend/pyproject.toml backend/
COPY backend/app/ backend/app/
RUN pip install --no-cache-dir ./backend

COPY backend/alembic/ backend/alembic/
COPY backend/alembic.ini backend/
COPY --from=frontend-build /build/frontend/dist frontend/dist
COPY deployment/start-web.sh /usr/local/bin/start-web

RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /opt/education-os

USER app
WORKDIR /opt/education-os/backend

EXPOSE 10000
ENTRYPOINT ["/usr/local/bin/start-web"]
