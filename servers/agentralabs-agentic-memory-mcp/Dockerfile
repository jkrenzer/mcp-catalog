FROM debian:trixie-slim AS base

ARG CONFIG_DIR=/config
ARG MEMORY_DIR=/memory
ENV CONFIG_DIR=${CONFIG_DIR}
ENV MEMORY_DIR=${MEMORY_DIR}

RUN cat <<EOF > /etc/apt/sources.list.d/backports.sources
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie-backports
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && apt-get install -t trixie-backports -y --no-install-recommends \
    cargo \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p ${CONFIG_DIR} ${MEMORY_DIR}
RUN cargo install agentic-memory-cli && \
    cargo install agentic-memory-mcp

VOLUME ${CONFIG_DIR} ${MEMORY_DIR}
ENTRYPOINT ["agentic-memory-mcp"]
CMD ["serve"]