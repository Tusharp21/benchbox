# benchbox end-to-end smoke test.
#
# Boots a clean Ubuntu 22.04, pretends to be a real user, runs scripts/install.sh
# in --local-source mode, then verifies the resulting CLI and the installer's
# dry-run path can execute without touching the real package system.
#
# Build + run (from repo root):
#   docker build -f tests/e2e/Dockerfile -t benchbox-e2e .
#   docker run --rm benchbox-e2e
#
# Used by the GitHub Actions `e2e` job to gate PRs before merge.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PATH=/home/tester/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Only install what benchbox's own install.sh requires on a fresh Ubuntu:
# python, venv, git, curl, ca-certificates. sudo is needed because ``benchbox
# install`` would call apt — the dry-run path we exercise below doesn't
# actually invoke apt, but the components probe dpkg-query so dpkg must exist.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        git \
        curl \
        ca-certificates \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# Matches the scenario a real user would hit: a non-root account with sudo.
RUN useradd --create-home --shell /bin/bash tester \
    && echo "tester ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/tester

# Copy the repo in (.dockerignore trims node_modules / __pycache__ / venvs).
COPY --chown=tester:tester . /src

USER tester
WORKDIR /home/tester

RUN BENCHBOX_SOURCE=/src bash /src/scripts/install.sh

COPY --chown=tester:tester tests/e2e/verify.sh /home/tester/verify.sh
RUN chmod +x /home/tester/verify.sh

CMD ["/home/tester/verify.sh"]
