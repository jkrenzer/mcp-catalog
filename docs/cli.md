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

## Clone a repository

`clone` uses the installed Git executable. It accepts pip-style Git URLs with an optional
revision and project subdirectory, and forwards options after `--` to `git clone`:

```bash
mcp-catalog clone git+https://github.com/example/project.git@v1.2.0#egg=project
mcp-catalog clone 'git+https://github.com/example/project.git@main#subdirectory=packages/server'
mcp-catalog clone https://github.com/example/project.git -- --depth 1 --branch main
```

Git prints its normal clone/check-out messages. The command reports the cloned directory or the
selected repository subdirectory; it does not change the calling shell's working directory.

## Manage servers

Add servers from a manifest file, from individual fields, or from both. `--set` takes
`path=value` pairs (MCP: the `fields` object); the value is parsed as YAML, so numbers, booleans
and `[a, b]` lists work. `schema_version` and `schema_kind` default to the current schema.

```bash
mcp-catalog server list catalog.yaml
mcp-catalog server show example catalog.yaml
mcp-catalog server add catalog.yaml --manifest examples/build-server.yaml
mcp-catalog server add catalog.yaml --set name=demo --set kind=image --set title=Demo \
  --set description='A demo.' --set image=ghcr.io/example/s@sha256:<digest>
mcp-catalog server update example catalog.yaml --manifest /tmp/example-updated.yaml
mcp-catalog server remove example catalog.yaml
```

`server edit` changes individual fields and leaves everything else, including comments, as it was:

```bash
mcp-catalog server edit example catalog.yaml \
  --set metadata.license=MIT \
  --set 'metadata.tags=[web, crawler]' \
  --set 'secrets[+]={name: example.key, env: EXAMPLE_KEY}' \
  --set 'runtime.env[name=REGION].value=eu' \
  --unset 'tools[0]'
```

| Path | Meaning |
|------|---------|
| `metadata.license` | Mapping keys separated by dots; missing mappings are created. |
| `tools[0].description`, `tools[-1]` | List element by index; negative indices count from the end. |
| `secrets[+]` | Append to a list (created when missing). |
| `runtime.env[name=REGION].value` | The list item whose mapping has `name == REGION`. |

Removals run before assignments. Every result is validated before anything is written; a
failing edit leaves the manifest untouched.

All commands that write (`server add|update|edit|remove`, `upstream update`, `tools capture`)
accept `--dry-run` (MCP: `dry_run: true`). It runs the same validation, writes nothing and prints
the unified diff that would be applied.

These commands edit either the embedded catalog `servers` list or the individual YAML files in `servers_dir`, according to the catalog layout. The update command keeps the existing server name and replaces the manifest wholesale; prefer `server edit` for small changes.

### Scaffold a manifest from a repository

```bash
mcp-catalog server scaffold-from-repo https://github.com/owner/repo --output /tmp/draft.yaml
```

The repository is shallow-cloned into a temporary directory and read as untrusted data; nothing
from it is executed. The draft manifest goes to stdout or `--output`; a report goes to stderr (MCP:
a dict with `manifest`, `found`, `missing` and `notes`):

- **Found**: each field with the file it came from. Sources are the Dockerfile, `pyproject.toml`,
  `package.json`, `Cargo.toml`, `LICENSE`, the README (heading, first paragraph and environment
  variable tables) and `.env.example`-style files. Variables that look like credentials become
  `secrets`; the rest become `config` properties wired through `runtime.env` with `|or:` defaults.
- **Missing**: each field that could not be determined, whether it is required, what value is
  expected and how to obtain it. The icon, category, tools and secret requirements always need a
  human or agent decision.
- **Notes**: items to review, such as a Dockerfile in a subdirectory or an exposed HTTP port.

An agent can pass the `manifest` straight to `server_add` as `fields` after completing the gaps.

### Capture tools from an image

```bash
mcp-catalog tools capture example catalog.yaml --dry-run
mcp-catalog tools capture example catalog.yaml --image ghcr.io/owner/image:tag --env API_KEY=x
```

This builds the server image locally (or uses `--image`), runs it with `docker run -i`, performs
the MCP `initialize` and `tools/list` exchange over stdio, and maps the result to the manifest
`tools` shape (sorted by name and argument name). The tools are written to the manifest's
`tools_file` when it has one and inline into `tools` otherwise. Docker must be available; the
devcontainer provides it through the Docker-outside-of-Docker feature. Capturing executes the
server image, so only capture images you trust.

### Test an MCP server image

```bash
mcp-catalog test server example catalog.yaml
mcp-catalog test server example catalog.yaml --image ghcr.io/owner/image:tag --env API_KEY=x
```

This runs the configured image server, or builds a build server locally unless `--image` is
provided. It performs the MCP `initialize` and `tools/list` exchange over stdio, including
pagination, and reports success only if the server responds successfully. `--env` can be repeated
to pass `NAME=value` pairs to the container, and `--timeout` sets the wait time for each MCP
request. Unlike `tools capture`, this command does not modify the catalog.

Image builds, tests, captures, publication inspection, and tooling-image builds require the Docker
CLI and a reachable Docker engine. The container images include the CLI and Buildx plugin, not the
engine; provide a host socket or configure `DOCKER_HOST`. The development container checks engine
connectivity at startup and warns on stderr if it is unavailable. Docker-backed commands also check
before running and report an actionable error instead of proceeding with an unusable Docker setup.

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

`--cache-from` may be repeated to import from multiple sources. Push builds enable inline cache
metadata in the image; tooling image builds also use their branch-scoped `latest` tag as a cache
source.

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
mcp-catalog docker catalog catalog.yaml --artifact --output dist/catalog-artifact.json
```

`docker server-entry` accepts `--image` to override a generated image reference. `docker catalog` writes the legacy `registry` document accepted by `docker mcp catalog import`; with `--artifact` it writes the payload of the OCI catalog artifact described below.

`catalog publish` pushes the catalog to the branch-aware catalog reference as an OCI artifact that `docker mcp catalog pull` consumes. It requires [oras](https://oras.land) on `PATH` and registry authentication (`oras login`). The artifact is an OCI image manifest with `artifactType` `application/vnd.docker.mcp.catalog.v1+json`, an empty config and one `application/json` layer holding `{title, servers}`. Every enabled server is an `image` or `remote` entry whose `snapshot.server` carries the full Docker MCP server entry. The manifest is annotated with the catalog title, description, repository and commit, and the pushed reference is verified to carry the catalog artifact type. Use it with Docker Desktop 4.62 or later:

```bash
docker mcp catalog pull ghcr.io/jkrenzer/mcp-catalog/catalog:latest
docker mcp gateway run --catalog ghcr.io/jkrenzer/mcp-catalog/catalog:latest
```

The package must be public for anonymous pulls. The earlier `FROM scratch` image containing `/catalog.json` is no longer published; reuse of the `catalog:latest` tag replaces it.

## MCP server

Install the optional FastMCP dependency and start the stdio server:

```bash
python -m pip install -e '.[mcp]'
mcp-catalog mcp serve
```

The MCP server exposes tools corresponding to the CLI's public functional commands. The shared operations live in `mcp_catalog.interfaces`; transport-specific Typer commands and FastMCP tools are grouped in `mcp_catalog.cli` and `mcp_catalog.mcp`, respectively. The hidden `validate-catalog` compatibility alias and the `mcp serve` launcher are not exposed as MCP tools.
