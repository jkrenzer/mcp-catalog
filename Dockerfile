FROM python:3.13-slim-bookworm AS base

ARG WORKSPACE_DIR=/workspace
ARG DEBIAN_FRONTEND=noninteractive
ARG VIRTUAL_ENV=/opt/venv
ENV VIRTUAL_ENV=${VIRTUAL_ENV} \
    PATH="${VIRTUAL_ENV}/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN mkdir -p ${WORKSPACE_DIR}
WORKDIR ${WORKSPACE_DIR}

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "${VIRTUAL_ENV}" && \
    pip install --upgrade pip

COPY pyproject.toml README.md ./
COPY src/ ./src/

FROM base AS development

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --group dev --editable .

COPY .docker/dev/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash", "-l"]


FROM base AS interactive

RUN mkdir /data
WORKDIR /data
VOLUME /data


FROM interactive AS mcp

RUN pip install --no-cache-dir ".[mcp]"

ENTRYPOINT ["mcp-catalog"]
CMD ["mcp", "serve"]


FROM interactive AS command

RUN pip install --no-cache-dir .

ENTRYPOINT ["mcp-catalog"]
CMD ["--help"]
