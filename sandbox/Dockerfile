# tieout-sandbox: the image every reconciliation runs in (under gVisor, no network).
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_SYSTEM_PYTHON=1 UV_NO_CACHE=1

WORKDIR /opt/tieout
COPY pyproject.toml ./
COPY tieout_lib ./tieout_lib
# The optional "ca" secret only exists for builds behind a TLS-intercepting proxy; it never lands in a layer.
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv pip install --system --no-cache . && rm -rf /opt/tieout /root/.cache /usr/local/bin/uv \
    && python -c "import tieout_lib, pandas, openpyxl, rapidfuzz; print('tieout_lib', tieout_lib.__version__)"

COPY attest.py /opt/attest.py
ARG GIT_SHA=dev
ARG BUILD_VERSION=1.0.0
RUN printf '{"image": "tieout-sandbox", "version": "%s", "git_sha": "%s"}\n' "$BUILD_VERSION" "$GIT_SHA" > /etc/image-build.json \
    && groupadd -g 10001 sandbox && useradd -u 10001 -g 10001 -M -d /tmp -s /usr/sbin/nologin sandbox \
    && mkdir -p /in /work /out && chown 10001:10001 /work /out && chmod 0755 /in

# Flatten: start from scratch so no environment variable from the base image
# carries over. The sandbox sees only the variables listed here.
FROM scratch
COPY --from=build / /
ENV PATH=/usr/local/bin:/usr/bin:/bin \
    LANG=C.UTF-8 \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    MPLCONFIGDIR=/tmp
USER 10001:10001
WORKDIR /work
CMD ["sleep", "infinity"]
