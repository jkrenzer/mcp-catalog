from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from mcp_catalog.interfaces import tools_capture
from mcp_catalog.interfaces.tools_capture import (
    capture_tools,
    test_server_image as run_server_mcp_test,
    tools_from_list_result,
)

FAKE_SERVER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        message = json.loads(line)
        if 'id' not in message:
            continue
        print('log line that is not json', flush=True)
        if message['method'] == 'initialize':
            result = {'protocolVersion': '2025-06-18', 'capabilities': {}}
        elif message['params'].get('cursor') == 'next':
            result = {'tools': [{'name': 'a_tool', 'description': 'first'}]}
        else:
            result = {
                'tools': [
                    {
                        'name': 'z_tool',
                        'description': 'last',
                        'annotations': {'readOnlyHint': True},
                        'inputSchema': {
                            'properties': {
                                'url': {'type': 'string', 'description': 'U'},
                                'tags': {
                                    'anyOf': [
                                        {'type': 'array', 'items': {'type': 'string'}},
                                        {'type': 'null'},
                                    ]
                                },
                            },
                            'required': ['url'],
                        },
                    }
                ],
                'nextCursor': 'next',
            }
        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
    """
)


def test_tools_from_list_result_maps_schema_and_sorts():
    tools = tools_from_list_result(
        [
            {
                'name': 'b',
                'description': 'B',
                'inputSchema': {
                    'properties': {
                        'x': {'type': ['integer', 'null'], 'description': 'X'},
                        'a': {'type': 'string'},
                    },
                    'required': ['a'],
                },
            },
            {'name': 'a'},
        ]
    )
    assert [tool['name'] for tool in tools] == ['a', 'b']
    assert tools[1]['arguments'] == [
        {'name': 'a', 'type': 'string', 'desc': ''},
        {'name': 'x', 'type': 'integer', 'desc': 'X', 'optional': True},
    ]


def test_capture_tools_speaks_mcp_over_stdio_with_pagination(tmp_path, monkeypatch):
    script = tmp_path / 'fake_server.py'
    script.write_text(FAKE_SERVER, encoding='utf-8')
    real_popen = subprocess.Popen
    seen = {}

    def fake_popen(command, **kwargs):
        seen['command'] = command
        return real_popen([sys.executable, str(script)], **kwargs)

    monkeypatch.setattr(tools_capture, 'require_docker_engine', lambda: None)
    monkeypatch.setattr(tools_capture.subprocess, 'Popen', fake_popen)

    tools = capture_tools('example/image:1', env={'KEY': 'v'}, timeout=10)

    assert seen['command'] == ['docker', 'run', '-i', '--rm', '-e', 'KEY=v', 'example/image:1']
    assert [tool['name'] for tool in tools] == ['a_tool', 'z_tool']
    z_tool = tools[1]
    assert z_tool['annotations'] == {'read_only_hint': True}
    assert {
        'name': 'tags',
        'type': 'array',
        'desc': '',
        'optional': True,
        'items': {'type': 'string'},
    } in z_tool['arguments']


def test_test_server_image_uses_resolved_image_and_returns_tool_count(monkeypatch, tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    catalog_path.write_text('servers: []\n', encoding='utf-8')
    monkeypatch.setattr(
        tools_capture,
        '_resolve_server_image',
        lambda path, name, image: (None, 'example/image:1'),
    )
    seen = {}

    def fake_capture(image, *, env, timeout):
        seen.update(image=image, env=env, timeout=timeout)
        return [{'name': 'tool_a'}, {'name': 'tool_b'}]

    monkeypatch.setattr(tools_capture, 'capture_tools', fake_capture)

    count = run_server_mcp_test(
        catalog_path, 'example', env={'KEY': 'value'}, timeout=12.0
    )

    assert count == 2
    assert seen == {'image': 'example/image:1', 'env': {'KEY': 'value'}, 'timeout': 12.0}


def test_capture_tools_reports_closed_stdout(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    monkeypatch.setattr(tools_capture, 'require_docker_engine', lambda: None)
    monkeypatch.setattr(
        tools_capture.subprocess,
        'Popen',
        lambda command, **kwargs: real_popen([sys.executable, '-c', 'pass'], **kwargs),
    )
    with pytest.raises((RuntimeError, BrokenPipeError)):
        capture_tools('x', timeout=5)


def test_json_dump_is_deterministic():
    tools = tools_from_list_result([{'name': 'a', 'description': 'd'}])
    assert json.dumps(tools, sort_keys=True) == json.dumps(tools, sort_keys=True)


def _docker_can_run_python_image() -> bool:
    try:
        return (
            subprocess.run(
                ['docker', 'image', 'inspect', 'python:3.13-slim-bookworm'],
                capture_output=True,
                timeout=30,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(
    not _docker_can_run_python_image(),
    reason='needs a Docker daemon with python:3.13-slim-bookworm available locally',
)
def test_capture_server_tools_with_real_docker_writes_inline_tools(tmp_path):
    """Runs a throwaway image built from the fake server above, then stores its tools."""
    from mcp_catalog.interfaces.servers import add_server
    from mcp_catalog.interfaces.tools_capture import capture_server_tools
    from mcp_catalog.io.yaml import load_yaml_file

    context = tmp_path / 'fake-image'
    context.mkdir()
    (context / 'server.py').write_text(FAKE_SERVER, encoding='utf-8')
    (context / 'Dockerfile').write_text(
        'FROM python:3.13-slim-bookworm\nCOPY server.py /server.py\nCMD ["python", "/server.py"]\n',
        encoding='utf-8',
    )
    tag = 'mcp-catalog-test/fake-mcp:capture'
    subprocess.run(['docker', 'build', '--quiet', '-t', tag, str(context)], check=True)
    try:
        catalog = tmp_path / 'catalog.yaml'
        (tmp_path / 'servers').mkdir()
        catalog.write_text(
            'schema_version: 1\n'
            'schema_kind: https://mcp-catalog.schema.krenzer.space/catalog.schema.json\n'
            'name: c\ntitle: C\ndescription: d\nservers_dir: servers\n',
            encoding='utf-8',
        )
        add_server(
            catalog,
            fields={
                'name': 'fake',
                'kind': 'build',
                'title': 'Fake',
                'description': 'Fake server.',
                'build.platforms': ['linux/amd64'],
                'source.context': str(context),
                'source.dockerfile': 'Dockerfile',
            },
        )
        dry = capture_server_tools(catalog, 'fake', image=tag, timeout=60, dry_run=True)
        assert not dry.applied and 'z_tool' in dry.diff
        applied = capture_server_tools(catalog, 'fake', image=tag, timeout=60)
        assert applied.applied and applied.details['tools'] == 2
        stored = load_yaml_file(tmp_path / 'servers' / 'fake.yaml')
        assert [tool['name'] for tool in stored['tools']] == ['a_tool', 'z_tool']
    finally:
        subprocess.run(['docker', 'rmi', '-f', tag], capture_output=True)
