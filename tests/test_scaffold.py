from __future__ import annotations

from mcp_catalog.interfaces.catalog import validate_server_document
from mcp_catalog.interfaces.scaffold import scaffold_from_checkout, scaffold_report

REPO = 'https://github.com/acme/web-tool.git'
SHA = 'a' * 40


def _write(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def test_scaffold_reads_project_files_and_env_examples(tmp_path):
    _write(
        tmp_path,
        {
            'Dockerfile': 'FROM python:3.13-slim\nCMD ["python", "-m", "tool"]\n',
            'pyproject.toml': (
                '[project]\nname = "tool"\ndescription = "Scrapes the web."\n'
                'license = {text = "MIT"}\nkeywords = ["web", "crawler"]\n'
            ),
            'README.md': (
                '# Web Tool\n\nIgnored intro.\n\n| Variable | Default | Purpose |\n|---|---|---|\n'
                '| `REQUEST_TIMEOUT` | `30` | Seconds before timeout |\n'
                '| `POLITE_MODE` | `true` | Retry after 429 |\n'
                '| `USER_AGENT` | `Mozilla/5.0 (compatible; …)` | HTTP User-Agent |\n'
            ),
            '.env.example': '# Your API key\nTOOL_API_KEY=\nTOOL_API_URL=https://api.example.com\n',
        },
    )
    result = scaffold_from_checkout(tmp_path, REPO, SHA)
    manifest = result['manifest']

    assert manifest['name'] == 'acme-web-tool'
    assert manifest['title'] == 'Web Tool'
    assert manifest['description'] == 'Scrapes the web.'
    assert manifest['metadata'] == {'owner': 'acme', 'license': 'MIT', 'tags': ['web', 'crawler']}
    assert manifest['source'] == {
        'repository': REPO,
        'revision': SHA,
        'context': '.',
        'dockerfile': 'Dockerfile',
    }
    assert [secret['env'] for secret in manifest['secrets']] == ['TOOL_API_KEY']
    assert manifest['secrets'][0]['description'] == 'Your API key'
    properties = manifest['config'][0]['properties']
    assert properties['request_timeout']['type'] == 'integer'
    assert properties['request_timeout']['default'] == 30
    assert properties['polite_mode']['default'] is True
    assert 'default' not in properties['user_agent']  # truncated README default is dropped
    assert properties['tool_api_url']['default'] == 'https://api.example.com'
    env = {entry['name']: entry['value'] for entry in manifest['runtime']['env']}
    assert env['REQUEST_TIMEOUT'] == '{{acme-web-tool.request_timeout|or:30}}'
    assert 'description' in result['found']

    validate_server_document(manifest, base_dir=tmp_path)


def test_scaffold_reports_gaps_with_requiredness(tmp_path):
    _write(tmp_path, {'README.md': '# Bare\n'})
    result = scaffold_from_checkout(tmp_path, REPO, SHA)
    missing = {gap['field']: gap for gap in result['missing']}

    assert missing['description']['required'] is True
    assert missing['source.dockerfile']['required'] is True
    assert missing['tools']['required'] is False
    assert 'tools capture' in missing['tools']['hint']
    assert missing['icon']['expected']
    report = scaffold_report(result)
    assert '[REQUIRED] description' in report
    assert report.index('[REQUIRED]') < report.index('[optional]')


def test_scaffold_falls_back_to_readme_paragraph_and_nested_dockerfile(tmp_path):
    _write(
        tmp_path,
        {
            'README.md': '# T\n\n[![badge](x)](y)\n\nA [useful](http://x) tool.\n',
            'docker/Dockerfile': 'FROM scratch\nEXPOSE 8080\n',
            'LICENSE': 'MIT License\n\nCopyright',
        },
    )
    result = scaffold_from_checkout(tmp_path, REPO, SHA, name='custom')
    manifest = result['manifest']
    assert manifest['name'] == 'custom'
    assert manifest['description'] == 'A useful tool.'
    assert manifest['source']['context'] == 'docker'
    assert manifest['metadata']['license'] == 'MIT'
    assert any('exposes a port' in note for note in result['notes'])
    assert any('review wording' in source for source in result['found'].values())
