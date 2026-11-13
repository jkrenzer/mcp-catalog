from __future__ import annotations

import pytest
from typer.testing import CliRunner

from mcp_catalog.cli import app
from mcp_catalog.interfaces.changes import apply_edits, parse_assignments, parse_path
from mcp_catalog.interfaces.servers import add_server, edit_server, remove_server
from mcp_catalog.io.yaml import load_yaml_file

runner = CliRunner()
SCHEMA = 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json'


@pytest.fixture
def catalog(tmp_path):
    (tmp_path / 'servers').mkdir()
    path = tmp_path / 'catalog.yaml'
    path.write_text(
        f'schema_version: 1\nschema_kind: {SCHEMA}\nname: c\ntitle: C\n'
        'description: Test catalog.\nservers_dir: servers\n',
        encoding='utf-8',
    )
    return path


IMAGE = 'ghcr.io/example/s@sha256:' + '0' * 64
FIELDS = {
    'name': 'demo',
    'kind': 'image',
    'title': 'Demo',
    'description': 'A demo server.',
    'image': IMAGE,
}


def test_parse_path_tokens():
    assert parse_path('a.b[0].c[+]') == ['a', 'b', 0, 'c', '+']
    assert parse_path('env[name=X].value') == ['env', ('name', 'X'), 'value']
    with pytest.raises(ValueError):
        parse_path('')


def test_set_creates_intermediates_and_appends_and_selects():
    document: dict = {}
    apply_edits(
        document,
        {
            'metadata.tags': ['a'],
            'runtime.env[+]': {'name': 'A', 'value': '1'},
            'runtime.env[name=A].value': '2',
            'tools[+].name': 't',
        },
    )
    assert document['runtime']['env'] == [{'name': 'A', 'value': '2'}]
    assert document['tools'] == [{'name': 't'}]
    apply_edits(document, unset_paths=['metadata.tags', 'runtime.env[name=A]'])
    assert document['metadata'] == {} and document['runtime']['env'] == []
    with pytest.raises(ValueError):
        apply_edits(document, unset_paths=['nothing.here'])


def test_parse_assignments_reads_yaml_values():
    assert parse_assignments(['a=1', 'b=[x, y]', 'c=hello world', 'd=true']) == {
        'a': 1,
        'b': ['x', 'y'],
        'c': 'hello world',
        'd': True,
    }
    with pytest.raises(ValueError):
        parse_assignments(['broken'])


def test_add_from_fields_only_writes_minimal_manifest(catalog):
    change = add_server(catalog, fields=FIELDS)
    assert change.applied
    document = load_yaml_file(catalog.parent / 'servers' / 'demo.yaml')
    assert set(document) == {
        'schema_version',
        'schema_kind',
        'name',
        'kind',
        'title',
        'description',
        'image',
    }


def test_add_dry_run_writes_nothing_and_shows_diff(catalog):
    change = add_server(catalog, fields=FIELDS, dry_run=True)
    assert not change.applied and 'name: demo' in change.diff
    assert not (catalog.parent / 'servers' / 'demo.yaml').exists()


def test_add_validates_before_writing(catalog):
    with pytest.raises(ValueError):
        add_server(catalog, fields={**FIELDS, 'image': 'no-digest'})
    assert not (catalog.parent / 'servers' / 'demo.yaml').exists()


def test_add_duplicate_is_rejected(catalog):
    add_server(catalog, fields=FIELDS)
    with pytest.raises(ValueError, match='already exists'):
        add_server(catalog, fields=FIELDS)


def test_edit_changes_only_the_requested_fields(catalog):
    add_server(catalog, fields=FIELDS)
    target = catalog.parent / 'servers' / 'demo.yaml'
    target.write_text('# keep me\n' + target.read_text(encoding='utf-8'), encoding='utf-8')
    edit_server(catalog, 'demo', set_values={'metadata.license': 'MIT'})
    text = target.read_text(encoding='utf-8')
    assert text.startswith('# keep me') and 'license: MIT' in text
    assert 'runtime' not in text and 'config' not in text


def test_edit_dry_run_and_invalid_edit_leave_file_untouched(catalog):
    add_server(catalog, fields=FIELDS)
    target = catalog.parent / 'servers' / 'demo.yaml'
    original = target.read_text(encoding='utf-8')
    edit_server(catalog, 'demo', set_values={'title': 'New'}, dry_run=True)
    with pytest.raises(ValueError):
        edit_server(catalog, 'demo', set_values={'name': 'renamed'})
    with pytest.raises(ValueError):
        edit_server(catalog, 'demo', set_values={'image': 'bad'})
    assert target.read_text(encoding='utf-8') == original


def test_remove_dry_run_then_apply(catalog):
    add_server(catalog, fields=FIELDS)
    target = catalog.parent / 'servers' / 'demo.yaml'
    remove_server(catalog, 'demo', dry_run=True)
    assert target.exists()
    remove_server(catalog, 'demo')
    assert not target.exists()


def test_inline_catalog_layout_edits_in_place(tmp_path):
    path = tmp_path / 'catalog.yaml'
    path.write_text(
        f'schema_version: 1\nschema_kind: {SCHEMA}\nname: c\ntitle: C\n'
        'description: d\nservers: []\n',
        encoding='utf-8',
    )
    add_server(path, fields=FIELDS)
    edit_server(path, 'demo', set_values={'title': 'Renamed title'})
    assert load_yaml_file(path)['servers'][0]['title'] == 'Renamed title'


def test_cli_set_edit_and_dry_run(catalog):
    base = ['server', 'add', str(catalog)]
    fields = [arg for key, value in FIELDS.items() for arg in ('--set', f'{key}={value}')]
    dry = runner.invoke(app, [*base, *fields, '--dry-run'])
    assert dry.exit_code == 0 and 'Dry run' in dry.stdout
    assert runner.invoke(app, [*base, *fields]).exit_code == 0
    edit = runner.invoke(
        app, ['server', 'edit', 'demo', str(catalog), '--set', 'metadata.tags=[a, b]']
    )
    assert edit.exit_code == 0
    assert load_yaml_file(catalog.parent / 'servers' / 'demo.yaml')['metadata']['tags'] == [
        'a',
        'b',
    ]
