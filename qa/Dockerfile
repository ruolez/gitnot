# Test client. BASE picks the git version under test:
#   debian:bookworm-slim = git 2.39 (same as macOS Apple Git)
#   ubuntu:24.04         = git 2.43 (the VPS installers)
#   debian:trixie-slim   = git 2.47
ARG BASE=debian:bookworm-slim
FROM ${BASE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git openssh-client python3 python3-pytest python3-requests ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /qa
CMD ["python3", "-m", "pytest", "-q", "e2e"]
