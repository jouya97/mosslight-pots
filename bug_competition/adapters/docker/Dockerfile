# Build from bug_competition/: docker build -f adapters/docker/Dockerfile -t docker.io/library/mosslight-tools:local .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs ripgrep && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /workspace
