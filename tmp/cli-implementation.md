# CLI implementation handoff

## Goal

Build a Typer CLI for validating and maintaining the declarative MCP catalog, producing deterministic Docker MCP artifacts, and executing explicit Docker publication steps.

## Progress

- [x] Inspected the existing Pydantic models, YAML I/O, catalog generator, image-reference helpers, examples, workflows, and tests.
- [x] Implemented the Typer command groups and supporting manifest/catalog operations.
- [x] Documented command examples and artifact/publication behavior.
- [x] Added targeted CLI, determinism, Docker-shape, schema-drift, and upstream update tests.
- [x] Added package logging with startup buffering, stderr output, repeatable level-aware log files, and an all-level stderr fallback if setup fails.
- [x] Ran the full test suite and checked committed schema drift.
- [x] Split shared operations into `interfaces/`, Typer commands into `cli/`, and FastMCP tools into `mcp/`.
- [x] Replaced click-to-mcp with FastMCP tools mirroring the CLI's public functional commands.
- [x] Verified the stdio protocol with FastMCP's client: it listed 18 tools and successfully called `branch_slug`.
- [x] Added local Docker context/Dockerfile sources for build servers, with manifest-relative path resolution and Pydantic directory/file validation.
- [x] Added `$GIT_BASE`, `$CWD`, shell-environment expansion for local paths, and environment expansion for Git/remote URLs before Pydantic URL validation.
- [x] Added multi-platform Buildx image publication and cache options to the shared build interface, CLI, and MCP tool.
- [x] Added CI checks for catalog validation, Ruff formatting/lint, mypy, pytest, schema drift, and conventional PR titles.
- [x] Added branch-push and manual GHCR publication with read-only validation permissions, a separate `packages: write` publisher, GITHUB_TOKEN login, Buildx caching, and manifest-configured platforms.
- [x] Added a pinned Docker MCP CLI/Gateway compatibility job and documented package association/access, PR title/squash merge rules, branch namespaces, private upstream credentials, and the absence of a hosted MCP endpoint.
- [x] Kept CI authentication for private Git upstreams out of build args and Docker build subprocess environments.
- [x] Documented that BuildKit secret mounts are not yet exposed by the CLI and must be implemented before builds needing build-time credentials can be published.
- [x] Validated workflow YAML with ruamel.yaml; asserted publication triggers, permissions, token login, Buildx usage, and explicit platforms.
- [x] Ran all 31 tests, Ruff format/lint, mypy, catalog validation, and schema drift checks successfully.

## Implemented command surface

- `validate` for catalog and server manifests; `schema generate/check`.
- `server list/show/add/update/remove`.
- `upstream resolve/update` (resolve only reads upstream; update explicitly rewrites the manifest revision).
- `plan` for stable build-plan JSON.
- `image build/publish`, with multi-platform Buildx push, cache configuration, and local or Git sources.
- `docker server-entry/catalog`.
- `catalog publish` and `publication inspect`.

## Important context

- Existing server manifests are Pydantic v2 discriminated models in `src/mcp_catalog/models/server.py`; catalog manifests may either embed servers or point to one YAML file per server under `servers_dir`.
- YAML must continue to use the safe round-trip helpers in `src/mcp_catalog/io/yaml.py`.
- Branch-aware image/catalog references are already centralized in `src/mcp_catalog/branching.py`.
- The Typer CLI entry point is `mcp_catalog.cli:main`; shared operations live in `interfaces/`, with separate Typer and FastMCP command modules.
- Docker and Git operations should be explicit subprocess calls with surfaced errors; tests should exercise generated artifacts and command behavior without requiring a daemon or network.
- The user-provided `build-server.yaml` attachment is a read-only snapshot and must not be edited.
- CLI output data remains on stdout; logs and human-readable progress/status messages go to stderr.
- CLI logging defaults to INFO. Global `--log-level` and repeatable `--log-file` options are handled by the root Typer callback; file specifications may be a path or `LEVEL:path`.
- `src/mcp_catalog/logging_config.py` owns package logger buffering and handler setup. Package code should obtain namespaced loggers through `get_logger`.
- `mcp-catalog mcp serve` depends on the optional `.[mcp]` extra; its `FastMCP.run` call explicitly selects stdio and disables the startup banner so stdout remains protocol-only.
- `mcp_catalog.workflows` remains a compatibility re-export facade; new workflows belong under `mcp_catalog.interfaces`.
- A build source is either the original Git-backed `SourceModel` (repository and pinned revision) or a `LocalSourceModel` (existing context directory and Dockerfile inside it). Local source upstream-revision commands are rejected.
- Local context paths in embedded catalog entries resolve from the catalog file; in server-file catalogs they resolve from the individual server manifest. Dockerfiles are relative to the context unless absolute.
- CI tools are in the PEP 735 `dev` dependency group; workflows upgrade pip then install with `pip install --group dev -e '.[mcp]'`. Pip's `--group` support was confirmed in the configured environment.
- `.github/workflows/ci.yml` and `publish.yml` pin actions to immutable commit SHAs and include version comments. Publishing is branch-push/manual only; it is not triggered by pull requests and never updates upstream revisions automatically.
- Branch `main` publishes in the main image/catalog namespace. Other branches use the deterministic hashed branch namespace from `branch_slug`. Server image tags include the catalog commit; catalog tags are `latest` within the branch namespace.
- `UPSTREAM_REPOSITORY_TOKEN` is optional and only needed to clone private upstream sources; GITHUB_TOKEN does not grant cross-repository access by default. Docker build subprocesses strip `GIT_CONFIG_*` from their environment.
- GHCR source labels can associate controllable server images with the repository; packages without that label (including the generated catalog image) must be linked manually in package settings. Visibility and Actions access are configured per package.
- Validation results: `pytest -q` passed 31 tests; `ruff format --check .`, `ruff check .`, `mypy src/mcp_catalog`, `mcp-catalog validate catalog.yaml`, and `mcp-catalog schema check schemas` passed. `actionlint` was unavailable; workflow YAML and key policy assertions were checked with ruamel.yaml.
- `git diff --check` reports trailing whitespace across the tracked `.gitignore` changes (CRLF-style lines); avoid broad line-ending normalization unless requested. The working tree includes earlier untracked project files; preserve them.
