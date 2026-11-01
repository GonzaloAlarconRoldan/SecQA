# syntax=docker/dockerfile:1.7
# ---- 1. build the web UI -----------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build   # writes to /app/src/secqa/hub/static

# ---- 2. build the Python wheel -----------------------------------------------
FROM python:3.12-slim AS wheel
WORKDIR /src
RUN pip install --no-cache-dir build==1.2.2
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY agent-kit/ agent-kit/
COPY --from=ui /app/src/secqa/hub/static/ src/secqa/hub/static/
RUN python -m build --wheel --outdir /dist

# ---- 3. runtime --------------------------------------------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="SecQA Hub" \
      org.opencontainers.image.description="Security & performance QA hub: runs, findings, defects, test cases" \
      org.opencontainers.image.source="https://github.com/GonzaloAlarconRoldan/SecQA" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SECQA_DATA_DIR=/data

COPY --from=wheel /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[hub,postgres]" && rm /tmp/*.whl \
 && useradd --system --uid 10001 --home /data secqa \
 && mkdir -p /data && chown secqa /data

USER secqa
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/api/health').status==200 else 1)"

CMD ["secqa", "hub", "serve", "--host", "0.0.0.0", "--port", "8787"]
