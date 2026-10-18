# Production image for compose.prod.yml. The dev images stay in backend/ and frontend/.
FROM node:22-slim AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /app/dist /app/frontend_dist
# collectstatic only needs settings to import; the key below exists for this one command.
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput
CMD ["gunicorn", "sharelo.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2"]

FROM app AS cron
# Literal version and checksum from https://github.com/aptible/supercronic/releases (linux-amd64).
ARG SUPERCRONIC_VERSION=v0.2.33
ARG SUPERCRONIC_SHA256=feefa310da569c81b99e1027b86b27b51e6ee9ab647747b49099645120cfc671
ADD https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN echo "${SUPERCRONIC_SHA256}  /usr/local/bin/supercronic" | sha256sum -c - && chmod +x /usr/local/bin/supercronic
COPY deploy/crontab /etc/crontab
CMD ["supercronic", "/etc/crontab"]
