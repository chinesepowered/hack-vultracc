# Tieout control plane API. Build context: the repo root.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv/tieout
COPY sandbox/pyproject.toml sandbox/uv.lock sandbox/
COPY sandbox/tieout_lib sandbox/tieout_lib
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    cd apps/api && uv sync --frozen --no-dev --no-install-project
COPY apps/api/tieout apps/api/tieout
COPY prompts prompts
COPY data/demo data/demo
ARG GIT_SHA=dev
RUN echo "$GIT_SHA" > apps/api/GIT_SHA
ENV PATH=/opt/venv/bin:$PATH PROMPTS_DIR=/srv/tieout/prompts DEMO_DATA_DIR=/srv/tieout/data/demo WEB_DIST=/srv/web
WORKDIR /srv/tieout/apps/api
EXPOSE 8000
CMD ["uvicorn", "tieout.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "75"]
