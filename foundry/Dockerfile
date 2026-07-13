# Foundry — Cedar-routed multi-model inference pool
# Build context must be the repo root (not foundry/), so this Dockerfile
# can COPY the full src/ tree for the editable helix-adapter install.
#
#   docker build -f foundry/Dockerfile -t helix-foundry .

FROM python:3.12-slim

WORKDIR /app

# System deps: cedar_python needs a Rust toolchain-built wheel; it ships
# prebuilt wheels for standard manylinux targets, so no compiler needed
# here — just certs for outbound TLS to whichever deployment's endpoint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the package first (better layer caching — only re-runs on
# dependency changes, not on every foundry.py edit)
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[widget]"

# Now the Foundry app itself
COPY foundry/ ./foundry/

WORKDIR /app/foundry

ENV HELIX_DEPLOYMENT=ollama-local
ENV PYTHONUNBUFFERED=1
# Bind to all interfaces inside the container — the actual "not exposed
# externally" boundary comes from the host-side -p 127.0.0.1:8800:8800
# port mapping instead. See HELIX_BIND_HOST handling in foundry.py.
ENV HELIX_BIND_HOST=0.0.0.0

EXPOSE 8800

CMD ["python3", "foundry.py", "8800"]
