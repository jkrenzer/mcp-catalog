ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ${PYTHON_IMAGE} AS docker-cli

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian %s stable\n' \
        "$(dpkg --print-architecture)" \
        "$(sed -n 's/^VERSION_CODENAME=//p' /etc/os-release)" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

FROM docker-cli AS base

ARG WORKSPACE_DIR=/workspace
ARG VIRTUAL_ENV=/opt/venv
ENV VIRTUAL_ENV=${VIRTUAL_ENV} \
    PATH="${VIRTUAL_ENV}/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR ${WORKSPACE_DIR}

RUN python -m venv "${VIRTUAL_ENV}"

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

FROM base AS development

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && pip install --no-cache-dir --group dev --editable . \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 .docker/dev/entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "-l"]

FROM docker-cli AS runtime

ARG WORKSPACE_DIR=/workspace
ARG VIRTUAL_ENV=/opt/venv
ENV VIRTUAL_ENV=${VIRTUAL_ENV} \
    PATH="${VIRTUAL_ENV}/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR ${WORKSPACE_DIR}

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=base ${VIRTUAL_ENV} ${VIRTUAL_ENV}

FROM runtime AS interactive

WORKDIR /data
VOLUME /data

FROM base AS mcp-dependencies

RUN pip install --no-cache-dir ".[mcp]"

FROM interactive AS mcp

COPY --from=mcp-dependencies ${VIRTUAL_ENV} ${VIRTUAL_ENV}

ENTRYPOINT ["mcp-catalog"]
CMD ["mcp", "serve"]

FROM runtime AS command

ENTRYPOINT ["mcp-catalog"]
CMD ["--help"]
