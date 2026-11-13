"""Capture a server's tool list by running its image and sending MCP ``tools/list``."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any

from ..logging_config import get_logger
from ..models import BuildServer, ImageServer
from .builds import build_image_for_server
from .catalog import find_server, load_catalog
from .changes import ChangeSet
from .servers import edit_server

logger = get_logger(__name__)

PROTOCOL_VERSION = '2025-06-18'
ANNOTATION_KEYS = {
    'title': 'title',
    'readOnlyHint': 'read_only_hint',
    'destructiveHint': 'destructive_hint',
    'idempotentHint': 'idempotent_hint',
    'openWorldHint': 'open_world_hint',
}


def _schema_type(schema: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Reduce a JSON Schema fragment to a catalog ``type`` and optional array ``items``."""
    for branch_key in ('anyOf', 'oneOf'):
        if branch_key in schema:
            branches = [
                branch
                for branch in schema[branch_key]
                if isinstance(branch, dict) and branch.get('type') != 'null'
            ]
            if branches:
                return _schema_type(branches[0])
    declared = schema.get('type', 'string')
    if isinstance(declared, list):
        declared = next((item for item in declared if item != 'null'), 'string')
    items = None
    if declared == 'array' and isinstance(schema.get('items'), dict):
        item_type, _ = _schema_type(schema['items'])
        items = {'type': item_type}
    return str(declared), items


def tools_from_list_result(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map MCP ``tools/list`` entries to the manifest ``tools`` shape, sorted by name."""
    mapped = []
    for tool in sorted(tools, key=lambda item: item['name']):
        entry: dict[str, Any] = {'name': tool['name'], 'description': tool.get('description', '')}
        input_schema = tool.get('inputSchema') or {}
        properties = input_schema.get('properties') or {}
        required = set(input_schema.get('required') or [])
        arguments = []
        for argument_name in sorted(properties):
            schema = properties[argument_name]
            argument_type, items = _schema_type(schema)
            argument: dict[str, Any] = {
                'name': argument_name,
                'type': argument_type,
                'desc': schema.get('description', ''),
            }
            if argument_name not in required:
                argument['optional'] = True
            if items is not None:
                argument['items'] = items
            arguments.append(argument)
        if arguments:
            entry['arguments'] = arguments
        annotations = {
            catalog_key: tool['annotations'][mcp_key]
            for mcp_key, catalog_key in ANNOTATION_KEYS.items()
            if mcp_key in (tool.get('annotations') or {})
        }
        if annotations:
            entry['annotations'] = annotations
        mapped.append(entry)
    return mapped


class _StdioClient:
    """Minimal newline-delimited JSON-RPC client for an MCP server on a subprocess."""

    def __init__(self, command: list[str]) -> None:
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._next_id = 0

    def _pump(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, message: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + '\n')
        self._process.stdin.flush()

    def notify(self, method: str) -> None:
        self._send({'jsonrpc': '2.0', 'method': method})

    def request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty as error:
                raise TimeoutError(f'No response to {method} within {timeout:g}s.') from error
            if line is None:
                raise RuntimeError(
                    'The server closed stdout before answering; it may not use stdio.'
                )
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # stray log line on stdout
            if message.get('id') != request_id:
                continue
            if 'error' in message:
                raise RuntimeError(f'{method} failed: {message["error"]}')
            return message['result']

    def close(self) -> None:
        self._process.kill()
        self._process.wait()


def capture_tools(
    image: str,
    *,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Run ``image`` over stdio and return its tools in the manifest ``tools`` shape."""
    command = ['docker', 'run', '-i', '--rm']
    for name, value in sorted((env or {}).items()):
        command += ['-e', f'{name}={value}']
    command.append(image)
    logger.info('Capturing tools from %s', image)
    client = _StdioClient(command)
    try:
        client.request(
            'initialize',
            {
                'protocolVersion': PROTOCOL_VERSION,
                'capabilities': {},
                'clientInfo': {'name': 'mcp-catalog', 'version': '0'},
            },
            timeout,
        )
        client.notify('notifications/initialized')
        tools: list[dict[str, Any]] = []
        params: dict[str, Any] = {}
        while True:
            result = client.request('tools/list', params, timeout)
            tools.extend(result.get('tools', []))
            cursor = result.get('nextCursor')
            if not cursor:
                break
            params = {'cursor': cursor}
    finally:
        client.close()
    return tools_from_list_result(tools)


def capture_server_tools(
    catalog_path: str | Path,
    name: str,
    *,
    image: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
    dry_run: bool = False,
) -> ChangeSet:
    """Capture the tools of a catalog server and store them in its manifest.

    Build servers are built locally first unless ``image`` is given. Tools go to the
    manifest's ``tools_file`` when it has one and otherwise inline into ``tools``.
    """
    catalog = load_catalog(catalog_path)
    server = find_server(catalog, name)
    if image is None:
        if isinstance(server, BuildServer):
            image = build_image_for_server(catalog, name=name)
        elif isinstance(server, ImageServer):
            image = server.image
        else:
            raise ValueError(f'Only build and image servers can be captured: {name}')
    tools = capture_tools(image, env=env, timeout=timeout)
    if not tools:
        raise ValueError(f'{image} reported no tools.')
    if server.tools_file is not None:
        target = Path(server.tools_file)
        before = target.read_text(encoding='utf-8') if target.exists() else None
        after = json.dumps(tools, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
        change = ChangeSet(
            'capture tools', target, before, after, details={'name': name, 'tools': len(tools)}
        )
        return change if dry_run else change.apply()
    change = edit_server(catalog_path, name, set_values={'tools': tools}, dry_run=dry_run)
    return ChangeSet(
        'capture tools',
        change.target,
        change.before,
        change.after,
        applied=change.applied,
        details={'name': name, 'tools': len(tools)},
    )
