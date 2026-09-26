# KubeMedic agent API and operator console.
#
#   docker build -t kubemedic:1.0 .
#
# The image runs as an unprivileged user, holds no credentials, and starts with
# authentication REQUIRED: it will not serve until KUBEMEDIC_API_TOKENS is
# provided (see deploy/kubemedic.yaml). Presenter tooling -- fault injection and
# the engine switch -- is off by default in this mode.
#
# Bob Shell is not bundled. To use the IBM Bob engine from a container, install
# it in a derived image and supply KUBEMEDIC_BOB_API_KEY from a Secret.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --system --uid 10001 --create-home --home-dir /home/kubemedic kubemedic \
    && mkdir -p /var/lib/kubemedic /app/records \
    && chown -R kubemedic:kubemedic /var/lib/kubemedic /app/records

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY agent ./agent
COPY mcp_server ./mcp_server
COPY scripts ./scripts
COPY static ./static
COPY .bob/skills/incident-correlation/references ./.bob/skills/incident-correlation/references

ENV KUBEMEDIC_API_HOST=0.0.0.0 \
    KUBEMEDIC_API_PORT=8100 \
    KUBEMEDIC_REQUIRE_AUTH=true \
    KUBEMEDIC_STATE_DB=/var/lib/kubemedic/state.db

USER kubemedic
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/api/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "agent.api"]
