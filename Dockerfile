# Aangan: one container serves the API and the web app.
#   docker build -t aangan . && docker run -p 8000:8000 --env-file backend/.env aangan

# 1. Build the web app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2. The backend, with the built web app next to it
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY --from=web /web/dist ./static

# The whole app is public on a host: no local tunnel guard. The household is saved under /data (mount a disk there to keep it).
ENV AANGAN_PUBLIC=1 AANGAN_STATIC_DIR=/app/static AANGAN_DATA_FILE=/data/household.json
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
