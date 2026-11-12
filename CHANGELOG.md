# Changelog

## Unreleased

- Server manifests describe every Docker MCP catalog field: icon, readme, upstream, date added,
  metadata, tools, secrets, config, OAuth, prefix, container runtime settings and remote
  transport/headers. The free-form `runtime` and `metadata` mappings became typed models with
  documented fields and JSON Schema descriptions.
- Server manifests accept `tools_file`, a manifest-relative JSON or YAML tools list, and the
  agentic memory server ships its 124 tools in `servers/agentralabs-agentic-memory-mcp/tools.json`.
- The agentic memory image reads its token from a bind-mounted file (default `/token`) or the
  `AGENTIC_TOKEN` variable, which the catalog entry offers as a Docker MCP secret; it exposes the
  HTTP port for standalone and sidecar use, treats empty environment values as unset, and ships a
  README describing stdio, HTTP and devcontainer deployments.
- `mcp-catalog self plan` and `self build` build and publish the tooling images (`command` and
  `mcp` Dockerfile targets) under `ghcr.io/jkrenzer/mcp-catalog/self/<component>` on `main` and
  `self/<branch slug>/<component>` elsewhere; the publish workflow pushes them. The `mcp` image
  now runs `mcp-catalog mcp serve`.
- The agentic memory entrypoint re-imports the exported snapshot by default, only warns when no
  import file exists or it is empty, and duplicates the combined stderr output to an optional
  `MCP_SERVER_LOG_FILE`, creating parent directories and never failing the run.
- Catalog manifests accept an optional `repository` URL used for OCI source labels and local
  build source links.
- Generated Docker MCP catalog entries include all declared fields; image builds apply
  `org.opencontainers.image.*` labels and the gateway's `io.docker.server.metadata` label, and
  build plans list them.
- Initial project scaffolding for declarative MCP catalog management.
- Added branch-aware image naming helpers, YAML validation, and scaffolded publish workflow files.
