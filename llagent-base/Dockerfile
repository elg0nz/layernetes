# llagent-base: the base image every LLAgent runs on.
#
# Provides: Python 3.12, pinned CrewAI, the FastMCP/FastAPI wrapper
# (server.py), sops + age for in-memory secret decryption, and the
# entrypoint. User projects layer on top:
#
#   FROM llagent-base:dev
#   COPY . /app        # must include crew.py (and keys.env, if any)
#
# Build: docker build -t llagent-base:dev .

FROM python:3.12-slim

# Buildx sets TARGETARCH; the legacy builder leaves it empty, so fall back
# to the build machine's arch (a wrong-arch sops is a runtime Exec format
# error, not a build failure).
ARG TARGETARCH=""
ARG SOPS_VERSION=3.9.4
ARG AGE_VERSION=1.2.1

# --- sops + age release binaries (pinned, checksum-verified) ---------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    TARGETARCH="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${TARGETARCH}" in \
      amd64) \
        SOPS_SHA256=5488e32bc471de7982ad895dd054bbab3ab91c417a118426134551e9626e4e85; \
        AGE_SHA256=7df45a6cc87d4da11cc03a539a7470c15b1041ab2b396af088fe9990f7c79d50;; \
      arm64) \
        SOPS_SHA256=16564c6b181d88505d9e0dfef62771894293d85cde5884d9b1a843859eee174b; \
        AGE_SHA256=57fd79a7ece5fe501f351b9dd51a82fbee1ea8db65a8839db17f5c080245e99f;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1;; \
    esac; \
    curl -fsSL -o /usr/local/bin/sops \
      "https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.${TARGETARCH}"; \
    echo "${SOPS_SHA256}  /usr/local/bin/sops" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/sops; \
    curl -fsSL -o /tmp/age.tar.gz \
      "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-${TARGETARCH}.tar.gz"; \
    echo "${AGE_SHA256}  /tmp/age.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/age.tar.gz -C /tmp; \
    install -m 0755 /tmp/age/age /tmp/age/age-keygen /usr/local/bin/; \
    rm -rf /tmp/age /tmp/age.tar.gz; \
    apt-get purge -y curl; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*; \
    sops --version; age --version

# --- Python runtime deps (pinned; verified to co-resolve on py3.12) --------
RUN pip install --no-cache-dir \
      crewai==1.15.1 \
      fastmcp==3.4.2 \
      fastapi==0.139.0 \
      "uvicorn[standard]==0.49.0"

# --- the wrapper ------------------------------------------------------------
COPY server.py entrypoint.sh /opt/llagent/
RUN chmod 0755 /opt/llagent/entrypoint.sh

# server.py is importable from anywhere; /app (the user's project, the
# WORKDIR) comes second so `import crew` finds the user's crew.py while the
# wrapper itself lives outside the user's copy path.
ENV PYTHONPATH=/opt/llagent:/app \
    PYTHONUNBUFFERED=1

RUN useradd --system --create-home --uid 10001 llagent && \
    mkdir -p /app && chown llagent:llagent /app
USER llagent

WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["/opt/llagent/entrypoint.sh"]
