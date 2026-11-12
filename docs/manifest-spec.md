# Manifest specification

## Schema version

The catalog and server manifests use `schema_version: 1`.

## Catalog layout

```yaml
schema_version: 1
name: personal-mcp-catalog
title: Personal MCP Catalog
description: Curated MCP servers maintained by jkrenzer.
repository: https://github.com/example/mcp-catalog
servers_dir: servers
```

A catalog must reference a directory containing one manifest per server. Server names must be lowercase and may contain only `a-z0-9` with optional hyphen separators.

`repository` is optional and names the Git repository that maintains the catalog. It becomes
the `org.opencontainers.image.source` label of the published catalog image and of locally
built server images, and the `source` link of locally built servers in the generated Docker
MCP catalog. Environment variables are expanded before URL validation.

The JSON Schemas in `schemas/` carry a `description` for every field; they are generated from
the Pydantic models with `mcp-catalog schema generate schemas`.

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

## Docker MCP catalog fields

Every server kind accepts the descriptive and configuration fields that the Docker MCP catalog
format (`docker mcp` gateway and the Docker MCP registry) defines. All of them are optional;
values that are not set are omitted from the generated catalog entry.

| Field | Purpose in the Docker MCP catalog |
|-------|-----------------------------------|
| `icon` | `icon`: URL of a small PNG, SVG or favicon logo (at most 512x512 pixels). |
| `readme` | `readme`: URL of the server documentation. |
| `upstream` | `upstream`: URL of the upstream project. Defaults to the Git source repository of build servers. |
| `date_added` | `dateAdded`: RFC 3339 timestamp; rendered in UTC. It is declared, never computed, so output stays deterministic. |
| `metadata.category`, `metadata.tags`, `metadata.license`, `metadata.owner` | `metadata`: categorisation shown in catalog UIs. Pull and star counters are computed by Docker Hub and cannot be declared. |
| `tools` | `tools`: advertised tools with `name`, `description`, `arguments` (`name`, `type`, `desc`, `optional`, `items`) and `annotations` (`title`, `read_only_hint`, `destructive_hint`, `idempotent_hint`, `open_world_hint`). The registry generates this list by running the server; this catalog cannot, so declare it. The gateway still discovers tools at runtime. |
| `tools_file` | Path to a JSON or YAML file holding the `tools` list in the same shape (the Docker registry's `tools.json` convention), for servers with many tools. Relative paths resolve from the manifest directory with the same variable expansion as local build paths. Mutually exclusive with `tools`. |
| `secrets` | `secrets`: `name` (`prefix.key`, usually `<server-name>.<key>`), `env`, `example`, `description`, `required`. Values are stored by users with `docker mcp secret set`. |
| `config` | `config`: user-configurable settings. Each entry has `description`, `properties` (JSON Schema fragments with a `type`), `required`, `any_of` and `one_of` requirement sets, and an optional `name` that defaults to the server name. |
| `oauth` | `oauth`: `providers` (`provider`, `secret`, `env`) and optional `scopes`. |
| `prefix` | `prefix`: prefix the gateway prepends to tool names. |

Build and image servers additionally accept container `runtime` settings:

| Field | Docker MCP catalog field |
|-------|--------------------------|
| `runtime.command` | `command`: arguments appended to the image entrypoint. |
| `runtime.volumes` | `volumes`: `host:container` mounts with an optional `:ro` or `:rw` suffix. |
| `runtime.user` | `user`: user the container runs as. |
| `runtime.long_lived` | `longLived`: keep the container running instead of starting it on demand. |
| `runtime.disable_network` | `disableNetwork`: disable all network access. |
| `runtime.allow_hosts` | `allowHosts`: allowed outbound `host:port` targets. |
| `runtime.extra_hosts` | `extraHosts`: additional `/etc/hosts` entries. |
| `runtime.env` | `env`: static environment variables (`name`, `value`). |

Remote servers accept `remote.transport_type` (`streamable-http`, the default, or `sse`) and
`remote.headers` instead of `runtime`.

Values in `runtime.env`, `runtime.command`, `runtime.volumes`, `runtime.user` and
`remote.headers` may reference user configuration with `{{server-name.property}}` templates.
The prefix must be the server name (or the name of one of its `config` entries); the gateway
substitutes the values users enter for the `config` properties. Unset properties expand to an
empty string; append the gateway's `|or:<default>` filter, as in `{{example.level|or:info}}`, to
supply a fallback. The gateway always runs container servers over stdio, so a manifest cannot
switch a container to an HTTP transport; use `kind: remote` for hosted endpoints.

Example:

```yaml
schema_version: 1
name: example
kind: image
title: Example
description: Example server with configuration.
image: ghcr.io/example/server@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
icon: https://www.google.com/s2/favicons?domain=example.com&sz=64
metadata:
  category: database
  tags: [example]
  license: MIT
runtime:
  volumes: ['{{example.data_dir}}:/data']
  env:
    - name: EXAMPLE_REGION
      value: '{{example.region}}'
  allow_hosts: [api.example.com:443]
secrets:
  - name: example.api_key
    env: EXAMPLE_API_KEY
    example: <EXAMPLE_API_KEY>
config:
  - description: Configure the example.com connection.
    properties:
      data_dir: {type: string, description: Host directory mounted at /data.}
      region: {type: string, default: eu}
    required: [data_dir]
```

See `examples/` for complete manifests of each kind. A `tools.json` can be captured from a
running server by sending it an MCP `tools/list` request and mapping each tool's `inputSchema`
properties to `arguments` (property name, `type`, `description` as `desc`, `optional` when the
property is not in `required`, and `items.type` for arrays).

## Generated image labels

`mcp-catalog image build` labels every built server image. Labels passed on the command line
override `LABEL` instructions in the Dockerfile, so the Dockerfile does not need to repeat them:

| Label | Value |
|-------|-------|
| `org.opencontainers.image.title` | `title` |
| `org.opencontainers.image.description` | `description`, whitespace collapsed to one line |
| `org.opencontainers.image.source` | Git source `repository`, or the catalog `repository` for local builds |
| `org.opencontainers.image.revision` | Git source `revision`, or the catalog commit for local builds |
| `org.opencontainers.image.url` | `upstream` (defaults to the Git source repository) |
| `org.opencontainers.image.documentation` | `readme` |
| `org.opencontainers.image.licenses` | `metadata.license` |
| `org.opencontainers.image.vendor` | `metadata.owner` |
| `io.docker.server.metadata` | Self-describing server metadata read by the `docker mcp` gateway |

`io.docker.server.metadata` is compact, key-sorted JSON (JSON is valid YAML, which is what the
gateway parses). It carries only the descriptive fields the gateway accepts from images:
`name`, `type`, `title`, `description`, `icon`, `readme`, `env` names (without values), `tools`,
`config`, `prefix` and `metadata`. Runtime settings, secrets, volumes and the image reference are
intentionally not part of the label; the gateway takes them only from the catalog. The same
labels appear under `labels` in build plans. `org.opencontainers.image.created` is not set so
that builds stay reproducible.

The published catalog image is labelled with `org.opencontainers.image.title`, `.description`,
`.source` (catalog `repository`) and `.revision` (catalog commit).

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
- Secret names and OAuth secret references must use `prefix.key` form.
- Environment variable names must be valid shell identifiers.
- `config` properties must declare a `type`; `required` entries must name declared properties.
- `{{prefix.property}}` templates must reference the server name or one of its `config` names.
- `remote.transport_type` must be `streamable-http` or `sse`; remote servers reject `runtime`.

## Migration policy

New schema versions may be introduced only with a documented migration path. The library rejects unsupported schema versions and keeps input strict.
