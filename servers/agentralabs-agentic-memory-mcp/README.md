# Agentralabs Agentic Memory MCP image

Container image for the [Agentic Memory MCP server](https://github.com/agentralabs/agentic-memory)
(`agentic-memory-mcp`, MIT). The image installs the upstream crates and wraps them in an
entrypoint that prepares the configuration, imports and exports memory snapshots and starts the
server over stdio or HTTP. It works inside the Docker MCP Toolkit and on its own, for example as
a devcontainer sidecar or a standalone deployment.

## Configuration

All settings are environment variables. Empty values fall back to the defaults.

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_SERVER_PROTOCOL` | `stdio` | `stdio` for MCP clients and the Docker MCP gateway, `http` to serve the MCP endpoint over the network. |
| `MCP_SERVER_HOST`, `MCP_SERVER_PORT` | `0.0.0.0`, `3000` | Bind address in `http` mode. The port is exposed by the image. |
| `AGENTIC_TOKEN` | unset | Bearer token clients must present in `http` mode. Required for `http`, ignored for `stdio`. |
| `MCP_SERVER_TOKEN_FILE` | `/token` | File read into `AGENTIC_TOKEN` at start-up when it exists. Bind-mount the token as a file; a missing file is fine, a directory is an error. |
| `MEMORY_DIR` | `/memory` | Volume that receives exported snapshots. |
| `MULTI_TENANT` | `false` | Set to `true` to enable upstream per-user brain files. Requires authenticated HTTP requests; use a separate data directory for each deployment. |
| `DATA_DIR` | `/memory/tenants` | Directory for per-user brain files when `MULTI_TENANT=true`. Keep it on persistent storage. |
| `EXPORT_MEMORY_FILE`, `EXPORT_MEMORY_INTERVAL` | `/memory/memory.amem`, `60` | Snapshot path (`.amem` or `.json`) and export interval in seconds. Exports also run on shutdown. In multi-tenant mode, use one `*` in the filename (for example `/memory/exports/*.json`) to export each `{DATA_DIR}/{user_id}.amem` tenant file as `{user_id}`. Set the file to an empty value to disable exports. |
| `IMPORT_MEMORY_FILE` | the export file | Snapshot (`.amem` or `.json`) imported at start-up. In multi-tenant mode, use one `*` in the filename (for example `/memory/imports/*.amem`) to import each match into `{DATA_DIR}/{filename-stem}.amem`. A missing single file warns and starts with empty memory; a glob with no matches warns and imports no tenant files. |
| `MCP_SERVER_LOG_LEVEL`, `RUST_LOG` | `info` | Log levels of the entrypoint and of the server (`error`, `warn`, `info`, `debug`, `trace`). |
| `MCP_SERVER_LOG_FILE` | unset | Optional file that receives a copy of everything written to stderr (entrypoint and server logs). Parent directories are created; if the file cannot be written, a warning is logged and the run continues. |
| `CONFIG_DIR` | `/config` | Volume where the generated server configuration is written. |

The working memory lives inside the container; mounting `/memory` persists it across restarts
because the exported snapshot is imported again at the next start.

Upstream multi-tenant mode stores each user brain at `{DATA_DIR}/{user_id}.amem`. Tenant glob
patterns require `MULTI_TENANT=true`; `*` is supported only in the filename, and each import
filename stem is used as the tenant ID.

## Standalone over stdio

```bash
docker run --rm -i \
  -v agentic-memory:/memory \
  ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>
```

MCP client configuration (Claude Desktop, VS Code, Cursor and similar):

```json
{
  "mcpServers": {
    "agentic-memory": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-v", "agentic-memory:/memory",
               "ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>"]
    }
  }
}
```

## Standalone over HTTP

Provide the token either as an environment variable or as a file mounted at `/token`:

```bash
docker run --rm -d --name agentic-memory \
  -p 3000:3000 \
  -e MCP_SERVER_PROTOCOL=http \
  -e AGENTIC_TOKEN=change-me \
  -v agentic-memory:/memory \
  ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>

# or with a token file (any path works when MCP_SERVER_TOKEN_FILE is set accordingly)
docker run --rm -d -p 3000:3000 -e MCP_SERVER_PROTOCOL=http \
  -v ./token.txt:/token:ro -v agentic-memory:/memory \
  ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>
```

Clients connect with the streamable HTTP transport to `http://localhost:3000/mcp` and send
the header `Authorization: Bearer <token>`; requests without a valid token are rejected with
status 401.

## Devcontainer sidecar

Run the server next to a devcontainer with Docker Compose and reach it by service name:

```yaml
services:
  devcontainer:
    build: .
    volumes: [..:/workspaces/project]
    command: sleep infinity
  agentic-memory:
    image: ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>
    environment:
      MCP_SERVER_PROTOCOL: http
    secrets: [agentic_token]
    volumes: [agentic-memory:/memory]
secrets:
  agentic_token:
    file: ./token.txt
volumes:
  agentic-memory:
```

Compose mounts the secret at `/run/secrets/agentic_token`; set
`MCP_SERVER_TOKEN_FILE=/run/secrets/agentic_token` in the service environment so the entrypoint
reads it, and point the devcontainer's MCP client at `http://agentic-memory:3000/mcp`.

### Multi-tenant Compose deployment with persistent snapshots

This standalone setup enables per-user brains and stores both the live tenant files and their
import/export snapshots on a named volume:

```yaml
services:
  agentic-memory:
    image: ghcr.io/jkrenzer/mcp-catalog/agentralabs-agentic-memory-mcp:<tag>
    ports:
      - "3000:3000"
    environment:
      MCP_SERVER_PROTOCOL: http
      MULTI_TENANT: "true"
      DATA_DIR: /memory/tenants
      IMPORT_MEMORY_FILE: "/memory/exports/*.amem"
      EXPORT_MEMORY_FILE: "/memory/exports/*.amem"
      EXPORT_MEMORY_INTERVAL: "60"
      MCP_SERVER_TOKEN_FILE: /run/secrets/agentic_token
    secrets:
      - agentic_token
    volumes:
      - agentic-memory-data:/memory

secrets:
  agentic_token:
    file: ./token.txt

volumes:
  agentic-memory-data:
```

Create `token.txt` with a secret token, then start the service with `docker compose up -d`.
The server stores live brains as `/memory/tenants/{user_id}.amem`; periodic and shutdown exports
write corresponding snapshots to `/memory/exports/{user_id}.amem`. On startup, the import pattern
restores any snapshots found there. The first run can report that no snapshots match; it starts
without imported tenant files and creates them as users connect.

The named volume survives container replacement and `docker compose down`; use
`docker compose down -v` only when you intend to delete the live tenant files and snapshots too.
Clients connect to `http://localhost:3000/mcp` and must authenticate with the configured token.

## Docker MCP Toolkit

The catalog entry in this repository declares the server for the Docker MCP gateway. The gateway
always runs the container over stdio, asks for a host directory that is mounted at `/memory`,
and offers the optional secret `agentralabs-agentic-memory-mcp.token` (injected as
`AGENTIC_TOKEN`). The secret is only needed if you run the same image over HTTP elsewhere.

```bash
docker mcp secret set agentralabs-agentic-memory-mcp.token=change-me
```
