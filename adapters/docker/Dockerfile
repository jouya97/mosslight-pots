# Build context is the repository root:
#   docker build -f adapters/docker/Dockerfile -t docker.io/library/mosslight-tools:local .
#
# One image, two uses. The host broker (harness/) and the host grader start
# every container from it with --network none, a read-only root and dropped
# capabilities; no container outlives its command.
#
#   /workspace   tool container, one per action: 128 MiB / 8192-inode tmpfs,
#                seeded from read-only /seed. Exports stay within 64 MiB logical
#                bytes / 4096 entries. Participant processes are terminated
#                before bounded export and publication.
#   /candidate   candidate container, one per probe, run as nobody: a
#                read-only bind mount of a freshly extracted committed
#                snapshot. Live-board checks also mount their own /check.py
#                read-only; final grading only prints observations.
#
# There is no long-lived agent container, no compose file and no /grader. The
# scaffold's "grader container the agent never touched" is the fresh read-only
# /candidate container; the trusted grader runs on the host
# (python -m bug_competition.grader.grader <protected>) and compares those
# observations with answers that never leave the host. grader/ and bug_competition/host_only/
# never enter the image: .dockerignore keeps the whole build context out, and
# the build fails below if any of it, or any grader/host data, is present.
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

RUN apt-get update && apt-get install -y --no-install-recommends git nodejs ripgrep chromium && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /workspace

# Copies nothing when .dockerignore is intact; used only to prove that.
COPY . /tmp/build-context/

# Fail the build rather than ship an image that carries grader or host data,
# a non-empty /workspace, or a different toolchain.
RUN set -eu; \
    if [ -n "$(find /tmp/build-context -mindepth 1 -print -quit)" ]; then \
      echo "FATAL: build context reached the image; restore .dockerignore" >&2; exit 1; fi; \
    rm -rf /tmp/build-context; \
    for sealed in /grader /host_only /bug_competition /candidate; do \
      if [ -e "$sealed" ]; then echo "FATAL: $sealed is in the image" >&2; exit 1; fi; \
    done; \
    leaked="$(find / -xdev \( -name host_only -o -name grader_data -o -name reference_solution \
      -o -name submission_contract.py -o -name manifest.json -o -name events.jsonl \) -print -quit)"; \
    if [ -n "$leaked" ]; then echo "FATAL: grader/host data in the image: $leaked" >&2; exit 1; fi; \
    if [ -n "$(ls -A /workspace)" ]; then echo "FATAL: /workspace must be empty; it is bind-mounted per action" >&2; exit 1; fi; \
    git --version && node --version && rg --version >/dev/null && python --version && chromium --version
