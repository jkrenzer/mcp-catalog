# Contributing

1. Create a virtual environment.
2. Install the project and development tools with `python -m pip install --group dev -e '.[mcp]'`.
3. Before opening a PR, run:

   ```bash
   mcp-catalog validate catalog.yaml
   ruff format --check .
   ruff check .
   mypy src/mcp_catalog
   pytest
   mcp-catalog schema check schemas
   ```

4. Keep changes compatible with the defined manifest schema and update generated schemas when
   needed.
5. Use a Conventional Commit pull request title. Branch names, including Copilot branch names, do
   not need a particular format. Squash merge so the PR title is the final commit subject. See
   [CI and publication](docs/ci-publication.md) for the title format and GHCR publishing details.
