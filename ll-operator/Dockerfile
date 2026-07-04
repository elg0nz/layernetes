# ll-operator: kopf-based Kubernetes operator reconciling LLAgent CRs.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies only (the project deliberately installs no packages —
# see pyproject.toml); handler code is run by file path below.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY operator/ ./operator/

# Non-root.
RUN useradd --uid 10001 --user-group --no-create-home ll-operator
USER 10001

# kopf liveness endpoint (the chart can point an httpGet probe at :8080/healthz).
EXPOSE 8080

# Standalone (no peering), watching only the platform namespace.
CMD ["/bin/sh", "-c", \
     "exec kopf run --standalone --namespace \"${PLATFORM_NAMESPACE:-layernetes}\" --liveness=http://0.0.0.0:8080/healthz /app/operator/main.py"]
