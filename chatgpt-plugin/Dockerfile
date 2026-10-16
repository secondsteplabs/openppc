# The hosted OpenPPC connector for ChatGPT (mcp.openppc.si). Build from the repository root:
#   docker build -f chatgpt-plugin/Dockerfile -t openppc-mcp .
# It serves streamable HTTP at /mcp, a health check at /health, and keeps nothing between calls.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY openppc ./openppc
COPY examples ./examples
COPY rulebook ./rulebook
RUN pip install ".[mcp]" && rm -rf /src && useradd --create-home --uid 10001 openppc

USER openppc
WORKDIR /home/openppc
# The public names it answers to, and each user's fair use: 30 audits or checks per 10 minutes, 2 at once.
ENV OPENPPC_ALLOWED_HOSTS=mcp.openppc.si OPENPPC_FAIR_USE=30/600/2
EXPOSE 8000
CMD ["sh", "-c", "exec openppc-mcp --http --host 0.0.0.0 --port ${PORT:-8000}"]
