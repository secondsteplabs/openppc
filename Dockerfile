# OpenPPC in a container. A plain build makes the command line; --target mcp makes the MCP server.
#
#   docker build -t openppc .
#   docker run --rm --network none -v "$PWD/exports:/data:ro" openppc audit search-term-waste search_terms.csv
#   docker run --rm --network none openppc check --sample
#
#   docker build --target mcp -t openppc-mcp .
#   docker run --rm -i openppc-mcp                                         (stdio; give it files with -v)
#   docker run --rm -p 8000:8000 openppc-mcp --http --host 0.0.0.0 --port 8000
#
# The base image is pinned by digest (Dependabot proposes updates). Only the files that build the package are
# copied in, and .dockerignore allows nothing else into the build, so a client export left in the working copy
# never reaches an image. The command line image doesn't have the MCP SDK: it makes no network calls and has no
# library that could.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS source

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY openppc ./openppc
# the wheel bundles the samples, so --sample works inside the image too
COPY examples/search_terms_acme.csv examples/keywords_acme.csv examples/account_structure_acme.json \
     examples/account_acme.json examples/ai_audit_sample.md ./examples/

FROM source AS mcp
RUN pip install ".[mcp]" && rm -rf /src && useradd --create-home --uid 10001 openppc
USER openppc
WORKDIR /data
EXPOSE 8000
ENTRYPOINT ["openppc-mcp"]

FROM source AS cli
RUN pip install . && rm -rf /src && useradd --create-home --uid 10001 openppc
USER openppc
WORKDIR /data
ENTRYPOINT ["openppc"]
CMD ["--help"]
