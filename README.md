# mcp-catalog

A small Python package for managing declarative MCP server catalogs, validating manifests, generating OCI catalog metadata, and computing branch-aware image names for Docker builds.

## Features

- Validate catalog and server manifests using Pydantic models.
- Support build, image, and remote MCP server entry types.
- Describe every Docker MCP catalog field (icon, metadata, tools, secrets, config, runtime settings) and label built images with OCI and `io.docker.server.metadata` labels.
- Generate JSON Schema for manifests.
- Compute branch-aware catalog and image references.
- Keep YAML handling safe and deterministic.

## Quick start

```bash
python -m pip install -e .
mcp-catalog validate catalog.yaml
mcp-catalog branch-slug feature/my-branch
```

See the [CLI reference](docs/cli.md) for examples covering schema drift checks, server management,
upstream revision updates, deterministic build plans, Docker MCP generation, image building, and
publication.

See [CI and publication](docs/ci-publication.md) for validation checks, pull request title and
merge requirements, and the GHCR publishing and access model.

For the optional FastMCP server, install with `python -m pip install -e '.[mcp]'` and run `mcp-catalog mcp serve`.

## Run with Docker

Published images of the tooling live under the `self` namespace:
`ghcr.io/jkrenzer/mcp-catalog/self/cli:latest` runs the CLI and
`ghcr.io/jkrenzer/mcp-catalog/self/mcp:latest` runs the stdio MCP server
(`docker run --rm -i -v "${PWD}:/data" ghcr.io/jkrenzer/mcp-catalog/self/mcp:latest`).
Branches publish under `self/<branch slug>/`.

Build the CLI image from the repository root:

```bash
docker build -t mcp-catalog .
```

The image uses a virtual environment at `/opt/venv` and makes its executables available on `PATH`. The entrypoint is `mcp-catalog`; pass a CLI command after the image name for a one-shot invocation. Mount the working directory when validating local manifests:

```bash
docker run --rm -v "${PWD}:/workspace" -w /workspace mcp-catalog validate catalog.yaml
docker run --rm mcp-catalog branch-slug feature/my-branch
```

Running the image without arguments displays CLI help.

## Development container

Open the repository in VS Code and select **Reopen in Container** to use the `.devcontainer` configuration. It builds the `development` target, installs the package and development dependencies in `/opt/venv`, and runs the development entrypoint before keeping the container available for an interactive session. The devcontainer includes Docker CLI and Buildx through the Docker-outside-of-Docker feature and uses the host Docker socket, so a Docker engine must be running on the host. This grants the devcontainer control over that engine.
