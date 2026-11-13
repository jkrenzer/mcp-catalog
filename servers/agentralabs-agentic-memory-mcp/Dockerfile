#check=skip=SecretsUsedInArgOrEnv
FROM debian:trixie-slim AS base

ARG CONFIG_DIR=/config
ARG MEMORY_DIR=/memory
ARG INTERNAL_MEMORY_FILE=/root/internal_memory.amem
ARG MCP_SERVER_TOKEN_FILE=/token
ENV CONFIG_DIR=${CONFIG_DIR}
ENV MEMORY_DIR=${MEMORY_DIR}
ENV CARGO_HOME=/usr/local/cargo
ENV PATH="${CARGO_HOME}/bin:${PATH}"
ENV INTERNAL_MEMORY_FILE=${INTERNAL_MEMORY_FILE}
ENV AMEM_BRAIN=${INTERNAL_MEMORY_FILE}
# Set the MCP_SERVER_PROTOCOL environment variable to either "stdio" or "http".
# "stdio" is what MCP clients and the Docker MCP gateway use; "http" serves the
# MCP endpoint over the network for standalone or sidecar deployments.
ENV MCP_SERVER_PROTOCOL=stdio
# Set the MCP_SERVER_HOST and MCP_SERVER_PORT environment variables to the address
# the server binds to in "http" mode. Empty values fall back to these defaults.
ENV MCP_SERVER_HOST=0.0.0.0
ENV MCP_SERVER_PORT=3000
# The token is required for the server to serve http requests. Either set the
# AGENTIC_TOKEN environment variable or bind-mount a file containing the token at
# MCP_SERVER_TOKEN_FILE (docker run -v ./token.txt:/token:ro ...). The entrypoint
# reads the file into AGENTIC_TOKEN at start-up. The file is not declared as a
# VOLUME: Docker would create a directory at that path, which cannot be read.
ENV MCP_SERVER_TOKEN_FILE=${MCP_SERVER_TOKEN_FILE}
# ENV AGENTIC_TOKEN=""
# Set the log level for the Rust application. Possible values are:
# error, warn, info, debug, trace.
ENV MCP_SERVER_LOG_LEVEL=info
ENV RUST_LOG=${MCP_SERVER_LOG_LEVEL}
# Set log filepath to which the container will log. 
ENV MCP_SERVER_LOG_FILE=""
# Set the export memory file suffix, either "json" or "amem". The default is "amem".
# Convenient way to change the memory format for export without 
# changing the EXPORT_MEMORY_FILE path.
ENV EXPORT_MEMORY_FILE_SUFFIX="amem"
# Export memory file path, if set, the memory will be exported to this file.
# Must either end with .json or .amem. If not set, the memory will not be exported.
ENV EXPORT_MEMORY_FILE=${MEMORY_DIR}/memory.${EXPORT_MEMORY_FILE_SUFFIX}
# Export memory interval in seconds, if set, the memory will be exported to
# EXPORT_MEMORY_FILE every EXPORT_MEMORY_INTERVAL seconds.
ENV EXPORT_MEMORY_INTERVAL=60
# Import memory file path, if set, the memory will be imported from this file.
# Must either end with .json or .amem. If not set, defaults to the export file.
ENV IMPORT_MEMORY_FILE=${EXPORT_MEMORY_FILE}


RUN cat <<EOF > /etc/apt/sources.list.d/backports.sources
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie-backports
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    && apt-get install -t trixie-backports -y --no-install-recommends \
    cargo \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p ${CONFIG_DIR} ${MEMORY_DIR}
RUN cargo install --all-features agentic-memory-cli && \
    cargo install --all-features agentic-memory-mcp

COPY entrypoint.py /usr/local/bin/agentic-memory-entrypoint
RUN chmod +x /usr/local/bin/agentic-memory-entrypoint

VOLUME ${CONFIG_DIR} ${MEMORY_DIR}
EXPOSE ${MCP_SERVER_PORT}
ENTRYPOINT ["python3", "/usr/local/bin/agentic-memory-entrypoint"]