# CI and publication

## Checks and pull requests

The CI workflow runs on every pull request and branch push. It validates `catalog.yaml`, checks
Ruff formatting and lint, runs mypy and pytest, and checks generated schema drift. A separate
compatibility job installs the pinned Docker MCP CLI/Gateway and runs `docker mcp --help`.

Pull request titles must follow Conventional Commits:

```text
<type>(<optional-scope>): <description>
```

Accepted types are `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`,
`style`, and `test`. The scope is optional; use lowercase, digits, `.`, `_`, `/`, or `-` when
provided. Examples:

```text
feat(cli): add server remove command
docs: describe GHCR access setup
fix!: reject invalid build context
```

The title check runs on the pull request title, not the branch name or commit messages, so
Copilot-generated branch names do not need to follow Conventional Commits. Use a squash merge and
keep the final PR title compliant; the squash commit then has the same Conventional Commit subject.
Do not use a merge strategy that produces a non-compliant final commit title.

## Publishing

The publication workflow runs after validation on branch pushes and can be started deliberately
with **Actions → Publish catalog and server images → Run workflow**. It does not run on
`pull_request` and does not use `pull_request_target`. No workflow automatically resolves or updates
upstream revisions; revision updates remain an explicit catalog-maintenance operation.

The workflow builds server images with Docker Buildx for the platforms declared in each manifest,
publishes the tooling images (`self/cli` and `self/mcp`, see the
[CLI reference](cli.md#tooling-images)) and publishes the generated Docker MCP catalog. Branch `main` uses the main namespace; every other
branch uses its isolated, normalized branch namespace. The workflow token is used for GHCR login.
Only the publishing job has `packages: write`; validation jobs have read-only repository access.
Buildx cache is stored using GitHub Actions cache scopes.

The workflow publishes OCI images and catalog data only. GHCR and GitHub Actions do not provide a
hosted MCP endpoint.

### GHCR package setup

The image names are derived from the repository owner and catalog naming rules. GitHub associates
a GHCR package with a repository through the `org.opencontainers.image.source` label. The CLI sets
that label automatically: locally built server images and the generated catalog image use the
catalog manifest's `repository` URL, so set `repository` in `catalog.yaml` to this repository.
Git-sourced server images are labelled with their upstream repository instead, because that is
where their Dockerfile and sources live; connect those GHCR packages to this repository from the
package's **Package settings** after their first publication if GitHub has not associated them
automatically.

Set package visibility explicitly in GHCR. A public package can be pulled anonymously; private
packages require authentication. Linking a package before publication can enable permission
inheritance from the repository. If linking an existing package later, review its settings and
explicitly enable inheritance if desired; linking alone does not necessarily change existing
permissions. For private packages, grant the consuming repository's Actions access under the
package's **Manage Actions access** settings. Keep publication permissions limited to this
repository's publishing workflow.

### Private upstream repositories

`GITHUB_TOKEN` is scoped to the workflow repository and does not automatically grant access to
private upstream repositories. For those sources, add an `UPSTREAM_REPOSITORY_TOKEN` Actions
secret with only the required read access to the upstream repository. The publish job uses it for
Git transport; it is not placed in manifests, build arguments, or image layers. If the catalog
references multiple private repositories that need different credentials, separate credential
configuration is not currently supported.

The CLI does not currently expose BuildKit secret mounts. Do not pass credentials needed during a
Docker build through manifest build arguments; support for securely providing build-time secrets is
missing and must be implemented before such builds can be published.

## Docker MCP CLI in CI

GitHub-hosted runners do not come with the Docker MCP CLI plugin installed. CI checks out Docker
MCP CLI/Gateway `v0.44.3` and builds it with Go `1.26.10` using the upstream `make docker-mcp`
target, then invokes it through `docker mcp`. The upstream module has a `replace` directive, so
`go install ...@v0.44.3` is not supported; building from its checkout lets Go apply the module's
own replacements. Keep both version pins explicit when upgrading the compatibility check.
