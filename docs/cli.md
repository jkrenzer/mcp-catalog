# CLI reference

Install the package and show the available commands:

```bash
python -m pip install -e .
mcp-catalog --help
```

Commands default to `catalog.yaml` in the current directory unless a different path is supplied.
Logging and progress messages are written to stderr; command data (such as JSON plans and server manifests) remains on stdout. CLI logging defaults to `INFO`. Set the global `--log-level` before the command to select `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Repeat `--log-file` to write to multiple paths; each file inherits the CLI log level unless prefixed with its own level:

```bash
mcp-catalog --log-level DEBUG --log-file ./catalog.log validate catalog.yaml
mcp-catalog --log-level WARNING --log-file ./warnings.log --log-file DEBUG:./details.log plan catalog.yaml
```

The package buffers logs until CLI options are configured. If CLI logging setup fails, buffered records of all levels are emitted to stderr.

## Validate and generate schemas

```bash
mcp-catalog validate catalog.yaml
mcp-catalog validate examples/build-server.yaml
mcp-catalog schema generate schemas
mcp-catalog schema check schemas
```

Catalog validation reads the configured `servers_dir` in sorted filename order when the catalog does not embed a `servers` list. A server file's base name must match its manifest `name`; validating a standalone server checks its content only. Schema checking compares parsed JSON values, so formatting-only changes do not constitute drift.

## Manage servers

Use `--manifest` with a complete, validated server YAML file when adding or replacing a server:

```bash
mcp-catalog server list catalog.yaml
mcp-catalog server show example catalog.yaml
mcp-catalog server add catalog.yaml --manifest examples/build-server.yaml
mcp-catalog server update example catalog.yaml --manifest /tmp/example-updated.yaml
mcp-catalog server remove example catalog.yaml
```

These commands edit either the embedded catalog `servers` list or the individual YAML files in `servers_dir`, according to the catalog layout. The update command keeps the existing server name.

## Upstream revisions and build plans

Resolving an upstream ref is read-only. Updating a revision is a separate, explicit operation:

```bash
mcp-catalog upstream resolve example catalog.yaml --ref main
mcp-catalog upstream update example catalog.yaml --ref main
```

Build plans are stable, name-sorted JSON. Supply `--catalog-commit` when running outside a Git checkout or when reproducing a plan for a specific catalog commit:

```bash
mcp-catalog plan catalog.yaml --branch feature/my-change --catalog-commit 0123456789abcdef0123456789abcdef01234567
mcp-catalog plan catalog.yaml --output dist/build-plan.json
```

## Build and publish images

Git-backed builds check out the exact `source.revision` recorded in the manifest. A build server can instead use a local Dockerfile and context directory; local paths are relative to the server manifest (or the catalog manifest for embedded servers), and the Dockerfile path is relative to the context. `$GIT_BASE` expands to the nearest directory containing `.git`, `$CWD` to the process working directory, and other `$NAME`/`${NAME}` variables expand from the process environment. Repository and remote URLs also expand environment variables before Pydantic URL validation. For a manifest with multiple platforms, choose one platform for a local `--load` build. To publish a multi-platform image directly, pass `--push`; without repeated `--platform` options it uses all platforms configured in the manifest. BuildKit cache options can be provided with `--cache-from` and `--cache-to`:

```bash
mcp-catalog image build example catalog.yaml --branch main --platform linux/amd64
mcp-catalog image publish example catalog.yaml --branch main
mcp-catalog image build example catalog.yaml --branch main --push \
  --cache-from type=gha,scope=example \
  --cache-to type=gha,scope=example,mode=max
```

For a local source, omit `repository` and `revision`:

```yaml
source:
  context: ${GIT_BASE}/servers/local-example
  dockerfile: Dockerfile
```

The context must exist and the Dockerfile must be a file inside it. Undefined environment variables and invalid paths/URLs fail validation. Build plans identify local sources with `source.type: local`.

Every build applies generated OCI labels (`org.opencontainers.image.*`) and the
`io.docker.server.metadata` label the Docker MCP gateway reads from self-describing images; the
labels are listed per server under `labels` in the build plan. See the
[manifest specification](manifest-spec.md#generated-image-labels) for the exact values.

`--catalog-commit` may be supplied to either command to reproduce the image tag. Git and Docker must be installed for Git sources; local sources only require Docker. Publication also requires registry authentication. Never put credentials in manifests or build args. The CLI does not currently support BuildKit secret mounts; do not provide build-time credentials to builds until this capability is implemented. See [CI and publication](ci-publication.md) for the publication workflow's upstream credential handling and GHCR setup.

## Tooling images

The repository Dockerfile also packages the catalog tooling itself: the `command` target is the
CLI and the `mcp` target is the FastMCP stdio server. Both are published under the `self`
namespace with the same branch rules as server images: `ghcr.io/jkrenzer/mcp-catalog/self/cli`
and `.../self/mcp` on `main`, and `.../self/<branch slug>/cli` on other branches. Each build
pushes an immutable `build-<commit>` tag and a moving `latest` tag and applies OCI labels
(title, description, version, source and URL from the catalog `repository`, revision):

```bash
mcp-catalog self plan catalog.yaml --branch main --catalog-commit 0123456789abcdef0123456789abcdef01234567
mcp-catalog self build cli catalog.yaml --branch main --platform linux/amd64
mcp-catalog self build mcp catalog.yaml --branch main --push \
  --cache-from type=gha,scope=mcp-catalog-self-mcp \
  --cache-to type=gha,scope=mcp-catalog-self-mcp,mode=max
```

The build context defaults to the Git repository root; pass `--context` to override it.

## Docker MCP catalog artifacts

The generated Docker MCP catalog uses version 2 metadata, sorts registry entries by server name, and excludes disabled servers. Build server image references are derived from the same commit and branch inputs as build plans. Each registry entry carries every field the Docker MCP catalog format defines for which the manifest provides a value: icon, readme, upstream, dateAdded, metadata, tools, secrets, env, command, volumes, user, longLived, disableNetwork, allowHosts, extraHosts, config, oauth, prefix and, for remote servers, the transport type and headers. Descriptions are collapsed to a single line. The `ref`, `source`, `icon`, `tools`, `prompts` and `resources` keys are always present because the Docker catalog UI expects them:

```bash
mcp-catalog docker server-entry example catalog.yaml --branch main --catalog-commit 0123456789abcdef0123456789abcdef01234567
mcp-catalog docker catalog catalog.yaml --output dist/docker-mcp-catalog.json
mcp-catalog catalog publish catalog.yaml --branch main
mcp-catalog publication inspect ghcr.io/jkrenzer/mcp-catalog/catalog:latest
```

`docker server-entry` accepts `--image` to override a generated image reference. `catalog publish` publishes the generated JSON as `/catalog.json` in an OCI image whose reference follows the branch-aware catalog naming rules; the image is labelled with the catalog title, description, repository and commit. Docker and appropriate registry permissions are required for publication and inspection.

The `docker mcp` CLI imports catalogs from local files or HTTP(S) URLs, not from OCI images. To use a published catalog, extract `/catalog.json` from the image (for example with `docker create` and `docker cp`) and run `docker mcp catalog import ./catalog.json`.

## MCP server

Install the optional FastMCP dependency and start the stdio server:

```bash
python -m pip install -e '.[mcp]'
mcp-catalog mcp serve
```

The MCP server exposes tools corresponding to the CLI's public functional commands. The shared operations live in `mcp_catalog.interfaces`; transport-specific Typer commands and FastMCP tools are grouped in `mcp_catalog.cli` and `mcp_catalog.mcp`, respectively. The hidden `validate-catalog` compatibility alias and the `mcp serve` launcher are not exposed as MCP tools.
