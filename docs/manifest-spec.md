# Manifest specification

## Schema version

The catalog and server manifests use `schema_version: 1`.

## Catalog layout

```yaml
schema_version: 1
name: personal-mcp-catalog
title: Personal MCP Catalog
description: Curated MCP servers maintained by jkrenzer.
servers_dir: servers
```

A catalog must reference a directory containing one manifest per server. Server names must be lowercase and may contain only `a-z0-9` with optional hyphen separators.

## Server manifest examples

### Build server

```yaml
schema_version: 1
name: local-server
kind: build
title: Local Server
description: Built from a Git repository.
enabled: true
source:
  repository: https://github.com/example/repo.git
  revision: 0123456789abcdef0123456789abcdef01234567
  context: .
  dockerfile: Dockerfile
build:
  platforms: [linux/amd64]
  args: {}
```

### Local build server

For a server whose Dockerfile is maintained outside an upstream repository, omit
`repository` and `revision`. `context` is a directory relative to this manifest,
and `dockerfile` is a file relative to that context:

```yaml
schema_version: 1
name: local-server
kind: build
title: Local Server
description: Built from a local Docker context.
source:
  context: ${GIT_BASE}/servers/local-server
  dockerfile: Dockerfile
build:
  platforms: [linux/amd64]
  args: {}
```

In file-backed manifests, relative local paths resolve from the manifest's
directory (the catalog's directory for embedded server entries). `$GIT_BASE`
expands to the nearest parent of the process working directory containing
`.git`; `$CWD` expands to the process working directory. Other `$NAME` and
`${NAME}` references expand from the process environment. Git repository and
remote endpoint URLs also support environment expansion before URL validation.
Git-relative context and Dockerfile values support shell-environment expansion
before their repository-relative path checks.

### Image server

```yaml
schema_version: 1
name: prebuilt-server
kind: image
title: Prebuilt server
description: Already published image.
enabled: true
image: ghcr.io/example/server@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

### Remote server

```yaml
schema_version: 1
name: remote-server
kind: remote
title: Remote server
description: Hosted MCP endpoint.
enabled: true
remote:
  url: https://example.com/mcp
```

## Validation rules

- `schema_version` must be exactly `1`.
- `name` must match `^[a-z0-9]+(?:-[a-z0-9]+)*$` and must not be `catalog`.
- Unknown YAML fields are rejected.
- Duplicate server names are rejected.
- The file name and manifest `name` must match.
- Image references must remain immutable and digest-pinned.
- Remote URLs must use valid HTTP/HTTPS URLs.
- Git build source paths must stay within the checked-out repository root.
- Local build contexts must be existing directories and Dockerfiles must be
  existing files contained in their context.
- URL values must be valid HTTP/HTTPS URLs after environment expansion.

## Migration policy

New schema versions may be introduced only with a documented migration path. The library rejects unsupported schema versions and keeps input strict.
